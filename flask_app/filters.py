from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def local_time(dt, format_type='time'):
    if not dt: 
        return ""
    
    # 1. Parse string to datetime if necessary
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except ValueError:
            return dt

    if not isinstance(dt, datetime):
        return str(dt)

    # 2. Handle Timezone
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        
    try:
        dt_local = dt.astimezone(ZoneInfo("America/Santiago"))
        
        # 3. Select Format Logic
        if format_type == 'day':
            return dt_local.strftime('%d/%m/%Y')  # e.g., 28/03/2026
        elif format_type == 'full':
            return dt_local.strftime('%d/%m/%Y %H:%M:%S')
        else:
            return dt_local.strftime('%H:%M:%S') # Default 'time'
            
    except Exception:
        return dt.strftime('%H:%M:%S')

def init_app(app):
    app.jinja_env.filters['local_time'] = local_time