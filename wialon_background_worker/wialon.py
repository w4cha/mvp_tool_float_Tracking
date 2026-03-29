import os
import time
import requests
import math
import re
import sys
import polyline
from datetime import datetime, date, timedelta, timezone, time as dt_time
from pathlib import Path
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlalchemy import create_engine, func, text, event
from sqlalchemy.orm import sessionmaker
from zoneinfo import ZoneInfo

# Project imports
sys.path.append(str(Path(__file__).resolve().parent.parent))
from models import VehicleTelemetry, SystemConfig, Vehicle, VehicleTelemetryHistory, VehicleRoute, VehicleTelemetryBackup

load_dotenv()

# --- CONFIG & SETUP ---
TOKEN = os.getenv('WIALON_TOKEN')
BASE_DIR = Path(__file__).resolve().parent.parent
DB_URL = f"sqlite:///{BASE_DIR / 'local_dev.db'}" if os.getenv("FLASK_ENV") == "development" else os.getenv("DATABASE_URL")
WIALON_URL = "https://hst-api.wialon.com/wialon/ajax.html"
BACKUP_AFTER_DAYS = 120
ASSUME_MAX_SPEED = 150
session_http = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session_http.mount('https://', HTTPAdapter(max_retries=retries))

engine = create_engine(DB_URL)
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Only execute these pragmas if we are in development/SQLite mode
    if os.getenv("FLASK_ENV") != "development":
        return

    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA wal_autocheckpoint=1000")
    cursor.close()

Session = sessionmaker(bind=engine)

# --- UTILS ---

def is_outside_operation_hours():
    """Returns True if current Chile time is between 02:00 and 05:00 next day."""
    tz = ZoneInfo("America/Santiago")
    now_chile = datetime.now(tz).time()
    return dt_time(2, 0) <= now_chile <= dt_time(5, 0)

def get_sid():
    params = {'svc': 'token/login', 'params': f'{{"token":"{TOKEN}"}}'}
    try:
        response = session_http.get(WIALON_URL, params=params, timeout=10).json()
        return response.get('eid')
    except Exception as e:
        print(f"Connection Error (Login): {e}")
        return None

def fetch_telemetry(sid):
    params = {
        'svc': 'core/search_items',
        'params': '{"spec":{"itemsType":"avl_unit","propName":"sys_name","propValueMask":"*","sortType":"sys_name"},"force":1,"flags":1025,"from":0,"to":0}',
        'sid': sid
    }
    try:
        return session_http.get(WIALON_URL, params=params, timeout=15).json()
    except Exception as e:
        print(f"Connection Error (Fetch): {e}")
        return None

def get_engine_status(item):
    try:
        lmsg = item.get('lmsg', {})
        params = lmsg.get('p', {})
        return bool(params.get('io_239', 0))
    except Exception:
        return False

def calc_app_distance(plat, plng, nlat, nlng):
    if any(val is None for val in [plat, plng, nlat, nlng]): 
        return 0.0
    lat1, lon1, lat2, lon2 = map(math.radians, [plat, plng, nlat, nlng])
    dlon, dlat = lon2 - lon1, lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 6371 * (2 * math.asin(math.sqrt(a)))

