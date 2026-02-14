import os
from dotenv import load_dotenv
from flask import request
from flask import Flask, redirect, render_template, request, send_file, session, flash, abort, url_for, make_response
from flask_app.forms import RegistrationForm, LoginForm
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_app.config import config_dict
from flask_app.filters import local_time, init_app
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
# bycrypt is similar to werkzeug but slower thus harder to bruteforce
# from flask_bcrypt import Bcrypt
from werkzeug.security import check_password_hash, generate_password_hash
from flask_app.models import db, User, VehicleTelemetry, SystemConfig, UserRole, Vehicle

load_dotenv()
login_manager = LoginManager()
crsf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    
    # run with $env:FLASK_ENV="development"; python app.py
    # to load development mode
    # Determine which config to use from environment
    env = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config_dict[env])
    init_app(app)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    crsf.init_app(app)
    
    return app

app = create_app()


login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    # Flask-Login passes a string ID; we convert to int for the DB lookup
    return User.query.get(int(user_id))

# this needs to change
@app.after_request
def add_header(response):
    # Only disable cache if it's NOT a static file (CSS/JS/Images)
    if not request.path.startswith('/static'):
        response.cache_control.no_store = True
        response.cache_control.max_age = 0
    return response

@app.route("/", methods=["GET"])
def main():
    return redirect(url_for("dashboard"))

@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    if request.method == "GET":
        all_vehicles = VehicleTelemetry.query.join(Vehicle).options(joinedload(VehicleTelemetry.parent_vehicle)).order_by(desc(VehicleTelemetry.speed)).all()
        return render_template("main.html", vehicles=all_vehicles)
    return "Metodo invalido", 405

@app.route("/reload_table", methods=["GET"])
@login_required
def reload_dashboard():
    if request.method == "GET":
        if (was_filtered := request.args.get("search")) and was_filtered:
            all_vehicles = VehicleTelemetry.query.join(Vehicle).filter(Vehicle.vehicle_id.ilike(f"%{was_filtered.upper()}%")).options(joinedload(VehicleTelemetry.parent_vehicle)).order_by(desc(VehicleTelemetry.speed)).all()
        else:
            all_vehicles = VehicleTelemetry.query.join(Vehicle).options(joinedload(VehicleTelemetry.parent_vehicle)).order_by(desc(VehicleTelemetry.speed)).all()
        return render_template("partials/vehicle_rows.html", vehicles=all_vehicles)
    return "Metodo invalido", 405

# this one is goin to need type_user=get_current_pass.type_user
# for promoting / soft delete users

@app.route("/logout", methods=["POST"])
def logout():
    if request.method == "POST":
        if current_user.is_authenticated:
            logout_user()
            flash("Has cerrado sesión correctamente.", "success")
        response = make_response("", 200)
        response.headers['HX-Redirect'] = url_for('login')
        return response
    return "Metodo invalido", 405

@app.route("/login", methods=['GET', 'POST'])
def login():
    if not current_user.is_authenticated:
        if request.method == "POST":
            form = LoginForm()
            if form.validate_on_submit():
                email = form.email.data
                password = form.password.data
                get_current_pass = User.query.filter_by(user_email=str(email).upper()).first()
                # active user comes from the mixin
                if get_current_pass and get_current_pass.active_user:
                    if check_password_hash(get_current_pass.user_password, password):
                        # no next injection because no next allowed
                        # it is a simple mvp after all
                        login_user(get_current_pass)
                        flash("sesion iniciada exitosamente", "success")
                        return redirect(url_for('user', username=get_current_pass.user_name))
                    flash("contraseña incorrecta", "error")
                    return redirect(url_for('login'))
                flash("email incorrecto", "error")
                return redirect(url_for("login")) 
            return render_template("regist.html", form=form) 
        elif request.method == "GET":
            form = LoginForm()
            return render_template("login.html", form=form)
        return "Metodo invalido", 405
    return redirect(url_for('dashboard'))

    
@app.route("/regist", methods=["GET", "POST"])
def regist():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == "POST":
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
    elif request.method == "GET":
        form = RegistrationForm()
        return render_template('regist.html', form=form)
    return "Metodo invalido", 405

@app.route("/user/<username>", methods=["GET"])
@login_required
def user(username):
    if request.method == "GET":
        user_to_view = User.query.filter_by(user_name=username).first_or_404()
        
        if current_user.user_role.name != 'ADMIN':
            if current_user.user_name != username:
                abort(403)
            # an non admin user should see its profile
            return render_template("user.html", user=user_to_view, found_users=[], worker_status=False)

        # Search Logic
        search_query = request.args.get('q', '')
        found_users = []
        if current_user.user_role.name == 'ADMIN' and search_query:
            found_users = User.query.filter(User.user_name.ilike(f"%{search_query}%")).all()

        # Get Worker Status for the Admin Panel
        config = SystemConfig.query.first()
        worker_status = config.worker_enabled if config else True

        return render_template("user.html", 
                            user=user_to_view, 
                            found_users=found_users, 
                            worker_status=worker_status)
    return "Metodo invalido", 405

# rank up/down uer for future inplementation
@app.route("/delete_user", methods=["POST"])
@login_required
def delete_user():
    if current_user.user_role.name != 'ADMIN': 
        abort(403)
    user_id = request.form.get('user_id')
    user = User.query.get(user_id)
    if user:
        user.active_user = False if user.active_user else True
        db.session.commit()
        flash(f"Cuenta usuario {user.user_name} {'activada' if user.active_user else 'desactivada'}", "success")
        
    return redirect(request.referrer or url_for('user', username=current_user.username))

@app.route("/search_vehicle", methods=["GET"])
@login_required
def search_vehicle():
    if request.method == "GET":
        search_term = request.args.get("search", "")
        # Case-insensitive search using SQLAlchemy
        results = VehicleTelemetry.query.join(Vehicle).filter(Vehicle.vehicle_id.ilike(f"%{search_term}%")).options(joinedload(VehicleTelemetry.parent_vehicle)).order_by(desc(VehicleTelemetry.speed)).all()
        return render_template("partials/vehicle_rows.html", vehicles=results)
    return "Metodo no valido", 405

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
    print(f"🚀 Server starting in debug = {app.config.get('DEBUG')}")
    # CANGE TO GUNICORN FOR FUTURE REALESE
    app.run(host='0.0.0.0', port=5000)