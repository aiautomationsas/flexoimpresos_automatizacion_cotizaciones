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
            
        # Refuerzo: asegúrate de que las claves críticas existen
        for key in ['authenticated', 'user_id', 'usuario_rol', 'perfil_usuario']:
            if key not in st.session_state:
                st.session_state[key] = None if key != 'authenticated' else False
        
    except Exception as e:
        st.error(f"Error crítico inicializando servicios: {e}")
        st.stop()

@st.cache_data
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
            'tipos_grafado': db.get_tipos_grafado(),
            'adhesivos': db.get_adhesivos()
        }
        
        # Verificar que se obtuvieron todos los datos necesarios (excluding adhesives for now as they might be optional initially)
        required_data = ['materiales', 'acabados', 'tipos_producto', 'clientes', 'formas_pago', 'tipos_grafado']
        missing_data = [k for k in required_data if k not in data or not data[k]]
        if missing_data:
            st.error(f"No se pudieron cargar los siguientes datos requeridos: {', '.join(missing_data)}")
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
        
        # Debug de form_data y ajustes admin
        print("\n=== DEBUG FORM DATA ===")
        print("Valores recibidos del formulario:")
        for key, value in form_data.items():
            print(f"{key}: {value} (tipo: {type(value)})")
        
        if st.session_state.usuario_rol == 'administrador':
            print("\n=== DEBUG AJUSTES ADMIN ===")
            print(f"Ajustar Material: {st.session_state.get('ajustar_material')}, Valor: {st.session_state.get('valor_material_ajustado')}")
            print(f"Ajustar Troquel: {st.session_state.get('ajustar_troquel')}, Valor: {st.session_state.get('precio_troquel')}")
            print(f"Ajustar Planchas: {st.session_state.get('ajustar_planchas')}, Valor: {st.session_state.get('precio_planchas')}")
            print(f"Ajustar Rentabilidad: {st.session_state.get('rentabilidad_ajustada')}")
        
        # Crear instancia de calculadora
        calculadora = CalculadoraCostosEscala(ancho_maximo=ANCHO_MAXIMO_MAQUINA)
        
        # Preparar datos para el cálculo
        es_manga = form_data['es_manga']
        num_tintas = form_data['num_tintas']
        material_id = form_data['material_id']
        adhesivo_id = form_data.get('adhesivo_id')
        
        # Obtener material y acabado de la base de datos
        # REMOVED: material = st.session_state.db.get_material(material_id) # No longer needed for price
        acabado = st.session_state.db.get_acabado(form_data.get('acabado_id')) if not es_manga else None
        
        # --- Determinar Valor Material --- 
        valor_material_base = 0.0
        ID_SIN_ADHESIVO = 4 # Assuming ID 4 corresponds to "Sin adhesivo"

        if not es_manga and adhesivo_id:
            # Etiqueta con adhesivo: Buscar valor combinado
            print(f"Buscando valor para Material ID: {material_id}, Adhesivo ID: {adhesivo_id}")
            valor_combinado = st.session_state.db.get_material_adhesivo_valor(material_id, adhesivo_id)
            if valor_combinado is not None:
                valor_material_base = valor_combinado
                print(f"Valor combinado encontrado: {valor_material_base}")
            else:
                st.error(f"No se encontró precio para la combinación de Material ID {material_id} y Adhesivo ID {adhesivo_id}. Por favor, verifique la configuración.")
                return None # Stop calculation if price not found
        elif not es_manga and not adhesivo_id:
            # Etiqueta SIN adhesivo seleccionado - REQUERIDO?
            st.error("Para Etiquetas, debe seleccionar un Adhesivo.")
            # Alternative: Fetch base material price if adhesive is optional
            # material = st.session_state.db.get_material(material_id)
            # if material:
            #     valor_material_base = material.valor
            # else:
            #     st.error(f"Material base ID {material_id} no encontrado.")
            #     return None
            return None # Assuming adhesive is required for etiquetas for now
        elif es_manga:
            # Manga: Buscar valor usando el ID del material y el ID de "Sin adhesivo"
            print(f"Buscando valor para Material ID (Manga): {material_id}, Adhesivo ID: {ID_SIN_ADHESIVO}")
            valor_manga = st.session_state.db.get_material_adhesivo_valor(material_id, ID_SIN_ADHESIVO)
            if valor_manga is not None:
                valor_material_base = valor_manga
                print(f"Valor encontrado para manga: {valor_material_base}")
            else:
                st.error(f"No se encontró precio base para el Material de Manga ID {material_id} (con adhesivo 'Sin adhesivo'). Verifique la tabla material_adhesivo.")
                return None
        # --- Fin Determinar Valor Material ---

        # === Aplicar Ajustes Admin (si existen y están activos) ===
        valor_material = valor_material_base # Start with the fetched value
        if st.session_state.get('ajustar_material'):
            valor_material = st.session_state.get('valor_material_ajustado', valor_material)
            print(f"ADMIN: Usando valor material ajustado: {valor_material}")

        # --- Troquel Cost Logic --- 
        valor_troquel_a_pasar = None # Default to None (signal internal calculation)
        if st.session_state.get('ajustar_troquel'):
            valor_troquel_a_pasar = st.session_state.get('precio_troquel', 0.0) # Use admin value if adjusting
            print(f"ADMIN: Usando valor troquel ajustado: {valor_troquel_a_pasar}")
        # Else: valor_troquel_a_pasar remains None
        # --- End Troquel Cost Logic ---
        
        # --- Plate cost Logic (already correct, but confirming) ---
        valor_plancha_a_pasar = None # Default to None (signal internal calculation)
        if st.session_state.get('ajustar_planchas'):
            # Use the TOTAL adjusted price directly
            valor_plancha_a_pasar = st.session_state.get('precio_planchas', 0.0)
            print(f"ADMIN: Usando valor TOTAL de planchas ajustado: {valor_plancha_a_pasar}")
        # Else: valor_plancha_a_pasar remains None
        # --- End Plate cost Logic ---

        rentabilidad = RENTABILIDAD_MANGAS if es_manga else RENTABILIDAD_ETIQUETAS
        rentabilidad_ajustada = st.session_state.get('rentabilidad_ajustada')
        if rentabilidad_ajustada is not None and rentabilidad_ajustada > 0:
            rentabilidad = rentabilidad_ajustada / 100.0  # Convertir % a decimal
            print(f"ADMIN: Usando rentabilidad ajustada: {rentabilidad}")
        else:
            print(f"Usando rentabilidad por defecto: {rentabilidad}")

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
            escalas=form_data['escalas'],
            pistas=form_data['pistas'],
            ancho=ancho_ajustado,
            avance=form_data['avance'],
            avance_total=form_data['avance'] + (GAP_AVANCE_MANGAS if es_manga else GAP_AVANCE_ETIQUETAS),
            desperdicio=0,
            velocidad_maquina=VELOCIDAD_MAQUINA_MANGAS_7_TINTAS if (es_manga and num_tintas >= 7) 
                            else VELOCIDAD_MAQUINA_NORMAL,
            rentabilidad=rentabilidad,  # Usar la rentabilidad determinada (ajustada o defecto)
            porcentaje_desperdicio=DESPERDICIO_MANGAS if es_manga else DESPERDICIO_ETIQUETAS,
            valor_metro=valor_material, # Usar el valor de material determinado (combinado/base + ajustado)
            troquel_existe=troquel_existe,
            planchas_por_separado=form_data.get('planchas_separadas', False)
        )
        
        # Calcular área de etiqueta usando la calculadora
        area_result = calculadora.calcular_area_etiqueta(datos_escala, num_tintas, es_manga)
        if 'error' in area_result:
            st.error(f"Error calculando área: {area_result['error']}")
            return None
        datos_escala.set_area_etiqueta(area_result['area'])
        
        print(f"\nDEBUG: Calling calculadora.calcular_costos_por_escala with:")
        print(f"  - datos: {datos_escala}")
        print(f"  - num_tintas: {num_tintas}")
        print(f"  - valor_plancha (pasado): {valor_plancha_a_pasar}")
        print(f"  - valor_troquel (adjusted): {valor_troquel_a_pasar}")
        print(f"  - valor_material (final, passed to calc): {valor_material}")
        print(f"  - valor_acabado: {acabado.valor if acabado else 0}")
        print(f"  - es_manga: {es_manga}")
        print(f"  - tipo_grafado_id: {form_data.get('tipo_grafado_id')}")

        # Realizar cálculos
        resultados = calculadora.calcular_costos_por_escala(
            datos=datos_escala,
            num_tintas=num_tintas,
            valor_plancha=valor_plancha_a_pasar, # Pass adjusted TOTAL value or None
            valor_troquel=valor_troquel_a_pasar, # Usar el valor de troquel determinado
            valor_material=valor_material, # Pasar el valor de material determinado (combinado/base + ajustado)
            valor_acabado=acabado.valor if acabado else 0,
            es_manga=es_manga,
            tipo_grafado_id=form_data.get('tipo_grafado_id')
        )
        
        if resultados:
            # Guardar resultados en session_state
            st.session_state.current_calculation = {
                'form_data': form_data,
                'results': resultados,
                'is_manga': es_manga,
                'timestamp': datetime.now().isoformat(),
                # Opcional: Guardar info sobre ajustes aplicados
                'admin_adjustments_applied': {
                    'material': st.session_state.get('ajustar_material', False),
                    'troquel': st.session_state.get('ajustar_troquel', False),
                    'planchas': st.session_state.get('ajustar_planchas', False),
                    'rentabilidad': rentabilidad_ajustada is not None and rentabilidad_ajustada > 0
                }
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

    # Saludo personalizado
    st.title("Cotizador Flexo Impresos 📊")
    st.write(f"Hola {st.session_state.perfil_usuario['nombre']}")

    st.write(f"Selecciona un cliente y un tipo de producto para comenzar a cotizar.")
    
    # Selector de cliente (filtrado por comercial)
    clientes = get_filtered_clients()
    cliente_seleccionado = st.selectbox(
        "Cliente",
        options=clientes,
        format_func=lambda x: x.nombre
    )
    
    if cliente_seleccionado:
        # --- Selección y confirmación de tipo de producto (fuera del formulario) ---
        # Mostrar solo si el tipo de producto NO ha sido seleccionado aún
        if not st.session_state.get('tipo_producto_seleccionado'):
            tipos_producto = st.session_state.db.get_tipos_producto()
            tipo_producto = st.selectbox(
                "Tipo de Producto",
                options=tipos_producto,
                format_func=lambda x: x.nombre,
                key="tipo_producto_select",
                help="Seleccione si es manga o etiqueta"
            )
            if st.button("Seleccionar producto"):
                st.session_state['tipo_producto_seleccionado'] = tipo_producto.id
                st.session_state['tipo_producto_objeto'] = tipo_producto
                st.rerun() # Forzar recarga para que el form aparezca

        # --- Formulario principal solo si ya se confirmó el tipo de producto ---
        else: # Si ya se seleccionó, muestra el formulario y un botón para cambiar
            st.success(f"Tipo de producto seleccionado: {st.session_state.tipo_producto_objeto.nombre}")
            if st.button("Cambiar tipo de producto"):
                del st.session_state['tipo_producto_seleccionado']
                del st.session_state['tipo_producto_objeto']
                st.rerun()
                
            # --- Inputs reactivos (sin form) ---
            # Llamar a la función que muestra los inputs
            datos_producto = mostrar_formulario_producto(cliente_seleccionado)

            # --- Ajustes Avanzados (Solo Admin) ---
            if st.session_state.usuario_rol == 'administrador':
                with st.expander("⚙️ Ajustes Avanzados (Admin)", expanded=True): # Keep expanded for easier access
                    st.markdown("##### Sobrescribir Valores Calculados")
                    st.caption("Marque la casilla para activar el ajuste e ingrese el nuevo valor.")

                    # --- Rentabilidad ---
                    st.divider()
                    rent_col1, rent_col2 = st.columns([1, 2], gap="medium")
                    with rent_col1:
                        ajustar_rentabilidad_checked = st.checkbox(
                            "Ajustar Rentabilidad", 
                            key='ajustar_rentabilidad', # New key for the checkbox
                            help="Activar para sobrescribir el % de rentabilidad por defecto."
                        )
                    with rent_col2:
                        if ajustar_rentabilidad_checked:
                            # Get current raw value from state for the input field
                            rentabilidad_ajustada_raw = st.session_state.get('rentabilidad_ajustada', None)
                            # Explicitly update session state from the number input
                            st.session_state.rentabilidad_ajustada = st.number_input(
                                "Nueva Rentabilidad (%)", 
                                key='rentabilidad_ajustada_input', # New key for the input widget
                                value=float(rentabilidad_ajustada_raw) if rentabilidad_ajustada_raw is not None else None, # Ensure initial value is float or None
                                min_value=0.1, # Prevent entering 0 directly, use checkbox to disable
                                max_value=100.0, 
                                step=0.1, 
                                format="%.1f",
                                help="Ingrese el nuevo porcentaje de rentabilidad (ej: 35.5).",
                                label_visibility="collapsed"
                            )
                        else:
                            # Reset state if unchecked and key exists
                            if 'rentabilidad_ajustada' in st.session_state:
                                st.session_state.rentabilidad_ajustada = None

                    # --- Material ---
                    st.divider()
                    mat_col1, mat_col2 = st.columns([1, 2], gap="medium")
                    with mat_col1:
                        ajustar_material_checked = st.checkbox(
                            "Ajustar Material", 
                            key='ajustar_material',
                            help="Activar para sobrescribir el costo por m² del material."
                        )
                    with mat_col2:
                        if ajustar_material_checked:
                            st.number_input(
                                "Nuevo Valor Material ($/m²)",
                                key='valor_material_ajustado', 
                                value=st.session_state.get('valor_material_ajustado', 0.0), 
                                min_value=0.0, step=1.0, format="%.2f",
                                help="Ingrese el nuevo costo por metro cuadrado ($/m²) del material.",
                                label_visibility="collapsed"
                            )
                        else:
                            # Reset state if unchecked
                            if 'valor_material_ajustado' in st.session_state:
                                st.session_state.valor_material_ajustado = 0.0
                    
                    # --- Troquel ---
                    st.divider()
                    troq_col1, troq_col2 = st.columns([1, 2], gap="medium")
                    with troq_col1:
                        ajustar_troquel_checked = st.checkbox(
                            "Ajustar Troquel", 
                            key='ajustar_troquel',
                            help="Activar para sobrescribir el costo del troquel."
                        )
                    with troq_col2:
                        if ajustar_troquel_checked:
                            st.number_input(
                                "Nuevo Precio Troquel ($)", 
                                key='precio_troquel', 
                                value=st.session_state.get('precio_troquel', 0.0), 
                                min_value=0.0, step=1.0, format="%.2f",
                                help="Ingrese el precio fijo para el troquel si se ajusta.",
                                label_visibility="collapsed"
                            )
                        else:
                            # Reset state if unchecked
                            if 'precio_troquel' in st.session_state:
                                st.session_state.precio_troquel = 0.0

                    # --- Planchas ---
                    st.divider()
                    plan_col1, plan_col2 = st.columns([1, 2], gap="medium")
                    with plan_col1:
                         ajustar_planchas_checked = st.checkbox(
                            "Ajustar Planchas", 
                            key='ajustar_planchas',
                            help="Activar para sobrescribir el costo total de las planchas."
                         )
                    with plan_col2:
                        if ajustar_planchas_checked:
                            # Explicitly update session state from the number input
                            st.session_state.precio_planchas = st.number_input(
                                "Nuevo Precio Total Planchas ($)", 
                                key='precio_planchas_input', # Use a different key for the widget itself
                                value=st.session_state.get('precio_planchas', 0.0), # Still use state for initial value
                                min_value=0.0, step=1.0, format="%.2f",
                                help="Ingrese el precio fijo total para todas las planchas si se ajusta.",
                                label_visibility="collapsed"
                            )
                        else:
                             # Reset if unchecked and key exists
                             if 'precio_planchas' in st.session_state:
                                st.session_state.precio_planchas = 0.0
            
            # --- Botón de acción fuera (ahora st.button) ---
            if st.button("Calcular"):
                if datos_producto:
                    # Añadir tipo_producto_id y es_manga a los datos antes de calcular
                    datos_producto['tipo_producto_id'] = st.session_state.get('tipo_producto_seleccionado')
                    datos_producto['es_manga'] = datos_producto['tipo_producto_id'] == 2

                    # Realizar cálculos
                    resultados = handle_calculation(datos_producto)
                    if resultados:
                        # Guardar resultados y mostrarlos
                        st.session_state.current_calculation = {
                            'cliente': cliente_seleccionado,
                            'form_data': datos_producto,
                            'results': resultados,
                            'timestamp': datetime.now().isoformat()
                        }
                        st.session_state.current_view = 'quote_results'
                        st.rerun()
                else:
                    st.warning("No se pudieron recolectar datos del formulario.")

def main():
    """Función principal que orquesta el flujo de la aplicación"""
    # Inicializar servicios primero
    initialize_services()

    # Inicializar el estado de la sesión
    SessionManager.init_session()

    # Si el usuario está autenticado pero faltan datos críticos, restaurar
    if st.session_state.get('authenticated', False):
        if not st.session_state.get('user_id') or not st.session_state.get('usuario_rol') or not st.session_state.get('perfil_usuario'):
            db = st.session_state.db
            user_id = st.session_state.get('user_id')
            perfil = db.get_perfil(user_id) if user_id else None
            usuario_rol = perfil.get('rol_nombre') if perfil else None
            SessionManager.full_init(user_id=user_id, usuario_rol=usuario_rol, perfil_usuario=perfil)

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
    col2, col3 = st.columns([2, 1])  # El formulario ocupa más espacio que el botón PDF

    with col2:
        st.markdown("#### Guardar Cotización")
        with st.form("guardar_cotizacion_form"):
            referencia = st.text_input(
                "Referencia para guardar la cotización",
                value=st.session_state.get('referencia_guardar', ""),
                key="referencia_guardar_input"
            )
            guardar = st.form_submit_button("Guardar Cotización", type="primary")
            if guardar:
                if not referencia.strip():
                    st.error("Debe ingresar una referencia para guardar la cotización.")
                else:
                    st.session_state.referencia_guardar = referencia
                    st.session_state.cotizacion_guardada = True
                    st.success("Cotización guardada exitosamente")
        # Mostrar el botón PDF solo después del éxito de guardado, justo debajo del mensaje de éxito
        if st.session_state.get('cotizacion_guardada', False):
            if st.button("Generar PDF"):
                st.info("Funcionalidad de PDF en desarrollo")
        # Botón Nueva Cotización siempre visible, pero al final
        if st.button("Nueva Cotización"):
            st.session_state.current_view = 'calculator'
            st.session_state.cotizacion_guardada = False
            st.session_state.referencia_guardar = ""
            st.rerun()

if __name__ == "__main__":
    main()
