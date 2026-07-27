'''
Databases
LEI 2025/2026


Metro Mondego System    


Execution:
    $ python rest_api.py [--setup]

Flags:
    --setup : Drop and recreate the database schema + seed data
'''

import argparse
import flask
import logging
from flask_jwt_extended import JWTManager, jwt_required
from dotenv import load_dotenv

load_dotenv()  

from config import Config
from global_functions import logger, landing_page, setup_database, check_database_setup

# Auth + registration
from authentication import (
    authenticate_user,
    register_admin,
    register_customer,
    role_required
)

# Admin endpoints
from admin_endpoints import (
    update_line_operation,
    update_fare_price,
    broadcast_notice,
    create_promotion
)

# Customer endpoints
from customer_endpoints import (
    get_notices,
    list_lines_next,
    wallet_topup,
    purchase_ticket,
    use_ticket
)

# Report endpoints (admin only)
from report_endpoints import (
    report_demand,
    report_top_spenders,
    report_monthly,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = flask.Flask(__name__)
app.config.from_object(Config)
jwt = JWTManager(app)

app.route('/')(landing_page)

# ---------------------------------------------------------------------------
# 1. Authentication  —  PUT /dbproj/user
# ---------------------------------------------------------------------------

@app.route('/dbproj/user', methods=['PUT'])
def authenticate_user_endpoint():
    return authenticate_user()

# ---------------------------------------------------------------------------
# 2. Add Administrator  —  PUT /dbproj/register/admin
#    Only Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/register/admin', methods=['PUT'])
@jwt_required()
@role_required('superadmin')
def register_admin_endpoint():
    return register_admin()

# ---------------------------------------------------------------------------
# 3. Add Customer  —  POST /dbproj/register/customer
#    Admin + Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/register/customer', methods=['POST'])
@jwt_required()
@role_required(['admin', 'superadmin'])
def register_customer_endpoint():
    return register_customer()

# ---------------------------------------------------------------------------
# 4. Update line operation settings  —  PUT /dbproj/line_operation/<line_id>
#    Admin + Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/line_operation/<int:line_id>', methods=['PUT'])
@jwt_required()
@role_required(['admin', 'superadmin'])
def update_line_operation_endpoint(line_id):
    return update_line_operation(line_id)

# ---------------------------------------------------------------------------
# 5. Update fare price  —  PUT /dbproj/fares/<fare_id>
#    Admin + Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/fares/<int:fare_id>', methods=['PUT'])
@jwt_required()
@role_required(['admin', 'superadmin'])
def update_fare_price_endpoint(fare_id):
    return update_fare_price(fare_id)

# ---------------------------------------------------------------------------
# 6. Broadcast notice  —  POST /dbproj/notices/broadcast
#    Admin + Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/notices/broadcast', methods=['POST'])
@jwt_required()
@role_required(['admin', 'superadmin'])
def broadcast_notice_endpoint():
    return broadcast_notice()

# ---------------------------------------------------------------------------
# 7. Create promotion  —  POST /dbproj/promotions
#    Admin + Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/promotions', methods=['POST'])
@jwt_required()
@role_required(['admin', 'superadmin'])
def create_promotion_endpoint():
    return create_promotion()

# ---------------------------------------------------------------------------
# 8. List lines and upcoming departures  —  GET /dbproj/lines_next
#    Customer
# ---------------------------------------------------------------------------

@app.route('/dbproj/lines_next', methods=['GET'])
@jwt_required()
@role_required('customer')
def list_lines_next_endpoint():
    return list_lines_next()

# ---------------------------------------------------------------------------
# 9. Add wallet funds  —  POST /dbproj/wallet/topup
#    Customer
# ---------------------------------------------------------------------------

@app.route('/dbproj/wallet/topup', methods=['POST'])
@jwt_required()
@role_required('customer')
def wallet_topup_endpoint():
    return wallet_topup()

# ---------------------------------------------------------------------------
# 10. Purchase ticket/pass  —  POST /dbproj/purchase
#     Customer
# ---------------------------------------------------------------------------

@app.route('/dbproj/purchase', methods=['POST'])
@jwt_required()
@role_required('customer')
def purchase_ticket_endpoint():
    return purchase_ticket()

# ---------------------------------------------------------------------------
# 11. Validate / use ticket  —  POST /dbproj/ticket/use/<ticket_id>
#     Customer
# ---------------------------------------------------------------------------

@app.route('/dbproj/ticket/use/<int:ticket_id>', methods=['POST'])
@jwt_required()
@role_required('customer')
def use_ticket_endpoint(ticket_id):
    return use_ticket(ticket_id)

# ---------------------------------------------------------------------------
# 12. Peak and low demand periods  —  GET /dbproj/report/demand
#     Admin + Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/report/demand', methods=['GET'])
@jwt_required()
@role_required(['admin', 'superadmin'])
def report_demand_endpoint():
    return report_demand()

# ---------------------------------------------------------------------------
# 13. Top spenders by line  —  GET /dbproj/report/top_spenders
#     Admin + Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/report/top_spenders', methods=['GET'])
@jwt_required()
@role_required(['admin', 'superadmin'])
def report_top_spenders_endpoint():
    return report_top_spenders()

# ---------------------------------------------------------------------------
# 14. Monthly report  —  GET /dbproj/report/monthly
#     Admin + Super Admin
# ---------------------------------------------------------------------------

@app.route('/dbproj/report/monthly', methods=['GET'])
@jwt_required()
@role_required(['admin', 'superadmin'])
def report_monthly_endpoint():
    return report_monthly()

# ---------------------------------------------------------------------------
# 15. Get notices  —  GET /dbproj/notices
#     Customer
# ---------------------------------------------------------------------------
 
@app.route('/dbproj/notices', methods=['GET'])
@jwt_required()
@role_required('customer')
def get_notices_endpoint():
    return get_notices()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Logging setup
    logging.basicConfig(filename='metro_mondego.log')
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s', '%H:%M:%S')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # CLI arguments
    parser = argparse.ArgumentParser(description='Metro Mondego REST API')
    parser.add_argument(
        '--setup',
        action='store_true',
        help='Drop and recreate the database schema + seed data'
    )
    args = parser.parse_args()

    if args.setup:
        setup_database()

    # Verify DB is ready before starting
    logger.info('Checking database setup...')
    with app.app_context():
        check_database_setup()

    host = '127.0.0.1'
    port = 8080
    logger.info(f'Starting Metro Mondego API on http://{host}:{port}')
    app.run(host=host, port=port, threaded=True)
