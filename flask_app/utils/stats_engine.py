import pandas as pd
import plotly.express as px
import json
import plotly.utils
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import select, func
from models import db, VehicleTelemetryHistory

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calcula la distancia en km entre dos puntos geográficos usando la fórmula de Haversine."""
    r = 6371  # Radio de la Tierra en km
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2)**2
    return 2 * r * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

def get_monthly_stats(patente, is_dark_mode=False, period='1h'):
    # 1. Límites temporales del vehículo
    bounds = db.session.query(
        func.min(VehicleTelemetryHistory.timestamp),
        func.max(VehicleTelemetryHistory.timestamp)
    ).filter(VehicleTelemetryHistory.vehicle_id == patente.upper()).first()

    first_ts, last_ts = bounds
    if not last_ts:
        return None, {"total_idle_events": 0, "avg_idle_time": 0}

    # 2. Configuración de Ventana y Resample
    period_map = {
        '1h':  {'delta': timedelta(hours=1), 'resample': '2min',  'format': '%H:%M'},
        '24h': {'delta': timedelta(days=1),  'resample': '30min', 'format': '%H:%M'},
        '7d':  {'delta': timedelta(days=7),  'resample': '12H',   'format': '%d %b'},
        '30d': {'delta': timedelta(days=30), 'resample': 'D',     'format': '%b %d'}
    }
    
    config = period_map.get(period, period_map['1h'])
    actual_start = max(last_ts - config['delta'], first_ts)

    # 3. Obtención de datos
    stmt = (
        select(VehicleTelemetryHistory)
        .filter(
            VehicleTelemetryHistory.vehicle_id == patente.upper(),
            VehicleTelemetryHistory.timestamp >= actual_start,
            VehicleTelemetryHistory.timestamp <= last_ts
        )
        .order_by(VehicleTelemetryHistory.timestamp.asc())
    )
    history = db.session.execute(stmt).scalars().all()
    
    if not history:
        return None, {"total_idle_events": 0, "avg_idle_time": 0}

    # 4. Procesamiento de DataFrame
    df = pd.DataFrame([{
        'ts': h.timestamp, 
        'speed': h.speed, 
        'moving': h.is_moving,
        'engine': h.engine_state,
        'lat': h.last_lat,
        'lng': h.last_lon
    } for h in history])
    
    df['ts'] = pd.to_datetime(df['ts'], utc=True)
    # set time to app location
    df['ts'] = df['ts'].dt.tz_convert('America/Santiago')
    # clean for plotly lavels
    df['ts'] = df['ts'].dt.tz_localize(None)
    # --- Limpieza y Cálculo de Distancia (Haversine con Máscara) ---
    # Eliminamos registros sin coordenadas o con ceros (errores GPS)
    df = df.dropna(subset=['lat', 'lng'])
    df = df[(df['lat'] != 0) & (df['lng'] != 0)]
    
    # Creamos desplazamientos
    df['lat_prev'] = df['lat'].shift()
    df['lng_prev'] = df['lng'].shift()
    
    # Solo calculamos donde existan ambos puntos para evitar NaNs en la función
    mask = df['lat_prev'].notna() & df['lng_prev'].notna()
    df.loc[mask, 'dist_km'] = haversine_distance(
        df.loc[mask, 'lat_prev'], 
        df.loc[mask, 'lng_prev'], 
        df.loc[mask, 'lat'], 
        df.loc[mask, 'lng']
    )
    df['dist_km'] = df['dist_km'].fillna(0)

    # --- Configuración Visual ---
    text_color = "#E0E0E0" if is_dark_mode else "#11191f"
    grid_color = "rgba(255,255,255,0.1)" if is_dark_mode else "rgba(0,0,0,0.05)"
    theme_template = "plotly_dark" if is_dark_mode else "plotly_white"

    common_layout = dict(
        template=theme_template,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=text_color, family="Inter, sans-serif"),
        margin=dict(l=50, r=20, t=40, b=50),
        xaxis=dict(showgrid=True, gridcolor=grid_color, tickfont=dict(color=text_color), color=text_color, automargin=True, linecolor=text_color),
        yaxis=dict(showgrid=True, gridcolor=grid_color, tickfont=dict(color=text_color), color=text_color, automargin=True, linecolor=text_color)
    )

    # --- GRÁFICO 1: Velocidad Máxima (Barras) ---
    df_max = df.set_index('ts')['speed'].resample(config['resample']).max().fillna(0).reset_index().sort_values(by='ts')
    fig_max = px.bar(df_max, x='ts', y='speed', color="speed", color_continuous_scale="turbo",
                     title="Velocidad Máxima (km/h)")
    fig_max.update_yaxes(type='linear', rangemode='tozero')
    fig_max.update_layout(**common_layout)
    fig_max.update_coloraxes(
    colorbar_tickfont_color=text_color,
    colorbar_title_font_color=text_color
)

    # --- GRÁFICO 2: Distancia Acumulada (Área) ---
    df_dist = df.set_index('ts')['dist_km'].resample(config['resample']).sum().reset_index()
    df_dist['km_acumulados'] = df_dist['dist_km'].cumsum().round(2)
    fig_dist = px.area(df_dist, x='ts', y='dist_km', color_discrete_sequence=['#2ecc71'],
                       title="Distancia Recorrida (km por intervalo)",
                       hover_data={"km_acumulados": True})
    fig_dist.update_layout(**common_layout)

    # --- GRÁFICO 3: Disponibilidad (Stacked Bar Horizontal) ---
    total_duration = (last_ts - actual_start).total_seconds() / 60
    
    # Lógica de estados para calcular tiempo neto activo/inactivo
    df = df.sort_values('ts')
    def determine_status(row):
        if row['engine'] and row['moving']:
            return 'moving'
        elif row['engine'] and not row['moving']:
            return 'idle'
        else:
            return 'off'

    df['status'] = df.apply(determine_status, axis=1)

    # 2. Group by status changes
    df['state_group'] = (df['status'] != df['status'].shift()).cumsum()

    # 3. Aggregate
    groups = df.groupby('state_group').agg(
        status=('status', 'first'),
        start=('ts', 'min'),
        end=('ts', 'max')
    )
    groups['dur_min'] = (groups['end'] - groups['start']).dt.total_seconds() / 60

    # 4. Final Totals
    active_min = groups[groups['status'] == 'moving']['dur_min'].sum()
    true_idle_min = groups[groups['status'] == 'idle']['dur_min'].sum()
    engine_off_min = groups[groups['status'] == 'off']['dur_min'].sum()

    df_usage = pd.DataFrame([
        {'Estado': 'Activo', 'Minutos': round(active_min, 1)},
        {'Estado': 'Parado', 'Minutos': round(true_idle_min, 1)},
        {'Estado': 'Motor apagado', 'Minutos': round(engine_off_min, 1)}
    ])
    df_usage['Visual_Group'] = "Disponibilidad"
    fig_usage = px.bar(df_usage, y='Visual_Group', x='Minutos', color='Estado', 
                       orientation='h', barmode='stack',
                       color_discrete_map={'Activo': '#2ecc71', 'Parado': '#f1c40f', 'Motor apagado': '#e74c3c'},
                       title="Disponibilidad de Operación (Tiempo Total)")
    
    usage_layout = common_layout.copy()
    usage_layout.update(dict(
        showlegend=True,
        xaxis=dict(title="Minutos en el periodo", tickfont=dict(color=text_color)),
        yaxis=dict(showticklabels=False, title=""),
        height=220,
        margin=dict(l=20, r=20, t=60, b=40)
    ))
    fig_usage.update_layout(**usage_layout)

    # 5. Resumen de métricas
    summary = {
        'total_km': round(df['dist_km'].sum(), 2),
        'active_ratio': round((active_min / total_duration) * 100, 1) if total_duration > 0 else 0,
        'avg_speed': round(df[df['moving'] == True]['speed'].mean(), 1) if not df.empty else 0,
        'total_idle_events': int(len(groups[(groups['status'] == False) & (groups['dur_min'] >= 20)]))
    }
    return {
    'max_speed': json.dumps(fig_max, cls=plotly.utils.PlotlyJSONEncoder),
    'distance': json.dumps(fig_dist, cls=plotly.utils.PlotlyJSONEncoder),
    'idle': json.dumps(fig_usage, cls=plotly.utils.PlotlyJSONEncoder)
}, summary