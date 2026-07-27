import flask
import psycopg2
from flask_jwt_extended import create_access_token, get_jwt, set_access_cookies
from functools import wraps
from global_functions import db_connection, logger, StatusCodes, check_required_fields, payload_contains_dangerous_chars
from hashing import verify_password, hash_password

# ---------------------------------------------------------------------------
# Login  (PUT /dbproj/user)
# ---------------------------------------------------------------------------

def authenticate_user():
    """
    Authenticate a user by username + password.
    Returns a JWT token that must be included in subsequent requests.
    Roles: 'customer', 'admin', 'superadmin'
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, ['username', 'password'])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'PUT /dbproj/user - payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # 1. Fetch user by username
        cur.execute("""
            SELECT user_id, password_hash
            FROM users
            WHERE username = %s
        """, (payload['username'],))

        row = cur.fetchone()
        if row is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': 'User not found',
                'results': None
            })

        user_id       = row[0]
        password_hash = row[1]

        # 2. Verify password
        if not verify_password(password_hash, payload['password']):
            logger.error('Invalid password provided')
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['bad_request'],
                'errors': 'Invalid password',
                'results': None
            })

        # 3. Determine role
        role = _get_user_role(cur, user_id)
        if role is None:
            cur.execute('ROLLBACK;')
            return flask.jsonify({
                'status': StatusCodes['internal_error'],
                'errors': 'User exists but has no assigned role',
                'results': None
            })

        logger.debug(f'PUT /dbproj/user - user_id: {user_id}, role: {role}')

        # 4. Generate JWT
        access_token = create_access_token(
            identity=str(user_id),
            additional_claims={'role': role}
        )

        response = flask.make_response(flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': access_token
        }))
        set_access_cookies(response, access_token)

        cur.execute('COMMIT;')
        return response

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'PUT /dbproj/user - error: {error}')
        if conn:
            conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['internal_error'],
            'errors': str(error),
            'results': None
        })
    finally:
        if cur:  cur.close()
        if conn: conn.close()


# ---------------------------------------------------------------------------
# Register Admin  (PUT /dbproj/register/admin)
# Only callable by the superadmin account
# ---------------------------------------------------------------------------

def register_admin():
    """
    Create a new administrator account.
    Only the Super Administrator can call this endpoint.
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, ['name', 'username', 'email', 'password'])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'PUT /dbproj/register/admin - payload: {payload}')

    try:
        cur.execute('BEGIN;')

        # Hash password
        hashed = hash_password(payload['password']).hex()

        # Insert into users
        cur.execute("""
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (%s, %s, %s, NOW())
            RETURNING user_id
        """, (payload['username'], payload['email'], hashed))

        user_id = cur.fetchone()[0]

        # Insert into administrator (is_super = False for newly created admins)
        cur.execute("""
            INSERT INTO administrator (name, is_super, users_user_id)
            VALUES (%s, FALSE, %s)
        """, (payload['name'], user_id))

        cur.execute('COMMIT;')
        logger.debug(f'Admin registered with user_id: {user_id}')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': {'user_id': user_id}
        })

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Username or email already in use',
            'results': None
        })
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'PUT /dbproj/register/admin - error: {error}')
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
# Register Customer  (POST /dbproj/register/customer)
# Only callable by admins
# ---------------------------------------------------------------------------

def register_customer():
    """
    Create a new customer account.
    Only Administrators (or Super Admin) can call this endpoint.
    """
    payload = flask.request.get_json()

    if payload_contains_dangerous_chars(payload):
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Payload contains dangerous characters',
            'results': None
        })

    missing = check_required_fields(payload, ['name', 'username', 'nif', 'phone', 'email', 'password'])
    if missing:
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': f'Missing required field(s): {", ".join(missing)}',
            'results': None
        })

    conn = db_connection()
    cur  = conn.cursor()
    logger.debug(f'POST /dbproj/register/customer - payload: {payload}')

    try:
        cur.execute('BEGIN;')

        hashed = hash_password(payload['password']).hex()

        # Insert into users
        cur.execute("""
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (%s, %s, %s, NOW())
            RETURNING user_id
        """, (payload['username'], payload['email'], hashed))

        user_id = cur.fetchone()[0]

        # Insert into customer (wallet starts at 0)
        cur.execute("""
            INSERT INTO customer (name, nif, phone, wallet_balance, users_user_id)
            VALUES (%s, %s, %s, 0.0, %s)
        """, (payload['name'], payload['nif'], payload['phone'], user_id))

        cur.execute('COMMIT;')
        logger.debug(f'Customer registered with user_id: {user_id}')

        return flask.jsonify({
            'status':  StatusCodes['success'],
            'errors':  None,
            'results': {'user_id': user_id}
        })

    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return flask.jsonify({
            'status': StatusCodes['bad_request'],
            'errors': 'Username, email or NIF already in use',
            'results': None
        })
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'POST /dbproj/register/customer - error: {error}')
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
# Internal helper — determine role from DB
# ---------------------------------------------------------------------------

def _get_user_role(cur, user_id):
    """
    Check which role table the user belongs to.
    Returns: 'superadmin' | 'admin' | 'customer' | None
    """
    # Check administrator table first
    cur.execute("""
        SELECT is_super FROM administrator
        WHERE users_user_id = %s
    """, (user_id,))
    row = cur.fetchone()
    if row is not None:
        return 'superadmin' if row[0] else 'admin'

    # Check customer table
    cur.execute("""
        SELECT 1 FROM customer
        WHERE users_user_id = %s
    """, (user_id,))
    if cur.fetchone() is not None:
        return 'customer'

    return None


# ---------------------------------------------------------------------------
# Role-based access control decorator
# ---------------------------------------------------------------------------

def role_required(required_roles):
    """
    Decorator that checks the JWT role claim against a list of allowed roles.
    Usage:
        @role_required(['admin', 'superadmin'])
        def my_endpoint(): ...
    """
    # Accept a single string or a list
    if isinstance(required_roles, str):
        required_roles = [required_roles]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            claims = get_jwt()
            user_role = claims.get('role')

            if user_role not in required_roles:
                logger.error(
                    f'Insufficient permissions - required: {required_roles}, actual: {user_role}'
                )
                return flask.jsonify({
                    'status': StatusCodes['bad_request'],
                    'errors': f'Insufficient permissions — required: {required_roles}, actual: {user_role}',
                    'results': None
                })

            return func(*args, **kwargs)
        return wrapper
    return decorator