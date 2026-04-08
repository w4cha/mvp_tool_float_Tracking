from flask import Blueprint, render_template, request, abort, make_response, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import desc, select, func
from sqlalchemy.orm import joinedload, contains_eager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from models import db, Vehicle, VehicleTelemetry, VehicleTelemetryHistory, Driver, Subject, VehicleAnnotations, VehicleState
from forms import AnnotationForm, EditVehicleForm
from utils.stats_engine import get_monthly_stats
from utils.routes_engine import return_vehicle_routes

fleet_bp = Blueprint('fleet', __name__)

def fetch_dashboard_vehicles(search_query=None, state_vehicle="ALL"):
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

@fleet_bp.route("/dashboard")
@login_required
def dashboard():
    vehicles = fetch_dashboard_vehicles()
    return render_template("dashboard.html", vehicles=vehicles, all_states=VehicleState)

@fleet_bp.route("/search_vehicle")
@login_required
def search_vehicle():
    search_val = request.args.get("search", "")
    vehicle_state = request.args.get("state", "ALL")
    vehicles = fetch_dashboard_vehicles(search_val, vehicle_state)
    return render_template("partials/dashboard_inner.html", vehicles=vehicles)

@fleet_bp.route("/reload_table")
@login_required
def reload_dashboard():
    search_val = request.args.get("search", "")
    vehicle_state = request.args.get("state", "ALL")
    vehicles = fetch_dashboard_vehicles(search_val, vehicle_state)
    return render_template("partials/dashboard_inner.html", vehicles=vehicles)

@fleet_bp.route("/detalle/<patente>", methods=["GET", "POST"])
@login_required
def detalle_vehiculo(patente):
    stmt = (
        select(Vehicle)
        .filter_by(vehicle_id=patente.upper())
        .options(joinedload(Vehicle.current_driver), joinedload(Vehicle.telemetry_data))
    )
    vehicle = db.session.execute(stmt).scalar_one_or_none()
    if not vehicle: 
        abort(404)

    three_hours_ago = datetime.now() - timedelta(hours=3)
    hist_stmt = (
        select(VehicleTelemetryHistory)
        .filter(VehicleTelemetryHistory.vehicle_id == patente.upper(), VehicleTelemetryHistory.timestamp >= three_hours_ago)
        .order_by(VehicleTelemetryHistory.timestamp.asc())
    )
    history = db.session.execute(hist_stmt).scalars().all()

    subject_filter = request.args.get('subject_filter')
    notes_query = vehicle.annotations_list
    if request.method == "GET" and subject_filter and request.headers.get('HX-Request'):
        if subject_filter != 'ALL':
            notes_query = [n for n in vehicle.annotations_list if n.subject.name == subject_filter]
        return render_template("partials/notes_list.html", vehicle=vehicle, notes=notes_query, subjects=Subject, selected_filter=subject_filter)
    
    edit_form = EditVehicleForm()
    drivers = Driver.query.order_by(Driver.name.asc()).all()
    edit_form.driver_id.choices = [('', 'Sin asignar')] + [(str(d.id), d.name) for d in drivers] + [('NEW', '➕ Registrar Nuevo Conductor...')]

    if request.method == 'GET':
        if vehicle.vehicle_state:
            edit_form.vehicle_state.data = vehicle.vehicle_state.name
        edit_form.driver_id.data = str(vehicle.driver_id) if vehicle.driver_id else ''
    
    form = AnnotationForm()
    if form.validate_on_submit():
        selected_subject = Subject[form.subject.data]
        new_note = VehicleAnnotations(vehicle_id=vehicle.id, subject=selected_subject, comment=form.comment.data)
        db.session.add(new_note)
        db.session.commit()
        if request.headers.get('HX-Request'):
            return render_template("partials/notes_list.html", vehicle=vehicle, notes=vehicle.annotations_list, subjects=Subject, selected_filter='ALL')
        flash("Nota guardada", "success")
        return redirect(url_for('fleet.detalle_vehiculo', patente=patente))

    bounds = db.session.query(func.min(VehicleTelemetryHistory.timestamp), func.max(VehicleTelemetryHistory.timestamp)).filter(VehicleTelemetryHistory.vehicle_id == patente.upper()).first()
    first_ts, last_ts = bounds
    data_age_hours = (last_ts - first_ts).total_seconds() / 3600 if first_ts and last_ts else 0
    
    is_dark = request.cookies.get('theme') == 'dark'
    graphs, summary = get_monthly_stats(patente, is_dark_mode=is_dark, period='1h', graph_type='max_speed')
    all_drivers = Driver.query.order_by(Driver.name.asc()).all()
    
    return render_template("detalle.html", vehicle=vehicle, history=history, edit_form=edit_form, form=form, graph_data=graphs, summary=summary, data_age_hours=data_age_hours, notes=notes_query, subjects=Subject, routes=[], selected_filter=subject_filter or 'ALL', all_drivers=all_drivers, all_states=VehicleState)

