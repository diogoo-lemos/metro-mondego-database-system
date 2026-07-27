import flask
import psycopg2
from global_functions import db_connection, logger, StatusCodes

# ---------------------------------------------------------------------------
# 12. Peak and low demand periods
#     GET /dbproj/report/demand
# ---------------------------------------------------------------------------

def report_demand():
    """
    For each line, return the time slot (hour) with the HIGHEST and LOWEST
    number of ticket validations.

    A time slot is defined as an hour interval (e.g. '08:00-08:59').
    Only one SQL query is used to obtain the information, using subqueries.

    Strategy:
      - Group validations by line and hour
      - For each line, find the hour with MAX and MIN validations
      - UNION the two result sets
      - Order by line_id, then validations DESC (peak first)
    """
    conn = db_connection()
    cur  = conn.cursor()
    logger.debug('GET /dbproj/report/demand')

    try:
        # SERIALIZABLE isolation — report must reflect a consistent snapshot (C5)
        cur.execute('BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;')

        cur.execute("""
            SELECT
                line_id,
                time_slot,
                validations
            FROM (
                SELECT
                    ft.line_lineoperation_line_id                           AS line_id,
                    TO_CHAR(DATE_TRUNC('hour', tv.used_at), 'HH24:00')
                        || '-' ||
                    TO_CHAR(DATE_TRUNC('hour', tv.used_at) + INTERVAL '59 minutes', 'HH24:59')
                                                                            AS time_slot,
                    COUNT(tv.validation_id)                                 AS validations
                FROM ticketvalidation tv
                JOIN purchase p
                    ON p.purchase_id = tv.purchase_purchase_id
                JOIN faretype ft
                    ON ft.fare_type_id = p.faretype_fare_type_id
                GROUP BY ft.line_lineoperation_line_id, DATE_TRUNC('hour', tv.used_at)
            ) AS hourly_stats
            WHERE (line_id, validations) IN (
                -- Peak: max validations per line
                SELECT line_id, MAX(validations)
                FROM (
                    SELECT
                        ft2.line_lineoperation_line_id  AS line_id,
                        COUNT(tv2.validation_id)         AS validations
                    FROM ticketvalidation tv2
                    JOIN purchase p2
                        ON p2.purchase_id = tv2.purchase_purchase_id
                    JOIN faretype ft2
                        ON ft2.fare_type_id = p2.faretype_fare_type_id
                    GROUP BY ft2.line_lineoperation_line_id, DATE_TRUNC('hour', tv2.used_at)
                ) AS agg2
                GROUP BY line_id

                UNION ALL

                -- Low: min validations per line
                SELECT line_id, MIN(validations)
                FROM (
                    SELECT
                        ft3.line_lineoperation_line_id  AS line_id,
                        COUNT(tv3.validation_id)         AS validations
                    FROM ticketvalidation tv3
                    JOIN purchase p3
                        ON p3.purchase_id = tv3.purchase_purchase_id
                    JOIN faretype ft3
                        ON ft3.fare_type_id = p3.faretype_fare_type_id
                    GROUP BY ft3.line_lineoperation_line_id, DATE_TRUNC('hour', tv3.used_at)
                ) AS agg3
                GROUP BY line_id
            )
            ORDER BY line_id, validations DESC
        """)

        rows = cur.fetchall()

        results = []
        for row in rows:
            results.append({
                'line_id':     row[0],
                'time_slot':   row[1],
                'validations': row[2]
            })

        cur.execute('COMMIT;')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': results
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'GET /dbproj/report/demand - error: {error}')
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
# 13. Top spenders by line
#     GET /dbproj/report/top_spenders
# ---------------------------------------------------------------------------

