import pandas as pd
import plotly.express as px
import json
import plotly.utils
import numpy as np
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from models import db, VehicleTelemetryHistory

def haversine_distance(lat1, lon1, lat2, lon2):
    r = 6371
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2)**2
    return 2 * r * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

def get_monthly_stats(patente, is_dark_mode=False, period='1h', custom_range=None, graph_type='max_speed'):
    # 1. Define Time Window
    if custom_range:
        actual_start, last_ts = custom_range
    else:
        # Optimized: Only find the latest point, don't scan for MIN(timestamp)
        last_ts = db.session.query(func.max(VehicleTelemetryHistory.timestamp))\
            .filter(VehicleTelemetryHistory.vehicle_id == patente.upper()).scalar()

        if not last_ts:
            return None, {}

        period_map = {
            '1h':  {'delta': timedelta(hours=1), 'resample': '5min'},
            '24h': {'delta': timedelta(days=1),  'resample': '30min'},
            '7d':  {'delta': timedelta(days=7),  'resample': '12h'},
            '30d': {'delta': timedelta(days=30), 'resample': 'D'}
        }
        config = period_map.get(period, period_map['1h'])
        actual_start = last_ts - config['delta']

    # Determine Resample Rule for Custom Ranges
    if custom_range:
        total_seconds = (last_ts - actual_start).total_seconds()
        # might need to heck this back latter
        target_points = 60
        resample_seconds = max(int(total_seconds / target_points), 10)
        resample_rule = f"{resample_seconds}s"
    else:
        resample_rule = config['resample']

    # 2. Optimized Data Fetch (Columns only, no full objects)
    stmt = (
        select(
            VehicleTelemetryHistory.timestamp,
            VehicleTelemetryHistory.speed,
            VehicleTelemetryHistory.is_moving,
            VehicleTelemetryHistory.engine_state,
            VehicleTelemetryHistory.last_lat,
            VehicleTelemetryHistory.last_lon
        )
        .filter(
            VehicleTelemetryHistory.vehicle_id == patente.upper(),
            VehicleTelemetryHistory.timestamp >= actual_start,
            VehicleTelemetryHistory.timestamp <= last_ts
        )
        .order_by(VehicleTelemetryHistory.timestamp.asc())
    )
    
    result = db.session.execute(stmt).all()
    if not result:
        return None, {}

    # 3. DataFrame Preparation
    df = pd.DataFrame(result, columns=['ts', 'speed', 'moving', 'engine', 'lat', 'lng'])
    df['ts'] = pd.to_datetime(df['ts'], utc=True).dt.tz_convert('America/Santiago').dt.tz_localize(None)

    # 4. Conditional Graph Generation
    text_color = "#E0E0E0" if is_dark_mode else "#11191f"
    grid_color = "rgba(255,255,255,0.1)" if is_dark_mode else "rgba(0,0,0,0.05)"
    theme_template = "plotly_dark" if is_dark_mode else "plotly_white"

    common_layout = dict(
        template=theme_template,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=text_color, family="Inter, sans-serif"),
        xaxis=dict(showgrid=True, gridcolor=grid_color, tickfont=dict(color=text_color)),
        yaxis=dict(showgrid=True, gridcolor=grid_color, tickfont=dict(color=text_color))
    )

    graph_json = None
    summary = {}

    if graph_type == 'max_speed':
        df_max = df.set_index('ts')['speed'].resample(resample_rule).max().fillna(0).reset_index()
        fig = px.bar(df_max, x='ts', y='speed', color="speed", color_continuous_scale="turbo",
                     title="Velocidad Máxima (km/h)")
        fig.update_layout(**common_layout)
        graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        summary['max_speed_period'] = round(df['speed'].max(), 1)

    elif graph_type == 'distance':
        # Haversine only if distance is requested
        df = df[(df['lat'] != 0) & (df['lng'] != 0)].dropna(subset=['lat', 'lng'])
        if not df.empty:
            df['dist_km'] = haversine_distance(df['lat'].shift(), df['lng'].shift(), df['lat'], df['lng']).fillna(0)
            df_dist = df.set_index('ts')['dist_km'].resample(resample_rule).sum().fillna(0).reset_index()
            fig = px.area(df_dist, x='ts', y='dist_km', title="Distancia Recorrida (km por intervalo)")
            fig.update_layout(**common_layout)
            graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
            summary['total_km'] = round(df['dist_km'].sum(), 2)

    elif graph_type == 'idle':
        # Engine State logic only if idle is requested
        df['status'] = np.where(df['engine'] & df['moving'], 'moving', 
                       np.where(df['engine'] & ~df['moving'], 'idle', 'off'))
        
        df['state_group'] = (df['status'] != df['status'].shift()).cumsum()
        groups = df.groupby('state_group').agg(status=('status', 'first'), start=('ts', 'min'), end=('ts', 'max'))
        groups['dur_min'] = (groups['end'] - groups['start']).dt.total_seconds() / 60

        active_min = groups[groups['status'] == 'moving']['dur_min'].sum()
        idle_min = groups[groups['status'] == 'idle']['dur_min'].sum()
        off_min = groups[groups['status'] == 'off']['dur_min'].sum()

        df_usage = pd.DataFrame([
            {'Estado': 'Activo', 'Minutos': round(active_min, 1)},
            {'Estado': 'Ralentí', 'Minutos': round(idle_min, 1)},
            {'Estado': 'Apagado', 'Minutos': round(off_min, 1)}
        ])
        
        fig = px.bar(df_usage, y=[0,0,0], x='Minutos', color='Estado', orientation='h', barmode='stack',
                     color_discrete_map={'Activo': '#2ecc71', 'Ralentí': '#f1c40f', 'Apagado': '#e74c3c'},
                     title="Uso de Motor vs Movimiento")
        
        fig.update_layout(**common_layout)
        fig.update_layout(showlegend=True, yaxis=dict(showticklabels=False, title=""), height=300)
        graph_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        total_period_min = active_min + idle_min + off_min
        summary['idle_ratio'] = round((idle_min / max(1, (active_min + idle_min + off_min))) * 100, 1)
        summary['total_period_min'] = round(total_period_min, 1)

    return graph_json, summary