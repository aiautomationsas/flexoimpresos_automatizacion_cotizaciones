import streamlit as st
from supabase import create_client
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import traceback # Import traceback for detailed error logging
import math
import time
from datetime import datetime # <-- AÑADIR IMPORTACIÓN

# Configuración de página - MOVER AL INICIO
st.set_page_config(
    page_title="Sistema de Cotización - Flexo Impresos",
    page_icon="🏭",
    layout="wide"
)

# Luego las importaciones del proyecto, agrupadas por funcionalidad
# Auth y DB
from src.auth.auth_manager import AuthManager
from src.data.database import DBManager
# --- NUEVO: Importar CotizacionManager ---
from src.logic.cotizacion_manager import CotizacionManager, CotizacionManagerError
# ---------------------------------------

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
from src.pdf.pdf_generator import generar_bytes_pdf_cotizacion, CotizacionPDF # Importar la nueva función helper y la clase

# Calculadoras
from src.logic.calculators.calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from src.logic.calculators.calculadora_litografia import CalculadoraLitografia
# --- NUEVO: Importar generador de informe ---
from src.logic.report_generator import generar_informe_tecnico_markdown, markdown_a_pdf
# --------------------------------------------

# UI Components - mover estas importaciones al final
from src.ui.auth_ui import handle_authentication, show_login, show_logout_button
from src.ui.calculator_view import show_calculator, show_quote_results # Mantener solo los usados
# MODIFICADO: Importar funciones específicas
from src.ui.calculator.product_section import (_mostrar_material, _mostrar_adhesivo, 
                                             _mostrar_grafado_altura, mostrar_secciones_internas_formulario)
# --- NUEVO: Importar vista de gestión y dashboard ---
from src.ui.manage_quotes_view import show_manage_quotes
from src.ui.manage_clients_view import show_manage_clients, show_create_client
from src.ui.dashboard_view import show_dashboard
# --- NUEVO: Importar vista de gestión de valores ---
from src.ui.manage_values_view import show_manage_values


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
            
        # --- NUEVO: Inicializar CotizacionManager ---
        if 'cotizacion_manager' not in st.session_state:
            st.session_state.cotizacion_manager = CotizacionManager(st.session_state.db)
        # ------------------------------------------
        
        # Refuerzo: asegúrate de que las claves críticas existen
        for key in ['authenticated', 'user_id', 'usuario_rol', 'perfil_usuario']:
            if key not in st.session_state:
                st.session_state[key] = None if key != 'authenticated' else False
        
    except Exception as e:
        st.error(f"Error crítico inicializando servicios: {e}")
        st.stop()

@st.cache_resource
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
            'adhesivos': db.get_adhesivos(),
            'estados_cotizacion': db.get_estados_cotizacion() # <-- AÑADIDO
        }
        
        # Verificar que se obtuvieron todos los datos necesarios (excluding adhesives for now as they might be optional initially)
        required_data = ['materiales', 'acabados', 'tipos_producto', 'clientes', 
                         'formas_pago', 'tipos_grafado', 'estados_cotizacion'] # <-- AÑADIDO a la verificación
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

