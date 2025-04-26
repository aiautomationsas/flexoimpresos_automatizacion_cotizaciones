from datetime import datetime
import streamlit as st
from supabase import create_client
from typing import Optional, Dict, Any, Tuple
import pandas as pd

# Luego las importaciones del proyecto, agrupadas por funcionalidad
# Auth y DB
from src.auth.auth_manager import AuthManager
from src.data.database import DBManager

# Models y Constants
from src.data.models import Cotizacion, Cliente, ReferenciaCliente
from src.config.constants import (
    RENTABILIDAD_MANGAS, RENTABILIDAD_ETIQUETAS,
    DESPERDICIO_MANGAS, DESPERDICIO_ETIQUETAS,
    VELOCIDAD_MAQUINA_NORMAL, VELOCIDAD_MAQUINA_MANGAS_7_TINTAS,
    GAP_AVANCE_ETIQUETAS, GAP_AVANCE_MANGAS,
    GAP_PISTAS_ETIQUETAS, GAP_PISTAS_MANGAS,
    FACTOR_ANCHO_MANGAS, INCREMENTO_ANCHO_MANGAS,
    ANCHO_MAXIMO_LITOGRAFIA, ANCHO_MAXIMO_MAQUINA
)

# Utils y PDF
from src.utils.session_manager import SessionManager
from src.pdf.pdf_generator import CotizacionPDF, MaterialesPDF

# Calculadoras
from src.logic.calculators.calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from src.logic.calculators.calculadora_litografia import CalculadoraLitografia

# UI Components - mover estas importaciones al final
from src.ui.auth_ui import handle_authentication, show_login, show_logout_button
from src.ui.calculator_view import show_calculator, show_quote_results, show_quote_summary
from src.ui.calculator.client_section import mostrar_seccion_cliente
from src.ui.calculator.product_section import mostrar_formulario_producto

# Configuración de página
st.set_page_config(
    page_title="Sistema de Cotización - Flexo Impresos",
    page_icon="🏭",
    layout="wide"
)