def create_vehicle_route(db_session, patente):
    """
    Creates a summarized route entry.
    DECISION: Uses a 'Physical Ceiling' (wall_clock_seconds) to ensure 
    durations never exceed the actual elapsed time between first and last point.
    """    
    last_route = db_session.query(VehicleRoute).filter_by(vehicle_id=patente).order_by(VehicleRoute.start_time.desc()).first()
    tz = ZoneInfo("America/Santiago")
    today_midnight = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    
    query = db_session.query(VehicleTelemetryHistory).filter_by(vehicle_id=patente)
    if last_route:
        last_route_utc = last_route.end_time.replace(tzinfo=timezone.utc)
        start_filter = max(last_route_utc, today_midnight)
        query = query.filter(VehicleTelemetryHistory.timestamp >= start_filter)
    else:
        query = query.filter(VehicleTelemetryHistory.timestamp > today_midnight)
    
    points = query.order_by(VehicleTelemetryHistory.timestamp.asc()).all()
    if len(points) < 2: 
        return

    # GUARD: We define the 'True Route' window starting at first active point and ending at last active point
    active_points = [p for p in points if p.engine_state or p.is_moving or p.speed > 1.0]
    if not active_points or len(active_points) < 2: 
        return

    for p in points:
        if p.timestamp.tzinfo is None:
            p.timestamp = p.timestamp.replace(tzinfo=timezone.utc)

    start_ts = active_points[0].timestamp
    end_ts = active_points[-1].timestamp

    if active_points:
        engine_on_count = sum(1 for p in active_points if p.engine_state)
        engine_ratio = engine_on_count / len(active_points)
            
        # DECISION: We require 80% (or very high) ignition for the actual MOVING part.
        if engine_ratio < 0.8: 
            print(f"[!] Ruta descartada: Integridad de ignición en trayecto baja ({round(engine_ratio*100)}%) para {patente}")
            return
    else:
        return
    total_dist = 0.0
    active_seconds = 0.0
    idle_time_seconds = 0.0
    
    for i in range(len(points)):
        curr = points[i]
        if i > 0:
            prev = points[i-1]
            if start_ts <= curr.timestamp <= end_ts:
                time_diff = (curr.timestamp - prev.timestamp).total_seconds()
                
                # SAFEGUARD: Ignore gaps > 30 mins to avoid 'teleportation' distance spikes
                if 0 < time_diff <= 1800:
                    total_dist += calc_app_distance(prev.last_lat, prev.last_lon, curr.last_lat, curr.last_lon)
                    # idependtly of the previous current state the vehicle moved
                    if prev.engine_state or prev.is_moving:
                        active_seconds += time_diff
                    
                    # 2. Total Idle Time (Ignition ON, but vehicle is stationary)
                    if prev.engine_state:
                        # CASE A: Sustained Stop (Was stopped, remains stopped)
                        if not prev.is_moving and not curr.is_moving:
                            idle_time_seconds += time_diff

                        # CASE B: The Transition Stop (Was moving, now stopped)
                        elif prev.is_moving and not curr.is_moving:
                            # momentum_est: roughly 1 second for every 10 km/h of speed.
                            # If going 60 km/h, we assume it took 6s to stop.
                            momentum_est = prev.speed / 10.0
                            
                            # We only count idle time AFTER the truck likely came to a full halt.
                            # max(0, ...) ensures we don't get negative numbers if the gap is tiny.
                            actual_idle_in_gap = max(0.0, time_diff - momentum_est)
                            idle_time_seconds += actual_idle_in_gap

                        # CASE C: The Start-up (Was stopped, now moving)
                        elif not prev.is_moving and curr.is_moving:
                            # Opposite logic: If it's now doing 40 km/h, it probably spent 
                            # the first ~4 seconds of the gap accelerating.
                            acceleration_est = curr.speed / 10.0
                            
                            # We assume it was idling for the part of the gap BEFORE it moved.
                            actual_idle_in_gap = max(0.0, time_diff - acceleration_est)
                            idle_time_seconds += actual_idle_in_gap

    # SAFEGUARD: Ignore GPS 'noise' movements in yards (usually < 500m)
    if total_dist < 0.5: 
        return 

    # SAFEGUARD: The Duration Clamp. Ensures active_seconds <= physical time elapsed
    wall_clock_seconds = (end_ts - start_ts).total_seconds()
    if wall_clock_seconds < 30: # If the 'trip' lasted less than 30 seconds, ignore it
        print(f"[!] Ignorando ruta fantasma para {patente}: duración insuficiente.")
        return
    sanitized_active_seconds = min(active_seconds, wall_clock_seconds)
    polyline_points = [(p.last_lat, p.last_lon) for p in points if start_ts <= p.timestamp <= end_ts]

    new_route = VehicleRoute(
        vehicle_id=patente,
        start_time=start_ts,
        end_time=end_ts,
        duration_minutes=round(sanitized_active_seconds / 60.0, 2),
        idle_minutes=round(min(idle_time_seconds, sanitized_active_seconds) / 60.0, 2),
        distance_km=round(total_dist, 2),
        max_speed=max(p.speed for p in points),
        avg_speed=round(sum(p.speed for p in points if p.speed > 0) / max(1, sum(1 for p in points if p.speed > 0)), 2),
        route_polyline=polyline.encode(polyline_points),
        total_points=len(polyline_points),
        start_lat=active_points[0].last_lat,
        start_lon=active_points[0].last_lon,
        end_lat=active_points[-1].last_lat,
        end_lon=active_points[-1].last_lon
    )
    db_session.add(new_route)
    print(f"[RT] Ruta generada para {patente}: {new_route.distance_km} km")

def avg_speed(sample_size, past_mean, current_speed):
    if sample_size <= 1: return float(current_speed)
    return past_mean + ((float(current_speed) - past_mean) / sample_size)

# --- CORE LOGIC ---

