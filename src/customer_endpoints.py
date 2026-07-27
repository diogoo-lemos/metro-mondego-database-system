import flask
import psycopg2
from flask_jwt_extended import get_jwt_identity
from global_functions import (
    db_connection, logger, StatusCodes,
    check_required_fields, payload_contains_dangerous_chars,
    VALID_PRODUCT_TYPES
)

# ---------------------------------------------------------------------------
# 8. List lines and upcoming departures
#    GET /dbproj/lines_next
# ---------------------------------------------------------------------------

def list_lines_next():
    """
    Return all lines with their next upcoming departure (from now),
    including available capacity and estimated delay.
    Only returns departures from lines that are currently open.
    """
    conn = db_connection()
    cur  = conn.cursor()
    logger.debug('GET /dbproj/lines_next')

    try:
        cur.execute("""
            SELECT
                l.line_id,
                l.name                                      AS line_name,
                s_origin.name                               AS origin_terminal,
                s_dest.name                                 AS destination_terminal,
                t.departure_time,
                0                                           AS estimated_delay_min,
                (t.capacity - t.booked_seats)               AS available_capacity
            FROM trip t
            JOIN line_lineoperation l
                ON t.line_lineoperation_line_id = l.line_id
            JOIN linestation ls_origin
                ON ls_origin.line_lineoperation_line_id = l.line_id
                AND ls_origin.position = (
                    SELECT MIN(position)
                    FROM linestation
                    WHERE line_lineoperation_line_id = l.line_id
                )
            JOIN station s_origin
                ON s_origin.station_id = ls_origin.station_station_id
            JOIN linestation ls_dest
                ON ls_dest.line_lineoperation_line_id = l.line_id
                AND ls_dest.position = (
                    SELECT MAX(position)
                    FROM linestation
                    WHERE line_lineoperation_line_id = l.line_id
                )
            JOIN station s_dest
                ON s_dest.station_id = ls_dest.station_station_id
            WHERE l.lineoperation_is_open = TRUE
              AND t.departure_time = (
                    SELECT MIN(t2.departure_time)
                    FROM trip t2
                    WHERE t2.line_lineoperation_line_id = l.line_id
                      AND t2.direction = t.direction
                      AND t2.departure_time > NOW()
              )
            ORDER BY l.line_id, t.direction
        """)

        rows = cur.fetchall()
        results = []
        for row in rows:
            results.append({
                'line_id':              row[0],
                'line_name':            row[1],
                'origin_terminal':      row[2],
                'destination_terminal': row[3],
                'departure_time':       str(row[4]),
                'estimated_delay_min':  row[5],
                'available_capacity':   row[6]
            })

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': results
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'GET /dbproj/lines_next - error: {error}')
        return flask.jsonify({
            'status': StatusCodes['internal_error'],
            'errors': str(error),
            'results': None
        })
    finally:
        if cur:  cur.close()
        if conn: conn.close()


# ---------------------------------------------------------------------------
# 9. Add wallet funds
#    POST /dbproj/wallet/topup
# ---------------------------------------------------------------------------

