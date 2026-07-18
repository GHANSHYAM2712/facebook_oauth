import os
import requests
import psycopg2
from flask import Blueprint, render_template, request, jsonify

signup_bp = Blueprint('signup_bp', __name__, url_prefix='/auth')

@signup_bp.route('/embedded-signup', methods=['GET'])
def embedded_signup():
    meta_app_id = os.getenv('META_APP_ID', '')
    meta_config_id = os.getenv('META_CONFIG_ID', '')
    meta_version = os.getenv('META_API_VERSION', 'v25.0')
    
    # Retrieve environment variables for PostgreSQL Database
    db_host = os.getenv('DB_HOST')
    db_port = os.getenv('DB_PORT', '5432')
    db_user = os.getenv('DB_USER')
    db_pass = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    
    organizations = []
    conn = None
    if all([db_host, db_user, db_pass, db_name]):
        try:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_pass,
                database=db_name
            )
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM organizations ORDER BY name;")
            rows = cursor.fetchall()
            organizations = [{'id': str(row[0]), 'name': row[1]} for row in rows]
            cursor.close()
        except Exception as e:
            # Resilient fallback, print/log warning but do not crash the view
            print(f"Warning: Could not fetch organizations for dropdown: {e}")
        finally:
            if conn:
                conn.close()

    return render_template(
        'embedded_signup.html',
        META_APP_ID=meta_app_id,
        CONFIG_ID=meta_config_id,
        META_API_VERSION=meta_version,
        organizations=organizations
    )

