from datetime import timezone
from zoneinfo import ZoneInfo

def local_time(dt):
    if not dt: 
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("America/Santiago")).strftime('%H:%M:%S')

def init_app(app):
    app.jinja_env.filters['local_time'] = local_time