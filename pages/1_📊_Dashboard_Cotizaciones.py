import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from db_manager import DBManager
import os
import json

# Configuración de la página
st.set_page_config(
    page_title="Dashboard de Cotizaciones",
    page_icon="📊",
    layout="wide"
)

# Tema personalizado para los gráficos
CHART_THEME = {
    'plot_bgcolor': 'rgba(0,0,0,0)',
    'paper_bgcolor': 'rgba(0,0,0,0)',
    'font': {
        'family': 'Helvetica Neue, Arial',
        'size': 12,
        'color': '#2c3e50'
    },
    'title': {
        'font': {
            'size': 24,
            'color': '#2c3e50'
        }
    },
    'xaxis': {
        'gridcolor': '#f0f0f0',
        'linecolor': '#e0e0e0'
    },
    'yaxis': {
        'gridcolor': '#f0f0f0',
        'linecolor': '#e0e0e0'
    }
}

# Paleta de colores personalizada
CUSTOM_COLORS = {
    'primary': '#2980b9',
    'success': '#2ecc71',
    'warning': '#f1c40f',
    'danger': '#e74c3c',
    'info': '#3498db',
    'neutral': '#95a5a6'
}

# Estilos personalizados
st.markdown("""
    <style>
        /* Estilo general */
        .main {
            padding: 2rem;
            background-color: #f8f9fa;
        }
        
        /* Títulos */
        h1 {
            color: #2c3e50;
            font-family: 'Helvetica Neue', sans-serif;
            font-weight: 700;
            padding: 1.5rem 0;
            text-align: center;
            background: linear-gradient(120deg, #2980b9, #2c3e50);
            color: white;
            border-radius: 10px;
            margin-bottom: 2rem;
        }
        
        h3 {
            color: #2c3e50;
            font-family: 'Helvetica Neue', sans-serif;
            padding: 1rem 0;
            border-bottom: 2px solid #3498db;
            margin-top: 2rem;
        }
        
        /* Tarjetas de métricas */
        div[data-testid="stMetric"] {
            background-color: white;
            padding: 1rem;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        div[data-testid="stMetric"]:hover {
            transform: translateY(-5px);
        }
        
        /* Gráficos */
        div[data-testid="stPlotlyChart"] {
            background-color: white;
            padding: 1rem;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin: 1rem 0;
        }
        
        /* Sidebar */
        .css-1d391kg {
            background-color: #f1f3f6;
            padding: 2rem 1rem;
        }
        
        /* Botones */
        .stButton>button {
            background-color: #2980b9;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 0.5rem 1rem;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        
        .stButton>button:hover {
            background-color: #2c3e50;
            transform: translateY(-2px);
        }
        
        /* DataFrames */
        div[data-testid="stDataFrame"] {
            background-color: white;
            padding: 1rem;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
    </style>
""", unsafe_allow_html=True)

# Inicializar el DBManager
db = DBManager()

# Mapeo de estados
ESTADOS = {
    1: "En negociación",
    2: "Aprobada",
    3: "Rechazada"
}

# Mapeo de colores
def get_color_map():
    return {
        'En negociación': '#3498db',
        'Aprobada': '#2ecc71',
        'Rechazada': '#e74c3c'
    }