@signup_bp.route('/exchange-token', methods=['POST'])
def exchange_token():
    data = request.get_json() or {}
    code = data.get('code')
    waba_id = data.get('waba_id')
    phone_number_id = data.get('phone_number_id')
    organization_id = data.get('organization_id')
    
    if not code:
        return jsonify({'success': False, 'error': 'Authorization code is required.'}), 400
    if not waba_id:
        return jsonify({'success': False, 'error': 'waba_id is required.'}), 400
    if not phone_number_id:
        return jsonify({'success': False, 'error': 'phone_number_id is required.'}), 400

    # Retrieve environment variables for Meta Graph API
    meta_app_id = os.getenv('META_APP_ID')
    meta_app_secret = os.getenv('META_APP_SECRET')

    if not meta_app_id or not meta_app_secret:
        return jsonify({'success': False, 'error': 'Server environment is misconfigured. META_APP_ID or META_APP_SECRET is missing.'}), 500

    # Retrieve environment variables for external Whatomate PostgreSQL Database
    db_host = os.getenv('DB_HOST')
    db_port = os.getenv('DB_PORT', '5432')
    db_user = os.getenv('DB_USER')
    db_pass = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    target_org_name = os.getenv('TARGET_ORGANIZATION_NAME', 'Shiva Developers')

    if not all([db_host, db_user, db_pass, db_name]):
        return jsonify({'success': False, 'error': 'Database environment is misconfigured. Missing DB_HOST, DB_USER, DB_PASSWORD, or DB_NAME.'}), 500

    conn = None
    try:
        # Step 1: Exchange code for user access token via Meta Graph API
        meta_version = os.getenv('META_API_VERSION', 'v25.0')
        
        token_url = f'https://graph.facebook.com/{meta_version}/oauth/access_token'
        token_params = {
            'client_id': meta_app_id,
            'client_secret': meta_app_secret,
            'code': code
        }
        
        token_response = requests.get(token_url, params=token_params)
        if token_response.status_code != 200:
            error_data = token_response.json().get('error', {})
            raise Exception(f"Failed to exchange code: {error_data.get('message', 'Unknown error')}")
            
        token_data = token_response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            raise Exception("No access_token returned in the OAuth exchange.")

        # Step 2: Fetch the display phone number using phone_number_id (fallback to raw phone_number_id if the call fails)
        display_phone_number = phone_number_id
        try:
            phone_url = f'https://graph.facebook.com/{meta_version}/{phone_number_id}'
            headers = {'Authorization': f'Bearer {access_token}'}
            phone_params = {'fields': 'display_phone_number'}
            phone_response = requests.get(phone_url, headers=headers, params=phone_params)
            if phone_response.status_code == 200:
                phone_info = phone_response.json()
                display_phone_number = phone_info.get('display_phone_number') or phone_number_id
        except Exception:
            display_phone_number = phone_number_id

        # Step 4: Establish psycopg2 connection to external Whatomate database
        try:
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_pass,
                database=db_name
            )
            cursor = conn.cursor()
        except Exception as db_conn_err:
            raise Exception(f"Failed to connect to the external Whatomate PostgreSQL database: {db_conn_err}")

        # Step 5: Query organizations table to verify and fetch ID dynamically
        try:
            if organization_id:
                cursor.execute("SELECT id FROM organizations WHERE id = %s;", (organization_id,))
            else:
                cursor.execute("SELECT id FROM organizations WHERE name = %s;", (target_org_name,))
            org = cursor.fetchone()
            if not org:
                raise Exception("Target organization not found inside the 'organizations' table.")
            organization_id = org[0]
        except Exception as org_err:
            raise Exception(f"Error querying organization ID: {org_err}")

        # Step 6: Dynamic Schema Resolution - Find target accounts table
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        target_table = None
        whatsapp_candidates = ['whatsapp_accounts', 'accounts', 'whatsapp_credentials', 'whatsapp_profiles']
        for candidate in whatsapp_candidates:
            if candidate in tables:
                target_table = candidate
                break
        
        if not target_table:
            # Fallback
            target_table = 'whatsapp_accounts'

        import uuid

        # Step 7: Dynamic Column Mapping - Identify columns in target table
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s;
        """, (target_table,))
        columns = [row[0] for row in cursor.fetchall()]

        # Map matching columns
        waba_col = 'whatsapp_business_account_id' if 'whatsapp_business_account_id' in columns else (
            'waba_id' if 'waba_id' in columns else (
                'whatsapp_business_id' if 'whatsapp_business_id' in columns else (
                    'business_id' if 'business_id' in columns else 'whatsapp_business_account_id'
                )
            )
        )
        phone_col = 'phone_number_id' if 'phone_number_id' in columns else ('phone_id' if 'phone_id' in columns else 'whatsapp_phone_number_id')
        token_col = 'access_token' if 'access_token' in columns else 'token'
        org_col = 'organization_id' if 'organization_id' in columns else 'org_id'

        # Validate that the mapped columns actually exist in the table (fallback checking)
        missing_columns = [col for col in [org_col, waba_col, phone_col, token_col] if col not in columns]
        if missing_columns:
            print(f"Warning: Mapped columns {missing_columns} not explicitly found in table '{target_table}'.")

        # Step 8: check if a row already exists for this organization_id
        cursor.execute(f"SELECT id FROM {target_table} WHERE {org_col} = %s;", (organization_id,))
        exists_row = cursor.fetchone()

        # Step 9: Perform UPDATE or INSERT SQL operation (UPSERT)
        if exists_row:
            # UPDATE existing row
            update_query = f"""
                UPDATE {target_table}
                SET {waba_col} = %s, {phone_col} = %s, {token_col} = %s, status = 'active', updated_at = NOW()
                WHERE {org_col} = %s;
            """
            cursor.execute(update_query, (waba_id, phone_number_id, access_token, organization_id))
        else:
            # INSERT new clean profile row with generated UUID for primary key
            new_uuid = str(uuid.uuid4())
            status_clause = ", status" if "status" in columns else ""
            status_val = ", 'active'" if "status" in columns else ""
            
            # Check for standard metadata columns and populate them
            meta_cols = []
            meta_vals = []
            if "created_at" in columns:
                meta_cols.append("created_at")
                meta_vals.append("NOW()")
            if "updated_at" in columns:
                meta_cols.append("updated_at")
                meta_vals.append("NOW()")
                
            meta_cols_str = ", " + ", ".join(meta_cols) if meta_cols else ""
            meta_vals_str = ", " + ", ".join(meta_vals) if meta_vals else ""

            insert_query = f"""
                INSERT INTO {target_table} (id, {org_col}, {waba_col}, {phone_col}, {token_col}{status_clause}{meta_cols_str})
                VALUES (%s, %s, %s, %s, %s{status_val}{meta_vals_str});
            """
            cursor.execute(insert_query, (new_uuid, organization_id, waba_id, phone_number_id, access_token))

        # Commit transactions
        conn.commit()
        cursor.close()

        return jsonify({
            'success': True,
            'organization_id': organization_id,
            'display_phone_number': display_phone_number
        })

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    finally:
        if conn:
            conn.close()

@signup_bp.route('/oauth-callback', methods=['GET'])
def oauth_callback():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Authorization Successful</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                background-color: #121212;
                color: #e0e0e0;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
            }
            .card {
                background-color: #1e1e1e;
                border-radius: 8px;
                padding: 40px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                text-align: center;
                max-width: 400px;
            }
            h1 { color: #4CAF50; margin-top: 0; }
            p { font-size: 1.1em; line-height: 1.5; color: #b0b0b0; }
            .btn {
                background-color: #3b5998;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 1em;
                border-radius: 4px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin-top: 15px;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Authorization Successful!</h1>
            <p>Your WhatsApp Embedded Signup process is complete. You may safely close this window to return to the onboarding dashboard.</p>
            <button onclick="window.close()" class="btn">Close Window</button>
        </div>
    </body>
    </html>
    """
