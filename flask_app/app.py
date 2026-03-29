# TODO FIX DOCKERFILE STRUCTURE SINCE MODELS.PY WAS MOVED
# ADD IN DETALLE_VEHICULO OPTIONS TO EDIT A VEHICULO INFO (LIKE ADD AN USER OR CHANGE ITS STATUS)
# CREATE BACKGROUND WORK (cron work) TO EXTRACT DATA IN VehicleTelemetryHistoy older than 3 months
# to prevent db cluttering
# more graph options and downloading pdf reports
# create a test suit
# improve looks of login/regist and user profile pages
# PARTITION BY MONTH TO MAKE DELETING OF DATA IN VehicleTelemetry History easier
# maybe global distribution stats

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, redirect, render_template, request, flash, abort, url_for, make_response
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import desc, select
from sqlalchemy.orm import joinedload, contains_eager
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

# Project imports
from forms import RegistrationForm, LoginForm, AnnotationForm, EditVehicleForm, ChangePasswordForm
from config import config_dict
from filters import init_app
sys.path.append(str(Path(__file__).resolve().parent.parent))

from models import db, User, func, VehicleTelemetry, SystemConfig, Vehicle, VehicleAnnotations, Subject, VehicleTelemetryHistory, Driver, VehicleState
from utils.stats_engine import get_monthly_stats
from utils.routes_engine import return_vehicle_routes
# Initialize extensions
login_manager = LoginManager()
login_manager.login_message = "Debes iniciar sesión para acceder al contenido"
login_manager.login_message_category = "info"
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    env = os.environ.get('FLASK_ENV', 'production')
    app.config.from_object(config_dict[env])
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    return app

app = create_app()
login_manager.login_view = "login"


# --- HELPER PARA DATOS DEL DASHBOARD ---
def fetch_dashboard_vehicles(search_query=None, state_vehicle="ALL"):
    """Lógica centralizada para obtener vehículos con su telemetría"""
    stmt = (
        select(VehicleTelemetry)
        .join(Vehicle)
        .options(contains_eager(VehicleTelemetry.parent_vehicle))
    )
    if search_query:
        stmt = stmt.filter(Vehicle.vehicle_id.ilike(f"%{search_query.upper().strip()}%"))
    if state_vehicle != "ALL" and state_vehicle in VehicleState.__members__:
        stmt = stmt.filter(Vehicle.vehicle_state == VehicleState[state_vehicle])
    stmt = stmt.order_by(desc(VehicleTelemetry.speed))
    return db.session.execute(stmt).scalars().all() or []

@login_manager.user_loader
def load_user(user_id):
    # Buscamos al usuario por ID
    user = db.session.get(User, int(user_id))
    
    # Si el usuario no existe O está desactivado, retornamos None
    # Esto provocará que Flask-Login lo trate como "AnonymousUser"
    if user and user.active_user:
        return user
    
    return None

@app.after_request
def add_header(response):
    if not request.path.startswith('/static'):
        response.cache_control.no_store = True
    return response

@app.before_request
def check_user_status():
    if current_user.is_authenticated:
        if not current_user.active_user:
            logout_user()
            flash("Tu cuenta ha sido desactivada. Contacta al administrador.", "error")
            return redirect(url_for('login'))

@app.route("/", methods=["GET"])
def main():
    return redirect(url_for("dashboard"))

@app.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    # Carga inicial de la página completa
    vehicles = fetch_dashboard_vehicles()
    return render_template("dashboard.html", vehicles=vehicles, all_states=VehicleState)

@app.route("/search_vehicle", methods=["GET"])
@login_required
def search_vehicle():
    # HTMX: Devuelve el bloque interno (Stats + Map + Table) al buscar
    search_val = request.args.get("search", "")
    vehicle_state = request.args.get("state", "ALL")
    vehicles = fetch_dashboard_vehicles(search_val, vehicle_state)
    return render_template("partials/dashboard_inner.html", vehicles=vehicles)

@app.route("/reload_table", methods=["GET"])
@login_required
def reload_dashboard():
    # HTMX: Devuelve el bloque interno en la recarga automática (cada 10s)
    search_val = request.args.get("search", "")
    vehicle_state = request.args.get("state", "ALL")
    vehicles = fetch_dashboard_vehicles(search_val, vehicle_state)
    return render_template("partials/dashboard_inner.html", vehicles=vehicles)

