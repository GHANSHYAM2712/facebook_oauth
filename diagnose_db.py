import os
import sys
import psycopg2
from dotenv import load_dotenv

# Load active environment variables
load_dotenv()

def print_status(label, text, color_code="\033[94m"):
    """Format status logging to the terminal with custom ANSI colors"""
    reset_code = "\033[0m"
    print(f"{color_code}[{label}]{reset_code} {text}")

def diagnose():
    print("=" * 60)
    print(" WHATOMATE DATABASE INTROSPECTION & DIAGNOSTIC UTILITY ")
    print("=" * 60)

    # 1. Load database parameters
    db_host = os.getenv('DB_HOST')
    db_port = os.getenv('DB_PORT', '5432')
    db_user = os.getenv('DB_USER')
    db_pass = os.getenv('DB_PASSWORD')
    db_name = os.getenv('DB_NAME')
    target_org = os.getenv('TARGET_ORGANIZATION_NAME', 'Shiva Developers')

    print_status("CONFIG", f"Target Organization: '{target_org}'")
    print_status("CONFIG", f"Host: {db_host} | Port: {db_port} | Database: {db_name} | User: {db_user}")

    if not all([db_host, db_user, db_pass, db_name]):
        print_status("ERROR", "Missing database credentials in .env file. Please check your config.", "\033[91m")
        sys.exit(1)

    # 2. Establish PostgreSQL connection
    conn = None
    try:
        print_status("CONN", "Establishing connection to PostgreSQL...")
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_pass,
            database=db_name
        )
        print_status("SUCCESS", "Connected to the database successfully!", "\033[92m")
    except Exception as e:
        print_status("ERROR", f"Connection failed: {e}", "\033[91m")
        print("\nSuggestions for Docker setup:")
        print("1. If running Flask on host and DB in Docker, ensure container port 5432 is mapped to host.")
        print("2. Verify that host name matches 'localhost' or '127.0.0.1'.")
        print("3. Check firewall or security settings on the PostgreSQL Docker instance.")
        sys.exit(1)

    try:
        cursor = conn.cursor()

        # 3. Query Organizations Table
        print_status("SCHEMA", "Querying 'organizations' table...")
        try:
            cursor.execute("SELECT id, name FROM organizations WHERE name = %s;", (target_org,))
            org = cursor.fetchone()
            if org:
                print_status("SUCCESS", f"Organization '{target_org}' found! ID: {org[0]}", "\033[92m")
                org_id = org[0]
            else:
                print_status("WARNING", f"Organization '{target_org}' NOT found.", "\033[93m")
                # List existing organizations to help the user configure
                cursor.execute("SELECT id, name FROM organizations LIMIT 5;")
                existing_orgs = cursor.fetchall()
                if existing_orgs:
                    print("\nAvailable organizations in database:")
                    for row in existing_orgs:
                        print(f" - ID: {row[0]} | Name: '{row[1]}'")
                    print("\nPlease update TARGET_ORGANIZATION_NAME in your .env file to match one of the above.")
                else:
                    print("\nNo organizations exist in the 'organizations' table currently.")
        except Exception as e:
            print_status("ERROR", f"Failed to query 'organizations' table: {e}", "\033[91m")

        # 4. Introspect active tables in the public schema
        print_status("SCHEMA", "Retrieving active tables inside 'public' schema...")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        tables = [row[0] for row in cursor.fetchall()]
        print_status("SCHEMA", f"Found {len(tables)} tables: {', '.join(tables)}")

        # 5. Look for WhatsApp-related tables
        target_table = None
        whatsapp_candidates = ['whatsapp_accounts', 'accounts', 'whatsapp_credentials', 'whatsapp_profiles']
        
        for candidate in whatsapp_candidates:
            if candidate in tables:
                target_table = candidate
                break
                
        if target_table:
            print_status("SUCCESS", f"Selected WhatsApp accounts target table: '{target_table}'", "\033[92m")
        else:
            # If no matches, fall back to first table that might relate, or suggest creating one
            matching = [t for t in tables if 'whatsapp' in t or 'account' in t]
            if matching:
                target_table = matching[0]
                print_status("WARNING", f"No standard candidate table found. Selecting similar table '{target_table}'...", "\033[93m")
            else:
                print_status("ERROR", "No whatsapp-related tables found in schema. Listing columns of default fallback 'whatsapp_accounts'.", "\033[91m")
                target_table = 'whatsapp_accounts'

        # 6. Retrieve columns and map them
        print_status("SCHEMA", f"Inspecting columns of table '{target_table}'...")
        try:
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s;
            """, (target_table,))
            columns_data = cursor.fetchall()
            columns = [row[0] for row in columns_data]
            
            print_status("SCHEMA", f"Columns found in '{target_table}':")
            for col, dtype in columns_data:
                print(f"  - {col} ({dtype})")
                
            # Column mapping checks
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
            
            print("\n" + "-" * 40)
            print(" DYNAMIC COLUMN MAPPING SUMMARY ")
            print("-" * 40)
            print(f" * Organization ID Mapping   => Column: '{org_col}' " + (f"[\033[92mMATCHED\033[0m]" if org_col in columns else "[\033[91mMISSING\033[0m]"))
            print(f" * WABA ID Mapping           => Column: '{waba_col}' " + (f"[\033[92mMATCHED\033[0m]" if waba_col in columns else "[\033[91mMISSING\033[0m]"))
            print(f" * Phone Number ID Mapping   => Column: '{phone_col}' " + (f"[\033[92mMATCHED\033[0m]" if phone_col in columns else "[\033[91mMISSING\033[0m]"))
            print(f" * Access Token Mapping      => Column: '{token_col}' " + (f"[\033[92mMATCHED\033[0m]" if token_col in columns else "[\033[91mMISSING\033[0m]"))
            print("-" * 40)

        except Exception as e:
            print_status("ERROR", f"Failed to retrieve column schemas for '{target_table}': {e}", "\033[91m")

        cursor.close()
    except Exception as e:
        print_status("ERROR", f"Cursor diagnostic error: {e}", "\033[91m")
    finally:
        if conn:
            conn.close()
            print_status("CONN", "Database connection closed.")
            
    print("=" * 60)

if __name__ == '__main__':
    diagnose()
