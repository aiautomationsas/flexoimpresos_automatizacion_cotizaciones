import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import traceback

# Importaciones del proyecto (ajustar según sea necesario)
from src.data.database import DBManager
from src.auth.auth_manager import AuthManager # O donde esté la lógica de roles

# Paleta de colores básica (restaurada)
COLOR_MAP_ESTADO = {
    'En negociación': '#5DADE2',
    'En Negociación': '#5DADE2',
    'Aprobada': '#2ecc71',
    'Descartada': '#e74c3c',
    'Anulada': '#e74c3c',
    'Desconocido': '#95a5a6' # Color para estados no mapeados o por ID
}

def _load_dashboard_data(_db: DBManager, comercial_id=None, start_date=None, end_date=None):
    """
    Carga y preprocesa los datos necesarios para el dashboard.
    """
    try:
        user_role = st.session_state.get('usuario_rol', None)
        user_id = st.session_state.get('user_id', None)
        
        # Enfoque mejorado con múltiples estrategias de carga de datos
        cotizaciones_list = []
        
        # Intentar primero con la nueva función RPC específica para el dashboard
        try:
            cotizaciones_list = _db.supabase.rpc('get_visible_cotizaciones_for_dashboard').execute().data
            print("DEBUG Dashboard: Cotizaciones obtenidas usando get_visible_cotizaciones_for_dashboard")
        except Exception as e_new_func:
            print(f"DEBUG Dashboard: Error con get_visible_cotizaciones_for_dashboard: {e_new_func}")
            # Fallback a la función original
            try:
                cotizaciones_list = _db.get_all_cotizaciones_overview()
                print("DEBUG Dashboard: Cotizaciones obtenidas usando get_all_cotizaciones_overview")
            except Exception as e_legacy:
                print(f"DEBUG Dashboard: Error también con get_all_cotizaciones_overview: {e_legacy}")
                st.error(f"Error obteniendo datos de cotizaciones. Contacte al administrador.")
                return pd.DataFrame()
        
        # Verificar si se obtuvieron datos
        if not cotizaciones_list:
            print("DEBUG Dashboard: No se obtuvieron cotizaciones de ninguna función")
            return pd.DataFrame()
        
        # Aplicar filtro de comercial según corresponda
        cotizaciones_filtradas = []
        key_user = 'id_usuario'       # Clave probable del creador/editor
        key_commercial = 'comercial_id' # Clave probable del asignado (Ajustar si es otro nombre)

        if user_role == 'administrador':
            if comercial_id:
                # Filtrar si CUALQUIERA de las claves coincide con el ID seleccionado
                cotizaciones_filtradas = [c for c in cotizaciones_list
                                          if str(c.get(key_user)) == str(comercial_id) or
                                             str(c.get(key_commercial)) == str(comercial_id)]
            else:
                cotizaciones_filtradas = cotizaciones_list
        elif user_role == 'comercial':
            key_comercial = 'id_usuario'
            
            # IMPLEMENTAR FILTRO COMBINADO
            cotizaciones_filtradas = [c for c in cotizaciones_list if str(c.get('id_usuario')) == str(user_id) or str(c.get('comercial_id')) == str(user_id)]
        else:
            st.error("Permisos insuficientes para ver el dashboard.")
            return pd.DataFrame()

        if not cotizaciones_filtradas:
            return pd.DataFrame()

        # Convertir a DataFrame
        df = pd.DataFrame(cotizaciones_filtradas)

        # --- Procesamiento y Validación de Columnas Esenciales ---
        required_cols = ['id', 'fecha_creacion', 'estado_id', 'cliente_nombre'] # Columnas mínimas esperadas
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.error(f"Error crítico: Faltan columnas esenciales en los datos de cotización: {', '.join(missing_cols)}. Verifique los métodos overview en DBManager.")
            return pd.DataFrame()

        # Convertir fecha
        df['fecha_creacion'] = pd.to_datetime(df['fecha_creacion'])

        # Mapear estado (obteniendo el mapa desde DB)
        try:
            estados_db = _db.get_estados_cotizacion()
            estados_map = {e.id: e.estado for e in estados_db}
        except Exception as e_state:
            st.warning(f"No se pudo cargar el mapeo de estados desde la DB: {e_state}. Se usarán IDs.")
            estados_map = {}
        df['estado_nombre'] = df['estado_id'].map(estados_map).fillna(df['estado_id'].astype(str)) # Usar ID si falla el mapeo

        # Mapear motivo rechazo (si existe la columna y la función)
        # Asumiendo que la columna se llama 'id_motivo_rechazo' <-- AJUSTADO
        if 'id_motivo_rechazo' in df.columns and hasattr(_db, 'get_motivos_rechazo'):
            try:
                motivos_db = _db.get_motivos_rechazo()
                motivos_map = {m.id: m.motivo for m in motivos_db}
                df['motivo_rechazo_nombre'] = df['id_motivo_rechazo'].map(motivos_map)
            except Exception as e_motivo:
                st.warning(f"No se pudo cargar el mapeo de motivos de rechazo: {e_motivo}")
                df['motivo_rechazo_nombre'] = None
        elif 'id_motivo_rechazo' in df.columns:
             df['motivo_rechazo_nombre'] = None # Columna existe pero no la función de mapeo

        # Filtrar por fecha (después de convertir a datetime)
        if start_date and end_date:
             df = df[(df['fecha_creacion'].dt.date >= start_date) & (df['fecha_creacion'].dt.date <= end_date)]

        # Renombrar columnas para consistencia (opcional pero recomendado)
        # Asegúrate que 'usuario_nombre' o similar exista si lo quieres renombrar
        rename_map = {}
        if 'usuario_nombre' in df.columns: # Ajusta 'usuario_nombre' al nombre real
            rename_map['usuario_nombre'] = 'comercial_nombre'
        if rename_map:
             df = df.rename(columns=rename_map)

        return df

    except Exception as e:
        st.error(f"Error cargando datos del dashboard: {e}")
        traceback.print_exc()
        return pd.DataFrame()


