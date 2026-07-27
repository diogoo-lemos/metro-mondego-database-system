import logging
import os
from pathlib import Path
import psycopg2

# ---------------------------------------------------------------------------
# Global variables
# ---------------------------------------------------------------------------

logger = logging.getLogger('logger')
BASE_DIR = Path(__file__).resolve().parent.parent

StatusCodes = {
    'success':        200,
    'bad_request':    400,
    'internal_error': 500
}

# Valid product types accepted by the system
VALID_PRODUCT_TYPES = [
    'single_trip',
    'daily',
    'monthly',
    'monthly_student',
    'monthly_senior'
]

# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def db_connection():
    """Open and return a new psycopg2 connection to the Metro Mondego DB.

    Credentials are read from environment variables (see .env.example)
    """
    try:
        db = psycopg2.connect(
            user     = os.getenv('DB_USER', 'metro_admin'),
            password = os.getenv('DB_PASSWORD'),
            host     = os.getenv('DB_HOST', '127.0.0.1'),
            port     = os.getenv('DB_PORT', '5432'),
            database = os.getenv('DB_NAME', 'metro_db')
        )
        return db
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f'Error connecting to the database: {error}')
        return None

# ---------------------------------------------------------------------------
# SQL script runner
# ---------------------------------------------------------------------------

def run_sql_script(script_path):
    """Execute a .sql file against the database."""
    conn = db_connection()
    cursor = conn.cursor()
    try:
        sql_file = BASE_DIR / script_path
        with open(sql_file, 'r', encoding='utf-8') as f:
            script_str = f.read()
        cursor.execute(script_str)
        conn.commit()
        print(f'{sql_file} executed successfully')
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def setup_database():
    """Drop all tables and recreate the full schema + seed data."""
    print('Setting up the Metro Mondego database...')
    run_sql_script('queries/drop_tables.sql')
    run_sql_script('queries/create_tables.sql')
    run_sql_script('queries/create_triggers.sql')
    run_sql_script('queries/seed_data.sql')
    print('Database setup complete.')

def check_database_setup():
    """Verify that the core tables exist. Exit with error if they don't."""
    conn = db_connection()
    cur = conn.cursor()
    try:
        required_tables = [
            'users', 'customer', 'administrator',
            'line_lineoperation', 'station', 'linestation',
            'trip', 'faretype', 'farehistory',
            'purchase', 'ticketvalidation',
            'promotion', 'wallettransaction',
            'notice', 'customernotice', 'trip_purchase'
        ]
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        existing = {row[0] for row in cur.fetchall()}
        missing = [t for t in required_tables if t not in existing]
        if missing:
            raise Exception(
                f'Database not properly set up. Missing tables: {missing}. '
                'Run with --setup flag.'
            )
    except Exception as e:
        print(str(e))
        exit(1)
    finally:
        cur.close()
        conn.close()

# ---------------------------------------------------------------------------
# Request validation helpers
# ---------------------------------------------------------------------------

def check_required_fields(payload, required_keys):
    """Return a list of keys missing from the payload."""
    missing = [key for key in required_keys if key not in payload]
    if missing:
        logger.error(f'Missing required fields: {", ".join(missing)}')
    return missing

def string_contains_dangerous_chars(input_str):
    """Basic SQL-injection guard for raw string values."""
    dangerous = [';', '--', '/*', '*/']
    return any(char in input_str for char in dangerous)

def payload_contains_dangerous_chars(payload):
    """Recursively check a JSON payload for dangerous characters."""
    for key, value in payload.items():
        if isinstance(value, dict):
            if payload_contains_dangerous_chars(value):
                return True
        elif isinstance(value, (list, tuple)):
            for element in value:
                if isinstance(element, str) and string_contains_dangerous_chars(element):
                    return True
                elif isinstance(element, (dict, list, tuple)):
                    if payload_contains_dangerous_chars({0: element}):
                        return True
        elif isinstance(value, str):
            if string_contains_dangerous_chars(value):
                return True
    return False

# ---------------------------------------------------------------------------
# Landing page 
# ---------------------------------------------------------------------------

def landing_page():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { background-color: #f2f2f2; font-family: Arial, sans-serif; }
            .container { width: 80%; margin: auto; text-align: center; padding-top: 80px; }
            h1 { color: #0057a8; }
            p  { font-size: 1.1em; color: #444; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1> Metro Mondego — REST API</h1>
            <p>Use Postman to interact with the available endpoints.</p>
        </div>
    </body>
    </html>
    """
