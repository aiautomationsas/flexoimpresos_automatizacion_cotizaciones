import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from db_manager import DBManager
import os
import json
from supabase import create_client
from typing import List, Dict
import traceback

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
    'primary': '#0F4C81',  # Reflex Blue
    'success': '#2ecc71',
    'warning': '#f1c40f',
    'danger': '#e74c3c',
    'info': '#5DADE2',    # Lighter Blue for info/secondary
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
            color: white; /* White text for contrast */
            font-family: 'Helvetica Neue', sans-serif;
            font-weight: 700;
            padding: 1.5rem 0;
            text-align: center;
            background-color: #0F4C81; /* Solid Reflex Blue */
            border-radius: 10px;
            margin-bottom: 2rem;
        }
        
        h3 {
            color: #2c3e50;
            font-family: 'Helvetica Neue', sans-serif;
            padding: 1rem 0;
            border-bottom: 2px solid #0F4C81; /* Reflex Blue border */
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
            background-color: #0F4C81; /* Solid Reflex Blue */
            color: white; /* White text */
            border: none;
            border-radius: 5px;
            padding: 0.5rem 1rem;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        
        .stButton>button:hover {
            background-color: #0B3A65; /* Darker Reflex Blue on hover */
            color: white; /* Keep text white */
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
if 'supabase' not in st.session_state:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    st.session_state.supabase = create_client(supabase_url, supabase_key)

db = DBManager(st.session_state.supabase)

# Verificar el rol del usuario
def get_user_role():
    try:
        user = st.session_state.supabase.auth.get_user()
        if not user or not user.user:
            return None
            
        response = st.session_state.supabase.from_('perfiles').select(
            'rol:roles(nombre)'
        ).eq('id', user.user.id).single().execute()
        
        if response.data:
            return response.data['rol']['nombre']
        return None
    except Exception as e:
        print(f"Error detallado al obtener rol: {traceback.format_exc()}")
        st.error(f"Error al obtener rol del usuario: {str(e)}")
        return None

# Mapeo de estados
ESTADOS = {
    1: "En negociación",
    2: "Aprobada",
    3: "Rechazada"
}

# Mapeo de colores
def get_color_map():
    return {
        'En negociación': '#5DADE2', # Lighter blue for negotiation
        'Aprobada': '#2ecc71',
        'Rechazada': '#e74c3c'
    }

# Función para obtener los datos de cotizaciones
def get_cotizaciones_data(comercial_id=None):
    try:
        user_role = get_user_role()
        if not user_role:
            st.error("No tienes permisos para ver las cotizaciones")
            return pd.DataFrame()

        # Obtener lista de cotizaciones visibles
        cotizaciones_list = db.get_visible_cotizaciones_list()
        if not cotizaciones_list:
            return pd.DataFrame()

        # Transformar los datos para el DataFrame
        data = []
        for cotizacion in cotizaciones_list:
            try:
                # La lista visible ya incluye toda la información necesaria
                estado_nombre = ESTADOS.get(cotizacion.get('estado_id'), "Desconocido")
                
                data.append({
                    'cotizacion_id': cotizacion.get('id'),
                    'numero_cotizacion': cotizacion.get('numero_cotizacion'),
                    'fecha_cotizacion': cotizacion.get('fecha_creacion'),
                    'estado_id': cotizacion.get('estado_id'),
                    'estado': estado_nombre,
                    'cliente_id': cotizacion.get('cliente_id'),
                    'nombre_cliente': cotizacion.get('cliente_nombre', 'Sin cliente'),
                    'usuario_id': cotizacion.get('usuario_id'),
                    'usuario_nombre': cotizacion.get('usuario_nombre', 'Sin perfil'),
                    'es_recotizacion': cotizacion.get('es_recotizacion', False),
                    'motivo_rechazo': cotizacion.get('motivo_rechazo')
                })
            except Exception as e:
                print(f"Error procesando cotización {cotizacion.get('id')}: {e}")
                continue
            
        df = pd.DataFrame(data)
        
        # Filtrar por comercial si es necesario y el usuario es administrador
        if comercial_id and user_role == 'administrador':
            df = df[df['usuario_id'] == comercial_id]
            
        return df
        
    except Exception as e:
        print(f"Error al obtener datos de cotizaciones: {str(e)}")
        traceback.print_exc()
        return pd.DataFrame()

# Función para obtener los comerciales
def get_comerciales():
    try:
        user_role = get_user_role()
        if not user_role:
            return pd.DataFrame()

        if user_role == 'administrador':
            # Los administradores ven todos los comerciales
            response = st.session_state.supabase.from_('perfiles').select(
                'id, nombre, rol:roles(nombre)'
            ).eq('roles.nombre', 'comercial').execute()
        elif user_role == 'comercial':
            # Los comerciales solo se ven a sí mismos
            user = st.session_state.supabase.auth.get_user()
            response = st.session_state.supabase.from_('perfiles').select(
                'id, nombre, rol:roles(nombre)'
            ).eq('id', user.user.id).execute()
        else:
            return pd.DataFrame()

        if not response.data:
            return pd.DataFrame()

        return pd.DataFrame([{
            'id': item['id'],
            'nombre': item['nombre']
        } for item in response.data])
    except Exception as e:
        print(f"Error detallado al obtener comerciales: {traceback.format_exc()}")
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
            <span style='background: linear-gradient(120deg, #0F4C81, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
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
            <span style='background: linear-gradient(120deg, #0F4C81, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                🔄 Análisis de Recotizaciones
            </span>
        </h3>
    """, unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    with col1:
        # Identificar recotizaciones por el campo es_recotizacion
        recotizaciones = len(df_filtrado[df_filtrado['es_recotizacion'] == True])
        nuevas = len(df_filtrado[df_filtrado['es_recotizacion'] == False])
        
        # Crear DataFrame para el gráfico de recotizaciones
        df_recot_plot = pd.DataFrame({
            'Tipo': ['Nuevas Cotizaciones', 'Recotizaciones'],
            'Cantidad': [nuevas, recotizaciones]
        })
        
        fig_recotizaciones = px.pie(
            df_recot_plot,
            values='Cantidad',
            names='Tipo',
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
        recot_por_cliente = df_recotizaciones.groupby('nombre_cliente').size().mean() if not df_recotizaciones.empty else 0
        st.metric(
            "Promedio de Recotizaciones por Cliente",
            f"{recot_por_cliente:.1f}",
            help="Número promedio de recotizaciones por cliente"
        )

    # Análisis Temporal con nuevo estilo
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #0F4C81, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
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
            <span style='background: linear-gradient(120deg, #0F4C81, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                👥 Análisis por Cliente
            </span>
        </h3>
    """, unsafe_allow_html=True)
    
    # Top 5 clientes por recotizaciones y nuevas cotizaciones
    col1, col2 = st.columns(2)

    with col1:
        # Top 5 clientes por número de recotizaciones
        df_recot = df_filtrado[df_filtrado['es_recotizacion'] == True]
        if not df_recot.empty:
            top_recot = df_recot['nombre_cliente'].value_counts().head(5).reset_index()
            top_recot.columns = ['Cliente', 'Recotizaciones']
            
            fig_recot = px.bar(
                top_recot,
                x='Cliente',
                y='Recotizaciones',
                title='Top 5 Clientes con Más Recotizaciones',
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
        else:
            st.info("No hay recotizaciones en el período seleccionado")

    with col2:
        # Top 5 clientes por número de cotizaciones nuevas
        df_nuevas = df_filtrado[df_filtrado['es_recotizacion'] == False]
        if not df_nuevas.empty:
            top_nuevas = df_nuevas['nombre_cliente'].value_counts().head(5).reset_index()
            top_nuevas.columns = ['Cliente', 'Cotizaciones']
            
            fig_nuevas = px.bar(
                top_nuevas,
                x='Cliente',
                y='Cotizaciones',
                title='Top 5 Clientes con Más Cotizaciones Nuevas',
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
        else:
            st.info("No hay cotizaciones nuevas en el período seleccionado")

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
            <span style='background: linear-gradient(120deg, #0F4C81, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
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

    # Después de la sección de métricas principales, agregar:
    
    # Análisis de Rechazos
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #0F4C81, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
                ❌ Análisis de Rechazos
            </span>
        </h3>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Gráfico de motivos de rechazo
        df_rechazadas = df_filtrado[df_filtrado['estado'] == 'Rechazada']
        if not df_rechazadas.empty:
            motivos_rechazo = df_rechazadas['motivo_rechazo'].value_counts()
            
            fig_motivos = px.pie(
                values=motivos_rechazo.values,
                names=motivos_rechazo.index,
                title='Distribución de Motivos de Rechazo',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_motivos.update_traces(
                textposition='inside',
                textinfo='percent+label',
                hovertemplate='%{label}<br>%{value} cotizaciones<br>%{percent}'
            )
            fig_motivos.update_layout(CHART_THEME)
            st.plotly_chart(fig_motivos, use_container_width=True)
        else:
            st.info("No hay cotizaciones rechazadas en el período seleccionado")
    
    with col2:
        # Métricas de rechazo
        if not df_rechazadas.empty:
            # Tasa de rechazo por cliente
            rechazo_por_cliente = df_rechazadas.groupby('nombre_cliente').size()
            cliente_mas_rechazos = rechazo_por_cliente.idxmax()
            num_rechazos_max = rechazo_por_cliente.max()
            
            st.metric(
                "Cliente con Más Rechazos",
                cliente_mas_rechazos,
                f"{num_rechazos_max} rechazos",
                help="Cliente con mayor número de cotizaciones rechazadas"
            )
            
            # Motivo más común de rechazo
            motivo_comun = df_rechazadas['motivo_rechazo'].mode()[0] if not df_rechazadas['motivo_rechazo'].empty else "No especificado"
            cantidad_motivo = df_rechazadas['motivo_rechazo'].value_counts().iloc[0]
            
            st.metric(
                "Motivo Más Común de Rechazo",
                motivo_comun,
                f"{cantidad_motivo} casos",
                help="Motivo más frecuente de rechazo de cotizaciones"
            )
            
            # Tasa de rechazo general
            tasa_rechazo = (len(df_rechazadas) / len(df_filtrado)) * 100
            st.metric(
                "Tasa de Rechazo General",
                f"{tasa_rechazo:.1f}%",
                help="Porcentaje de cotizaciones rechazadas sobre el total"
            )

    # Detalle de Cotizaciones con nuevo estilo
    st.markdown("""
        <h3 style='margin-bottom: 1.5rem;'>
            <span style='background: linear-gradient(120deg, #0F4C81, #2c3e50); -webkit-background-clip: text; -webkit-text-fill-color: transparent;'>
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
        'usuario_nombre',
        'nombre_cliente',
        'motivo_rechazo'
    ]].copy()
    
    df_display['fecha_cotizacion'] = df_display['fecha_cotizacion'].dt.strftime('%Y-%m-%d %H:%M')
    df_display['motivo_rechazo'] = df_display['motivo_rechazo'].fillna('-')
    
    st.dataframe(
        df_display.sort_values('fecha_cotizacion', ascending=False),
        hide_index=True,
        use_container_width=True
    )

    if 'selected_referencia' in st.session_state and st.session_state.selected_referencia:
        ref_info = st.session_state.selected_referencia
        # Actualizar para usar usuario_id
        cotizacion_data = {
            'cliente_id': ref_info.get('cliente_id'),
            'referencia_id': ref_info.get('id'),
            'usuario_id': ref_info.get('usuario_id'), # Usar usuario_id
            # ... otros campos necesarios para la cotización ...
        }
        st.session_state.cotizacion_data = cotizacion_data
        st.session_state.cotizacion_edit_mode = True
        # st.switch_page("pages/2_ Cotizador.py") # Asegúrate que el nombre sea correcto
        st.switch_page("pages/2_Cotizador.py")
    else:
        st.warning("Selecciona una referencia para continuar.") 