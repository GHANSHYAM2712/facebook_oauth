from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class PendingWABACredentials(db.Model):
    __tablename__ = 'pending_waba_credentials'

    id = db.Column(db.Integer, primary_key=True)
    waba_id = db.Column(db.String(100), nullable=True)
    phone_number_id = db.Column(db.String(100), nullable=True)
    access_token = db.Column(db.Text, nullable=True)
    display_phone_number = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'added', 'failed'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    error_message = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'waba_id': self.waba_id,
            'phone_number_id': self.phone_number_id,
            'access_token': self.access_token,
            'display_phone_number': self.display_phone_number,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'error_message': self.error_message
        }

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
