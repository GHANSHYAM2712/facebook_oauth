from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, PendingWABACredentials, User

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('admin_bp.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Look up user in the DB (for simpler testing, if no user exists we'll create a default one below)
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            session['logged_in'] = True
            session['username'] = username
            flash('Logged in successfully.', 'success')
            next_url = request.args.get('next') or url_for('admin_bp.pending_credentials')
            return redirect(next_url)
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html')

@admin_bp.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('admin_bp.login'))

@admin_bp.route('/pending-credentials', methods=['GET'])
@login_required
def pending_credentials():
    # Query all rows where status == 'pending' ordered by created_at desc
    credentials = PendingWABACredentials.query.filter_by(status='pending').order_by(PendingWABACredentials.created_at.desc()).all()
    # Also fetch other statuses so we have an audit trail (added/failed)
    history = PendingWABACredentials.query.filter(PendingWABACredentials.status != 'pending').order_by(PendingWABACredentials.created_at.desc()).all()
    
    return render_template(
        'pending_credentials.html',
        credentials=credentials,
        history=history
    )

@admin_bp.route('/pending-credentials/<int:cred_id>/update-status', methods=['POST'])
@login_required
def update_status(cred_id):
    cred = db.session.get(PendingWABACredentials, cred_id)
    if not cred:
        return jsonify({'success': False, 'error': 'Credential record not found.'}), 404
        
    status = request.form.get('status') or (request.json or {}).get('status')
    if status not in ['pending', 'added', 'failed']:
        return jsonify({'success': False, 'error': 'Invalid status choice.'}), 400
        
    cred.status = status
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({'success': True, 'id': cred.id, 'status': cred.status})
        
    flash(f"Credential status updated to '{status}'.", 'success')
    return redirect(url_for('admin_bp.pending_credentials'))