def handle_calculation(form_data: Dict[str, Any], cliente_obj: Cliente) -> Optional[Dict[str, Any]]:
    """
    Maneja el proceso de cálculo de la cotización.
    
    Args:
        form_data: Diccionario con los datos del formulario
        cliente_obj: Objeto Cliente seleccionado
        
    Returns:
        Optional[Dict[str, Any]]: Resultados del cálculo o None si hay error
    """
    try:
        # Debug inicial para rastrear flujo del cálculo
        print("\n======= INICIO DEL PROCESO DE CÁLCULO =======")
        print(f"Datos recibidos: es_manga={form_data.get('es_manga')}, num_tintas={form_data.get('num_tintas')}, acabado_id={form_data.get('acabado_id')}")
        
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
            planchas_por_separado=form_data.get('planchas_separadas', False),
        )
        
        # --- Calcular Mejor Opción de Desperdicio UNA VEZ ---
        calc_lito = CalculadoraLitografia() # Necesitamos instancia para obtener mejor opción
        try:
            mejor_opcion = calc_lito.obtener_mejor_opcion_desperdicio(datos_escala, es_manga)
            if mejor_opcion is None:
                st.error("No se encontró una configuración de cilindro/repetición válida para este avance.")
                return None
            print(f"\nMejor Opción Desperdicio: Dientes={mejor_opcion.dientes}, Reps={mejor_opcion.repeticiones}, Medida={mejor_opcion.medida_mm}, Desp={mejor_opcion.desperdicio:.4f}")
        except ValueError as e_desp:
            st.error(f"Error determinando la mejor opción de desperdicio: {e_desp}")
            return None
        # -----------------------------------------------------

        # Calcular área de etiqueta usando la calculadora (¿Se necesita antes de calcular_costos_por_escala?)
        # area_result = calculadora.calcular_area_etiqueta(datos_escala, num_tintas, es_manga) # Parece que no se usa directamente ahora
        # if 'error' in area_result:
        #     st.error(f"Error calculando área: {area_result['error']}")
        #     return None
        # datos_escala.set_area_etiqueta(area_result['area'])

        # ---- AJUSTAR NÚMERO DE TINTAS SI EL ACABADO LO REQUIERE ----
        num_tintas = form_data['num_tintas']  # Número original seleccionado por el usuario
        acabado_id = form_data.get('acabado_id')
        es_manga = form_data['es_manga']
        
        # Ajustar tintas para acabados especiales
        num_tintas_ajustado = num_tintas
        if not es_manga and acabado_id in [3, 4, 5, 6]:
            num_tintas_ajustado = num_tintas + 1
            print(f"\n=== AJUSTE DE TINTAS POR ACABADO ESPECIAL ===")
            print(f"Tintas originales seleccionadas: {num_tintas}")
            print(f"Acabado ID {acabado_id} requiere 1 tinta adicional")
            print(f"Tintas ajustadas para cálculos: {num_tintas_ajustado}")
            
            # Validar que no se exceda el límite
            if num_tintas_ajustado > 7:
                st.error(f"El acabado seleccionado requiere 1 tinta adicional en el cálculo. "
                         f"Con las {num_tintas} tintas seleccionadas, se excede el máximo de 7 tintas "
                         f"permitidas. Para este acabado, seleccione máximo 6 tintas.")
                return None
        else:
            print(f"\n=== SIN AJUSTE DE TINTAS ===")
            print(f"Tintas seleccionadas: {num_tintas} (sin ajuste)")
            
        # A partir de este punto, usamos num_tintas_ajustado para todos los cálculos internos
        
        # --- GUARDAR DATOS DE CALCULO PARA GUARDADO POSTERIOR --- 
        # Guardamos los valores finales que se usaron en el cálculo
        # para pasarlos luego a guardar_calculos_escala
        
        # Calcular valor_troquel por defecto (si no ajustado) usando mejor_opcion
        valor_troquel_defecto = 0.0
        if not st.session_state.get('ajustar_troquel'):
            # El troquel no depende directamente del número de tintas, pero lo agregamos aquí
            # para mantener la coherencia en el código
            troquel_result = calc_lito.calcular_valor_troquel(
                datos_escala, 
                mejor_opcion.repeticiones, # Usar repeticiones de mejor opción
                troquel_existe=datos_escala.troquel_existe, # Usar valor procesado
                tipo_grafado_id=form_data.get('tipo_grafado_id'), # Pasar ID
                es_manga=es_manga # <-- Añadir parámetro es_manga
            )
            if 'error' in troquel_result:
                 st.warning(f"Advertencia: No se pudo calcular el valor del troquel por defecto: {troquel_result['error']}")
            else:
                 valor_troquel_defecto = troquel_result.get('valor', 0.0)

        # Calcular valor_plancha por defecto (si no ajustado)
        valor_plancha_defecto = 0.0
        precio_sin_constante = None # Inicializar para guardar el valor separado
        if not st.session_state.get('ajustar_planchas'):
             # Usar el número de tintas ajustado para calcular la plancha
             plancha_result = calc_lito.calcular_precio_plancha(datos_escala, num_tintas_ajustado, es_manga)
             if 'error' in plancha_result:
                 st.warning(f"Advertencia: No se pudo calcular el valor de plancha por defecto: {plancha_result['error']}")
             else:
                 # Usar el precio que incluye la división por constante si planchas_por_separado=False
                 valor_plancha_defecto = plancha_result.get('precio', 0.0)
                 # Guardar el precio ANTES de aplicar la constante (si existe)
                 if plancha_result.get('detalles'):
                    precio_sin_constante = plancha_result['detalles'].get('precio_sin_constante')

        datos_calculo_persistir = {
            'valor_material': valor_material, # Valor final usado
            'valor_plancha': st.session_state.get('precio_planchas', valor_plancha_defecto) if st.session_state.get('ajustar_planchas') else valor_plancha_defecto,
            'valor_acabado': acabado.valor if acabado else 0,
            'valor_troquel': st.session_state.get('precio_troquel', valor_troquel_defecto) if st.session_state.get('ajustar_troquel') else valor_troquel_defecto,
            'rentabilidad': datos_escala.rentabilidad, # Guardar el valor decimal directamente
            
            # --- CORREGIDO: Añadir lógica para valor_plancha_separado --- 
            # 'valor_plancha_separado': (
            #     st.session_state.get('precio_planchas') if st.session_state.get('ajustar_planchas') and datos_escala.planchas_por_separado
            #     else precio_sin_constante if datos_escala.planchas_por_separado and precio_sin_constante is not None
            #     else None
            # ),
            # ----------------------------------------------------------
            'avance': datos_escala.avance,
            'ancho': form_data['ancho'], # Guardar ancho original sin ajuste de manga
            'unidad_z_dientes': mejor_opcion.dientes if mejor_opcion else 0, # <-- CORREGIDO
            'existe_troquel': datos_escala.troquel_existe, # Usar valor procesado
            'planchas_x_separado': datos_escala.planchas_por_separado,
            'num_tintas': num_tintas, # Número de tintas original
            'num_tintas_ajustado': num_tintas_ajustado, # Número de tintas ajustado (con tinta adicional por acabado si aplica)
            'numero_pistas': datos_escala.pistas,
            'num_paquetes_rollos': form_data['num_paquetes'],
            'tipo_producto_id': form_data['tipo_producto_id'],
            'tipo_grafado_id': form_data.get('tipo_grafado_id'), # Usar ID guardado
            'altura_grafado': form_data.get('altura_grafado'),
            'valor_plancha_separado': None, # Inicializar para aplicar la lógica de redondeo
            'acabado_id': form_data.get('acabado_id') # Añadir ID de acabado
        }
        
        # --- Aplicar Fórmula de Redondeo a valor_plancha_separado --- 
        valor_plancha_separado_base = None
        if datos_calculo_persistir['planchas_x_separado']: # Solo aplica si las planchas son separadas
            if st.session_state.get('ajustar_planchas'):
                valor_plancha_separado_base = st.session_state.get('precio_planchas')
            elif precio_sin_constante is not None:
                valor_plancha_separado_base = precio_sin_constante
        
        if valor_plancha_separado_base is not None and valor_plancha_separado_base > 0:
            try:
                valor_dividido = valor_plancha_separado_base / 0.7
                # Redondear hacia arriba al siguiente múltiplo de 10000
                valor_redondeado = math.ceil(valor_dividido / 10000) * 10000
                datos_calculo_persistir['valor_plancha_separado'] = float(valor_redondeado) # Guardar como float
                print(f"Valor plancha separado (Base: {valor_plancha_separado_base:.2f}, Dividido: {valor_dividido:.2f}, Redondeado: {valor_redondeado:.2f})")
            except Exception as e_round:
                print(f"Error aplicando redondeo a valor_plancha_separado: {e_round}")
                datos_calculo_persistir['valor_plancha_separado'] = None # Poner None si hay error
        else:
             datos_calculo_persistir['valor_plancha_separado'] = None # Si no aplica o es cero
        # -------------------------------------------------------------

        # Realizar cálculos principales por escala
        print(f"\n=== REALIZAR CÁLCULOS PRINCIPALES POR ESCALA ===")
        print(f"  - Tintas originales: {num_tintas}")
        print(f"  - Tintas ajustadas: {num_tintas_ajustado}")
        print(f"  - Es manga: {es_manga}")
        print(f"  - Acabado ID: {acabado_id}")

        resultados = calculadora.calcular_costos_por_escala(
            datos=datos_escala,
            num_tintas=num_tintas_ajustado,  # IMPORTANTE: Usar el valor AJUSTADO que incluye +1 para acabados especiales
            valor_plancha=datos_calculo_persistir['valor_plancha'], 
            valor_troquel=datos_calculo_persistir['valor_troquel'], 
            valor_material=datos_calculo_persistir['valor_material'], 
            valor_acabado=datos_calculo_persistir['valor_acabado'],
            es_manga=es_manga,
            tipo_grafado_id=datos_calculo_persistir['tipo_grafado_id'], 
            acabado_id=acabado_id
        )
        
        if resultados:
            # --- NUEVO: Preparar modelo Cotizacion usando CotizacionManager --- 
            print("\nCálculo exitoso. Preparando modelo de cotización...")
            try:
                manager = st.session_state.cotizacion_manager
                # Construir kwargs para el manager
                kwargs_modelo = {
                    'material_adhesivo_id': form_data['material_adhesivo_id'], # Usar la clave correcta
                    'acabado_id': form_data.get('acabado_id') if not es_manga else 10, # ID 10 = Sin acabado
                    'num_tintas': num_tintas, # Usar tintas originales (no ajustadas) para mostrar al usuario
                    'num_paquetes_rollos': form_data['num_paquetes'],
                    'es_manga': es_manga,
                    'tipo_grafado': form_data.get('tipo_grafado_nombre'), # Pasar nombre si existe
                    'valor_troquel': datos_calculo_persistir['valor_troquel'], # Usar valor final persistido
                    'valor_plancha_separado': datos_calculo_persistir.get('valor_plancha_separado'), # Valor ya calculado/ajustado
                    'planchas_x_separado': datos_escala.planchas_por_separado,
                    'existe_troquel': datos_escala.troquel_existe, # Usar valor procesado
                    'numero_pistas': datos_escala.pistas,
                    'avance': datos_escala.avance, # Usar avance de datos_escala
                    'ancho': form_data['ancho'], # Ancho original
                    'tipo_producto_id': form_data['tipo_producto_id'],
                    'forma_pago_id': form_data['forma_pago_id'],
                    'altura_grafado': form_data.get('altura_grafado'),
                    'tipo_foil_id': st.session_state.get("tipo_foil_id"), # <--- LÍNEA AÑADIDA
                    'escalas_resultados': resultados # Pasar la lista de dicts
                }
                
                # Asegurarse de pasar el tipo_grafado_id si es manga
                if es_manga:
                    kwargs_modelo['tipo_grafado_id'] = form_data.get('tipo_grafado_id')

                st.session_state.cotizacion_model = manager.preparar_nueva_cotizacion_model(**kwargs_modelo)
                print("Modelo Cotizacion preparado y guardado en session_state.")
                st.session_state.cotizacion_calculada = True # Indicar que hay un cálculo listo

            except CotizacionManagerError as cme:
                st.error(f"Error preparando el modelo de cotización: {cme}")
                return None # Falló la preparación, no continuar
            except Exception as e_prep:
                st.error(f"Error inesperado preparando el modelo: {e_prep}")
                traceback.print_exc()
                return None
            # ----------------------------------------------------------------
            
            # --- NUEVO: Determinar si ajustes admin estaban activos ---
            admin_ajustes_activos_calculo = False
            if st.session_state.get('usuario_rol') == 'administrador':
                if (st.session_state.get('ajustar_material') or 
                    st.session_state.get('ajustar_troquel') or 
                    st.session_state.get('ajustar_planchas') or
                    (st.session_state.get('rentabilidad_ajustada') is not None and st.session_state.get('rentabilidad_ajustada') > 0)):
                    admin_ajustes_activos_calculo = True
            # ------------------------------------------------------

            # Guardar resultados y cambiar vista
            st.session_state.current_calculation = {
                'form_data': form_data,
                'cliente': cliente_obj,
                'results': resultados,
                'is_manga': es_manga,
                'timestamp': datetime.now().isoformat(),
                'calculos_para_guardar': datos_calculo_persistir, 
                # --- AÑADIR EL NUEVO FLAG AQUÍ ---
                'admin_ajustes_activos': admin_ajustes_activos_calculo, 
                # ----------------------------------
                'admin_adjustments_applied': { # Mantener esto también si se usa en otro lado
                    'material': st.session_state.get('ajustar_material', False),
                    'troquel': st.session_state.get('ajustar_troquel', False),
                    'planchas': st.session_state.get('ajustar_planchas', False),
                    'rentabilidad': rentabilidad_ajustada is not None and rentabilidad_ajustada > 0
                }
            }
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

    # Define las claves y los nombres para mostrar
    options = {
        'calculator': "📝 Cotizador",
        'manage_quotes': "📂 Gestionar Cotizaciones",
        'manage_clients': "👥 Gestionar Clientes",
        'dashboard': "📊 Dashboard", # Nueva opción
    }
    
    # Solo mostrar la opción de gestión de valores a administradores
    if st.session_state.get('usuario_rol') == 'administrador':
        options['manage_values'] = "💰 Administrar Valores"

    # Obtener la vista actual o default a 'calculator'
    current_view_key = st.session_state.get('current_view', 'calculator')
    
    # Asegurarse de que la vista actual sea válida para la navegación
    # Si la vista actual no es una de las opciones del radio (p.ej. 'quote_results'),
    # mantenemos esa vista pero seleccionamos 'calculator' en el radio visualmente.
    if current_view_key not in options:
        nav_display_key = 'calculator' # Clave para mostrar en el radio
    else:
        nav_display_key = current_view_key # La vista actual es una opción del radio

    # Encontrar el índice de la opción a mostrar en el radio
    try:
        current_index = list(options.keys()).index(nav_display_key)
    except ValueError:
        current_index = 0 # Default seguro al primer índice

    # Mostrar el radio button
    selected_display_name = st.sidebar.radio(
        "Ir a:",
        list(options.values()),
        index=current_index, 
        key="navigation_radio"
    )

    # Obtener la clave de la vista que CORRESPONDE al radio seleccionado
    selected_key_from_radio = next((k for k, v in options.items() if v == selected_display_name), 'calculator')

    # Cambiar la vista SOLO si la selección del radio es DIFERENTE a la 
    # clave que usamos para mostrar la selección inicial (nav_display_key).
    # Esto significa que el usuario hizo clic activamente en una opción diferente.
    if selected_key_from_radio != nav_display_key:
        st.session_state.current_view = selected_key_from_radio
        # Limpiar estado específico de cálculo/resultados al navegar manualmente
        if 'current_calculation' in st.session_state: del st.session_state['current_calculation']
        if 'cotizacion_model' in st.session_state: del st.session_state['cotizacion_model']
        if 'cotizacion_guardada' in st.session_state: del st.session_state['cotizacion_guardada']
        if 'modo_edicion' in st.session_state: 
             st.session_state.modo_edicion = False # Salir de modo edición si navegamos fuera
             st.session_state.cotizacion_id_editar = None # <-- Corregido nombre de clave
             st.session_state.datos_cotizacion_editar = None # <-- Limpiar datos cargados
        # --- INICIO: Limpiar también recotizacion_info --- 
        if 'recotizacion_info' in st.session_state: 
             del st.session_state['recotizacion_info']
        # --- FIN: Limpiar también recotizacion_info --- 
        SessionManager.reset_calculator_widgets() # Resetear widgets también
        st.rerun() 

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
    """Obtiene todos los clientes sin filtrar. Los comerciales pueden ver todos los clientes,
    aunque solo pueden trabajar con las referencias que les corresponden."""
    # Siempre mostrar todos los clientes independientemente del rol
    return st.session_state.db.get_clientes()