def wallet_topup():
    """
    Add funds to the authenticated customer's wallet.
    Inserts a record in wallettransaction and updates wallet_balance.
    Both operations are atomic — rollback if either fails.
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, ['amount', 'payment_method'])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    amount = float(payload['amount'])
    if amount <= 0:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Amount must be greater than 0',
            'results': None
        })

    customer_user_id = int(get_jwt_identity())

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'POST /dbproj/wallet/topup - user_id: {customer_user_id}, payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # Lock the customer row to avoid concurrent top-up race conditions
        cur.execute("""
            SELECT wallet_balance FROM customer
            WHERE users_user_id = %s
            FOR UPDATE
        """, (customer_user_id,))

        row = cur.fetchone()
        if row is None:
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': 'Customer not found',
                'results': None
            })

        # Insert wallet transaction record
        cur.execute("""
            INSERT INTO wallettransaction (amount, payment_method, created_at, customer_users_user_id)
            VALUES (%s, %s, NOW(), %s)
        """, (amount, payload['payment_method'], customer_user_id))

        # Update wallet balance
        cur.execute("""
            UPDATE customer
            SET wallet_balance = wallet_balance + %s
            WHERE users_user_id = %s
            RETURNING wallet_balance
        """, (amount, customer_user_id))

        new_balance = cur.fetchone()[0]

        cur.execute('COMMIT;')
        logger.debug(f'Wallet topped up for user {customer_user_id}: new balance = {new_balance}')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': {'new_balance': float(new_balance)}
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /dbproj/wallet/topup - error: {error}')
        if conn: conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['internal_error'],
            'errors': str(error),
            'results': None
        })
    finally:
        if cur:  cur.close()
        if conn: conn.close()


# ---------------------------------------------------------------------------
# 10. Purchase ticket / pass
#     POST /dbproj/purchase
# ---------------------------------------------------------------------------

def purchase_ticket():
    """
    Buy a ticket or pass for a given line and travel date.

    Flow:
      1. Lock customer row (double purchase / insufficient balance)
      2. Resolve the correct faretype for the line + product_type
      3. Get current price from farehistory (most recent effective_from <= today)
      4. Apply promotion discount if one is active for this line + product_type + travel_date
      5. Lock the trip row for the travel_date (last seat)
      6. Check seat availability
      7. Insert purchase record
      8. Associate purchase with trip in trip_purchase
      9. Deduction of wallet balance is handled by a DB trigger on purchase INSERT
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, ['line_id', 'product_type', 'travel_date'])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    if payload['product_type'] not in VALID_PRODUCT_TYPES:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Invalid product_type. Must be one of: {VALID_PRODUCT_TYPES}',
            'results': None
        })

    customer_user_id = int(get_jwt_identity())
    is_single_trip   = payload['product_type'] == 'single_trip'

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'POST /dbproj/purchase - user_id: {customer_user_id}, payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # 1. Lock customer row — prevents double-purchase with insufficient balance 
        cur.execute("""
            SELECT wallet_balance FROM customer
            WHERE users_user_id = %s
            FOR UPDATE
        """, (customer_user_id,))

        customer_row = cur.fetchone()
        if customer_row is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': 'Customer not found',
                'results': None
            })

        # 2. Resolve line, faretype, current price and active promotion in a single query.
        #    JOIN chain: line → faretype → farehistory (most recent price <= travel_date)
        #    LEFT JOIN promotion to get the best active discount if one exists on travel_date.
        #    FOR UPDATE on farehistory prevents concurrent price changes.
        cur.execute("""
            SELECT
                ft.fare_type_id,
                fh.price                AS base_price,
                pr.promotion_id,
                pr.discount_percent
            FROM line_lineoperation l
            JOIN faretype ft
                ON ft.line_lineoperation_line_id = l.line_id
               AND ft.type = %s
            JOIN farehistory fh
                ON fh.faretype_fare_type_id = ft.fare_type_id
               AND fh.effective_from = (
                   SELECT MAX(fh2.effective_from)
                   FROM farehistory fh2
                   WHERE fh2.faretype_fare_type_id = ft.fare_type_id
                     AND fh2.effective_from <= %s
               )
            LEFT JOIN promotion pr
                ON pr.faretype_fare_type_id = ft.fare_type_id
               AND pr.line_lineoperation_line_id = l.line_id
               AND pr.start_date <= %s
               AND pr.end_date   >= %s
               AND pr.discount_percent = (
                   SELECT MAX(pr2.discount_percent)
                   FROM promotion pr2
                   WHERE pr2.faretype_fare_type_id = ft.fare_type_id
                     AND pr2.line_lineoperation_line_id = l.line_id
                     AND pr2.start_date <= %s
                     AND pr2.end_date   >= %s
               )
            WHERE l.line_id = %s
              AND l.lineoperation_is_open = TRUE
            FOR UPDATE OF fh
        """, (
            payload['product_type'],
            payload['travel_date'],
            payload['travel_date'], payload['travel_date'],
            payload['travel_date'], payload['travel_date'],
            payload['line_id']
        ))

        fare_row = cur.fetchone()
        if fare_row is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': f'Line {payload["line_id"]} not found, closed, or no valid fare/price for "{payload["product_type"]}" on {payload["travel_date"]}',
                'results': None
            })

        fare_type_id, base_price, promotion_id, discount_percent = fare_row
        base_price  = float(base_price)
        discount    = float(discount_percent) if discount_percent is not None else 0.0
        final_price = round(base_price * (1 - discount / 100), 2)

        # For monthly passes, check no active pass already exists for this month
        if not is_single_trip and payload['product_type'] != 'daily':
            cur.execute("""
                SELECT purchase_id FROM purchase
                WHERE customer_users_user_id = %s
                  AND faretype_fare_type_id = %s
                  AND DATE_TRUNC('month', travel_date) = DATE_TRUNC('month', %s::DATE)
            """, (customer_user_id, fare_type_id, payload['travel_date']))

            if cur.fetchone() is not None:
                cur.execute('ROLLBACK;')
                return flask.jsonify({
                    'status': StatusCodes['bad_request'],
                    'errors': 'You already have an active pass for this line and month',
                    'results': None
                })

        # 3. For single_trip: lock the trip row and check seat availability 
        trip_id      = None
        trip_line_id = None

        if is_single_trip:
            cur.execute("""
                SELECT trip_id, line_lineoperation_line_id, capacity, booked_seats
                FROM trip
                WHERE line_lineoperation_line_id = %s
                  AND DATE(departure_time) = %s
                ORDER BY departure_time
                LIMIT 1
                FOR UPDATE
            """, (payload['line_id'], payload['travel_date']))

            trip_row = cur.fetchone()
            if trip_row is None:
                cur.execute('ROLLBACK;')
                return flask.jsonify({
                    'status': StatusCodes['bad_request'],
                    'errors': f'No trip found for line {payload["line_id"]} on {payload["travel_date"]}',
                    'results': None
                })

            trip_id, trip_line_id, capacity, booked_seats = trip_row

            if booked_seats >= capacity:
                cur.execute('ROLLBACK;')
                return flask.jsonify({
                    'status': StatusCodes['bad_request'],
                    'errors': 'No seats available for this trip',
                    'results': None
                })

        # 4. Insert purchase record
        # Wallet deduction is handled automatically by the DB trigger
        cur.execute("""
            INSERT INTO purchase (
                travel_date, final_price, purchased_at,
                promotion_promotion_id, faretype_fare_type_id, customer_users_user_id
            )
            VALUES (%s, %s, NOW(), %s, %s, %s)
            RETURNING purchase_id
        """, (
            payload['travel_date'],
            final_price,
            promotion_id,
            fare_type_id,
            customer_user_id
        ))

        purchase_id = cur.fetchone()[0]

        # 5. Associate purchase with trip (single_trip only)
        if is_single_trip:
            cur.execute("""
                INSERT INTO trip_purchase (
                    trip_trip_id, trip_line_lineoperation_line_id, purchase_purchase_id
                )
                VALUES (%s, %s, %s)
            """, (trip_id, trip_line_id, purchase_id))

            # Update booked seats
            cur.execute("""
                UPDATE trip
                SET booked_seats = booked_seats + 1
                WHERE trip_id = %s
                  AND line_lineoperation_line_id = %s
            """, (trip_id, trip_line_id))

        cur.execute('COMMIT;')
        logger.debug(f'Purchase {purchase_id} created for user {customer_user_id}, price: {final_price}')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': {
                'purchase_id': purchase_id,
                'final_price': final_price
            }
        })

    except psycopg2.errors.RaiseException as db_error:
        # Triggered by DB-level trigger (e.g. insufficient balance)
        logger.error(f'POST /dbproj/purchase - trigger error: {db_error}')
        if conn: conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': str(db_error).split('\n')[0],
            'results': None
        })
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /dbproj/purchase - error: {error}')
        if conn: conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['internal_error'],
            'errors': str(error),
            'results': None
        })
    finally:
        if cur:  cur.close()
        if conn: conn.close()