@app.route("/detalle/<patente>", methods=["GET", "POST"])
@login_required
def detalle_vehiculo(patente):
    # --- 1. Buscar Vehículo con sus relaciones ---
    stmt = (
        select(Vehicle)
        .filter_by(vehicle_id=patente.upper())
        .options(
            joinedload(Vehicle.current_driver),
            joinedload(Vehicle.telemetry_data)
        )
    )
    vehicle = db.session.execute(stmt).scalar_one_or_none()
    if not vehicle: 
        abort(404)

    # --- 2. Historial de las últimas 3 horas para el Mapa ---
    three_hours_ago = datetime.now() - timedelta(hours=3)
    hist_stmt = (
        select(VehicleTelemetryHistory)
        .filter(
            VehicleTelemetryHistory.vehicle_id == patente.upper(),
            VehicleTelemetryHistory.timestamp >= three_hours_ago
        )
        .order_by(VehicleTelemetryHistory.timestamp.asc())
    )
    history = db.session.execute(hist_stmt).scalars().all()

    subject_filter = request.args.get('subject_filter')
    notes_query = vehicle.annotations_list
    if request.method == "GET" and subject_filter and request.headers.get('HX-Request'):
        if subject_filter != 'ALL':
            notes_query = [n for n in vehicle.annotations_list if n.subject.name == subject_filter]
        return render_template("partials/notes_list.html", 
                                vehicle=vehicle, 
                                notes=notes_query, 
                                subjects=Subject,
                                selected_filter=subject_filter)
    
    edit_form = EditVehicleForm()
    
    drivers = Driver.query.order_by(Driver.name.asc()).all()
    edit_form.driver_id.choices = [('', 'Sin asignar')] + \
                                  [(str(d.id), d.name) for d in drivers] + \
                                  [('NEW', '➕ Registrar Nuevo Conductor...')]

    if request.method == 'GET':
        if vehicle.vehicle_state:
            edit_form.vehicle_state.data = vehicle.vehicle_state.name
        edit_form.driver_id.data = str(vehicle.driver_id) if vehicle.driver_id else ''
    
    # --- 3. Formulario de Anotaciones ---
    form = AnnotationForm()
    if form.validate_on_submit():
        selected_subject = Subject[form.subject.data]
        new_note = VehicleAnnotations(
            vehicle_id=vehicle.id,
            subject=selected_subject,
            comment=form.comment.data
        )
        db.session.add(new_note)
        db.session.commit()
        
        if request.headers.get('HX-Request'):
            return render_template("partials/notes_list.html", 
                                 vehicle=vehicle, 
                                 notes=vehicle.annotations_list, 
                                 subjects=Subject,
                                 selected_filter='ALL')
            
        flash("Nota guardada", "success")
        return redirect(url_for('detalle_vehiculo', patente=patente))

    # --- 4. Procesamiento de Stats Dinámico ---
    bounds = db.session.query(
        func.min(VehicleTelemetryHistory.timestamp),
        func.max(VehicleTelemetryHistory.timestamp)
    ).filter(VehicleTelemetryHistory.vehicle_id == patente.upper()).first()

    first_ts, last_ts = bounds
    data_age_hours = 0
    if first_ts and last_ts:
        data_age_hours = (last_ts - first_ts).total_seconds() / 3600
    
    is_dark = request.cookies.get('theme') == 'dark'
    
    # Page load starts with '1h' speed peaks graph
    graphs, summary = get_monthly_stats(patente, is_dark_mode=is_dark, period='1h')
    all_drivers = Driver.query.order_by(Driver.name.asc()).all()
    
    # Notice we don't calculate routes on standard page load to save compute.
    # We only fetch it when the user switches to 'trayectos' via HTMX!
    
    return render_template(
        "detalle.html", 
        vehicle=vehicle, 
        history=history,
        edit_form=edit_form, 
        form=form, 
        graphs=graphs, 
        summary=summary,
        data_age_hours=data_age_hours, # This limits the select options
        notes=notes_query, 
        subjects=Subject,
        routes=[], # Empty array initially
        selected_filter=subject_filter or 'ALL',
        all_drivers=all_drivers,
        all_states=VehicleState
    )

@app.route("/update_stats/<patente>", methods=["GET"])
@login_required
def update_stats(patente):
    # 1. Gather the HTMX parameters
    graph_type = request.args.get('graph-type', 'max_speed')
    period = request.args.get('period-select', '1h')
    
    is_dark = request.cookies.get('theme') == 'dark'
    
    # 2. Re-calculate data age so selectors remain accurate after swaps
    bounds = db.session.query(
        func.min(VehicleTelemetryHistory.timestamp),
        func.max(VehicleTelemetryHistory.timestamp)
    ).filter(VehicleTelemetryHistory.vehicle_id == patente.upper()).first()

    first_ts, last_ts = bounds
    data_age_hours = 0
    if first_ts and last_ts:
        data_age_hours = (last_ts - first_ts).total_seconds() / 3600

    # 3. ROUTER: Decide between routes or graphs
    if graph_type == 'trayectos':
        # Default to 6h if the user selected 'trayectos' and was on '1h'
        if period == '1h':
            period = '6h'
        all_routes = return_vehicle_routes(period=period, plate=patente)
        
        return render_template("partials/routes_render.html", 
                               vehicle=Vehicle.query.filter_by(vehicle_id=patente.upper()).first_or_404(),
                               routes=all_routes, 
                               period=period,
                               data_age_hours=data_age_hours)
    
    else:
        # Standard Graphs Mode
        graphs, summary = get_monthly_stats(patente, is_dark_mode=is_dark, period=period)
        
        return render_template("partials/stats_render.html", 
                               vehicle=Vehicle.query.filter_by(vehicle_id=patente.upper()).first_or_404(),
                               graphs=graphs, 
                               summary=summary, 
                               period=period,
                               active_type=graph_type,
                               data_age_hours=data_age_hours)