def _mostrar_ajustes_admin():
    """Muestra la sección de ajustes avanzados para administradores (fuera del form)."""
    if st.session_state.usuario_rol == 'administrador':
        with st.expander("⚙️ Ajustes Avanzados (Admin)"):
            st.markdown("##### Sobrescribir Valores Calculados")
            st.caption("Marque la casilla para activar el ajuste e ingrese el nuevo valor.")
            
            # Rentabilidad
            st.divider()
            ajustar_rentabilidad_checked = st.checkbox("Ajustar Rentabilidad", key='ajustar_rentabilidad')
            if ajustar_rentabilidad_checked:
                valor_rentabilidad = st.number_input(
                    "Nueva Rentabilidad (%)", 
                    key='rentabilidad_ajustada',
                    min_value=0.1, 
                    max_value=100.0, 
                    step=0.1, 
                    format="%.1f"
                )
                st.caption(f"Valor configurado: {valor_rentabilidad}%")
            else: 
                if 'rentabilidad_ajustada' in st.session_state:
                    st.session_state.rentabilidad_ajustada = None
            
            # Material
            st.divider()
            ajustar_material_checked = st.checkbox("Ajustar Material", key='ajustar_material')
            if ajustar_material_checked:
                valor_material = st.number_input(
                    "Nuevo Valor Material ($/m²)", 
                    key='valor_material_ajustado', 
                    min_value=0.0, 
                    step=1.0, 
                    format="%.2f"
                )
                st.caption(f"Valor configurado: ${valor_material}/m²")
            else: 
                if 'valor_material_ajustado' in st.session_state:
                    st.session_state.valor_material_ajustado = 0.0
            
            # Troquel
            st.divider()
            ajustar_troquel_checked = st.checkbox("Ajustar Troquel", key='ajustar_troquel')
            if ajustar_troquel_checked:
                valor_troquel = st.number_input(
                    "Nuevo Precio Troquel ($)", 
                    key='precio_troquel', 
                    min_value=0.0, 
                    step=1.0, 
                    format="%.2f"
                )
                st.caption(f"Valor configurado: ${valor_troquel}")
            else: 
                if 'precio_troquel' in st.session_state:
                    st.session_state.precio_troquel = 0.0
            
            # Planchas
            st.divider()
            ajustar_planchas_checked = st.checkbox("Ajustar Planchas", key='ajustar_planchas')
            if ajustar_planchas_checked:
                valor_planchas = st.number_input(
                    "Nuevo Precio Total Planchas ($)", 
                    key='precio_planchas', 
                    min_value=0.0, 
                    step=1.0, 
                    format="%.2f"
                )
                st.caption(f"Valor configurado: ${valor_planchas}")
            else: 
                if 'precio_planchas' in st.session_state:
                    st.session_state.precio_planchas = 0.0
# --- Fin _mostrar_ajustes_admin ---