def process_data(items):
    db_session = Session()
    try:
        with db_session.no_autoflush:
            config = db_session.query(SystemConfig).first()
            if not (config and config.worker_enabled):
                print("[*] Proceso desactivado actualmente")
                return

            for item in items.get('items', []):
                raw_name = str(item.get('nm'))
                match = re.search(r"([A-Z]{4}-[0-9]{2})", raw_name, re.IGNORECASE)
                if not match: continue
                
                patente = match.group(1).upper()
                pos = item.get('pos') or {}
                current_x, current_y = pos.get('x') or 0, pos.get('y') or 0
                speed = round(pos.get('s') or 0, 2)
                
                # SAFEGUARD: 3.0 km/h threshold filters out GPS 'walking' drift while parked
                moving = speed > 3.0 
                engine_on = get_engine_status(item)

                vehicle = db_session.query(Vehicle).filter_by(vehicle_id=patente).first()
                if not vehicle:
                    vehicle = Vehicle(vehicle_id=patente)
                    db_session.add(vehicle)
                    db_session.flush()

                t_data = vehicle.telemetry_data
                if not t_data:
                    t_data = VehicleTelemetry(vehicle_id=vehicle.id, raw_data=item, engine_state=engine_on,
                                              last_lat=current_y, last_lon=current_x, is_moving=moving)
                    db_session.add(t_data)
                    db_session.flush()

                # DECISION: ANCHOR TO HISTORY. 
                # Decision made to fetch last SAVED record to compare time/distance.
                # This prevents logging based on ephemeral live updates.
                last_log = db_session.query(VehicleTelemetryHistory).filter_by(vehicle_id=patente).order_by(VehicleTelemetryHistory.timestamp.desc()).first()

                dist_moved = 0.0
                passed_time = 999999 
                believable_desplacement = True
                if last_log:
                    dist_moved = calc_app_distance(last_log.last_lat, last_log.last_lon, current_y, current_x)
                    now_utc = datetime.now(timezone.utc)
                    last_log_ts = last_log.timestamp.replace(tzinfo=timezone.utc)
                    passed_time = (now_utc - last_log_ts).total_seconds()
                    implied_speed_kmh = (dist_moved / (passed_time / 3600)) if passed_time > 0 else 999
                    believable_desplacement = implied_speed_kmh < ASSUME_MAX_SPEED
                    if not believable_desplacement:
                        print(f"[!] Salto Implausible para {patente}: {dist_moved:.2f}km en {passed_time}s ({implied_speed_kmh:.1f} km/h). Ignorando distancia.")
                        dist_moved = 0.0
            
                # DECISION: TRIGGER LOGIC (STRICT)
                # 1. 50m filter + Engine ON (Solves GPS bounce in Quilpué while parked)
                significant_move = (dist_moved > 0.050) and engine_on
                # 2. Log if ignition or moving status actually flips
                engine_changed = engine_on != t_data.engine_state
                state_changed = moving != t_data.is_moving
                # 3. Dynamic Heartbeat: 15m if running, 4h if off.
                heartbeat_limit = 900 if engine_on else 14400
                stale_data = passed_time > heartbeat_limit

                should_log_history = (significant_move or engine_changed or state_changed or stale_data) and believable_desplacement

                # DECISION: Route creation triggered on 'Dead Stop' (Ignition OFF + Speed 0)
                just_stopped = (not moving and not engine_on) and (t_data.is_moving or t_data.engine_state)
                if just_stopped:
                    try:
                        create_vehicle_route(db_session, patente)
                    except Exception as e:
                        print(f"[!] Error creando ruta para {patente}: {e}")

                # UPDATE LIVE STATE (Always happens every 30s)
                t_data.speed, t_data.is_moving, t_data.engine_state = speed, moving, engine_on
                t_data.last_lat, t_data.last_lon, t_data.raw_data = current_y, current_x, item
                if believable_desplacement:
                    t_data.accumulated_distance += dist_moved

                # SAVE HISTORY (Only happens on Triggers)
                if should_log_history:
                    db_session.add(VehicleTelemetryHistory(
                        vehicle_id=patente, speed=speed, last_lat=current_y, last_lon=current_x,
                        is_moving=moving, engine_state=engine_on
                    ))

            db_session.commit()
            print(f"[√] Ciclo completado a las {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"Error en base de datos: {e}")
        db_session.rollback()
    finally:
        db_session.close()

def run_daily_maintenance():
    db_session = Session()
    try:
        tz = ZoneInfo("America/Santiago")
        current_time = datetime.now(tz)
        today_santiago = current_time.date()
        config = db_session.query(SystemConfig).first()
        if config and config.last_maintenance_date: 
            last_maint_santiago = config.last_maintenance_date.astimezone(tz)
            # Now compare apples-to-apples in Santiago time
            if last_maint_santiago.date() == today_santiago:
                return

        print(f"[{datetime.now(tz).strftime('%H:%M:%S')}] Iniciando Mantenimiento Diario...")

        threshold_utc = datetime.now(timezone.utc) - timedelta(days=BACKUP_AFTER_DAYS)
        if os.getenv("FLASK_ENV") != "development":
            move_query = text("""
                WITH deleted_rows AS (
                    DELETE FROM telemetria_historial
                    WHERE timestamp < :limit
                    RETURNING vehicle_id, speed, last_lat, last_lon, is_moving, engine_state, timestamp
                )
                INSERT INTO telemetria_backup (vehicle_id, speed, last_lat, last_lon, is_moving, engine_state, timestamp)
                SELECT * FROM deleted_rows;
            """)

            result = db_session.execute(move_query, {"limit": threshold_utc})
            rows_moved = result.rowcount
        
            if rows_moved > 0:
                print(f"[+] Backup exitoso: {rows_moved} registros movidos a almacenamiento en frío.")
            else:
                print("[*] No hay datos antiguos para archivar.")

            for i in range(2):
                target_dt = (current_time.replace(day=1) + timedelta(days=i*31)).replace(day=1)
                suffix = target_dt.strftime("%Y_%m")
                db_session.execute(text(f"CREATE TABLE IF NOT EXISTS telemetria_historial_{suffix} PARTITION OF telemetria_historial FOR VALUES FROM ('{target_dt.strftime('%Y-%m-%d')}') TO ('{(target_dt + timedelta(days=32)).replace(day=1).strftime('%Y-%m-%d')}');"))
            if config:
                config.last_maintenance_date = datetime.now(timezone.utc)
            else:
                db_session.add(SystemConfig(worker_enabled=True, last_maintenance_date=datetime.now(timezone.utc)))
            db_session.commit()
            print("[+] Mantenimiento producción completado exitosamente.")
        else:
            print("[*] Modo desarrollo (SQLite): Iniciando migración masiva...")
            
            try:
                # 1. Insert into backup from history (Set-based, very fast)
                db_session.execute(text("""
                    INSERT INTO telemetria_backup (vehicle_id, speed, last_lat, last_lon, is_moving, engine_state, timestamp)
                    SELECT vehicle_id, speed, last_lat, last_lon, is_moving, engine_state, timestamp
                    FROM telemetria_historial
                    WHERE timestamp < :limit
                """), {"limit": threshold_utc})
                
                # 2. Delete from history
                result = db_session.execute(text("""
                    DELETE FROM telemetria_historial WHERE timestamp < :limit
                """), {"limit": threshold_utc})
                
                rows_moved = result.rowcount
                if rows_moved > 0:
                    print(f"[+] Backup exitoso: {rows_moved} registros movidos a almacenamiento en frío.")
                else:
                    print("[*] No hay datos antiguos para archivar.")
                if config:
                    config.last_maintenance_date = datetime.now(timezone.utc)
                else:
                    db_session.add(SystemConfig(worker_enabled=True, last_maintenance_date=datetime.now(timezone.utc)))
                db_session.commit()
                print("[+] Mantenimiento desarrollo completado exitosamente.")
            except Exception as e:
                print(f"[!] Error en migración SQLite: {e}")
    except Exception as e:
        print(f"[!] Error en mantenimiento: {e}"); db_session.rollback()
    finally:
        db_session.close()

if __name__ == "__main__":
    sid = None
    print(">>> [SISTEMA] Iniciando Wialon Worker...")
    try:
        engine.connect()
        print(f">>> [DB] Conexión exitosa a: {DB_URL}")
    except Exception as e:
        print(f">>> [ERROR DB] No se pudo conectar: {e}"); sys.exit(1)

    while True:
        now = datetime.now(ZoneInfo("America/Santiago"))
        print(f"--- Ciclo {now.strftime('%Y-%m-%d %H:%M:%S')} ---")

        if is_outside_operation_hours():
            print(f"[*] Fuera de horario operativo. Ejecutando mantenimiento...")
            run_daily_maintenance()
            print("[*] Durmiendo por 5 minutos...")
            time.sleep(300); continue

        if not sid:
            print("[*] Intentando obtener SID de Wialon...")
            sid = get_sid()
            if not sid: 
                print("[!] Error: No se pudo obtener SID. Reintentando en 30s...")
                time.sleep(30); continue
            print(f"[+] SID obtenido con éxito: {sid}")

        print("[*] Solicitando telemetría...")
        data = fetch_telemetry(sid)
        if data and 'items' in data:
            print(f"[+] Datos recibidos: {len(data['items'])} unidades encontradas.")
            process_data(data)
        elif data and data.get('error'):
            print(f"[!] Wialon Error {data.get('error')}. Reseteando sesión...")
            sid = None
        else:
            print("[?] Respuesta inesperada de Wialon o sin items.")

        time.sleep(30)