# Función para obtener los datos de cotizaciones
def get_cotizaciones_data(comercial_id=None):
    try:
        # Construir la consulta base
        query = db.client.from_('cotizaciones').select(
            'id, numero_cotizacion, creado_en, estado, referencia_cliente_id, estado:estados_cotizacion(id), es_recotizacion'
        ).order('creado_en.desc')
        
        # Obtener las cotizaciones
        response = query.execute()
        
        if not response.data:
            return pd.DataFrame()
            
        # Obtener las referencias de cliente con sus relaciones
        referencias_ids = [row['referencia_cliente_id'] for row in response.data]
        referencias_query = db.client.from_('referencias_cliente').select(
            'id, cliente:clientes(id, nombre), comercial:comerciales(id, nombre), id_comercial'
        ).in_('id', referencias_ids)
        
        referencias_response = referencias_query.execute()
        
        # Crear un diccionario para mapear referencias
        referencias_map = {
            ref['id']: {
                'cliente': ref.get('cliente', {}),
                'comercial': ref.get('comercial', {}),
                'id_comercial': ref.get('id_comercial')
            }
            for ref in referencias_response.data
        }
        
        # Transformar los datos para el DataFrame
        data = []
        for row in response.data:
            ref_info = referencias_map.get(row['referencia_cliente_id'], {})
            cliente_info = ref_info.get('cliente', {})
            comercial_info = ref_info.get('comercial', {})
            estado_info = row.get('estado', {})
            
            # Obtener el ID del estado y mapearlo al nombre correspondiente
            estado_id = estado_info.get('id') if estado_info else None
            estado_nombre = ESTADOS.get(estado_id, "Desconocido")
            
            data.append({
                'cotizacion_id': row['id'],
                'numero_cotizacion': row['numero_cotizacion'],
                'fecha_cotizacion': row['creado_en'],
                'estado_id': estado_id,
                'estado': estado_nombre,
                'cliente_id': cliente_info.get('id'),
                'nombre_cliente': cliente_info.get('nombre', 'Sin cliente'),
                'comercial_id': ref_info.get('id_comercial'),
                'nombre_comercial': comercial_info.get('nombre', 'Sin asignar'),
                'es_recotizacion': row.get('es_recotizacion', False)
            })
            
        df = pd.DataFrame(data)
        
        # Filtrar por comercial si es necesario
        if comercial_id:
            df = df[df['comercial_id'] == comercial_id]
            
        return df
        
    except Exception as e:
        st.error(f"Error al obtener datos de cotizaciones: {str(e)}")
        if hasattr(e, 'response'):
            st.error(f"Detalles de la respuesta: {e.response}")
        return pd.DataFrame()

# Función para obtener los comerciales
def get_comerciales():
    try:
        response = db.client.from_('comerciales').select('*').execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error al obtener comerciales: {str(e)}")
        return pd.DataFrame()

# Título principal con estilo mejorado
st.markdown("""
    <div style='text-align: center; padding: 2rem 0;'>
        <h1>📊 Dashboard de Cotizaciones</h1>
        <p style='color: #7f8c8d; font-size: 1.2em; margin-top: 1rem;'>
            Sistema de Análisis y Seguimiento de Cotizaciones
        </p>
    </div>
""", unsafe_allow_html=True)

# Sección de filtros
st.sidebar.header("Filtros")

# Obtener comerciales primero
df_comerciales = get_comerciales()

# Filtro de comercial (ahora va primero)
comercial_seleccionado = None
if not df_comerciales.empty:
    comercial_opciones = [("Todos", "Todos")] + list(zip(df_comerciales['id'], df_comerciales['nombre']))
    comercial_id, comercial_nombre = st.sidebar.selectbox(
        "Comercial",
        options=comercial_opciones,
        format_func=lambda x: x[1]
    )
    if comercial_id != "Todos":
        comercial_seleccionado = comercial_id

# Obtener datos filtrados por comercial si es necesario
df_cotizaciones = get_cotizaciones_data(comercial_seleccionado)

if df_cotizaciones.empty:
    st.error("No se encontraron cotizaciones para los filtros seleccionados")