@fleet_bp.route("/update_stats/<patente>", methods=["GET"])
@login_required
def update_stats(patente):
    graph_type = request.args.get('graph-type', 'max_speed')
    period = request.args.get('period-select', '1h')
    start_date_raw = request.args.get('start_date')
    end_date_raw = request.args.get('end_date')
    custom_range, custom_date_error = None, None
    chile_tz = ZoneInfo("America/Santiago")
    now_chile = datetime.now(ZoneInfo("America/Santiago"))

    if period == 'custom' and start_date_raw and end_date_raw:
        try:
            start_dt = datetime.fromisoformat(start_date_raw).replace(tzinfo=chile_tz)
            end_dt = datetime.fromisoformat(end_date_raw).replace(tzinfo=chile_tz)
            start_utc, end_utc = start_dt.astimezone(ZoneInfo("UTC")), end_dt.astimezone(ZoneInfo("UTC"))
            diff = end_utc - start_utc
            if not (diff < timedelta(hours=1) or diff > timedelta(days=120)):
                custom_range = (start_utc, end_utc)
            else:
                custom_date_error = '<span class="error">rango de tiempo debe ser entre 1 hora hasta 120 días</span>'
        except ValueError:
            period = '1h'
    
    is_dark = request.cookies.get('theme') == 'dark'
    bounds = db.session.query(func.min(VehicleTelemetryHistory.timestamp), func.max(VehicleTelemetryHistory.timestamp)).filter(VehicleTelemetryHistory.vehicle_id == patente.upper()).first()
    first_ts, last_ts = bounds
    data_age_hours = (last_ts - first_ts).total_seconds() / 3600 if first_ts and last_ts else 0

    vehicle = Vehicle.query.filter_by(vehicle_id=patente.upper()).first_or_404()
    start_date_val = start_date_raw or (now_chile - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
    end_date_val = end_date_raw or now_chile.strftime('%Y-%m-%dT%H:%M')
    header_context = {"vehicle": vehicle, "period": period, "active_type": graph_type, "data_age_hours": data_age_hours, "start_date_val": start_date_val, "end_date_val": end_date_val, "custom_date_error": custom_date_error}

    if graph_type == 'trayectos':
        if period == '1h': period = '6h'
        all_routes = return_vehicle_routes(period=period, plate=patente, custom_range=custom_range)
        return render_template("partials/routes_render.html", routes=all_routes, **header_context)
    else:
        graphs, summary = get_monthly_stats(patente, is_dark_mode=is_dark, period=period, custom_range=custom_range, graph_type=graph_type)
        return render_template("partials/stats_render.html", graph_data=graphs, summary=summary, **header_context)

@fleet_bp.route('/vehiculo/<patente>/edit', methods=['POST'])
@login_required
def edit_vehicle(patente):
    vehicle = Vehicle.query.filter_by(vehicle_id=patente.upper()).first_or_404()
    form = EditVehicleForm()
    drivers = Driver.query.all()
    form.driver_id.choices = [('', 'Sin asignar'), ('NEW', 'NEW')] + [(str(d.id), d.name) for d in drivers]

    if form.validate_on_submit():
        if form.driver_id.data == "NEW":
            if form.new_driver_name.data:
                new_driver = Driver(name=form.new_driver_name.data, driver_email=form.new_driver_email.data, phone=form.new_driver_phone.data)
                db.session.add(new_driver)
                db.session.flush()
                vehicle.driver_id = new_driver.id
        else:
            vehicle.driver_id = int(form.driver_id.data) if form.driver_id.data else None
        vehicle.vehicle_state = VehicleState[form.vehicle_state.data]
        db.session.commit()
        response = make_response(render_template('partials/vehicle_info_card.html', vehicle=vehicle))
        response.headers['HX-Trigger'] = 'closeModal'
        return response
    return render_template('partials/modal_edit_form.html', edit_form=form, vehicle=vehicle), 422