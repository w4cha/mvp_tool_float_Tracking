import os
from flask import Flask, redirect, render_template, request, flash, abort, url_for, make_response
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

# Project imports
from forms import RegistrationForm, LoginForm
from config import config_dict
from filters import local_time, init_app
from models import db, User, VehicleTelemetry, SystemConfig, Vehicle

# Initialize extensions
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    
    # Determine config from environment (Defaults to production for Render)
    env = os.environ.get('FLASK_ENV', 'production')
    app.config.from_object(config_dict[env])
    
    # Middleware for Render's Load Balancer (Fixes HTTPS and Redirects)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Initialize extensions with app context
    init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    return app

app = create_app()
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.after_request
def add_header(response):
    # Disable cache for dynamic content, allow for static files
    if not request.path.startswith('/static'):
        response.cache_control.no_store = True
    return response

# --- ROUTES ---

@app.route("/", methods=["GET"])
def main():
    return redirect(url_for("dashboard"))

@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    all_vehicles = VehicleTelemetry.query.join(Vehicle).options(
        joinedload(VehicleTelemetry.parent_vehicle)
    ).order_by(desc(VehicleTelemetry.speed)).all()
    return render_template("main.html", vehicles=all_vehicles)

@app.route("/reload_table", methods=["GET"])
@login_required
def reload_dashboard():
    search = request.args.get("search")
    query = VehicleTelemetry.query.join(Vehicle)
    
    if search:
        query = query.filter(Vehicle.vehicle_id.ilike(f"%{search.upper()}%"))
        
    all_vehicles = query.options(
        joinedload(VehicleTelemetry.parent_vehicle)
    ).order_by(desc(VehicleTelemetry.speed)).all()
    
    return render_template("partials/vehicle_rows.html", vehicles=all_vehicles)

@app.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Has cerrado sesión correctamente.", "success")
    
    response = make_response("", 200)
    response.headers['HX-Redirect'] = url_for('login')
    return response

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(user_email=str(form.email.data).upper()).first()
        if user and user.active_user and check_password_hash(user.user_password, form.password.data):
            login_user(user)
            flash("Sesión iniciada exitosamente", "success")
            return redirect(url_for('user', username=user.user_name))
        
        flash("Email o contraseña incorrectos", "error")
        return redirect(url_for('login'))

    return render_template("login.html", form=form)

@app.route("/regist", methods=["GET", "POST"])
def regist():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            user_name=str(form.username.data).upper(),
            user_email=str(form.email.data).upper(),
            user_password=hashed_password,
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Tu cuenta ha sido creada. ¡Ya puedes iniciar sesión!', 'success')
        return redirect(url_for('login'))
        
    return render_template("regist.html", form=form)

@app.route("/user/<username>", methods=["GET"])
@login_required
def user(username):
    user_to_view = User.query.filter_by(user_name=username).first_or_404()
    
    if current_user.user_role.name != 'ADMIN' and current_user.user_name != username:
        abort(403)

    found_users = []
    if current_user.user_role.name == 'ADMIN':
        search_query = request.args.get('q', '')
        if search_query:
            found_users = User.query.filter(User.user_name.ilike(f"%{search_query}%")).all()

    config = SystemConfig.query.first()
    worker_status = config.worker_enabled if config else True

    return render_template("user.html", 
                         user=user_to_view, 
                         found_users=found_users, 
                         worker_status=worker_status)

@app.route("/delete_user", methods=["POST"])
@login_required
def delete_user():
    if current_user.user_role.name != 'ADMIN': 
        abort(403)
    
    user_id = request.form.get('user_id')
    target_user = User.query.get(user_id)
    if target_user:
        target_user.active_user = not target_user.active_user
        db.session.commit()
        status = 'activada' if target_user.active_user else 'desactivada'
        flash(f"Cuenta usuario {target_user.user_name} {status}", "success")
        
    return redirect(request.referrer or url_for('user', username=current_user.user_name))

@app.route("/toggle_worker", methods=["POST"])
@login_required
def toggle_worker():
    if current_user.user_role.name != 'ADMIN':
        abort(403)
    
    config = SystemConfig.query.first()
    if not config:
        config = SystemConfig(worker_enabled=True)
        db.session.add(config)
    
    config.worker_enabled = not config.worker_enabled
    db.session.commit()
    
    status = "iniciado" if config.worker_enabled else "detenido"
    flash(f"El consumidor de telemetría ha sido {status}.", "info")
    return redirect(request.referrer or url_for('user', username=current_user.user_name))

if __name__ == "__main__":
    # Local dev entry point
    app.run(host='0.0.0.0', port=5000)