else:
    # Filtro de fechas
    col1, col2 = st.sidebar.columns(2)
    with col1:
        fecha_inicio = st.date_input(
            "Fecha Inicio",
            value=datetime.now() - timedelta(days=30),
            max_value=datetime.now()
        )
    with col2:
        fecha_fin = st.date_input(
            "Fecha Fin",
            value=datetime.now(),
            max_value=datetime.now()
        )

    # Aplicar filtros de fecha
    df_cotizaciones['fecha_cotizacion'] = pd.to_datetime(df_cotizaciones['fecha_cotizacion'])
    mask = (df_cotizaciones['fecha_cotizacion'].dt.date >= fecha_inicio) & \
           (df_cotizaciones['fecha_cotizacion'].dt.date <= fecha_fin)

    df_filtrado = df_cotizaciones[mask]

    # Métricas principales con nuevo estilo
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #2980b9, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                📈 Métricas Principales
            </span>
        </h3>
    """, unsafe_allow_html=True)
    
    # Distribución de Estados y Métricas
    col1, col2 = st.columns([1, 3])

    with col1:
        # Gráfico de distribución de estados
        fig_pie = px.pie(
            df_filtrado,
            names='estado',
            title='Distribución de Estados',
            hole=0.4,
            color='estado',
            color_discrete_map=get_color_map()
        )
        fig_pie.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='%{label}<br>%{value} cotizaciones<br>%{percent}'
        )
        fig_pie.update_layout(CHART_THEME)
        st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        col_a, col_b, col_c, col_d = st.columns(4)
        
        with col_a:
            st.metric(
                "Total Cotizaciones",
                len(df_filtrado),
                delta=None,
                help="Número total de cotizaciones en el período seleccionado"
            )
        with col_b:
            st.metric(
                "Aprobadas",
                len(df_filtrado[df_filtrado['estado'] == 'Aprobada']),
                delta=f"{(len(df_filtrado[df_filtrado['estado'] == 'Aprobada'])/len(df_filtrado)*100 if len(df_filtrado) > 0 else 0):.1f}%",
                help="Cotizaciones aprobadas"
            )
        with col_c:
            st.metric(
                "Rechazadas",
                len(df_filtrado[df_filtrado['estado'] == 'Rechazada']),
                delta=f"{(len(df_filtrado[df_filtrado['estado'] == 'Rechazada'])/len(df_filtrado)*100 if len(df_filtrado) > 0 else 0):.1f}%",
                delta_color="inverse",
                help="Cotizaciones rechazadas"
            )
        with col_d:
            st.metric(
                "En Negociación",
                len(df_filtrado[df_filtrado['estado'] == 'En negociación']),
                delta=f"{(len(df_filtrado[df_filtrado['estado'] == 'En negociación'])/len(df_filtrado)*100 if len(df_filtrado) > 0 else 0):.1f}%",
                help="Cotizaciones en proceso de negociación"
            )

    # Análisis de Recotizaciones con nuevo estilo
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #2980b9, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                🔄 Análisis de Recotizaciones
            </span>
        </h3>
    """, unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    with col1:
        # Identificar recotizaciones por el campo es_recotizacion
        recotizaciones = len(df_filtrado[df_filtrado['es_recotizacion'] == True])
        nuevas = len(df_filtrado[df_filtrado['es_recotizacion'] == False])
        
        fig_recotizaciones = px.pie(
            values=[nuevas, recotizaciones],
            names=['Nuevas Cotizaciones', 'Recotizaciones'],
            title='Distribución de Nuevas Cotizaciones vs Recotizaciones',
            color_discrete_sequence=[CUSTOM_COLORS['success'], CUSTOM_COLORS['warning']],
            hole=0.4
        )
        fig_recotizaciones.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='%{label}<br>%{value} cotizaciones<br>%{percent}'
        )
        fig_recotizaciones.update_layout(CHART_THEME)
        st.plotly_chart(fig_recotizaciones, use_container_width=True)

    with col2:
        # Tasa de éxito de recotizaciones
        df_recotizaciones = df_filtrado[df_filtrado['es_recotizacion'] == True]
        tasa_exito_recot = len(df_recotizaciones[df_recotizaciones['estado'] == 'Aprobada']) / len(df_recotizaciones) * 100 if len(df_recotizaciones) > 0 else 0
        
        st.metric(
            "Tasa de Éxito en Recotizaciones",
            f"{tasa_exito_recot:.1f}%",
            help="Porcentaje de recotizaciones que fueron aprobadas"
        )
        
        # Promedio de recotizaciones por cliente
        recot_por_cliente = df_recotizaciones.groupby('nombre_cliente').size().mean()
        st.metric(
            "Promedio de Recotizaciones por Cliente",
            f"{recot_por_cliente:.1f}",
            help="Número promedio de recotizaciones por cliente"
        )

    # Análisis Temporal con nuevo estilo
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #2980b9, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                📅 Análisis Temporal
            </span>
        </h3>
    """, unsafe_allow_html=True)
    
    # Tendencia semanal
    df_temporal = df_filtrado.copy()
    df_temporal['semana'] = df_temporal['fecha_cotizacion'].dt.strftime('%Y-W%U')
    tendencia_semanal = df_temporal.groupby(['semana', 'estado']).size().reset_index(name='count')
    
    fig_tendencia = px.line(
        tendencia_semanal,
        x='semana',
        y='count',
        color='estado',
        title='Tendencia Semanal por Estado',
        color_discrete_map=get_color_map(),
        markers=True
    )
    fig_tendencia.update_layout(
        **CHART_THEME,
        xaxis_title="Semana",
        yaxis_title="Número de Cotizaciones",
        legend_title="Estado",
        hovermode='x unified'
    )
    fig_tendencia.update_traces(
        line=dict(width=3),
        marker=dict(size=8)
    )
    st.plotly_chart(fig_tendencia, use_container_width=True)

    # Análisis por Cliente con nuevo estilo
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #2980b9, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                👥 Análisis por Cliente
            </span>
        </h3>
    """, unsafe_allow_html=True)
    
    # Top 5 clientes por recotizaciones y nuevas cotizaciones
    col1, col2 = st.columns(2)

    with col1:
        # Top 5 clientes por número de recotizaciones
        df_recot = df_filtrado[df_filtrado['es_recotizacion'] == True]
        top_recot = df_recot['nombre_cliente'].value_counts().head(5)
        
        fig_recot = px.bar(
            x=top_recot.index,
            y=top_recot.values,
            title='Top 5 Clientes con Más Recotizaciones',
            labels={'x': 'Cliente', 'y': 'Número de Recotizaciones'},
            color_discrete_sequence=[CUSTOM_COLORS['warning']]
        )
        fig_recot.update_layout(
            **CHART_THEME,
            showlegend=False,
            bargap=0.3,
            bargroupgap=0.1
        )
        fig_recot.update_traces(
            hovertemplate='%{x}<br>Recotizaciones: %{y}<extra></extra>'
        )
        st.plotly_chart(fig_recot, use_container_width=True)

    with col2:
        # Top 5 clientes por número de cotizaciones nuevas
        df_nuevas = df_filtrado[df_filtrado['es_recotizacion'] == False]
        top_nuevas = df_nuevas['nombre_cliente'].value_counts().head(5)
        
        fig_nuevas = px.bar(
            x=top_nuevas.index,
            y=top_nuevas.values,
            title='Top 5 Clientes con Más Cotizaciones Nuevas',
            labels={'x': 'Cliente', 'y': 'Número de Cotizaciones Nuevas'},
            color_discrete_sequence=[CUSTOM_COLORS['primary']]
        )
        fig_nuevas.update_layout(
            **CHART_THEME,
            showlegend=False,
            bargap=0.3,
            bargroupgap=0.1
        )
        fig_nuevas.update_traces(
            hovertemplate='%{x}<br>Cotizaciones Nuevas: %{y}<extra></extra>'
        )
        st.plotly_chart(fig_nuevas, use_container_width=True)

    # Análisis detallado por cliente
    col1, col2 = st.columns(2)

    with col1:
        # Top 5 clientes por número total de cotizaciones
        top_clientes = df_filtrado['nombre_cliente'].value_counts().head(5)
        fig_clientes = px.bar(
            x=top_clientes.index,
            y=top_clientes.values,
            title='Top 5 Clientes por Número Total de Cotizaciones',
            labels={'x': 'Cliente', 'y': 'Número de Cotizaciones'},
            color_discrete_sequence=[CUSTOM_COLORS['success']]
        )
        fig_clientes.update_layout(
            **CHART_THEME,
            showlegend=False,
            bargap=0.3,
            bargroupgap=0.1
        )
        fig_clientes.update_traces(
            hovertemplate='%{x}<br>Total Cotizaciones: %{y}<extra></extra>'
        )
        st.plotly_chart(fig_clientes, use_container_width=True)

    with col2:
        # Tasa de aprobación por cliente (top 5)
        clientes_stats = df_filtrado.groupby('nombre_cliente').agg({
            'estado': lambda x: (x == 'Aprobada').mean() * 100,
            'cotizacion_id': 'count'
        }).reset_index()
        clientes_stats.columns = ['Cliente', 'Tasa_Aprobacion', 'Total_Cotizaciones']
        clientes_stats = clientes_stats[clientes_stats['Total_Cotizaciones'] >= 2]  # Mínimo 2 cotizaciones
        top_clientes_tasa = clientes_stats.nlargest(5, 'Tasa_Aprobacion')
        
        fig_tasa = px.bar(
            top_clientes_tasa,
            x='Cliente',
            y='Tasa_Aprobacion',
            title='Top 5 Clientes por Tasa de Aprobación',
            labels={'Tasa_Aprobacion': 'Tasa de Aprobación (%)'},
            color_discrete_sequence=[CUSTOM_COLORS['info']]
        )
        fig_tasa.update_layout(
            **CHART_THEME,
            showlegend=False,
            bargap=0.3,
            bargroupgap=0.1
        )
        fig_tasa.update_traces(
            hovertemplate='%{x}<br>Tasa de Aprobación: %{y:.1f}%<extra></extra>'
        )
        st.plotly_chart(fig_tasa, use_container_width=True)

    # KPIs Adicionales con nuevo estilo
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #2980b9, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                📊 KPIs Adicionales
            </span>
        </h3>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)

    with col1:
        # Promedio de cotizaciones por día
        dias_periodo = (df_filtrado['fecha_cotizacion'].max() - df_filtrado['fecha_cotizacion'].min()).days + 1
        promedio_diario = len(df_filtrado) / dias_periodo if dias_periodo > 0 else 0
        st.metric(
            "Promedio Diario de Cotizaciones",
            f"{promedio_diario:.1f}",
            help="Promedio de cotizaciones generadas por día"
        )

    with col2:
        # Tiempo promedio de decisión (para cotizaciones no en negociación)
        df_decididas = df_filtrado[df_filtrado['estado'] != 'En negociación']
        if not df_decididas.empty:
            tiempo_decision = (df_decididas['fecha_cotizacion'].max() - df_decididas['fecha_cotizacion'].min()).days
            st.metric(
                "Tiempo Promedio de Decisión",
                f"{tiempo_decision} días",
                help="Tiempo promedio entre creación y decisión final"
            )

    with col3:
        # Efectividad del comercial
        if comercial_seleccionado:
            efectividad = (len(df_filtrado[df_filtrado['estado'] == 'Aprobada']) / len(df_filtrado) * 100) if len(df_filtrado) > 0 else 0
            st.metric(
                "Efectividad del Comercial",
                f"{efectividad:.1f}%",
                help="Porcentaje de cotizaciones aprobadas sobre el total"
            )

    # Detalle de Cotizaciones con nuevo estilo
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #2980b9, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                📋 Detalle de Cotizaciones
            </span>
        </h3>
    """, unsafe_allow_html=True)
    
    # Botón de descarga mejorado
    st.markdown("""
        <div style='display: flex; justify-content: flex-end; margin: 1rem 0;'>
    """, unsafe_allow_html=True)
    csv = df_filtrado.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar Datos",
        data=csv,
        file_name=f"cotizaciones_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Tabla mejorada con más columnas y mejor formato
    df_display = df_filtrado[[
        'numero_cotizacion',
        'fecha_cotizacion',
        'estado',
        'nombre_comercial',
        'nombre_cliente'
    ]].copy()
    
    df_display['fecha_cotizacion'] = df_display['fecha_cotizacion'].dt.strftime('%Y-%m-%d %H:%M')
    
    st.dataframe(
        df_display.sort_values('fecha_cotizacion', ascending=False),
        hide_index=True,
        use_container_width=True
    ) 