# Cargar CSS
try:
    with open("static/styles.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
except FileNotFoundError:
    st.warning("Archivo CSS no encontrado. La aplicación funcionará con estilos por defecto.")

def initialize_session_state():
    """Inicializa el estado básico de la sesión si no existe"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    
    if 'current_view' not in st.session_state:
        st.session_state.current_view = 'calculator'  # Valores posibles: 'calculator', 'quote_results'
    
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    if 'calculation_history' not in st.session_state:
        st.session_state.calculation_history = []

def initialize_services():
    """Inicializa los servicios principales (Supabase, Auth, DB) si no existen"""
    try:
        if 'supabase' not in st.session_state:
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
            st.session_state.supabase = create_client(supabase_url, supabase_key)
        
        if 'auth_manager' not in st.session_state:
            st.session_state.auth_manager = AuthManager(st.session_state.supabase)
            st.session_state.auth_manager.initialize_session_state()
        
        if 'db' not in st.session_state:
            st.session_state.db = DBManager(st.session_state.supabase)
            
    except Exception as e:
        st.error(f"Error crítico inicializando servicios: {e}")
        st.stop()

def load_initial_data() -> Dict[str, Any]:
    """
    Carga los datos iniciales necesarios para la calculadora.
    
    Returns:
        Dict con los datos necesarios para la operación de la calculadora
    """
    try:
        db = st.session_state.db
        data = {
            'materiales': db.get_materiales(),
            'acabados': db.get_acabados(),
            'tipos_producto': db.get_tipos_producto(),
            'clientes': db.get_clientes(),
            'formas_pago': db.get_formas_pago(),
            'tipos_grafado': db.get_tipos_grafado()
        }
        
        # Verificar que se obtuvieron todos los datos necesarios
        missing_data = [k for k, v in data.items() if not v]
        if missing_data:
            st.error(f"No se pudieron cargar los siguientes datos: {', '.join(missing_data)}")
            return {}
            
        return data
        
    except Exception as e:
        st.error(f"Error cargando datos iniciales: {str(e)}")
        if st.session_state.get('usuario_rol') == 'administrador':
            st.exception(e)
        return {}

def handle_calculation(form_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Maneja el proceso de cálculo de la cotización.
    
    Args:
        form_data: Diccionario con los datos del formulario
        
    Returns:
        Optional[Dict[str, Any]]: Resultados del cálculo o None si hay error
    """
    try:
        # Validar datos necesarios
        required_fields = ['ancho', 'avance', 'pistas', 'num_tintas', 'num_paquetes', 
                         'material_id', 'es_manga', 'escalas']
        missing_fields = [field for field in required_fields if field not in form_data]
        
        if missing_fields:
            st.error(f"Faltan los siguientes campos requeridos: {', '.join(missing_fields)}")
            return None
            
        if not form_data['escalas']:
            st.error("Debe seleccionar al menos una escala para cotizar")
            return None
        
        # Debug de form_data
        print("\n=== DEBUG FORM DATA ===")
        print("Valores recibidos del formulario:")
        for key, value in form_data.items():
            print(f"{key}: {value} (tipo: {type(value)})")
        
        # Crear instancia de calculadora
        calculadora = CalculadoraCostosEscala(ancho_maximo=ANCHO_MAXIMO_MAQUINA)
        
        # Preparar datos para el cálculo
        es_manga = form_data['es_manga']
        
        # Obtener material y acabado de la base de datos
        material = st.session_state.db.get_material(form_data['material_id'])
        acabado = st.session_state.db.get_acabado(form_data.get('acabado_id')) if not es_manga else None
        
        # Procesar troquel_existe explícitamente
        troquel_existe = form_data.get('tiene_troquel')
        print(f"\nValor de troquel_existe antes de procesar: {troquel_existe} (tipo: {type(troquel_existe)})")
        if isinstance(troquel_existe, str):
            troquel_existe = troquel_existe.lower() == 'true'
        else:
            troquel_existe = bool(troquel_existe)
        print(f"Valor de troquel_existe después de procesar: {troquel_existe}")
        
        # Ajustar el ancho si es manga
        ancho_base = form_data['ancho']
        if es_manga:
            ancho_ajustado = (ancho_base * FACTOR_ANCHO_MANGAS) + INCREMENTO_ANCHO_MANGAS
            print(f"\n=== AJUSTE DE ANCHO PARA MANGA ===")
            print(f"Ancho original: {ancho_base}")
            print(f"Factor manga: {FACTOR_ANCHO_MANGAS}")
            print(f"Incremento manga: {INCREMENTO_ANCHO_MANGAS}")
            print(f"Ancho ajustado: ({ancho_base} * {FACTOR_ANCHO_MANGAS}) + {INCREMENTO_ANCHO_MANGAS} = {ancho_ajustado}")
        else:
            ancho_ajustado = ancho_base
        
        # Usar las escalas definidas por el usuario
        datos_escala = DatosEscala(
            escalas=form_data['escalas'],  # Usar las escalas seleccionadas
            pistas=form_data['pistas'],
            ancho=ancho_ajustado,  # Usar el ancho ajustado
            avance=form_data['avance'],
            avance_total=form_data['avance'] + (GAP_AVANCE_MANGAS if es_manga else GAP_AVANCE_ETIQUETAS),
            desperdicio=0,  # Se calculará en la función
            velocidad_maquina=VELOCIDAD_MAQUINA_MANGAS_7_TINTAS if (es_manga and form_data['num_tintas'] >= 7) 
                            else VELOCIDAD_MAQUINA_NORMAL,
            rentabilidad=RENTABILIDAD_MANGAS if es_manga else RENTABILIDAD_ETIQUETAS,
            porcentaje_desperdicio=DESPERDICIO_MANGAS if es_manga else DESPERDICIO_ETIQUETAS,
            valor_metro=material.valor if material else 0.0,
            troquel_existe=troquel_existe,  # Usar el valor procesado
            planchas_por_separado=form_data.get('planchas_separadas', False)  # También actualizar esto
        )
        
        # Calcular área de etiqueta usando la calculadora
        area_result = calculadora.calcular_area_etiqueta(datos_escala, form_data['num_tintas'], es_manga)
        if 'error' in area_result:
            st.error(f"Error calculando área: {area_result['error']}")
            return None
        datos_escala.set_area_etiqueta(area_result['area'])
        
        # Realizar cálculos
        resultados = calculadora.calcular_costos_por_escala(
            datos=datos_escala,
            num_tintas=form_data['num_tintas'],
            valor_plancha=form_data.get('valor_plancha', 0),
            valor_troquel=form_data.get('valor_troquel', 0),
            valor_material=material.valor if material else 0,
            valor_acabado=acabado.valor if acabado else 0,
            es_manga=es_manga
        )
        
        if resultados:
            # Guardar resultados en session_state
            st.session_state.current_calculation = {
                'form_data': form_data,
                'results': resultados,
                'is_manga': es_manga,
                'timestamp': datetime.now().isoformat()
            }
            
            # Cambiar vista y forzar rerun
            st.session_state.current_view = 'quote_results'
            st.rerun()
            
        return resultados
        
    except Exception as e:
        st.error(f"Error en el cálculo: {str(e)}")
        if st.session_state.get('usuario_rol') == 'administrador':
            st.exception(e)
        return None

def show_navigation():
    """Muestra la barra de navegación con las diferentes opciones"""
    st.sidebar.markdown("### Navegación")
    
    options = {
        'calculator': "Calculadora",
        'quote_history': "Historial de Cotizaciones",
        'reports': "Reportes"
    }
    
    selected = st.sidebar.radio("Ir a:", list(options.values()))
    
    # Actualizar vista actual basado en la selección
    st.session_state.current_view = next(k for k, v in options.items() if v == selected)

def initialize_session():
    """Inicializa el estado de la sesión después del login"""
    if 'user' not in st.session_state:
        return False
        
    user_id = st.session_state.user_id
    db = st.session_state.db
    
    # Cargar perfil y permisos
    perfil = db.get_perfil(user_id)
    if not perfil:
        return False
        
    # Guardar información crítica en session_state
    st.session_state.usuario_rol = perfil.get('rol_nombre')
    st.session_state.comercial_id = user_id
    st.session_state.perfil_usuario = perfil
    
    return True

def get_filtered_clients():
    """Obtiene clientes filtrados por comercial si no es admin"""
    if st.session_state.usuario_rol == 'administrador':
        return st.session_state.db.get_clientes()
    return st.session_state.db.get_clientes_by_comercial(
        st.session_state.comercial_id
    )

def mostrar_calculadora():
    """Vista principal de la calculadora"""
    if not initialize_session():
        st.error("Error de inicialización")
        return
        
    # Mostrar información del comercial (no editable)
    st.write(f"**Comercial:** {st.session_state.perfil_usuario['nombre']}")
    
    # Selector de cliente (filtrado por comercial)
    clientes = get_filtered_clients()
    cliente_seleccionado = st.selectbox(
        "Cliente",
        options=clientes,
        format_func=lambda x: x.nombre
    )
    
    if cliente_seleccionado:
        # Campo para la referencia
        referencia = st.text_input(
            "Referencia del cliente",
            help="Ingrese una descripción o referencia para esta cotización"
        )
        
        if referencia:
            st.session_state.referencia_actual = referencia
            
            # Crear formulario para los datos del producto
            with st.form("formulario_producto"):
                # Mostrar el formulario del producto
                datos_producto = mostrar_formulario_producto(cliente_seleccionado)
                
                # Botón de cálculo
                if st.form_submit_button("Calcular"):
                    if datos_producto:
                        # Realizar cálculos
                        resultados = handle_calculation(datos_producto)
                        if resultados:
                            # Guardar resultados y mostrarlos
                            st.session_state.current_calculation = {
                                'cliente': cliente_seleccionado,
                                'referencia': referencia,
                                'form_data': datos_producto,
                                'results': resultados,
                                'timestamp': datetime.now().isoformat()
                            }
                            st.session_state.current_view = 'quote_results'
                            st.rerun()

def main():
    """Función principal que orquesta el flujo de la aplicación"""
    # Inicializar servicios primero
    initialize_services()
    
    # Inicializar el estado de la sesión
    SessionManager.init_session()
    
    # Verificar autenticación
    if not st.session_state.authenticated:
        show_login()
        return
    
    # Mostrar botón de logout en el sidebar si está autenticado
    show_logout_button()
    
    # Mostrar mensajes pendientes
    if st.session_state.messages:
        for msg_type, message in st.session_state.messages:
            if msg_type == 'success':
                st.success(message)
            elif msg_type == 'error':
                st.error(message)
            else:
                st.info(message)
        SessionManager.clear_messages()
    
    # Mostrar la vista actual
    if st.session_state.current_view == 'calculator':
        mostrar_calculadora()
    elif st.session_state.current_view == 'quote_results':
        show_quote_results()
    elif st.session_state.current_view == 'quote_history':
        show_quote_history()
    elif st.session_state.current_view == 'reports':
        show_reports()

def show_quote_history():
    """Muestra el historial de cotizaciones"""
    st.subheader("Historial de Cotizaciones")
    
    if not st.session_state.calculation_history:
        st.info("No hay cotizaciones en el historial.")
        return
    
    for idx, calc in enumerate(reversed(st.session_state.calculation_history[-10:])):
        with st.expander(f"Cotización {len(st.session_state.calculation_history) - idx}", expanded=idx==0):
            show_quote_summary(calc['form_data'], calc['results'], calc['is_manga'])

def show_reports():
    """Muestra la sección de reportes"""
    st.subheader("Reportes y Análisis")
    st.info("Sección en desarrollo...")

def show_quote_results():
    """Muestra los resultados de la cotización calculada."""
    if 'current_calculation' not in st.session_state or not st.session_state.current_calculation:
        st.error("No hay resultados para mostrar. Por favor, realice un cálculo primero.")
        return

    calc = st.session_state.current_calculation
    
    st.markdown("## Resultados de la Cotización")
    
    # Información básica
    st.markdown("### Información General")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Tipo de Producto:** {'Manga' if calc['is_manga'] else 'Etiqueta'}")
        st.write(f"**Referencia:** {calc['form_data'].get('referencia', 'N/A')}")
        st.write(f"**Fecha:** {datetime.fromisoformat(calc['timestamp']).strftime('%Y-%m-%d %H:%M')}")
    
    # Mostrar resultados para cada escala
    st.markdown("### Resultados por Escala")
    
    # Crear tabla de resultados
    resultados_df = pd.DataFrame(calc['results'])
    resultados_df = resultados_df.rename(columns={
        'escala': 'Escala',
        'valor_unidad': 'Valor por Unidad',
        'metros': 'Metros',
        'tiempo_horas': 'Tiempo (horas)',
        'montaje': 'Montaje',
        'mo_y_maq': 'MO y Maquinaria',
        'tintas': 'Tintas',
        'papel_lam': 'Material',
        'desperdicio': 'Desperdicio'
    })
    
    # Formatear columnas numéricas
    formato_moneda = lambda x: f"${x:,.2f}"
    formato_numero = lambda x: f"{x:,.2f}"
    
    resultados_df['Valor por Unidad'] = resultados_df['Valor por Unidad'].apply(formato_moneda)
    resultados_df['Montaje'] = resultados_df['Montaje'].apply(formato_moneda)
    resultados_df['MO y Maquinaria'] = resultados_df['MO y Maquinaria'].apply(formato_moneda)
    resultados_df['Tintas'] = resultados_df['Tintas'].apply(formato_moneda)
    resultados_df['Material'] = resultados_df['Material'].apply(formato_moneda)
    resultados_df['Desperdicio'] = resultados_df['Desperdicio'].apply(formato_moneda)
    resultados_df['Metros'] = resultados_df['Metros'].apply(formato_numero)
    resultados_df['Tiempo (horas)'] = resultados_df['Tiempo (horas)'].apply(formato_numero)
    
    st.dataframe(resultados_df)
    
    # Botones de acción
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Nueva Cotización"):
            st.session_state.current_view = 'calculator'
            st.rerun()
    with col2:
        if st.button("Guardar Cotización"):
            # Aquí iría la lógica para guardar en la base de datos
            st.success("Cotización guardada exitosamente")
    with col3:
        if st.button("Generar PDF"):
            # Aquí iría la lógica para generar el PDF
            st.info("Funcionalidad de PDF en desarrollo")

if __name__ == "__main__":
    main()