# ---------------------------------------------------------------------------
# 11. Validate / use ticket
#     POST /dbproj/ticket/use/<ticket_id>
# ---------------------------------------------------------------------------

def use_ticket(ticket_id):
    """
    Validate and register the use of a ticket (purchase_id).

    Checks:
      - The purchase belongs to the authenticated customer
      - The ticket's faretype belongs to the correct line (via station_id)
      - For single_trip: ticket has not been used before
      - For daily: ticket is used within 24h of first use
      - For monthly passes: ticket is used within the validity month

    Inserts a record in ticketvalidation on success.
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, ['used_at', 'station_id'])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    customer_user_id = int(get_jwt_identity())

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'POST /dbproj/ticket/use/{ticket_id} - user_id: {customer_user_id}, payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # 1. Fetch purchase, verify ownership, verify station belongs to line,
        #    and retrieve existing validations — all in a single query.
        #    FOR UPDATE on purchase prevents concurrent use of the same ticket.
        cur.execute("""
            SELECT
                p.purchase_id,
                p.travel_date,
                p.customer_users_user_id,
                ft.type                         AS product_type,
                ft.line_lineoperation_line_id   AS line_id,
                EXISTS (
                    SELECT 1 FROM linestation ls
                    WHERE ls.station_station_id         = %s
                      AND ls.line_lineoperation_line_id = ft.line_lineoperation_line_id
                )                               AS station_valid,
                (
                    SELECT COUNT(tv.validation_id)
                    FROM ticketvalidation tv
                    WHERE tv.purchase_purchase_id = p.purchase_id
                )                               AS validation_count,
                (
                    SELECT MIN(tv2.used_at)
                    FROM ticketvalidation tv2
                    WHERE tv2.purchase_purchase_id = p.purchase_id
                )                               AS first_used_at
            FROM purchase p
            JOIN faretype ft ON ft.fare_type_id = p.faretype_fare_type_id
            WHERE p.purchase_id = %s
            FOR UPDATE OF p
        """, (payload['station_id'], ticket_id))

        purchase_row = cur.fetchone()
        if purchase_row is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': f'Ticket {ticket_id} not found',
                'results': None
            })

        p_id, travel_date, owner_id, product_type, line_id, station_valid, validation_count, first_used_at = purchase_row

        if owner_id != customer_user_id:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': 'This ticket does not belong to you',
                'results': None
            })

        if not station_valid:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': f'Station {payload["station_id"]} does not belong to line {line_id}',
                'results': None
            })

        # 2. Validate according to product_type rules
        used_at = payload['used_at']  # string — DB will cast to TIMESTAMP

        if product_type == 'single_trip':
            if validation_count >= 1:
                cur.execute('ROLLBACK;')
                return flask.jsonify({
                    'status': StatusCodes['bad_request'],
                    'errors': 'Single trip ticket has already been used',
                    'results': None
                })

        elif product_type == 'daily':
            if validation_count > 0:
                cur.execute("""
                    SELECT %s::TIMESTAMP - %s::TIMESTAMP > INTERVAL '24 hours'
                """, (used_at, str(first_used_at)))
                expired = cur.fetchone()[0]
                if expired:
                    cur.execute('ROLLBACK;')
                    return flask.jsonify({
                        'status': StatusCodes['bad_request'],
                        'errors': 'Daily ticket has expired (24h limit exceeded)',
                        'results': None
                    })

        elif product_type in ('monthly', 'monthly_student', 'monthly_senior'):
            # Valid for the entire calendar month of travel_date
            cur.execute("""
                SELECT
                    DATE_TRUNC('month', %s::DATE) <= %s::TIMESTAMP
                    AND %s::TIMESTAMP < DATE_TRUNC('month', %s::DATE) + INTERVAL '1 month'
            """, (str(travel_date), used_at, used_at, str(travel_date)))

            valid = cur.fetchone()[0]
            if not valid:
                cur.execute('ROLLBACK;')
                return flask.jsonify({
                    'status': StatusCodes['bad_request'],
                    'errors': 'Monthly pass is not valid for the requested date',
                    'results': None
                })

        # 3. Insert validation record
        cur.execute("""
            INSERT INTO ticketvalidation (used_at, purchase_purchase_id, station_station_id)
            VALUES (%s::TIMESTAMP, %s, %s)
            RETURNING validation_id
        """, (used_at, ticket_id, payload['station_id']))

        validation_id = cur.fetchone()[0]

        cur.execute('COMMIT;')
        logger.debug(f'Ticket {ticket_id} validated — validation_id: {validation_id}')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': None
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /dbproj/ticket/use/{ticket_id} - error: {error}')
        if conn: conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['internal_error'],
            'errors': str(error),
            'results': None
        })
    finally:
        if cur:  cur.close()
        if conn: conn.close()

# ---------------------------------------------------------------------------
# 15. Get notices (customer)
#     GET /dbproj/notices
# ---------------------------------------------------------------------------
 
def get_notices():
    """
    Return all notices for the authenticated customer.
    For each notice that has not yet been read (read_at IS NULL),
    set read_at = NOW() atomically in the same transaction.
 
    Response includes, for each notice:
      - notice_id
      - title
      - message
      - sent_at
      - read_at  (NULL if it was unread before this request — will be set now)
    """
    customer_user_id = int(get_jwt_identity())
 
    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'GET /dbproj/notices - user_id: {customer_user_id}')
 
    try:
        cur.execute('BEGIN;')
 
        # 1. Fetch all notices for this customer, locking unread rows
        cur.execute("""
            SELECT
                n.notice_id,
                n.title,
                n.message,
                n.sent_at,
                cn.read_at
            FROM customernotice cn
            JOIN notice n ON n.notice_id = cn.notice_notice_id
            WHERE cn.customer_users_user_id = %s
            ORDER BY n.sent_at DESC
            FOR UPDATE OF cn
        """, (customer_user_id,))
 
        rows = cur.fetchall()
 
        if not rows:
            cur.execute('COMMIT;')
            return flask.jsonify({
                'status':  StatusCodes['success'],
                'errors':  None,
                'results': []
            })
 
        # 2. Mark all unread notices as read now
        cur.execute("""
            UPDATE customernotice
            SET read_at = NOW()
            WHERE customer_users_user_id = %s
              AND read_at IS NULL
        """, (customer_user_id,))
 
        cur.execute('COMMIT;')
 
        # 3. Build response — read_at for previously unread notices will show as None
        #    (the client now knows they were just read; a second call will show the timestamp)
        results = []
        for row in rows:
            notice_id, title, message, sent_at, read_at = row
            results.append({
                'notice_id': notice_id,
                'title':     title,
                'message':   message,
                'sent_at':   str(sent_at),
                'read_at':   str(read_at) if read_at else None
            })
 
        logger.debug(f'Notices fetched for user {customer_user_id}: {len(results)} notices')
 
        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': results
        })
 
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'GET /dbproj/notices - error: {error}')
        if conn: conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['internal_error'],
            'errors': str(error),
            'results': None
        })
    finally:
        if cur:  cur.close()
        if conn: conn.close()