@app.route('/vehiculo/<patente>/edit', methods=['POST'])
@login_required
def edit_vehicle(patente):
    vehicle = Vehicle.query.filter_by(vehicle_id=patente.upper()).first_or_404()
    form = EditVehicleForm()
    
    # Re-poblar opciones para validación
    drivers = Driver.query.all()
    form.driver_id.choices = [('', 'Sin asignar'), ('NEW', 'NEW')] + [(str(d.id), d.name) for d in drivers]

    if form.validate_on_submit():
        # 1. Manejo de Conductor
        if form.driver_id.data == "NEW":
            if form.new_driver_name.data:
                new_driver = Driver(
                    name=form.new_driver_name.data,
                    driver_email=form.new_driver_email.data,
                    phone=form.new_driver_phone.data
                )
                db.session.add(new_driver)
                db.session.flush()
                vehicle.driver_id = new_driver.id
        else:
            vehicle.driver_id = int(form.driver_id.data) if form.driver_id.data else None

        # 2. Manejo de Estado (Enum)
        vehicle.vehicle_state = VehicleState[form.vehicle_state.data]
        
        db.session.commit()
        response = make_response(render_template('partials/vehicle_info_card.html', vehicle=vehicle))
        response.headers['HX-Trigger'] = 'closeModal' # Disparamos evento JS para cerrar
        return response
    
    return render_template('partials/modal_edit_form.html', edit_form=form, vehicle=vehicle), 422

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        email_val = str(form.email.data).upper().strip()
        stmt = select(User).filter_by(user_email=email_val)
        user = db.session.execute(stmt).scalar_one_or_none()
        
        if user and check_password_hash(user.user_password, form.password.data):
            login_user(user)
            flash("Sesión iniciada exitosamente", "success")
            return redirect(url_for('dashboard'))
        
        flash("Email o contraseña incorrectos", "error")
        return redirect(url_for('login'))

    return render_template("login.html", form=form)

@app.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Has cerrado sesión correctamente.", "success")
    
    response = make_response("", 200)
    response.headers['HX-Redirect'] = url_for('login')
    return response

@app.route("/regist", methods=["GET", "POST"])
def regist():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            user_name=str(form.username.data).upper().strip(),
            user_email=str(form.email.data).upper().strip(),
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
    stmt = select(User).filter_by(user_name=username.upper())
    user_to_view = db.session.execute(stmt).scalar_one_or_none()
    password_form = ChangePasswordForm()
    
    if not user_to_view:
        abort(404)
    
    if current_user.user_role.name != 'ADMIN' and current_user.user_name != username.upper():
        abort(403)

    found_users = []
    if current_user.user_role.name == 'ADMIN':
        search_query = request.args.get('q', '').upper()
        if search_query:
            stmt_search = select(User).filter(User.user_name.ilike(f"%{search_query}%"))
            found_users = db.session.execute(stmt_search).scalars().all()
        if request.headers.get('HX-Request'):
            return render_template("partials/user_table_row.html", found_users=found_users)


    config_stmt = select(SystemConfig)
    config = db.session.execute(config_stmt).scalar_one_or_none()
    worker_status = config.worker_enabled if config else True

    return render_template("user.html", 
                         user=user_to_view, 
                         found_users=found_users, 
                         worker_status=worker_status,
                         password_form=password_form)

@app.route("/delete_user", methods=["POST"])
@login_required
def delete_user():
    if current_user.user_role.name != 'ADMIN': 
        abort(403)
    
    u_id = request.form.get('user_id')
    target_user = db.session.get(User, u_id)
    
    if target_user:
        target_user.active_user = not getattr(target_user, 'active_user', True)
        db.session.commit()
        status = 'activada' if target_user.active_user else 'desactivada'
        flash(f"Cuenta usuario {target_user.user_name} {status}", "success")
        
    return redirect(request.referrer or url_for('user', username=current_user.user_name))

@app.route("/change_password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        # Actualizamos la contraseña del usuario logueado
        current_user.user_password = generate_password_hash(form.new_password.data)
        db.session.commit()
        flash("Tu contraseña ha sido actualizada correctamente.", "success")
    else:
        # Si hay errores de validación (ej: contraseñas no coinciden)
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error en {getattr(form, field).label.text}: {error}", "error")
                
    return redirect(url_for('user', username=current_user.user_name))

@app.route("/toggle_worker", methods=["POST"])
@login_required
def toggle_worker():
    if current_user.user_role.name != 'ADMIN':
        abort(403)
    
    stmt = select(SystemConfig)
    config = db.session.execute(stmt).scalar_one_or_none()
    
    if not config:
        config = SystemConfig(worker_enabled=True)
        db.session.add(config)
    
    config.worker_enabled = not config.worker_enabled
    db.session.commit()
    
    status = "iniciado" if config.worker_enabled else "detenido"
    flash(f"El consumidor de telemetría ha sido {status}.", "info")
    return redirect(request.referrer or url_for('user', username=current_user.user_name))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)