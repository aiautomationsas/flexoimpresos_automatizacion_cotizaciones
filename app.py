from datetime import datetime
import streamlit as st
from supabase import create_client
from typing import Optional, Dict, Any, Tuple
import pandas as pd
import traceback # Import traceback for detailed error logging
import math # <-- AÑADIR IMPORTACIÓN

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

        # --- GUARDAR DATOS DE CALCULO PARA GUARDADO POSTERIOR --- 
        # Guardamos los valores finales que se usaron en el cálculo
        # para pasarlos luego a guardar_calculos_escala
        
        # Calcular valor_troquel por defecto (si no ajustado) usando mejor_opcion
        valor_troquel_defecto = 0.0
        if not st.session_state.get('ajustar_troquel'):
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
             plancha_result = calc_lito.calcular_precio_plancha(datos_escala, num_tintas, es_manga)
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
            'num_tintas': num_tintas,
            'numero_pistas': datos_escala.pistas,
            'num_paquetes_rollos': form_data['num_paquetes'],
            'tipo_producto_id': form_data['tipo_producto_id'],
            'tipo_grafado_id': form_data.get('tipo_grafado_id'), # Usar ID guardado
            'altura_grafado': form_data.get('altura_grafado'),
            'valor_plancha_separado': None # Inicializar para aplicar la lógica de redondeo
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
        print(f"\nDEBUG: Calling calculadora.calcular_costos_por_escala with:")
        print(f"  - datos: {datos_escala}")
        print(f"  - num_tintas: {num_tintas}")
        # Pasar los mismos valores finales que se usarán para persistir
        print(f"  - valor_plancha (final): {datos_calculo_persistir['valor_plancha']}")
        print(f"  - valor_troquel (final): {datos_calculo_persistir['valor_troquel']}")
        print(f"  - valor_material (final): {datos_calculo_persistir['valor_material']}")
        print(f"  - valor_acabado: {datos_calculo_persistir['valor_acabado']}")
        print(f"  - es_manga: {es_manga}")
        print(f"  - tipo_grafado_id: {datos_calculo_persistir['tipo_grafado_id']}")
        # NOTA: CalculadoraCostosEscala necesita usar estos valores directamente,
        # sin recalcular plancha/troquel internamente si ya vienen dados.

        resultados = calculadora.calcular_costos_por_escala(
            datos=datos_escala,
            num_tintas=num_tintas,
            valor_plancha=datos_calculo_persistir['valor_plancha'], # Pasar valor final
            valor_troquel=datos_calculo_persistir['valor_troquel'], # Pasar valor final
            valor_material=datos_calculo_persistir['valor_material'], # Pasar valor final
            valor_acabado=datos_calculo_persistir['valor_acabado'],
            es_manga=es_manga,
            tipo_grafado_id=datos_calculo_persistir['tipo_grafado_id'] # Pasar ID
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
                    'num_tintas': num_tintas,
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
            
            # Guardar resultados y cambiar vista (sin cambios aquí)
            st.session_state.current_calculation = {
                'form_data': form_data,
                'cliente': cliente_obj,
                'results': resultados,
                'is_manga': es_manga,
                'timestamp': datetime.now().isoformat(),
                'calculos_para_guardar': datos_calculo_persistir, # <-- INCLUIR AQUÍ
                # Opcional: Guardar info sobre ajustes aplicados
                'admin_adjustments_applied': {
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

                    # Realizar cálculos - PASS CLIENTE OBJECT
                    resultados = handle_calculation(datos_producto, cliente_seleccionado)
                    # --- REMOVED (redundant state setting, handled by handle_calculation) --- 
                    # if resultados:
                    #     st.session_state.current_calculation = {
                    #         'cliente': cliente_seleccionado, # This was missing before
                    #         'form_data': datos_producto,
                    #         'results': resultados,
                    #         'timestamp': datetime.now().isoformat()
                    #     }
                    #     st.session_state.current_view = 'quote_results'
                    #     st.rerun()
                    # ---------------------------------------------------------------------
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
    
    # --- PRIMERO: Verificar si ya se guardó la cotización --- 
    if st.session_state.get('cotizacion_guardada', False) and st.session_state.get('cotizacion_id') is not None:
        st.success(f"Cotización #{st.session_state.cotizacion_id} guardada ✓")
        
        # --- Botones de PDF y Nueva Cotización (lógica sin cambios, dependen de estado) ---
        col_pdf, col_new = st.columns(2)
        with col_pdf:
             # --- Lógica para botón Generar PDF --- 
             if st.button("📄 Generar PDF", key="pdf_button_saved"):
                  with st.spinner("Generando PDF..."):
                      try:
                          # Obtener datos completos usando el ID guardado
                          datos_pdf = st.session_state.db.get_datos_completos_cotizacion(st.session_state.cotizacion_id)
                          if datos_pdf:
                              pdf_gen = CotizacionPDF()
                              pdf_bytes = pdf_gen.generar_pdf(datos_pdf)
                              # Ofrecer descarga
                              st.download_button(
                                  label="Descargar PDF Ahora",
                                  data=pdf_bytes,
                                  file_name=f"Cotizacion_{datos_pdf.get('consecutivo', 'N')}.pdf",
                                  mime="application/pdf"
                              )
                          else:
                              st.error("No se pudieron obtener los datos completos para generar el PDF.")
                      except Exception as e_pdf:
                          st.error(f"Error generando PDF: {e_pdf}")
                          traceback.print_exc()
        
        with col_new:
            if st.button("Nueva Cotización", key="new_quote_button_saved"):
                st.session_state.current_view = 'calculator'
                st.session_state.cotizacion_guardada = False
                st.session_state.referencia_guardar = ""
                st.session_state.cotizacion_model = None
                st.session_state.current_calculation = None
                st.rerun()
        return # Terminar aquí si ya está guardada
    # ----------------------------------------------------------

    # --- Si no está guardada, verificar si hay un cálculo válido --- 
    if 'current_calculation' not in st.session_state or not st.session_state.current_calculation:
        st.error("No hay resultados para mostrar. Por favor, realice un cálculo primero.")
        if st.button("Volver a Calcular", key="back_to_calc_no_results"):
            st.session_state.current_view = 'calculator'
            st.rerun()
        return
    # Verificar si el modelo de cotización está listo (preparado por handle_calculation)
    if 'cotizacion_model' not in st.session_state or st.session_state.cotizacion_model is None:
        st.error("Error interno: Modelo de cotización no preparado. Por favor, recalcule.")
        if st.button("Volver a Calcular", key="back_to_calc_no_model"):
            st.session_state.current_view = 'calculator'
            st.rerun()
        return
    # Verificar que calculos_para_guardar exista dentro de calc
    calc = st.session_state.current_calculation
    if 'calculos_para_guardar' not in calc or not calc['calculos_para_guardar']:
        st.error("Error interno: Datos de cálculo para guardar no encontrados. Por favor, recalcule.")
        if st.button("Volver a Calcular", key="back_to_calc_no_save_data"):
            st.session_state.current_view = 'calculator'
            st.rerun()
        return
    
    # --- Si hay cálculo válido, obtener datos y mostrar --- 
    cotizacion_preparada = st.session_state.cotizacion_model # Modelo listo para guardar
    datos_calculo_persistir = calc['calculos_para_guardar']
    
    st.markdown("## Resultados de la Cotización")
    
    # Información básica
    st.markdown("### Información General")
    col1_info, col2_info = st.columns(2)
    with col1_info:
        st.write(f"**Tipo de Producto:** {'Manga' if calc['is_manga'] else 'Etiqueta'}")
        # Mostrar Referencia ingresada (aún no guardada)
        st.write(f"**Referencia (a guardar):** {st.session_state.get('referencia_guardar', '(Ingrese abajo)')}") 
        st.write(f"**Fecha Cálculo:** {datetime.fromisoformat(calc['timestamp']).strftime('%Y-%m-%d %H:%M')}")
    
    # Mostrar resultados para cada escala
    st.markdown("### Resultados por Escala")
    
    # Crear tabla de resultados (sin cambios aquí)
    resultados_df = pd.DataFrame(calc['results'])
    # ... (resto del formateo de la tabla sin cambios) ...
    st.dataframe(resultados_df)
    
    # --- Formulario y Lógica de Guardado --- 
    st.markdown("#### Guardar Cotización")
    # El formulario solo se muestra si la cotización NO está guardada
    with st.form("guardar_cotizacion_form"):
        # Input para la descripción de la referencia
        referencia_desc = st.text_input(
            "Referencia / Descripción para guardar *",
            value=st.session_state.get('referencia_guardar', ""),
            key="referencia_guardar_input", # Mantener key consistente
            help="Ingrese un nombre o descripción única para esta cotización (Ej: Etiqueta XYZ V1)"
        )
        
        # --- RESTAURAR: Selector de Comercial para Admin ---
        selected_comercial_id = None # Inicializar fuera del if para validación posterior
        if st.session_state.get('usuario_rol') == 'administrador':
            try:
                comerciales = st.session_state.db.get_perfiles_by_role('comercial')
                if comerciales:
                    # Opciones para el selectbox: (ID, Nombre)
                    opciones_comercial = [(c['id'], c['nombre']) for c in comerciales] 
                    # Añadir opción placeholder 
                    opciones_display = [(None, "-- Seleccione Comercial --")] + opciones_comercial
                    
                    # Mostrar el selectbox
                    selected_option = st.selectbox(
                        "Asignar a Comercial *", 
                        options=opciones_display, 
                        format_func=lambda x: x[1], # Mostrar nombre
                        key="comercial_selector_admin", # Usar la key correcta
                        help="Seleccione el comercial al que pertenece esta cotización."
                    )
                    # selected_comercial_id se obtendrá del estado DENTRO del submit button
                else:
                    st.warning("No se encontraron comerciales para asignar.")
            except Exception as e_comm:
                st.error(f"Error al cargar lista de comerciales: {e_comm}")
        # ----------------------------------------------------

        guardar = st.form_submit_button("Guardar Cotización", type="primary")
        
        if guardar:
            error_guardado = False
            if not referencia_desc.strip():
                st.error("Debe ingresar una Referencia / Descripción para guardar la cotización.")
                error_guardado = True
                
            comercial_id_para_guardar = None
            if st.session_state.get('usuario_rol') == 'administrador':
                # Re-obtener valor del selector dentro del form submit
                # Asumiendo que la key del selector es "comercial_selector_admin"
                selected_comercial_tuple = st.session_state.get("comercial_selector_admin")
                if selected_comercial_tuple and selected_comercial_tuple[0] is not None:
                     selected_comercial_id = selected_comercial_tuple[0]
                else:
                     selected_comercial_id = None # Asegurar None si no seleccionó
                
                if selected_comercial_id is None:
                    st.error("Como administrador, debe seleccionar un comercial para asignar la cotización.")
                    error_guardado = True
                else:
                    comercial_id_para_guardar = selected_comercial_id
            else:
                comercial_id_para_guardar = st.session_state.user_id 
            
            if not error_guardado:
                st.session_state.referencia_guardar = referencia_desc
                with st.spinner("Guardando cotización..."):                        
                    try:
                        cliente_id = calc['cliente'].id 
                        # datos_calculo_persistir ya está disponible aquí
                        
                        if not comercial_id_para_guardar or not cliente_id or not datos_calculo_persistir:
                             st.error("Error interno: Faltan datos para guardar (cliente, comercial o cálculos).")
                        else:
                            manager = st.session_state.cotizacion_manager
                            success, message, cotizacion_id = manager.guardar_nueva_cotizacion(
                                cotizacion_model=cotizacion_preparada, 
                                cliente_id=cliente_id,
                                referencia_descripcion=referencia_desc,
                                comercial_id=comercial_id_para_guardar,
                                datos_calculo=datos_calculo_persistir 
                            )
                            
                            if success:
                                st.success(message)
                                st.session_state.cotizacion_guardada = True
                                st.session_state.cotizacion_id = cotizacion_id
                                st.session_state.cotizacion_model.id = cotizacion_id 
                                # --- Limpiar cálculo DESPUÉS de guardar --- 
                                st.session_state.current_calculation = None
                                # -----------------------------------------
                                st.rerun() # Refrescar para mostrar estado guardado
                            else:
                                st.error(f"Error al guardar: {message}")

                    except CotizacionManagerError as cme:
                        st.error(f"Error al guardar: {cme}")
                    except Exception as e_save:
                        st.error(f"Error inesperado al guardar: {e_save}")
                        traceback.print_exc()
                                
    # Botón Nueva Cotización (solo visible si hay cálculo pero no se ha guardado)
    if st.button("Nueva Cotización", key="new_quote_button_results"):
        st.session_state.current_view = 'calculator'
        st.session_state.cotizacion_guardada = False
        st.session_state.referencia_guardar = ""
        st.session_state.cotizacion_model = None
        st.session_state.current_calculation = None
        st.rerun()

if __name__ == "__main__":
    main()