def report_top_spenders():
    """
    For each line, return the customer(s) with the highest total spending
    over the last 30 days.

    If multiple customers share the top spending value on the same line,
    all of them are returned.

    Only one SQL query is used, with subqueries.
    SERIALIZABLE isolation ensures consistent aggregation.
    """
    conn = db_connection()
    cur  = conn.cursor()
    logger.debug('GET /dbproj/report/top_spenders')

    try:
        cur.execute('BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;')

        cur.execute("""
            SELECT
                per_line.line_id,
                per_line.customer_id,
                u.username          AS customer_name,
                per_line.spent
            FROM (
                SELECT
                    ft.line_lineoperation_line_id   AS line_id,
                    p.customer_users_user_id         AS customer_id,
                    SUM(p.final_price)               AS spent
                FROM purchase p
                JOIN faretype ft
                    ON ft.fare_type_id = p.faretype_fare_type_id
                WHERE p.purchased_at >= NOW() - INTERVAL '30 days'
                GROUP BY ft.line_lineoperation_line_id, p.customer_users_user_id
            ) AS per_line
            JOIN customer c
                ON c.users_user_id = per_line.customer_id
            JOIN users u
                ON u.user_id = c.users_user_id
            WHERE per_line.spent = (
                -- Subquery: find the max spent for this line in the last 30 days
                SELECT MAX(spent_inner)
                FROM (
                    SELECT
                        SUM(p2.final_price) AS spent_inner
                    FROM purchase p2
                    JOIN faretype ft2
                        ON ft2.fare_type_id = p2.faretype_fare_type_id
                    WHERE ft2.line_lineoperation_line_id = per_line.line_id
                      AND p2.purchased_at >= NOW() - INTERVAL '30 days'
                    GROUP BY p2.customer_users_user_id
                ) AS max_inner
            )
            ORDER BY per_line.line_id, per_line.spent DESC
        """)

        rows = cur.fetchall()

        results = []
        for row in rows:
            results.append({
                'line_id':       row[0],
                'customer_id':   row[1],
                'customer_name': row[2],
                'spent':         float(row[3])
            })

        cur.execute('COMMIT;')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': results
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'GET /dbproj/report/top_spenders - error: {error}')
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
# 14. Monthly report
#     GET /dbproj/report/monthly
# ---------------------------------------------------------------------------

def report_monthly():
    """
    For each line and month, show:
      - active_customers : customers with >= 1 ticket validation
      - repeat_customers : customers with >= 2 ticket validations

    Only one SQL query is used, with subqueries.
    SERIALIZABLE isolation ensures consistent aggregation.
    """
    conn = db_connection()
    cur  = conn.cursor()
    logger.debug('GET /dbproj/report/monthly')

    try:
        cur.execute('BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;')

        cur.execute("""
            SELECT
                line_id,
                month,
                COUNT(customer_id)                                      AS active_customers,
                COUNT(CASE WHEN validation_count >= 2 THEN 1 END)       AS repeat_customers
            FROM (
                SELECT
                    ft.line_lineoperation_line_id       AS line_id,
                    EXTRACT(MONTH FROM tv.used_at)       AS month,
                    p.customer_users_user_id             AS customer_id,
                    COUNT(tv.validation_id)              AS validation_count
                FROM ticketvalidation tv
                JOIN purchase p
                    ON p.purchase_id = tv.purchase_purchase_id
                JOIN faretype ft
                    ON ft.fare_type_id = p.faretype_fare_type_id
                GROUP BY
                    ft.line_lineoperation_line_id,
                    EXTRACT(MONTH FROM tv.used_at),
                    p.customer_users_user_id
            ) AS per_customer_month
            GROUP BY line_id, month
            ORDER BY line_id, month
        """)

        rows = cur.fetchall()

        results = []
        for row in rows:
            results.append({
                'line_id':          row[0],
                'month':            int(row[1]),
                'active_customers': row[2],
                'repeat_customers': row[3]
            })

        cur.execute('COMMIT;')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': results
        })

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'GET /dbproj/report/monthly - error: {error}')
        if conn: conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['internal_error'],
            'errors': str(error),
            'results': None
        })
    finally:
        if cur:  cur.close()
        if conn: conn.close()
