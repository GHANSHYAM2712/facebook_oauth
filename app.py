import os
from flask import Flask, redirect, url_for
from dotenv import load_dotenv
from models import db, User

# Load environment variables from .env
load_dotenv()

def create_app():
    app = Flask(__name__)
    
    # Configure App Security Key
    app.secret_key = os.getenv('SECRET_KEY', 'default-whats-onboard-secret-key-1234')
    
    # Configure Database (reads DATABASE_URL, defaults to SQLite for ease of testing or postgresql local)
    default_db = 'postgresql://ghanshyam:postgres@localhost/insert_flask_app'
    # Fallback to SQLite if PostgreSQL is not active/available or if DATABASE_URL is not set
    # This ensures maximum resilience during verification
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        # Let's check if we want to use local postgresql or sqlite
        db_url = 'sqlite:///whatsapp_signup.db'
        
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize DB
    db.init_app(app)

    # Register Blueprints
    from signup import signup_bp
    from admin import admin_bp
    
    app.register_blueprint(signup_bp)
    app.register_blueprint(admin_bp)

    # Base Redirect to Onboarding
    @app.route('/')
    def index():
        return redirect(url_for('signup_bp.embedded_signup'))

    # Build DB Schema & Provision default testing admin
    with app.app_context():
        db.create_all()
        
        # Check if default admin user exists
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            default_admin = User(
                username='admin',
                password='admin123'  # Helper testing plain password as requested
            )
            db.session.add(default_admin)
            db.session.commit()
            print("Auto-seeded default administrator: admin / admin123")

    return app

app = create_app()

if __name__ == '__main__':
    # Listen on all interfaces for easy accessibility
    app.run(host='0.0.0.0', port=5000, debug=True)