def mostrar_calculadora():
    """Vista principal de la calculadora"""
    if not initialize_session():
        st.error("Error de inicialización")
        return

    # --- Lógica de Carga para Modo Edición ---
    datos_cargados = None
    is_edit_mode = st.session_state.get('modo_edicion', False)
    if is_edit_mode:
        # --- INICIO CAMBIO ---
        # cotizacion_id_editar = st.session_state.get('cotizacion_a_editar_id') # <-- Clave incorrecta
        cotizacion_id_editar = st.session_state.get('cotizacion_id_editar') # <-- Clave correcta
        # --- FIN CAMBIO ---
        if cotizacion_id_editar:
            # Solo cargar si no tenemos ya los datos cargados en sesión 
            # (evita recargar en cada rerun dentro del modo edición)
            if 'datos_cotizacion_editar' not in st.session_state or st.session_state.datos_cotizacion_editar is None:
                st.info(f"**Modo Edición:** Cargando datos de Cotización ID {cotizacion_id_editar}")
                with st.spinner("Cargando datos para edición..."):
                    db = st.session_state.db
                    datos_cargados = db.get_full_cotizacion_details(cotizacion_id_editar)
                    if datos_cargados:
                        st.session_state.datos_cotizacion_editar = datos_cargados
                        
                        # --- INICIO DIAGNÓSTICO TEMPORAL ---
                        st.warning(f"DEBUG - Datos Cargados: numero_pistas={datos_cargados.get('numero_pistas')} (tipo: {type(datos_cargados.get('numero_pistas', '')).__name__}), forma_pago_id={datos_cargados.get('forma_pago_id')} (tipo: {type(datos_cargados.get('forma_pago_id', '')).__name__})")
                        # --- FIN DIAGNÓSTICO TEMPORAL ---
                        
                        # Forzar tipo producto ANTES de mostrar selector
                        tipo_producto_id_cargado = datos_cargados.get('tipo_producto_id')
                        if tipo_producto_id_cargado:
                            tipos_producto_list = st.session_state.initial_data.get('tipos_producto', [])
                            tipo_producto_obj_cargado = next((tp for tp in tipos_producto_list if tp.id == tipo_producto_id_cargado), None)
                            if tipo_producto_obj_cargado:
                                st.session_state['tipo_producto_seleccionado'] = tipo_producto_id_cargado
                                st.session_state['tipo_producto_objeto'] = tipo_producto_obj_cargado
                            else:
                                st.error(f"Error crítico: Tipo de producto ID {tipo_producto_id_cargado} de la cotización no se encontró en los datos iniciales. No se puede editar.")
                                # Limpiar estado para evitar inconsistencias
                                if 'tipo_producto_objeto' in st.session_state: del st.session_state['tipo_producto_objeto']
                                if 'tipo_producto_seleccionado' in st.session_state: del st.session_state['tipo_producto_seleccionado']
                                st.session_state.modo_edicion = False # Salir del modo edición
                                st.session_state.cotizacion_a_editar_id = None
                                st.session_state.datos_cotizacion_editar = None
                                # Detener la ejecución de esta función para este rerun
                                return # <-- AÑADIDO: Detener si no se encuentra el objeto
                        else:
                            st.warning("Cotización sin tipo de producto definido.")
                            # También deberíamos detenernos aquí si el tipo es esencial
                            st.error("Error crítico: La cotización a editar no tiene tipo de producto definido. No se puede editar.")
                            if 'tipo_producto_objeto' in st.session_state: del st.session_state['tipo_producto_objeto']
                            if 'tipo_producto_seleccionado' in st.session_state: del st.session_state['tipo_producto_seleccionado']
                            st.session_state.modo_edicion = False # Salir del modo edición
                            st.session_state.cotizacion_a_editar_id = None
                            st.session_state.datos_cotizacion_editar = None
                            return # <-- AÑADIDO: Detener si falta el ID
                    else:
                        st.error(f"No se pudieron cargar detalles para Cotización ID {cotizacion_id_editar}.")
                        st.session_state.modo_edicion = False
                        st.session_state.cotizacion_a_editar_id = None
                        st.rerun()
            else:
                 # Ya tenemos los datos cargados, usarlos
                 datos_cargados = st.session_state.datos_cotizacion_editar 
        else:
             st.warning("Modo edición activado pero no se encontró ID.")
             st.session_state.modo_edicion = False
             # Limpiar por si acaso
             if 'datos_cotizacion_editar' in st.session_state: del st.session_state['datos_cotizacion_editar']
             st.rerun()

    # --- Barra de Edición (si aplica) --- 
    if is_edit_mode:
        edit_cols = st.columns([0.8, 0.2])
        with edit_cols[0]:
            st.warning("**✏️ Modo Edición:** Modificando cotización existente. Los cambios sobrescribirán la versión anterior.")
            st.caption("Nota: Precios actuales de materiales/acabados serán usados al recalcular.")
        with edit_cols[1]:
            if st.button("❌ Cancelar Edición", key="cancel_edit_button", use_container_width=True):
                st.session_state.modo_edicion = False
                st.session_state.cotizacion_a_editar_id = None
                st.session_state.datos_cotizacion_editar = None
                SessionManager.reset_calculator_widgets()
                st.session_state.current_view = 'manage_quotes' # Volver a la lista
                st.rerun()
        st.divider()
        st.title("📝 Editar Cotización") 
    else:
        st.title("📊 Cotizador Flexo Impresos")
    # --- Fin Barra Edición ---
    
    st.write(f"Selecciona un cliente y un tipo de producto para comenzar a cotizar.")
    
    clientes = get_filtered_clients()
    default_cliente_index = 0
    if is_edit_mode and datos_cargados:
        cliente_id_cargado = datos_cargados.get('cliente_id')
        if cliente_id_cargado:
            try:
                default_cliente_index = next(i for i, c in enumerate(clientes) if c.id == cliente_id_cargado)
            except StopIteration:
                 st.warning(f"Cliente ID {cliente_id_cargado} no encontrado.")
                 default_cliente_index = 0 
                 
    cliente_seleccionado = st.selectbox(
        "Cliente",
        options=clientes,
        format_func=lambda x: x.nombre,
        index=default_cliente_index, 
        key="cliente_selector",
        disabled=is_edit_mode # Deshabilitar en modo edición
    )
    
    if cliente_seleccionado:
        st.session_state.cliente_seleccionado = cliente_seleccionado 
        
        # === INICIO SECCIÓN FUERA DEL FORMULARIO ===
        
        # -- Tipo de Producto (Fuera del form) --
        tipo_producto_seleccionado_id = None
        tipo_producto_objeto = None
        if not is_edit_mode:
            # Permitir seleccionar si no estamos editando
            if 'tipo_producto_seleccionado' not in st.session_state:
                tipos_producto = st.session_state.initial_data.get('tipos_producto', [])
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
                    # Limpiar material/adhesivo si cambia tipo producto
                    st.session_state['material_id'] = None
                    st.session_state['adhesivo_id'] = None
                    st.rerun()
            else:
                # Mostrar tipo ya seleccionado y botón para cambiar
                tipo_producto_seleccionado_id = st.session_state['tipo_producto_seleccionado']
                
                # --- VERIFICACIÓN ADICIONAL: Si el ID es None, manejar como si no existiera la clave ---
                if tipo_producto_seleccionado_id is None:
                    st.warning("Debe seleccionar un tipo de producto para continuar.")
                    # Limpiar la clave del estado para forzar el flujo correcto
                    del st.session_state['tipo_producto_seleccionado']
                    if 'tipo_producto_objeto' in st.session_state: 
                        del st.session_state['tipo_producto_objeto']
                    # Forzar rerun para mostrar el selector de tipo
                    st.rerun()
                # --- FIN VERIFICACIÓN ADICIONAL ---
                
                # --- REFUERZO: Volver a buscar el objeto desde el ID --- 
                tipos_producto_list = st.session_state.initial_data.get('tipos_producto', [])
                tipo_producto_objeto = next((tp for tp in tipos_producto_list if tp.id == tipo_producto_seleccionado_id), None)
                
                # Guardar el objeto recuperado (o None si no se encontró) de nuevo en el estado
                st.session_state['tipo_producto_objeto'] = tipo_producto_objeto 
                # -----------------------------------------------------
                
                # --- Verificación (ya existente y ahora más robusta) --- 
                if tipo_producto_objeto is not None:
                    st.success(f"Tipo producto: {tipo_producto_objeto.nombre}")
                else:
                    # Ahora este error indica que el ID guardado no corresponde a ningún tipo válido
                    st.error(f"Error crítico: ID de tipo de producto ({tipo_producto_seleccionado_id}) inválido en sesión.")
                    if st.button("Reintentar selección de producto"):
                         del st.session_state['tipo_producto_seleccionado']
                         if 'tipo_producto_objeto' in st.session_state: del st.session_state['tipo_producto_objeto']
                         st.rerun()
                    return # Detener ejecución si el objeto es None aquí
                    
                if st.button("Cambiar tipo de producto"):
                    del st.session_state['tipo_producto_seleccionado']
                    del st.session_state['tipo_producto_objeto']
                    # Limpiar también material/adhesivo
                    st.session_state['material_id'] = None
                    st.session_state['adhesivo_id'] = None
                    st.rerun()
        else: 
            # Modo edición: solo mostrar, obtener ID y objeto del estado
            tipo_producto_seleccionado_id = st.session_state.get('tipo_producto_seleccionado')
            tipo_producto_objeto = st.session_state.get('tipo_producto_objeto')
            if tipo_producto_objeto is not None: # <-- CORRECCIÓN: Check explícito para None
                 st.success(f"Tipo producto: {tipo_producto_objeto.nombre} (No editable)")
            else:
                 st.error("Error: Tipo de producto no definido en modo edición.")
                 return # No continuar si falta en modo edición
        
        # Determinar es_manga basado en la selección (necesario para _mostrar_material)
        es_manga = (tipo_producto_seleccionado_id == 2) if tipo_producto_seleccionado_id else False
        st.session_state['es_manga'] = es_manga
        
        # -- Material (Fuera del form, si ya se seleccionó Tipo Producto) --
        material_obj_actual = None
        if tipo_producto_seleccionado_id:
            materiales = st.session_state.initial_data.get('materiales', [])
            _mostrar_material(es_manga, materiales, datos_cargados)
            st.divider()
            # Obtener el objeto material actual DESPUÉS de llamar a _mostrar_material
            material_obj_actual = st.session_state.get('material_select')
        
        # -- Adhesivo (Fuera del form, si aplica y hay material) --
        if not es_manga and material_obj_actual:
            material_id_actual = material_obj_actual.id
            adhesivos_filtrados = []
            db = st.session_state.db
            try:
                print(f"APP: Llamando a get_adhesivos_for_material para ID: {material_id_actual}") # DEBUG
                adhesivos_filtrados = db.get_adhesivos_for_material(material_id_actual)
                print(f"APP: Resultado get_adhesivos_for_material: {len(adhesivos_filtrados)} items") # DEBUG
            except Exception as e:
                st.error(f"APP: Error al obtener adhesivos: {e}")
                
            # Llamar a _mostrar_adhesivo fuera del form
            _mostrar_adhesivo(adhesivos_filtrados, material_obj_actual, datos_cargados)
            st.divider()
            
        # -- Grafado (Fuera del form, si es manga) --
        if es_manga:
            tipos_grafado = st.session_state.initial_data.get('tipos_grafado', [])
            _mostrar_grafado_altura(es_manga, tipos_grafado, datos_cargados)
            st.divider()
            
        # -- Ajustes Admin (Fuera del form) --> SE MOVERÁ AL FINAL <--
        # _mostrar_ajustes_admin() 
        # st.divider()

        # === FIN SECCIÓN FUERA DEL FORMULARIO (INICIAL) ===
        
        # --- INICIO FORMULARIO (SOLO WIDGETS INTERNOS) --- 
        # Mostrar el formulario SOLO si ya se seleccionó el tipo de producto
        if tipo_producto_seleccionado_id:
            # Ya no usamos st.form aquí, los widgets se leen directamente de session_state
            # Eliminamos with st.form(...) y st.form_submit_button
            
            # === MOVER LÓGICA DE ESCALAS AQUÍ ===
            # --- INICIO: Lógica para obtener valor inicial de escalas en modo edición --- 
            default_escalas_str = "" 
            if is_edit_mode and datos_cargados:
                escalas_guardadas = datos_cargados.get('escalas_guardadas') 
                if escalas_guardadas and isinstance(escalas_guardadas, list):
                    default_escalas_str = ", ".join(map(str, escalas_guardadas))
                    print(f"-- DEBUG (Modo Edición): Escalas cargadas: {escalas_guardadas} -> String: '{default_escalas_str}'")
                else:
                    print(f"-- DEBUG (Modo Edición): No se encontraron 'escalas_guardadas' válidas.")
            # --- FIN: Lógica para obtener valor inicial --- 
            # ====================================
            
            # Llamar a la función refactorizada para mostrar secciones internas
            # PASAR default_escalas_str A LA FUNCIÓN
            mostrar_secciones_internas_formulario(
                es_manga=es_manga, 
                initial_data=st.session_state.initial_data, 
                datos_cargados=datos_cargados, 
                default_escalas=default_escalas_str # <-- NUEVO ARGUMENTO
            )
            
            # -- EL CÓDIGO AÑADIDO ERRÓNEAMENTE POR EL PASO ANTERIOR SE ELIMINA DE AQUÍ --
            
            # --- Ajustes Admin YA NO ESTÁ AQUÍ --- 

            # --- El botón Calcular/Actualizar se mueve abajo --- 
                
            # --- MOVER AJUSTES ADMIN AQUÍ (SOLO DESPUÉS DE SELECCIONAR TIPO PRODUCTO) --- 
        st.divider() # Añadir un divisor antes de los ajustes
        _mostrar_ajustes_admin() # Llamar a la función de ajustes aquí
        # --- NO MOSTRAR AJUSTES ADMIN AQUÍ SI NO SE HA SELECCIONADO TIPO PRODUCTO --- 
        # st.divider()
        # _mostrar_ajustes_admin()
        # st.divider()

        # --- MOVER BOTÓN CALCULAR/ACTUALIZAR AQUÍ --- 
        if tipo_producto_seleccionado_id: # Solo mostrar si hay tipo producto
            # Mostrar ajustes Admin también solo después de seleccionar tipo producto
            st.divider()

            button_label = "Actualizar Cálculo" if is_edit_mode else "Calcular"
            if st.button(button_label, key="calculate_button_main"):
                # === RECOLECTAR DATOS ===
                datos_formulario_enviado = {}
                validation_errors = []
                try:
                    # ** Obtener valores de FUERA del form (desde session_state) **
                    datos_formulario_enviado['material_id'] = st.session_state.get('material_id')
                    datos_formulario_enviado['adhesivo_id'] = st.session_state.get('adhesivo_id') # Será None si es manga o no se seleccionó
                    datos_formulario_enviado['tipo_producto_id'] = st.session_state.get('tipo_producto_seleccionado')
                    datos_formulario_enviado['es_manga'] = st.session_state.get('es_manga')
                    
                    # Validar que los IDs necesarios (fuera del form) existan
                    if not datos_formulario_enviado['material_id']:
                         validation_errors.append("Material no definido en sesión.")
                    if not datos_formulario_enviado['es_manga'] and not datos_formulario_enviado['adhesivo_id']:
                         validation_errors.append("Adhesivo no definido en sesión para etiquetas.")
                    if not datos_formulario_enviado['tipo_producto_id']:
                        validation_errors.append("Tipo de producto no definido en sesión.")

                    # ** Obtener valores de DENTRO del form (desde session_state via keys) **
                    # Escalas 
                    escalas_texto = st.session_state.get('escalas_texto_input', '')
                    escalas_usuario = [int(e.strip()) for e in escalas_texto.split(",") if e.strip()]
                    if not escalas_usuario or any(e < 100 for e in escalas_usuario):
                        raise ValueError("Ingrese al menos una escala válida (>= 100).")
                    datos_formulario_enviado['escalas'] = sorted(list(set(escalas_usuario)))
                    
                    # Dimensiones y Tintas
                    datos_formulario_enviado['ancho'] = float(st.session_state.get('ancho', 0.0))
                    datos_formulario_enviado['avance'] = float(st.session_state.get('avance', 0.0))
                    datos_formulario_enviado['num_tintas'] = int(st.session_state.get('num_tintas', 0))
                    # Pistas 
                    if datos_formulario_enviado['es_manga']:
                         if st.session_state.get('usuario_rol') == 'comercial': datos_formulario_enviado['pistas'] = 1
                         else: datos_formulario_enviado['pistas'] = int(st.session_state.get('num_pistas_manga', 1))
                    else:
                        datos_formulario_enviado['pistas'] = int(st.session_state.get('num_pistas_otro', 1))

                    # Acabado/Grafado
                    if datos_formulario_enviado['es_manga']:
                        grafado_obj = st.session_state.get('tipo_grafado_select')
                        if grafado_obj:
                            datos_formulario_enviado['tipo_grafado_id'] = grafado_obj.id
                            datos_formulario_enviado['tipo_grafado_nombre'] = grafado_obj.nombre

                            # --- Validación de altura_grafado ---
                            if grafado_obj.id in [3, 4]: # IDs que requieren altura
                                altura_grafado_value = st.session_state.get('altura_grafado')
                                if altura_grafado_value is not None:
                                    try:
                                        # Intentar convertir a float solo si no es None
                                        datos_formulario_enviado['altura_grafado'] = float(altura_grafado_value)
                                    except (ValueError, TypeError):
                                        validation_errors.append("Altura de grafado debe ser un número válido.")
                                        datos_formulario_enviado['altura_grafado'] = None
                                else:
                                    # Es requerido, así que si es None, es un error
                                    validation_errors.append("Altura de grafado es requerida para este tipo de grafado.")
                                    datos_formulario_enviado['altura_grafado'] = None
                            # --- Fin Validación ---
                            else: # Si el tipo de grafado no requiere altura
                                datos_formulario_enviado['altura_grafado'] = None
                        else:
                            validation_errors.append("Tipo de grafado no seleccionado.")
                        datos_formulario_enviado['acabado_id'] = None
                    else: # Etiqueta
                        acabado_obj = st.session_state.get('acabado_select')
                        if acabado_obj:
                            datos_formulario_enviado['acabado_id'] = acabado_obj.id
                        else:
                            validation_errors.append("Acabado no seleccionado.")
                        datos_formulario_enviado['tipo_grafado_id'] = None
                        datos_formulario_enviado['altura_grafado'] = None

                    # Empaque
                    datos_formulario_enviado['num_paquetes'] = int(st.session_state.get('num_paquetes', 0))
                    # Opciones Adicionales
                    datos_formulario_enviado['tiene_troquel'] = bool(st.session_state.get('tiene_troquel', False))
                    datos_formulario_enviado['planchas_separadas'] = bool(st.session_state.get('planchas_separadas', False))
                    # Forma de Pago 
                    forma_pago_obj = st.session_state.get('forma_pago_select')
                    if forma_pago_obj: datos_formulario_enviado['forma_pago_id'] = forma_pago_obj.id
                    else: validation_errors.append("Forma de pago no seleccionada.")
                         
                    # Calcular ID Combinado (como antes)
                    mat_id = datos_formulario_enviado.get('material_id')
                    adh_id = datos_formulario_enviado.get('adhesivo_id')
                    id_combinado = None
                    if mat_id:
                        db = st.session_state.db
                        if datos_formulario_enviado['es_manga']:
                            ID_SIN_ADHESIVO = 4 # Asumiendo ID 4
                            ma_entry = db.get_material_adhesivo_entry(mat_id, ID_SIN_ADHESIVO)
                            if ma_entry: id_combinado = ma_entry['id']
                        elif adh_id:
                            ma_entry = db.get_material_adhesivo_entry(mat_id, adh_id)
                            if ma_entry: id_combinado = ma_entry['id']
                    if id_combinado: datos_formulario_enviado['material_adhesivo_id'] = id_combinado
                    else: validation_errors.append("No se encontró ID combinado Material/Adhesivo. Verifique config.")
                         
                except ValueError as ve: validation_errors.append(f"Error en valor numérico: {ve}")
                except KeyError as ke: validation_errors.append(f"Falta un campo esperado en session_state: {ke}")
                except Exception as e: validation_errors.append(f"Error inesperado recolectando datos: {e}")
                # === FIN RECOLECCIÓN ===
                
                # --- Validación y Ejecución --- 
                if not validation_errors:
                    # Necesitamos el objeto cliente seleccionado, asegurarnos que está en sesión
                    cliente_seleccionado = st.session_state.get('cliente_seleccionado')
                    if cliente_seleccionado:
                        resultados = handle_calculation(datos_formulario_enviado, cliente_seleccionado)
                    else:
                        st.error("Error interno: Cliente no encontrado en sesión.")
                else:
                    for error in validation_errors: st.error(error)
                    st.warning("No se pudo calcular debido a errores en los datos ingresados.")
        # --- FIN MOVIMIENTO BOTÓN ---