def show_dashboard():
    """Muestra la vista del dashboard de cotizaciones."""
    st.title("📊 Dashboard de Cotizaciones")

    if 'db' not in st.session_state:
        st.error("Error: La conexión a la base de datos no está inicializada.")
        return

    db = st.session_state.db
    user_role = st.session_state.get('usuario_rol', None)

    # --- Filtros en el Sidebar ---
    st.sidebar.header("Filtros")

    # Filtro de Comercial (Solo para Admin)
    comercial_seleccionado_id = None
    if user_role == 'administrador':
        try:
            comerciales = db.get_perfiles_by_role('comercial')
            if comerciales:
                # Crear diccionario id -> nombre
                opciones_comercial = {c['id']: c['nombre'] for c in comerciales}
                # Crear lista de tuplas para el selectbox (id, nombre)
                opciones_display = [(None, "Todos")] + list(opciones_comercial.items())

                # Guardar el resultado de selectbox (que es una tupla)
                selected_tuple = st.sidebar.selectbox(
                    "Comercial",
                    options=opciones_display,
                    format_func=lambda x: x[1], # Mostrar el nombre
                    key="dashboard_comercial_filter"
                )
                # Extraer el ID de la tupla seleccionada
                comercial_seleccionado_id = selected_tuple[0] if selected_tuple else None
            else:
                st.sidebar.warning("No se encontraron comerciales.")
        except Exception as e:
            st.sidebar.error(f"Error cargando comerciales: {e}")
            traceback.print_exc() # Mostrar error detallado

    # Filtro de Fechas
    default_start_date = datetime.now().date() - timedelta(days=30)
    default_end_date = datetime.now().date()

    col1_f, col2_f = st.sidebar.columns(2)
    with col1_f:
        fecha_inicio = st.date_input("Fecha Inicio", value=default_start_date, key="dashboard_date_start")
    with col2_f:
        fecha_fin = st.date_input("Fecha Fin", value=default_end_date, key="dashboard_date_end")

    # Validar fechas
    if fecha_inicio > fecha_fin:
        st.sidebar.error("La fecha de inicio no puede ser posterior a la fecha de fin.")
        return

    # --- Cargar Datos Filtrados ---
    # Pasar fechas como objetos date
    df_filtrado = _load_dashboard_data(db, comercial_seleccionado_id, fecha_inicio, fecha_fin)

    # --- Mostrar Dashboard ---
    if df_filtrado.empty:
        st.info("No se encontraron cotizaciones para los filtros seleccionados.") # Cambiado a st.info
        return

    st.markdown("### Métricas Principales")
    # --- IMPLEMENTACIÓN DE MÉTRICAS --- 
    total_cotizaciones = len(df_filtrado)
    aprobadas = len(df_filtrado[df_filtrado['estado_nombre'] == 'Aprobada'])
    descartadas = len(df_filtrado[df_filtrado['estado_nombre'] == 'Descartada'])
    negociacion = len(df_filtrado[df_filtrado['estado_nombre'] == 'En Negociación'])
    anuladas = len(df_filtrado[df_filtrado['estado_nombre'] == 'Anulada'])

    tasa_aprobacion_str = f"{(aprobadas / total_cotizaciones * 100):.1f}%" if total_cotizaciones > 0 else "0.0%"
    tasa_descarte_str = f"{(descartadas / total_cotizaciones * 100):.1f}%" if total_cotizaciones > 0 else "0.0%"
    tasa_negociacion_str = f"{(negociacion / total_cotizaciones * 100):.1f}%" if total_cotizaciones > 0 else "0.0%"
    tasa_anulada_str = f"{(anuladas / total_cotizaciones * 100):.1f}%" if total_cotizaciones > 0 else "0.0%"

    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    with col_m1:
        st.metric("Total Cotizaciones", total_cotizaciones)
    with col_m2:
        st.metric("Aprobadas", aprobadas, delta=tasa_aprobacion_str)
    with col_m3:
        st.metric("Descartadas", descartadas, delta=tasa_descarte_str, delta_color="inverse")
    with col_m4:
        st.metric("En Negociación", negociacion, delta=tasa_negociacion_str)
    with col_m5:
        st.metric("Anuladas", anuladas, delta=tasa_anulada_str, delta_color="off")
    # -------------------------------------
    st.divider() # Añadir separador

    col1_viz, col2_viz = st.columns(2)
    with col1_viz:
        st.markdown("#### Distribución por Estado")
        # --- IMPLEMENTACIÓN GRÁFICO PIE --- 
        if 'estado_nombre' in df_filtrado.columns:
            counts = df_filtrado['estado_nombre'].value_counts()
            fig_pie = px.pie(values=counts.values, names=counts.index,
                             title='Distribución de Estados',
                             color=counts.index,
                             color_discrete_map=COLOR_MAP_ESTADO, # Usar mapa de colores
                             hole=0.4)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label',
                                  hovertemplate='%{label}<br>%{value} cotizaciones<br>%{percent}')
            # TODO: Aplicar CHART_THEME si se define
            # fig_pie.update_layout(CHART_THEME)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.warning("Columna 'estado_nombre' no disponible para gráfico.")
        # -----------------------------------


    with col2_viz:
        st.markdown("#### Tendencia Temporal (Semanal)")
        # TODO: Implementar gráfico de línea (px.line)
        if 'fecha_creacion' in df_filtrado.columns and 'id' in df_filtrado.columns:
            # Agrupar por semana y estado
            df_temporal_estado = df_filtrado.copy()
            df_temporal_estado['semana'] = df_temporal_estado['fecha_creacion'].dt.strftime('%Y-W%U')
            tendencia_semanal_estado = df_temporal_estado.groupby(['semana', 'estado_nombre'])['id'].count().reset_index(name='cantidad')

            fig_line = px.line(tendencia_semanal_estado,
                               x='semana', y='cantidad', color='estado_nombre',
                               title='Cotizaciones por Semana y Estado',
                               markers=True,
                               color_discrete_map=COLOR_MAP_ESTADO) # Usar mapa de colores
            fig_line.update_layout(xaxis_title="Semana", yaxis_title="Número de Cotizaciones", legend_title="Estado")
            # TODO: Aplicar CHART_THEME si se define
            # fig_line.update_layout(CHART_THEME)
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.warning("Columnas 'fecha_creacion' o 'id' no disponibles para gráfico temporal.")

    st.divider()
    st.markdown("### Detalle de Cotizaciones")

    # Seleccionar columnas relevantes y renombrar si es necesario
    columnas_mostrar = ['numero_cotizacion', 'fecha_creacion', 'estado_nombre',
                        'cliente_nombre', 'comercial_nombre', 'motivo_rechazo_nombre']
    columnas_existentes = [col for col in columnas_mostrar if col in df_filtrado.columns]

    if columnas_existentes:
        df_display = df_filtrado[columnas_existentes].copy()
        # Formatear fecha si existe
        if 'fecha_creacion' in df_display.columns:
            df_display['fecha_creacion'] = pd.to_datetime(df_display['fecha_creacion']).dt.strftime('%Y-%m-%d')

        # Llenar NaN en motivo con '-' para display
        if 'motivo_rechazo_nombre' in df_display.columns:
             df_display['motivo_rechazo_nombre'] = df_display['motivo_rechazo_nombre'].fillna('-')

        # Ordenar por fecha más reciente
        sort_col = 'fecha_creacion' if 'fecha_creacion' in df_display.columns else columnas_existentes[0]
        st.dataframe(df_display.sort_values(by=sort_col, ascending=False), hide_index=True, use_container_width=True)

        # Botón de descarga con clave única y más específica
        st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
        csv = df_filtrado.to_csv(index=False).encode('utf-8')
        # Crear un sufijo único para la clave
        key_suffix = f"{fecha_inicio}_{fecha_fin}"
        if comercial_seleccionado_id: # Añadir ID de comercial si está filtrado
            key_suffix += f"_{comercial_seleccionado_id}"
        st.download_button(
            label="📥 Descargar Datos Filtrados (CSV)",
            data=csv,
            file_name=f"dashboard_data_{fecha_inicio}_to_{fecha_fin}.csv",
            mime="text/csv",
            key=f"download_dashboard_csv_{key_suffix}" # Usar el sufijo dinámico
        )
    else:
        st.warning("No hay columnas suficientes para mostrar el detalle.")

    st.divider()

    # --- INICIO: Análisis de Recotizaciones ---
    if 'es_recotizacion' in df_filtrado.columns:
        st.markdown("### Análisis de Recotizaciones")
        col_recot1, col_recot2 = st.columns(2)

        with col_recot1:
            recot_counts = df_filtrado['es_recotizacion'].value_counts()
            recot_map = {True: 'Recotizaciones', False: 'Nuevas'}
            recot_data = pd.DataFrame({
                'Tipo': recot_counts.index.map(recot_map),
                'Cantidad': recot_counts.values
            })

            fig_recot_pie = px.pie(recot_data, values='Cantidad', names='Tipo',
                                 title='Nuevas vs. Recotizaciones',
                                 color='Tipo',
                                 color_discrete_map={'Recotizaciones': '#f1c40f', 'Nuevas': '#3498db'},
                                 hole=0.4)
            fig_recot_pie.update_traces(textposition='inside', textinfo='percent+label',
                                      hovertemplate='%{label}<br>%{value}<br>%{percent}')
            # TODO: Aplicar CHART_THEME
            st.plotly_chart(fig_recot_pie, use_container_width=True)

        with col_recot2:
            df_recotizaciones_solo = df_filtrado[df_filtrado['es_recotizacion'] == True]
            total_recot = len(df_recotizaciones_solo)
            aprobadas_recot = len(df_recotizaciones_solo[df_recotizaciones_solo['estado_nombre'] == 'Aprobada'])
            tasa_exito_recot = (aprobadas_recot / total_recot * 100) if total_recot > 0 else 0

            st.metric("Tasa Éxito Recotizaciones", f"{tasa_exito_recot:.1f}%",
                      help="Porcentaje de recotizaciones que fueron aprobadas.")

            if 'cliente_nombre' in df_recotizaciones_solo.columns and not df_recotizaciones_solo.empty:
                recot_por_cliente = df_recotizaciones_solo.groupby('cliente_nombre')['id'].count().mean()
                st.metric("Promedio Recot./Cliente", f"{recot_por_cliente:.1f}",
                          help="Número promedio de recotizaciones por cliente (entre clientes con recot.)")
            else:
                 st.caption("No hay datos de cliente para calcular promedio.")

            st.divider()
    else:
        st.warning("⚠️ Análisis de Recotizaciones no disponible. La columna 'es_recotizacion' no se encuentra en los datos cargados. Contacta al administrador para corregir esto en la base de datos o ajustar DBManager.")
        st.divider()
    # --- FIN: Análisis de Recotizaciones ---

    # --- INICIO: Análisis por Cliente ---
    st.markdown("### Análisis por Cliente")
    if 'cliente_nombre' in df_filtrado.columns:
        col_cli1, col_cli2 = st.columns(2)

        # Gráficos de Recotizaciones y Nuevas por Cliente (AÑADIDOS)
        if 'es_recotizacion' in df_filtrado.columns:
            with col_cli1:
                df_recot = df_filtrado[df_filtrado['es_recotizacion'] == True]
                if not df_recot.empty:
                    top_recot_cli = df_recot['cliente_nombre'].value_counts().nlargest(5)
                    if not top_recot_cli.empty:
                        fig_cli_recot = px.bar(top_recot_cli, x=top_recot_cli.index, y=top_recot_cli.values,
                                             title='Top 5 Clientes (Más Recotizaciones)',
                                             labels={'index': 'Cliente', 'y': 'Cantidad'},
                                             color_discrete_sequence=['#f1c40f'])
                        fig_cli_recot.update_layout(showlegend=False)
                        st.plotly_chart(fig_cli_recot, use_container_width=True)
                    else:
                        st.info("No hay datos de recotizaciones por cliente.")
                else:
                    st.info("No hay recotizaciones en el período.")

            with col_cli2:
                df_nuevas = df_filtrado[df_filtrado['es_recotizacion'] == False]
                if not df_nuevas.empty:
                    top_nuevas_cli = df_nuevas['cliente_nombre'].value_counts().nlargest(5)
                    if not top_nuevas_cli.empty:
                        fig_cli_nuevas = px.bar(top_nuevas_cli, x=top_nuevas_cli.index, y=top_nuevas_cli.values,
                                              title='Top 5 Clientes (Más Cotizaciones Nuevas)',
                                              labels={'index': 'Cliente', 'y': 'Cantidad'},
                                              color_discrete_sequence=['#3498db'])
                        fig_cli_nuevas.update_layout(showlegend=False)
                        st.plotly_chart(fig_cli_nuevas, use_container_width=True)
                    else:
                        st.info("No hay datos de cotizaciones nuevas por cliente.")
                else:
                    st.info("No hay cotizaciones nuevas en el período.")

            st.divider() # Separador antes de los otros gráficos de cliente
        else:
            st.info("Los gráficos de clientes por tipo de cotización no están disponibles debido a que la columna 'es_recotizacion' no está presente en los datos.")

        # Gráficos de Total y Tasa de Aprobación (EXISTENTES)
        col_cli_tot, col_cli_tasa = st.columns(2)
        with col_cli_tot:
            # Top 5 Clientes por Total Cotizaciones
            top_clientes_total = df_filtrado['cliente_nombre'].value_counts().nlargest(5)
            if not top_clientes_total.empty:
                fig_cli_total = px.bar(top_clientes_total, x=top_clientes_total.index, y=top_clientes_total.values,
                                     title='Top 5 Clientes (Total Cotizaciones)',
                                     labels={'index': 'Cliente', 'y': 'Cantidad'},
                                     color_discrete_sequence=['#2ecc71'])
                fig_cli_total.update_layout(showlegend=False)
                # TODO: Aplicar CHART_THEME
                st.plotly_chart(fig_cli_total, use_container_width=True)
            else:
                st.info("No hay suficientes datos de clientes.")

        with col_cli_tasa:
            # Top 5 Clientes por Tasa de Aprobación (con min 2 cotizaciones)
            cliente_stats = df_filtrado.groupby('cliente_nombre').agg(
                total_cotizaciones=('id', 'count'),
                aprobadas=('estado_nombre', lambda x: (x == 'Aprobada').sum())
            ).reset_index()
            cliente_stats = cliente_stats[cliente_stats['total_cotizaciones'] >= 2]
            if not cliente_stats.empty:
                 cliente_stats['tasa_aprobacion'] = (cliente_stats['aprobadas'] / cliente_stats['total_cotizaciones'] * 100)
                 top_clientes_tasa = cliente_stats.nlargest(5, 'tasa_aprobacion')

                 if not top_clientes_tasa.empty:
                     fig_cli_tasa = px.bar(top_clientes_tasa, x='cliente_nombre', y='tasa_aprobacion',
                                          title='Top 5 Clientes (Tasa Aprobación > 1 cot.)',
                                          labels={'cliente_nombre': 'Cliente', 'tasa_aprobacion': 'Tasa Aprob. (%)'},
                                          color_discrete_sequence=['#5DADE2'])
                     fig_cli_tasa.update_layout(yaxis_ticksuffix="%", showlegend=False)
                     # TODO: Aplicar CHART_THEME
                     st.plotly_chart(fig_cli_tasa, use_container_width=True)
                 else:
                      st.info("No hay clientes con >= 2 cotizaciones para calcular tasa.")
            else:
                 st.info("No hay clientes con >= 2 cotizaciones para calcular tasa.")
        st.divider()
    else:
        st.warning("Columna 'cliente_nombre' no encontrada para análisis.")
    # --- FIN: Análisis por Cliente ---

    # --- INICIO: KPIs Adicionales ---
    st.markdown("### KPIs Adicionales")
    if not df_filtrado.empty and 'fecha_creacion' in df_filtrado.columns:
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)

        with col_kpi1:
            # Promedio de cotizaciones por día
            if len(df_filtrado['fecha_creacion']) > 0:
                min_date = df_filtrado['fecha_creacion'].min().date()
                max_date = df_filtrado['fecha_creacion'].max().date()
                dias_periodo = (max_date - min_date).days + 1
                promedio_diario = len(df_filtrado) / dias_periodo if dias_periodo > 0 else len(df_filtrado)
                st.metric(
                    "Promedio Diario Cot.",
                    f"{promedio_diario:.1f}",
                    help="Promedio de cotizaciones generadas por día en el período."
                )
            else:
                st.metric("Promedio Diario Cot.", "N/A")

        with col_kpi2:
            # Tiempo promedio de decisión (simplificado: duración del periodo para decididas)
            # Una métrica más precisa requeriría fecha de decisión
            df_decididas = df_filtrado[df_filtrado['estado_nombre'] != 'En Negociación']
            # Excluimos también 'Anulada' para el rango de decisión
            estados_finales_excluir = ['En Negociación', 'Anulada']
            df_decididas = df_filtrado[~df_filtrado['estado_nombre'].isin(estados_finales_excluir)]
            if not df_decididas.empty and len(df_decididas['fecha_creacion']) > 0:
                min_date_dec = df_decididas['fecha_creacion'].min().date()
                max_date_dec = df_decididas['fecha_creacion'].max().date()
                tiempo_decision_aprox = (max_date_dec - min_date_dec).days
                st.metric(
                    "Rango Decisión (aprox)",
                    f"{tiempo_decision_aprox} días",
                    help="Rango de días entre la primera y última cotización decidida (Aprob/Rechaz) en el período."
                )
            else:
                st.metric("Rango Decisión (aprox)", "N/A")

        with col_kpi3:
            # Efectividad del comercial (si aplica)
            # Solo se muestra si se filtró por un comercial específico
            if user_role == 'administrador' and comercial_seleccionado_id:
                aprobadas_comercial = len(df_filtrado[df_filtrado['estado_nombre'] == 'Aprobada'])
                total_comercial = len(df_filtrado)
                efectividad = (aprobadas_comercial / total_comercial * 100) if total_comercial > 0 else 0
                # Obtener nombre del comercial para el título (opcional, requiere consulta extra o pasarlo)
                # comercial_nombre_sel = opciones_comercial.get(comercial_seleccionado_id, "Seleccionado")
                st.metric(
                    f"Efectividad Comercial",
                    f"{efectividad:.1f}%",
                    help=f"% de cotizaciones aprobadas para el comercial seleccionado."
                )
            elif user_role == 'comercial': # Para el comercial logueado
                 aprobadas_prop = len(df_filtrado[df_filtrado['estado_nombre'] == 'Aprobada'])
                 total_prop = len(df_filtrado)
                 efectividad_prop = (aprobadas_prop / total_prop * 100) if total_prop > 0 else 0
                 st.metric(
                    "Mi Efectividad",
                    f"{efectividad_prop:.1f}%",
                    help="% de mis cotizaciones que fueron aprobadas."
                 )
            # else: # No mostrar si es admin viendo 'Todos'
            #     st.metric("Efectividad Comercial", "N/A", help="Filtre por un comercial específico.")

        st.divider()
    else:
        st.info("No hay datos suficientes para calcular KPIs adicionales.")
    # --- FIN: KPIs Adicionales ---

    # --- INICIO: Análisis de Descartes ---
    st.markdown("### Análisis de Descartes")
    df_descartadas = df_filtrado[df_filtrado['estado_nombre'] == 'Descartada']
    if not df_descartadas.empty:
        col_rech1, col_rech2 = st.columns(2)
        
        with col_rech1:
            # Verificar que tenemos la columna necesaria
            if 'motivo_rechazo_nombre' in df_descartadas.columns:
                # Mapeo correcto de motivos de rechazo (completamos el mapa durante la carga de datos)
                motivos_counts = df_descartadas['motivo_rechazo_nombre'].fillna('No especificado').value_counts()
                
                if not motivos_counts.empty:
                    fig_rech_pie = px.pie(values=motivos_counts.values, names=motivos_counts.index,
                                       title='Distribución Motivos de Descarte',
                                       color_discrete_sequence=px.colors.qualitative.Pastel,
                                       hole=0.4)
                    fig_rech_pie.update_traces(textposition='inside', textinfo='percent+label',
                                          hovertemplate='%{label}<br>%{value}<br>%{percent}')
                    st.plotly_chart(fig_rech_pie, use_container_width=True)
                else:
                    st.info("No hay datos de motivos de descarte disponibles.")
            else:
                # Intentar usar id_motivo_rechazo directamente si está disponible
                if 'id_motivo_rechazo' in df_descartadas.columns:
                    # Intentar obtener los motivos de rechazo desde la base de datos
                    try:
                        motivos_db = db.get_motivos_rechazo()
                        motivos_map = {m.id: m.motivo for m in motivos_db}
                        
                        # Crear la columna temporal para el gráfico
                        df_descartadas['temp_motivo'] = df_descartadas['id_motivo_rechazo'].map(motivos_map).fillna('No especificado')
                        motivos_counts = df_descartadas['temp_motivo'].value_counts()
                        
                        if not motivos_counts.empty:
                            fig_rech_pie = px.pie(values=motivos_counts.values, names=motivos_counts.index,
                                              title='Distribución Motivos de Descarte',
                                              color_discrete_sequence=px.colors.qualitative.Pastel,
                                              hole=0.4)
                            fig_rech_pie.update_traces(textposition='inside', textinfo='percent+label',
                                                  hovertemplate='%{label}<br>%{value}<br>%{percent}')
                            st.plotly_chart(fig_rech_pie, use_container_width=True)
                        else:
                            st.info("No hay datos de motivos de descarte disponibles.")
                    except Exception as e:
                        st.warning(f"Error al generar gráfico de motivos de descarte: {e}")
                else:
                    st.warning("No se encuentra la columna para motivos de descarte.")

            # Tasa de Descarte General
            if total_cotizaciones > 0:
                tasa_descarte_gen = (len(df_descartadas) / total_cotizaciones) * 100
                st.metric(
                    "Tasa Descarte General",
                    f"{tasa_descarte_gen:.1f}%",
                    delta_color="inverse",
                    help="% de cotizaciones descartadas sobre el total filtrado."
                )
            else:
                st.metric("Tasa Descarte General", "0.0%", delta_color="inverse")

        with col_rech2:
            # Cliente con más descartes
            if 'cliente_nombre' in df_descartadas.columns:
                rechazos_por_cliente = df_descartadas['cliente_nombre'].value_counts()
                if not rechazos_por_cliente.empty:
                     cliente_mas_rechazos = rechazos_por_cliente.idxmax()
                     num_mas_rechazos = rechazos_por_cliente.max()
                     st.metric("Cliente con Más Descartes", cliente_mas_rechazos, f"{num_mas_rechazos} descartes")
                else:
                     st.caption("No hay datos de clientes descartados.")

            # Motivo más común
            if not motivos_counts.empty:
                motivo_comun = motivos_counts.idxmax()
                num_motivo_comun = motivos_counts.max()
                st.metric("Motivo de Descarte Más Común", motivo_comun, f"{num_motivo_comun} casos")
            else:
                 st.caption("No hay datos de motivos de descarte.")

    elif df_descartadas.empty:
        st.info("No hay cotizaciones descartadas en el período seleccionado.")
    else: # Hay descartes pero no la columna motivo
        st.warning("Columna 'motivo_rechazo_nombre' no encontrada para análisis de descartes.")
        # Podrías mostrar métricas generales de descarte aquí si lo deseas

    st.divider()
    # --- FIN: Análisis de Descartes ---

    st.subheader("📊 Análisis de Cotizaciones Perdidas")

    perdidas_df = df_filtrado[df_filtrado['estado_nombre'] == 'Perdida'].copy()
    motivos_counts = pd.Series(dtype='int') # <-- INICIALIZAR AQUÍ

    if perdidas_df.empty:
        st.info("No hay cotizaciones perdidas para analizar en el período seleccionado.")
    else:
        col_perd1, col_perd2 = st.columns(2)
        
        with col_perd1:
            # Verificar que tenemos la columna necesaria
            if 'motivo_rechazo_nombre' in perdidas_df.columns:
                # Mapeo correcto de motivos de rechazo (completamos el mapa durante la carga de datos)
                motivos_counts = perdidas_df['motivo_rechazo_nombre'].fillna('No especificado').value_counts()
                
                if not motivos_counts.empty:
                    fig_perd_pie = px.pie(values=motivos_counts.values, names=motivos_counts.index,
                                       title='Distribución Motivos de Pérdida',
                                       color_discrete_sequence=px.colors.qualitative.Set2,
                                       hole=0.4)
                    fig_perd_pie.update_traces(textposition='inside', textinfo='percent+label',
                                          hovertemplate='%{label}<br>%{value}<br>%{percent}')
                    st.plotly_chart(fig_perd_pie, use_container_width=True)
                else:
                    st.info("No hay datos de motivos de pérdida disponibles.")
            elif 'id_motivo_rechazo' in perdidas_df.columns:
                # Intentar usar id_motivo_rechazo directamente si está disponible
                try:
                    motivos_db = db.get_motivos_rechazo()
                    motivos_map = {m.id: m.motivo for m in motivos_db}
                    
                    # Crear la columna temporal para el gráfico
                    perdidas_df['temp_motivo'] = perdidas_df['id_motivo_rechazo'].map(motivos_map).fillna('No especificado')
                    motivos_counts = perdidas_df['temp_motivo'].value_counts()
                    
                    if not motivos_counts.empty:
                        fig_perd_pie = px.pie(values=motivos_counts.values, names=motivos_counts.index,
                                          title='Distribución Motivos de Pérdida',
                                          color_discrete_sequence=px.colors.qualitative.Set2,
                                          hole=0.4)
                        fig_perd_pie.update_traces(textposition='inside', textinfo='percent+label',
                                              hovertemplate='%{label}<br>%{value}<br>%{percent}')
                        st.plotly_chart(fig_perd_pie, use_container_width=True)
                    else:
                        st.info("No hay datos de motivos de pérdida disponibles.")
                except Exception as e:
                    st.warning(f"Error al generar gráfico de motivos de pérdida: {e}")
            else:
                st.warning("No se encuentra la columna para motivos de pérdida.")

            # Tasa de Pérdida General
            if total_cotizaciones > 0:
                tasa_perdida_gen = (len(perdidas_df) / total_cotizaciones) * 100
                st.metric(
                    "Tasa de Cotizaciones Perdidas",
                    f"{tasa_perdida_gen:.1f}%",
                    delta_color="inverse",
                    help="% de cotizaciones perdidas sobre el total filtrado."
                )
            else:
                st.metric("Tasa de Cotizaciones Perdidas", "0.0%", delta_color="inverse")

        with col_perd2:
            # Cliente con más pérdidas
            if 'cliente_nombre' in perdidas_df.columns:
                perdidas_por_cliente = perdidas_df['cliente_nombre'].value_counts()
                if not perdidas_por_cliente.empty:
                     cliente_mas_perdidas = perdidas_por_cliente.idxmax()
                     num_mas_perdidas = perdidas_por_cliente.max()
                     st.metric("Cliente con Más Pérdidas", cliente_mas_perdidas, f"{num_mas_perdidas} casos")
                else:
                     st.caption("No hay datos de clientes con cotizaciones perdidas.")

            # Motivo más común de pérdida
            if 'motivo_rechazo_nombre' in perdidas_df.columns and not motivos_counts.empty:
                motivo_comun = motivos_counts.idxmax()
                num_motivo_comun = motivos_counts.max()
                st.metric("Motivo de Pérdida Más Común", motivo_comun, f"{num_motivo_comun} casos")
            else:
                 st.caption("No hay datos de motivos de pérdida.")
                 
        # Tendencia temporal de cotizaciones perdidas
        st.subheader("Tendencia de Cotizaciones Perdidas")
        if 'fecha_creacion' in perdidas_df.columns and not perdidas_df.empty:
            # Agrupar por mes
            perdidas_df['mes'] = perdidas_df['fecha_creacion'].dt.strftime('%Y-%m')
            tendencia_mensual = perdidas_df.groupby('mes')['id'].count().reset_index(name='cantidad')
            
            fig_tendencia = px.line(tendencia_mensual, x='mes', y='cantidad', 
                                 title='Evolución Mensual de Cotizaciones Perdidas',
                                 markers=True,
                                 color_discrete_sequence=['#FF5733'])
            fig_tendencia.update_layout(xaxis_title="Mes", yaxis_title="Número de Cotizaciones")
            st.plotly_chart(fig_tendencia, use_container_width=True)
            
        # Top clientes con cotizaciones perdidas
        if 'cliente_nombre' in perdidas_df.columns and not perdidas_df.empty:
            st.subheader("Top Clientes con Cotizaciones Perdidas")
            top_perdidas_clientes = perdidas_df['cliente_nombre'].value_counts().nlargest(5)
            
            if not top_perdidas_clientes.empty:
                fig_cli_perdidas = px.bar(top_perdidas_clientes, 
                                       x=top_perdidas_clientes.index, 
                                       y=top_perdidas_clientes.values,
                                       title='Top 5 Clientes con Más Cotizaciones Perdidas',
                                       labels={'index': 'Cliente', 'y': 'Cantidad'},
                                       color_discrete_sequence=['#FF5733'])
                fig_cli_perdidas.update_layout(showlegend=False)
                st.plotly_chart(fig_cli_perdidas, use_container_width=True)
            else:
                st.info("No hay suficientes datos para mostrar clientes con cotizaciones perdidas.")

    st.divider()  # Separador visual


# Para pruebas locales (opcional)
if __name__ == "__main__":
    # Simular inicialización de session_state si es necesario para pruebas
    if 'db' not in st.session_state:
        # Aquí necesitarías inicializar una instancia de DBManager para probar
        # from supabase import create_client
        # st.session_state.supabase = create_client(...)
        # st.session_state.db = DBManager(st.session_state.supabase)
        st.warning("Ejecutando en modo local: Se requiere inicialización manual de DBManager.")
    # Simular rol
    st.session_state.usuario_rol = 'administrador' # o 'comercial'
    st.session_state.user_id = 'some_user_id_for_testing'

    show_dashboard() 