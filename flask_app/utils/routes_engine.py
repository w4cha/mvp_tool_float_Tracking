from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from models import db, VehicleRoute

def return_vehicle_routes(period, plate, custom_range=None):
    if custom_range and len(custom_range) == 2:
        start_filter, end_filter = custom_range
    else:
        now = datetime.now(timezone.utc)
        delta = {
            '6h': timedelta(hours=6),
            '24h': timedelta(days=1),
            '7d': timedelta(days=7),
            '30d': timedelta(days=30)
        }.get(period, timedelta(hours=6))
        
        start_filter = now - delta
    
    routes = VehicleRoute.query.filter(
        VehicleRoute.vehicle_id == plate.upper(),
        VehicleRoute.start_time >= start_filter
    ).order_by(VehicleRoute.start_time.asc()).all()

    chile_tz = ZoneInfo("America/Santiago")
    # Convert routes to dict for JSON serialization in the template
    routes_data = []
    for r in routes:
        start_utc = r.start_time.replace(tzinfo=timezone.utc)
        end_utc = r.end_time.replace(tzinfo=timezone.utc)
        start_cl = start_utc.astimezone(chile_tz)
        end_cl = end_utc.astimezone(chile_tz)
        routes_data.append({
            "id": r.id,
            "start": start_cl.isoformat(),
            "end": end_cl.isoformat(),
            "dist": round(r.distance_km, 2),
            "duration": round(r.duration_minutes, 1),
            "max_speed": r.max_speed,
            "avg_speed": round(r.avg_speed, 1),
            "idle": round(r.idle_minutes, 1),
            "polyline": r.route_polyline,
            "start_coords": [r.start_lat, r.start_lon],
            "end_coords": [r.end_lat, r.end_lon]
        })
    return routes_data