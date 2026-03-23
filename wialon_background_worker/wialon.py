import os
import time
import requests
import math
import re
from dotenv import load_dotenv
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import VehicleTelemetry, SystemConfig, Vehicle

load_dotenv()

# Config
TOKEN = os.getenv('WIALON_TOKEN')
BASE_DIR = Path(__file__).resolve().parent.parent
if os.getenv("FLASK_ENV") == "development":
    DB_URL = f"sqlite:///{BASE_DIR / 'local_dev.db'}"
else:
    DB_URL = os.getenv("DATABASE_URL")
WIALON_URL = "https://hst-api.wialon.com/wialon/ajax.html"

# Setup Requests Session with Retries
session_http = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session_http.mount('https://', HTTPAdapter(max_retries=retries))

engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)

def get_sid():
    params = {'svc': 'token/login', 'params': f'{{"token":"{TOKEN}"}}'}
    try:
        # Added timeout (10 seconds)
        response = session_http.get(WIALON_URL, params=params, timeout=10).json()
        content = response.get('eid')
        if content is not None:
            return response.get('eid')
        print(response)
        return None
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

def calc_app_distance(plat, plng, nlat, nlng):
    if any(val is None for val in [plat, plng, nlat, nlng]):
        return 0.0
    lat1, lon1, lat2, lon2 = map(math.radians, [plat, plng, nlat, nlng])
    # Haversine
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    return 6371 * c

def avg_speed(sample_size, past_mean, current_speed):
    if sample_size <= 1:
        return float(current_speed)
    return past_mean + ((float(current_speed) - past_mean) / sample_size)

def process_data(items):
    db_session = Session()
    try:
        for item in items.get('items', []):
            h_id = item.get('id') 
            pos = item.get('pos') or {}
            lmsg = item.get('lmsg') or {}
            
            # Logic: is_moving
            current_x, current_y = pos.get('x'), pos.get('y')
            last_x = (lmsg.get('pos', {}) or {}).get('x') if lmsg else None
            last_y = (lmsg.get('pos', {})  or {}).get('y') if lmsg else None
            speed = round(pos.get('s') or 0, 2)
            if all(isinstance(val, (float, int)) for val in [current_x, current_y, last_x, last_y]):
                moving = speed > 0 or (round(current_x, 1) != round(last_x, 1) or round(current_y, 1) != round(last_y, 1))
            else:
                moving = speed > 0 or (current_x != last_x or current_y != last_y)

            # Upsert Logic
            vehicle = db_session.query(Vehicle).filter_by(harwdare_id=h_id).first()

            if not vehicle:
                # FIRST TIME: Set everything
                clean_name = re.sub(r"^([A-Z]{4}-[0-9]{2}).+$", r"\1", str(item.get('nm')), flags=re.IGNORECASE)
                vehicle = Vehicle(
                 vehicle_id=clean_name,
                 vehicle_type=item.get('cls'),
                 harwdare_id=h_id
                )
                db_session.add(vehicle)
                db_session.flush()
                print(f"New vehicle registered: {clean_name}")
                vehicle_telemetry = VehicleTelemetry(
                    vehicle_id=vehicle.id,
                    raw_data=item,
                    max_registered_speed=speed,
                    speed=speed,
                    accumulated_distance=0,
                    mean_speed=0,
                    sample_size=0
                )
                db_session.add(vehicle_telemetry)
                print(f"New telemetry registered: {item.get('nm')}")
            else:
                vehicle_telemetry = db_session.query(VehicleTelemetry).filter_by(vehicle_id=vehicle.id).first()
            try:
                last_speed = float(vehicle_telemetry.speed)
            except ValueError:
                last_speed = 0
            vehicle_telemetry.speed = speed
            vehicle_telemetry.max_registered_speed = max(vehicle_telemetry.max_registered_speed, last_speed)
            vehicle_telemetry.is_moving = bool(moving)
            vehicle_telemetry.raw_data = item
            if moving:
                vehicle_telemetry.sample_size += 1
                vehicle_telemetry.mean_speed = avg_speed(vehicle_telemetry.sample_size, vehicle_telemetry.mean_speed, vehicle_telemetry.speed)
            moved_distance = calc_app_distance(vehicle_telemetry.last_lat, vehicle_telemetry.last_lon, current_y, current_x)
            if moving and moved_distance > 0.01:
                vehicle_telemetry.accumulated_distance += moved_distance
            vehicle_telemetry.last_lat = current_y
            vehicle_telemetry.last_lon = current_x
        db_session.commit()
    except Exception as e:
        print(f"Database Error: {e.__repr__()}")
        db_session.rollback()
    else:
        print("Db updated succesfully")
    finally:
        db_session.close()

def is_worker_enabled():
    """Checks the database to see if the admin has paused the worker."""
    db_session = Session()
    try:
        config = db_session.query(SystemConfig).first()
        # If no config exists yet, assume True
        return config.worker_enabled if config else True
    except Exception as e:
        print(f"Error checking status: {e.__repr__()}")
        return True
    finally:
        db_session.close()

if __name__ == "__main__":
    try:
        sid = None
        while True:
            # STEP 1: Check if we are allowed to run
            if is_worker_enabled():
                if not sid:
                    print("Attempting login to Wialon...")
                    sid = get_sid()
                if sid:
                    data = fetch_telemetry(sid)
                    
                    if data and data.get('error') == 1:
                        print("Session expired. Re-logging in on next tick.")
                        sid = None 
                    elif data and 'items' in data:
                        process_data(data)
                        print(f"Update completed at {time.strftime('%H:%M:%S')}")
                    else:
                        print("Unexpected response or empty data.")
            else:
                print(f"Worker PAUSED by Admin at {time.strftime('%H:%M:%S')}. Sleeping...")
                # If paused, clear the sid so we start fresh when resumed
                sid = None 

            # Wait 30 seconds
            time.sleep(30)
    except KeyboardInterrupt:
        print("End of process")