def show_manage_clients():
    """Muestra la vista para gestionar clientes."""
    st.title("Gestión de Clientes")
    
    # Botón para crear nuevo cliente
    if st.button("➕ Crear Nuevo Cliente"):
        st.session_state.current_view = 'crear_cliente'
        st.rerun()
        return
        
    # Mostrar lista de clientes existentes
    db_manager = st.session_state.db
    user_role = st.session_state.usuario_rol
    
    try:
        clientes = db_manager.get_clientes()
        if clientes:
            # Crear DataFrame para mostrar los clientes
            df_clientes = pd.DataFrame([{
                'NIT': c.codigo,
                'Nombre': c.nombre,
                'Contacto': c.persona_contacto or '',
                'Correo': c.correo_electronico or '',
                'Teléfono': c.telefono or ''
            } for c in clientes])
            
            st.dataframe(
                df_clientes,
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No hay clientes registrados.")
    except Exception as e:
        st.error(f"Error al cargar los clientes: {str(e)}")

def show_create_client():
    """Muestra el formulario para crear un nuevo cliente."""
    st.title("Crear Nuevo Cliente")
    
    # Botón para volver a la lista de clientes
    if st.button("← Volver a la lista de clientes"):
        st.session_state.current_view = 'manage_clients'
        st.rerun()
        return

    # Formulario de creación de cliente
    with st.form("crear_cliente_form"):
        st.write("### Información del Cliente")
        
        # Campos del formulario
        nit = st.text_input("NIT/CC *", 
                           help="Identificador único del cliente (solo números)")
        nombre = st.text_input("Nombre del Cliente *",
                             help="Nombre completo o razón social")
        
        col1, col2 = st.columns(2)
        with col1:
            contacto = st.text_input("Persona de Contacto",
                                   help="Nombre de la persona de contacto")
            telefono = st.text_input("Teléfono",
                                   help="Número de teléfono del cliente")
        
        with col2:
            email = st.text_input("Correo Electrónico",
                                help="Correo electrónico de contacto",
                                key="email_input")
        
        # Botón de submit
        submitted = st.form_submit_button("Crear Cliente")
        
        if submitted:
            # Validaciones básicas
            if not nit or not nombre:
                st.error("Los campos NIT y Nombre son obligatorios.")
                return
                
            # Validar que el NIT sea numérico
            if not nit.isdigit():
                st.error("El NIT debe contener solo números.")
                return
            
            # Validar formato de correo si se proporciona
            if email and '@' not in email:
                st.error("Por favor ingrese un correo electrónico válido.")
                return
                
            try:
                # Crear objeto Cliente
                nuevo_cliente = Cliente(
                    id=None,  # El ID será asignado por la base de datos
                    codigo=nit,
                    nombre=nombre,
                    persona_contacto=contacto if contacto else None,
                    correo_electronico=email if email else None,
                    telefono=telefono if telefono else None
                )
                
                # Intentar crear el cliente
                db = st.session_state.db
                cliente_creado = db.crear_cliente(nuevo_cliente)
                
                if cliente_creado:
                    st.success("¡Cliente creado exitosamente!")
                    # Esperar un momento y redirigir
                    time.sleep(2)
                    st.session_state.current_view = 'manage_clients'
                    st.rerun()
                else:
                    st.error("No se pudo crear el cliente. Por favor, intente nuevamente.")
                    
            except Exception as e:
                error_msg = str(e)
                if "duplicate key" in error_msg.lower():
                    st.error(f"Ya existe un cliente con el NIT {nit}.")
                else:
                    st.error(f"Error al crear el cliente: {error_msg}")
                if st.session_state.get('usuario_rol') == 'administrador':
                    st.exception(e)

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
        
    # --- Mostrar Navegación --- 
    show_navigation()
    # ------------------------

    # --- Cargar datos iniciales si no están ---
    # Asegurar que la clave exista, aunque sea como None inicialmente
    if 'initial_data' not in st.session_state:
        st.session_state.initial_data = None 

    # Intentar cargar solo si aún no tenemos datos válidos
    if st.session_state.initial_data is None: 
        with st.spinner("Cargando datos iniciales (materiales, acabados, etc.)..."):
            try:
                # Llamar a la función cacheada
                data = load_initial_data() 
                if data:
                    st.session_state.initial_data = data
                else:
                    # Si load_initial_data devuelve None o {}, marcamos que no se cargó
                    st.session_state.initial_data = None 
                    SessionManager.add_message('error', "Error crítico: No se pudieron cargar los datos iniciales necesarios (empty data returned).")
            except Exception as e_load:
                 st.session_state.initial_data = None # Marcar como no cargado en excepción
                 SessionManager.add_message('error', f"Excepción al cargar datos iniciales: {e_load}")
                 if st.session_state.get('usuario_rol') == 'administrador':
                     st.exception(e_load)

    # Verificar si los datos se cargaron correctamente ANTES de continuar
    if not st.session_state.get('initial_data'):
        st.error("No se pudieron cargar los datos iniciales. La aplicación no puede continuar.")
        # Mostrar mensajes de error acumulados
        if st.session_state.messages:
            for msg_type, message in st.session_state.messages:
                if msg_type == 'error': st.error(message)
                else: st.info(message)
            SessionManager.clear_messages()
        st.stop() # Detener ejecución si los datos no están
    # --------------------------------------------

    # Mostrar la vista actual
    current_view = st.session_state.get('current_view', 'calculator') # Obtener vista actual

    if current_view == 'calculator':
        mostrar_calculadora()
    elif current_view == 'quote_results':
        show_quote_results()
    elif current_view == 'manage_quotes':
        # --- MODIFICACIÓN: Llamar a la función importada --- 
        show_manage_quotes()
        # --------------------------------------------------
    elif current_view == 'manage_clients':
        # --- MODIFICACIÓN: Llamar a la función importada --- 
        show_manage_clients()
        # --------------------------------------------------
    elif current_view == 'crear_cliente':
        # --- MODIFICACIÓN: Llamar a la función importada --- 
        show_create_client()
        # --------------------------------------------------
    # --- MODIFICACIÓN: Llamar a la función importada --- 
    elif current_view == 'dashboard':
        show_dashboard()
    # --------------------------------------------------
    # --- NUEVA OPCIÓN DE MENÚ ---
    elif current_view == 'manage_values':
        show_manage_values()
    # ---------------------------
    # elif st.session_state.current_view == 'reports': # Ya no se usa directamente
    #     show_reports()
    else:
        # Si la vista no coincide con ninguna opción, volver a la calculadora
        st.warning(f"Vista desconocida: {current_view}. Volviendo a la calculadora.")
        st.session_state.current_view = 'calculator'
        st.rerun()

def show_quote_results():
    """Muestra los resultados de la cotización calculada."""
    # --- MOSTRAR INFORME SI YA ESTÁ GUARDADA ---
    if st.session_state.get('cotizacion_guardada', False) and st.session_state.get('cotizacion_id') is not None:
        # Obtener el número de cotización de los datos completos
        numero_cotizacion = None
        if 'datos_completos_cot' in st.session_state and st.session_state.datos_completos_cot:
            numero_cotizacion = st.session_state.datos_completos_cot.get('numero_cotizacion', None)
            
        # Mostrar mensaje con el número de cotización si está disponible
        if numero_cotizacion:
            st.success(f"Cotización #{numero_cotizacion} guardada ✓")
        else:
            st.success(f"Cotización #{st.session_state.cotizacion_id} guardada ✓")
        
        # --- Botones de PDF y Nueva Cotización ---
        col_pdf, col_new = st.columns(2)
        with col_pdf:
             # --- Lógica para botón Generar PDF --- 
             if st.button("📄 Generar PDF", key="pdf_button_saved"):
                  with st.spinner("Generando PDF..."):
                      try:
                          # Obtener datos completos usando el ID guardado
                        cotizacion_id = st.session_state.cotizacion_id
                        datos_pdf = st.session_state.db.get_datos_completos_cotizacion(cotizacion_id)
                        if datos_pdf:
                              print(f"DEBUG PDF COTIZACION: datos_pdf contiene: {datos_pdf}") # <-- LÍNEA DE DEBUG AÑADIDA
                              pdf_gen = CotizacionPDF()
                              pdf_bytes = pdf_gen.generar_pdf(datos_pdf)
                              # Ofrecer descarga
                              st.download_button(
                                  label="Descargar PDF Ahora",
                                  data=pdf_bytes,
                                file_name=f"{datos_pdf.get('identificador', f'Cotizacion_{datos_pdf.get('consecutivo', 'N')}').replace(' ', '_')}.pdf", # Usar identificador, con fallback y reemplazo de espacios
                                  mime="application/pdf"
                              )
                        else:
                              st.error("No se pudieron obtener los datos completos para generar el PDF.")
                      except Exception as e_pdf:
                          st.error(f"Error generando PDF: {e_pdf}")
                          traceback.print_exc()
        
        with col_new:
            if st.button("Nueva Cotización", key="new_quote_button_saved"):
                # Resetear todo para una nueva cotización
                st.session_state.current_view = 'calculator'
                st.session_state.cotizacion_guardada = False
                st.session_state.referencia_guardar = ""
                st.session_state.cotizacion_model = None
                st.session_state.current_calculation = None
                st.session_state.modo_edicion = False
                st.session_state.cotizacion_id_editar = None
                st.session_state.datos_cotizacion_editar = None
                if 'recotizacion_info' in st.session_state:
                    del st.session_state['recotizacion_info']
                if 'informe_tecnico_md' in st.session_state: # Limpiar informe anterior
                    del st.session_state['informe_tecnico_md']
                SessionManager.reset_calculator_widgets()
                st.rerun()
                
        # --- MOSTRAR INFORME TÉCNICO (SI EXISTE) ---
        st.divider() # Separador visual
        st.subheader("Informe Técnico para Impresión")
        informe_md = st.session_state.get("informe_tecnico_md", "*El informe técnico se genera al guardar la cotización.*")
        st.markdown(informe_md)
        
        # Botón para descargar el informe en PDF
        if 'cotizacion_guardada' in st.session_state and st.session_state.cotizacion_guardada and informe_md and informe_md != "*El informe técnico se genera al guardar la cotización.*":
            try:
                # Generar nombre de archivo usando número de cotización o identificador
                id_para_archivo = 'informe'  # Valor predeterminado
                nombre_cliente = ''
                if 'datos_completos_cot' in st.session_state and st.session_state.datos_completos_cot:
                    nombre_cliente = st.session_state.datos_completos_cot.get('cliente_nombre', '').replace(' ', '_')
                    numero_cotizacion = st.session_state.datos_completos_cot.get('numero_cotizacion', '')
                    if numero_cotizacion:
                        id_para_archivo = f"{numero_cotizacion}_{nombre_cliente}"
                
                nombre_archivo = f"Informe_Tecnico_{id_para_archivo}"
                
                # Generar enlace de descarga
                pdf_download_link = markdown_a_pdf(informe_md, nombre_archivo)
                if pdf_download_link:
                    st.markdown(pdf_download_link, unsafe_allow_html=True)
                else:
                    st.error("No se pudo generar el PDF para descarga.")
            except Exception as e_pdf:
                st.error(f"Error al preparar PDF para descarga: {e_pdf}")
        # -----------------------------------------
        return # Terminar aquí si ya está guardada

    # --- Lógica si la cotización AÚN NO está guardada ---
    if 'current_calculation' not in st.session_state or not st.session_state.current_calculation:
        st.error("No hay resultados para mostrar. Por favor, realice un cálculo primero.")
        if st.button("Volver a Calcular", key="back_to_calc_no_results"):
            st.session_state.current_view = 'calculator'
            st.rerun()
        return
    if 'cotizacion_model' not in st.session_state or st.session_state.cotizacion_model is None:
        st.error("Error interno: Modelo de cotización no preparado. Por favor, recalcule.")
        if st.button("Volver a Calcular", key="back_to_calc_no_model"):
            st.session_state.current_view = 'calculator'
            st.rerun()
        return
    calc = st.session_state.current_calculation
    if 'calculos_para_guardar' not in calc or not calc['calculos_para_guardar']:
        st.error("Error interno: Datos de cálculo para guardar no encontrados. Por favor, recalcule.")
        if st.button("Volver a Calcular", key="back_to_calc_no_save_data"):
            st.session_state.current_view = 'calculator'
            st.rerun()
        return
    
    cotizacion_preparada = st.session_state.cotizacion_model # Modelo listo para guardar
    datos_calculo_persistir = calc['calculos_para_guardar']
    
    st.markdown("## Resultados de la Cotización")
    

    # Mostrar resultados para cada escala
    st.markdown("### Resultados por Escala")
    resultados_df = pd.DataFrame(calc['results'])
    
    # Si existe el campo num_tintas_mostrar, usar ese para mostrar en lugar de num_tintas
    if 'num_tintas_mostrar' in resultados_df.columns:
        # Hacemos una copia para no modificar los datos originales guardados en session_state
        df_mostrar = resultados_df.copy()
        # Renombrar la columna para mayor claridad en el dataframe
        df_mostrar = df_mostrar.rename(columns={'num_tintas_mostrar': 'Tintas'})
        # Quitar columnas internas/técnicas que no son necesarias para el usuario
        columnas_a_quitar = ['num_tintas_original', 'num_tintas_interno', 'num_tintas']
        columnas_mostrar = [col for col in df_mostrar.columns if col not in columnas_a_quitar]
        st.dataframe(df_mostrar[columnas_mostrar])
    else:
        # Si no existe, mostrar el dataframe original
        st.dataframe(resultados_df)
    
    st.divider()
    
    # --- Formulario y Lógica de Guardado --- 
    is_edit_mode = st.session_state.get('modo_edicion', False)
    section_title = "Actualizar Cotización" if is_edit_mode else "Guardar Cotización"
    button_label = "💾 Actualizar" if is_edit_mode else "💾 Guardar Cotización"
    st.markdown(f"#### {section_title}")
    
    default_referencia = ""
    if is_edit_mode and 'datos_cotizacion_editar' in st.session_state and st.session_state.datos_cotizacion_editar:
        default_referencia = st.session_state.datos_cotizacion_editar.get('referencia_descripcion', "")
    elif 'referencia_guardar' in st.session_state:
        default_referencia = st.session_state.referencia_guardar
    
    with st.form("guardar_cotizacion_form"):
        referencia_desc = st.text_input(
            "Descripción de la referencia *",
            value=default_referencia,
            key="referencia_guardar_input", 
            help="Ingrese un nombre o descripción única para esta cotización (Ej: Etiqueta XYZ V1)"
        )
        
        # Selección de Comercial (Solo Admin)
        selected_comercial_id = None 
        if st.session_state.get('usuario_rol') == 'administrador':
            try:
                comerciales = st.session_state.db.get_perfiles_by_role('comercial')
                if comerciales:
                    opciones_comercial = [(c['id'], c['nombre']) for c in comerciales] 
                    opciones_display = [(None, "-- Seleccione Comercial --")] + opciones_comercial
                    default_comercial_index = 0
                    comercial_id_cargado = None
                    if is_edit_mode and 'datos_cotizacion_editar' in st.session_state and st.session_state.datos_cotizacion_editar:
                        comercial_id_cargado = st.session_state.datos_cotizacion_editar.get('comercial_id') 
                        if comercial_id_cargado:
                            try:
                                default_comercial_index = next(i for i, (id, _) in enumerate(opciones_display) if id == comercial_id_cargado)
                            except StopIteration:
                                default_comercial_index = 0 
                    selected_option = st.selectbox(
                        "Asignar a Comercial *", 
                        options=opciones_display, 
                        format_func=lambda x: x[1], 
                        key="comercial_selector_admin", 
                        index=default_comercial_index,
                        help="Seleccione el comercial al que pertenece esta cotización."
                    )
                else:
                    st.warning("No se encontraron comerciales para asignar.")
            except Exception as e_comm:
                st.error(f"Error al cargar lista de comerciales: {e_comm}")

        guardar = st.form_submit_button(button_label, type="primary")
        
        if guardar:
            # --- INICIO DEBUG ---
            print("--- DEBUG: Botón Guardar presionado ---")
            # --- FIN DEBUG ---
            error_guardado = False
            # Validaciones
            if not referencia_desc.strip():
                st.error("Debe ingresar una Referencia / Descripción para guardar la cotización.")
                error_guardado = True
            comercial_id_para_guardar = None
            if st.session_state.get('usuario_rol') == 'administrador':
                selected_comercial_tuple = st.session_state.get("comercial_selector_admin")
                selected_comercial_id = selected_comercial_tuple[0] if selected_comercial_tuple else None
                if selected_comercial_id is None:
                    st.error("Como administrador, debe seleccionar un comercial.")
                    error_guardado = True
                else:
                    comercial_id_para_guardar = selected_comercial_id
            else:
                comercial_id_para_guardar = st.session_state.user_id 
            
            # --- INICIO DEBUG ---
            print(f"--- DEBUG: Validaciones pasadas: {not error_guardado} ---")
            # --- FIN DEBUG ---

            # Proceso de Guardado/Actualización
            if not error_guardado:
                st.session_state.referencia_guardar = referencia_desc 
                spinner_text = "Actualizando cotización..." if is_edit_mode else "Guardando cotización..."
                # --- INICIO DEBUG ---
                print(f"--- DEBUG: Intentando guardar/actualizar. Modo edición: {is_edit_mode} ---")
                # --- FIN DEBUG ---
                with st.spinner(spinner_text):
                    try:
                        cliente_id = calc['cliente'].id 
                        if not comercial_id_para_guardar or not cliente_id or not datos_calculo_persistir:
                             st.error("Error interno: Faltan datos (cliente, comercial o cálculos).")
                             # --- INICIO DEBUG ---
                             print(f"--- DEBUG: Faltan datos! Comercial: {comercial_id_para_guardar}, Cliente: {cliente_id}, Datos Calculo: {'Sí' if datos_calculo_persistir else 'No'} ---")
                             # --- FIN DEBUG ---
                        else:
                            manager = st.session_state.cotizacion_manager
                            success = False
                            message = ""
                            cotizacion_id_final = None

                            # --- INICIO DEBUG ---
                            print(f"--- DEBUG: Llamando al manager. Modo edición: {is_edit_mode} ---")
                            # --- FIN DEBUG ---
                            if is_edit_mode:
                                cotizacion_id_a_actualizar = st.session_state.get('cotizacion_id_editar')
                                if not cotizacion_id_a_actualizar:
                                     st.error("Error: ID de cotización a editar no encontrado.")
                                else:
                                    es_recotizacion = False
                                    recotizacion_info_actual = st.session_state.get('recotizacion_info')
                                    if recotizacion_info_actual and recotizacion_info_actual['id'] == cotizacion_id_a_actualizar:
                                        es_recotizacion = True
                                    
                                    # --- DETECCIÓN DE AJUSTES ADMIN --- 
                                    admin_ajustes_activos = False
                                    if st.session_state.get('usuario_rol') == 'administrador':
                                        # Verificar todas las posibles formas de ajuste
                                        rentabilidad_ajustada = st.session_state.get('rentabilidad_ajustada')
                                        
                                        # --- DIAGNÓSTICO ESPECÍFICO DE RENTABILIDAD ---
                                        rentabilidad_modificada = st.session_state.get('ajustar_rentabilidad') or (rentabilidad_ajustada is not None and rentabilidad_ajustada > 0)
                                        # --- INICIO DEBUG: Diagnóstico Rentabilidad ---
                                        if rentabilidad_modificada:
                                            print(f"⚠️ DEBUG: Admin modificó rentabilidad. ajustar_rentabilidad={st.session_state.get('ajustar_rentabilidad')}, rentabilidad_ajustada={rentabilidad_ajustada}")
                                        # --- FIN DEBUG ---
                                        # --- FIN DIAGNÓSTICO ESPECÍFICO ---
                                        
                                        if (st.session_state.get('ajustar_rentabilidad') or 
                                            st.session_state.get('ajustar_material') or 
                                            st.session_state.get('ajustar_troquel') or 
                                            st.session_state.get('ajustar_planchas') or
                                            (rentabilidad_ajustada is not None and rentabilidad_ajustada > 0)):
                                            admin_ajustes_activos = True
                                            # --- INICIO DEBUG: Ajustes Admin ---
                                            print(f"--- DEBUG: AJUSTES ADMIN DETECTADOS ---")
                                            print(f"  ajustar_rentabilidad: {st.session_state.get('ajustar_rentabilidad')}")
                                            print(f"  rentabilidad_ajustada: {rentabilidad_ajustada}")
                                            print(f"  ajustar_material: {st.session_state.get('ajustar_material')}")
                                            print(f"  ajustar_troquel: {st.session_state.get('ajustar_troquel')}")
                                            print(f"  ajustar_planchas: {st.session_state.get('ajustar_planchas')}")
                                            # --- FIN DEBUG ---
                                    # --- FIN DETECCIÓN --- 
                                    
                                    # --- INICIO DEBUG: Antes de llamar actualizar ---
                                    print(f"--- DEBUG: Llamando manager.actualizar_cotizacion_existente(cotizacion_id={cotizacion_id_a_actualizar}, ...) ---")
                                    # --- FIN DEBUG ---
                                    success, message = manager.actualizar_cotizacion_existente(
                                        cotizacion_id=cotizacion_id_a_actualizar,
                                        cotizacion_model=cotizacion_preparada, 
                                        cliente_id=cliente_id,
                                        referencia_descripcion=referencia_desc,
                                        comercial_id=comercial_id_para_guardar,
                                        datos_calculo=datos_calculo_persistir,
                                        modificado_por=st.session_state.user_id,
                                        es_recotizacion=es_recotizacion,
                                        admin_ajustes_activos=admin_ajustes_activos  # Pasar el nuevo parámetro
                                    )
                                    # --- INICIO DEBUG: Después de llamar actualizar ---
                                    print(f"--- DEBUG: Resultado manager.actualizar: success={success}, message='{message}' ---")
                                    # --- FIN DEBUG ---
                                    if success: 
                                        cotizacion_id_final = cotizacion_id_a_actualizar
                                        # --- INICIO DEBUG ---
                                        print(f"--- DEBUG: Después de actualizar, cotizacion_id_final={cotizacion_id_final}")
                                        # --- FIN DEBUG ---
                            else:
                                # --- INICIO DEBUG: Antes de llamar guardar nueva ---
                                print(f"--- DEBUG: Llamando manager.guardar_nueva_cotizacion(...) ---")
                                # --- FIN DEBUG ---
                                admin_ajustes_activos = calc.get('admin_ajustes_activos', False)
                                success, message, cotizacion_id = manager.guardar_nueva_cotizacion(
                                    cotizacion_preparada, 
                                    cliente_id,
                                    referencia_desc,
                                    comercial_id_para_guardar,
                                    datos_calculo_persistir, 
                                    admin_ajustes_activos 
                                )
                                # --- INICIO DEBUG: Después de llamar guardar nueva ---
                                print(f"--- DEBUG: Resultado manager.guardar_nueva: success={success}, message='{message}', cotizacion_id={cotizacion_id} ---")
                                # --- FIN DEBUG ---
                                if success: 
                                    cotizacion_id_final = cotizacion_id
                                    # --- INICIO DEBUG ---
                                    print(f"--- DEBUG: Después de guardar nueva, cotizacion_id_final={cotizacion_id_final}")
                                    # --- FIN DEBUG ---

                            # --- SI EL GUARDADO/ACTUALIZACIÓN FUE EXITOSO (código para ambos casos) --- 
                            if success and cotizacion_id_final:
                                # --- INICIO DEBUG ---
                                print(f"--- DEBUG: Guardado/Actualización exitoso (ID: {cotizacion_id_final}). Generando informe y limpiando... ---")
                                # --- FIN DEBUG ---
                                st.success(message)
                                st.session_state.cotizacion_guardada = True
                                st.session_state.cotizacion_id = cotizacion_id_final
                                
                                # --- GENERAR INFORME TÉCNICO AQUÍ --- 
                                try:
                                    # --- INICIO DEBUG ---
                                    print(f"--- DEBUG: Intentando generar informe para Cotización ID: {cotizacion_id_final}")
                                    # --- FIN DEBUG ---
                                    # Obtener datos completos y frescos de la cotización recién guardada/actualizada
                                    datos_completos_cot = st.session_state.db.get_full_cotizacion_details(cotizacion_id_final)
                                    if datos_completos_cot:
                                        st.session_state.datos_completos_cot = datos_completos_cot
                                        # Generar el markdown usando la función importada
                                        informe_md = generar_informe_tecnico_markdown(
                                            cotizacion_data=datos_completos_cot,
                                            calculos_guardados=datos_calculo_persistir # Usar los datos que se guardaron
                                        )
                                        st.session_state.informe_tecnico_md = informe_md
                                        # --- INICIO DEBUG ---
                                        print("--- DEBUG: Informe técnico generado y guardado en session_state. ---")
                                        # --- FIN DEBUG ---
                                    else:
                                        st.warning("Cotización guardada, pero no se pudieron obtener datos completos para generar el informe técnico.")
                                        st.session_state.informe_tecnico_md = "Error al obtener datos completos para el informe."
                                        # --- INICIO DEBUG ---
                                        print("--- DEBUG: Error al obtener datos completos para informe. ---")
                                        # --- FIN DEBUG ---
                                except Exception as e_report:
                                    st.warning(f"Cotización guardada, pero ocurrió un error al generar el informe técnico: {e_report}")
                                    traceback.print_exc()
                                    st.session_state.informe_tecnico_md = f"Error generando informe: {e_report}"
                                    # --- INICIO DEBUG ---
                                    print(f"--- DEBUG: Excepción generando informe: {e_report} ---")
                                    # --- FIN DEBUG ---
                                
                                # --- Limpieza post-éxito ---
                                st.session_state.modo_edicion = False 
                                st.session_state.cotizacion_id_editar = None 
                                st.session_state.datos_cotizacion_editar = None 
                                st.session_state.cotizacion_model = None # Limpiar modelo
                                st.session_state.current_calculation = None
                                if 'recotizacion_info' in st.session_state:
                                    del st.session_state['recotizacion_info']
                                SessionManager.reset_calculator_widgets()
                                # --- INICIO DEBUG ---
                                print(f"--- DEBUG: Rerun después de éxito. ---")
                                # --- FIN DEBUG ---
                                st.rerun() # Rerun para mostrar estado guardado y informe
                            elif not success:
                                st.error(f"Error al guardar/actualizar: {message}")
                                # --- INICIO DEBUG ---
                                print(f"--- DEBUG: Error reportado por el manager: {message} ---")
                                # --- FIN DEBUG ---
                    except CotizacionManagerError as cme:
                        st.error(f"Error en guardado/actualización: {cme}")
                        # --- INICIO DEBUG ---
                        print(f"--- DEBUG: CotizacionManagerError: {cme} ---")
                        # --- FIN DEBUG ---
                    except Exception as e_save:
                        st.error(f"Error inesperado: {e_save}")
                        traceback.print_exc()
                        # --- INICIO DEBUG ---
                        print(f"--- DEBUG: Excepción inesperada en guardado: {e_save} ---")
                        # --- FIN DEBUG ---
                                
    # Botón Nueva Cotización 
    st.divider()
    if st.button("Nueva Cotización", key="new_quote_button_results"):
        # Resetear todo para una nueva cotización
        st.session_state.current_view = 'calculator'
        st.session_state.cotizacion_guardada = False
        st.session_state.referencia_guardar = ""
        st.session_state.cotizacion_model = None
        st.session_state.current_calculation = None
        st.session_state.modo_edicion = False
        st.session_state.cotizacion_id_editar = None 
        st.session_state.datos_cotizacion_editar = None 
        if 'recotizacion_info' in st.session_state:
            del st.session_state['recotizacion_info']
        if 'informe_tecnico_md' in st.session_state: # Limpiar informe anterior
            del st.session_state['informe_tecnico_md']
        SessionManager.reset_calculator_widgets()
        st.rerun()

# La implementación de show_manage_quotes se ha movido a src/ui/manage_quotes_view.py
# y se importa al inicio del archivo como: from src.ui.manage_quotes_view import show_manage_quotes

def show_reports():
    """Muestra la vista de reportes."""
    st.title("Reportes")
    st.write("Funcionalidad de reportes en desarrollo.")
    # Aquí se implementará la lógica para mostrar reportes

if __name__ == "__main__":
    main()
