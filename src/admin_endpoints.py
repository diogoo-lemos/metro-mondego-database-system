import flask
import psycopg2
from flask_jwt_extended import get_jwt_identity
from global_functions import db_connection, logger, StatusCodes, check_required_fields, payload_contains_dangerous_chars, VALID_PRODUCT_TYPES

# ---------------------------------------------------------------------------
# 4. Update line operation settings
#    PUT /dbproj/line_operation/<line_id>
# ---------------------------------------------------------------------------

def update_line_operation(line_id):
    """
    Update operational parameters of a given line.
    Allowed fields: start_time, end_time, frequency_minutes, vehicle_capacity, is_open
    At least one field must be provided.
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    allowed_fields = {
        'start_time':         'lineoperation_start_time',
        'end_time':           'lineoperation_end_time',
        'frequency_minutes':  'lineoperation_frequency',
        'vehicle_capacity':   'lineoperation_capacity',
        'is_open':            'lineoperation_is_open'
    }

    # Build dynamic SET clause with only the fields provided
    updates = {}
    for field, column in allowed_fields.items():
        if field in payload:
            updates[column] = payload[field]

    if not updates:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'At least one field must be provided: {list(allowed_fields.keys())}',
            'results': None
        })

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'PUT /dbproj/line_operation/{line_id} - payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # Check that the line exists
        cur.execute('SELECT line_id FROM line_lineoperation WHERE line_id = %s', (line_id,))
        if cur.fetchone() is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': f'Line {line_id} not found',
                'results': None
            })

        # Build and execute the UPDATE
        set_clause = ', '.join([f'{col} = %s' for col in updates.keys()])
        values     = list(updates.values()) + [line_id]

        cur.execute(f"""
            UPDATE line_lineoperation
            SET {set_clause}
            WHERE line_id = %s
        """, values)

        cur.execute('COMMIT;')
        logger.debug(f'Line {line_id} updated successfully')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': None
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'PUT /dbproj/line_operation/{line_id} - error: {error}')
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
# 5. Update fare price
#    PUT /dbproj/fares/<fare_id>
# ---------------------------------------------------------------------------

def update_fare_price(fare_id):
    """
    Change the price of a fare type.
    Inserts a new record in farehistory to preserve price history.
    The old record is never deleted — admins can review past prices analytically.
    Uses SELECT FOR UPDATE on the faretype row to avoid concurrency conflict.
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, ['price', 'effective_from'])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    if float(payload['price']) <= 0:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Price must be greater than 0',
            'results': None
        })

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'PUT /dbproj/fares/{fare_id} - payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # Lock the faretype row to prevent concurrent price changes (concurrency C3)
        cur.execute("""
            SELECT fare_type_id FROM faretype
            WHERE fare_type_id = %s
            FOR UPDATE
        """, (fare_id,))

        if cur.fetchone() is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': f'Fare type {fare_id} not found',
                'results': None
            })

        # Insert new price record into farehistory (preserves full price history)
        cur.execute("""
            INSERT INTO farehistory (price, effective_from, faretype_fare_type_id)
            VALUES (%s, %s, %s)
        """, (payload['price'], payload['effective_from'], fare_id))

        cur.execute('COMMIT;')
        logger.debug(f'Fare {fare_id} price updated to {payload["price"]} from {payload["effective_from"]}')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': None
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'PUT /dbproj/fares/{fare_id} - error: {error}')
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
# 6. Broadcast notice
#    POST /dbproj/notices/broadcast
# ---------------------------------------------------------------------------

def broadcast_notice():
    """
    Send a notice to ALL active customers.
    Inserts one record in notice and one record in customernotice per customer.
    If any insertion fails, the entire transaction is rolled back (no partial broadcast).
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, ['title', 'message'])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    # Get admin user_id from JWT
    admin_user_id = int(get_jwt_identity())

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'POST /dbproj/notices/broadcast - payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # Insert the notice
        cur.execute("""
            INSERT INTO notice (title, message, sent_at, administrator_users_user_id)
            VALUES (%s, %s, NOW(), %s)
            RETURNING notice_id
        """, (payload['title'], payload['message'], admin_user_id))

        notice_id = cur.fetchone()[0]

        # Distribute to all customers via customernotice
        cur.execute("""
            INSERT INTO customernotice (customer_users_user_id, notice_notice_id, read_at)
            SELECT users_user_id, %s, NULL
            FROM customer
        """, (notice_id,))

        cur.execute('COMMIT;')
        logger.debug(f'Notice {notice_id} broadcast to all customers')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': None
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /dbproj/notices/broadcast - error: {error}')
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
# 7. Create promotion / discount rule
#    POST /dbproj/promotions
# ---------------------------------------------------------------------------

def create_promotion():
    """
    Insert a promotion so customers can buy cheaper tickets.
    Validates that the line exists, the product_type is valid,
    and that the discount is between 1 and 100.
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, [
        'name', 'line_id', 'product_type',
        'discount_percent', 'start_date', 'end_date'
    ])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    # Validate product_type
    if payload['product_type'] not in VALID_PRODUCT_TYPES:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Invalid product_type. Must be one of: {VALID_PRODUCT_TYPES}',
            'results': None
        })

    # Validate discount range
    discount = float(payload['discount_percent'])
    if not (1 <= discount <= 100):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'discount_percent must be between 1 and 100',
            'results': None
        })

    # Validate dates
    if payload['start_date'] >= payload['end_date']:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'start_date must be before end_date',
            'results': None
        })

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'POST /dbproj/promotions - payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # Check that the line exists
        cur.execute("""
            SELECT line_id FROM line_lineoperation WHERE line_id = %s
        """, (payload['line_id'],))
        if cur.fetchone() is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': f'Line {payload["line_id"]} not found',
                'results': None
            })

        # Resolve the fare_type_id for the given line + product_type
        cur.execute("""
            SELECT fare_type_id FROM faretype
            WHERE line_lineoperation_line_id = %s
              AND type = %s
        """, (payload['line_id'], payload['product_type']))

        fare_row = cur.fetchone()
        if fare_row is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': f'No fare found for line {payload["line_id"]} and product type "{payload["product_type"]}"',
                'results': None
            })

        fare_type_id = fare_row[0]

        # Insert the promotion
        cur.execute("""
            INSERT INTO promotion (
                name, discount_percent, start_date, end_date,
                line_lineoperation_line_id, faretype_fare_type_id
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING promotion_id
        """, (
            payload['name'],
            discount,
            payload['start_date'],
            payload['end_date'],
            payload['line_id'],
            fare_type_id
        ))

        promotion_id = cur.fetchone()[0]

        cur.execute('COMMIT;')
        logger.debug(f'Promotion {promotion_id} created successfully')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': {'promotion_id': promotion_id}
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /dbproj/promotions - error: {error}')
        if conn: conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['internal_error'],
            'errors': str(error),
            'results': None
        })
    finally:
        if cur:  cur.close()
        if conn: conn.close()
