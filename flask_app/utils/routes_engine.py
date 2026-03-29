from datetime import datetime, timedelta, timezone
from models import db, VehicleRoute

def return_vehicle_routes(period, plate):
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

    # Convert routes to dict for JSON serialization in the template
    routes_data = []
    for r in routes:
        routes_data.append({
            "id": r.id,
            "start": r.start_time.isoformat(),
            "end": r.end_time.isoformat(),
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