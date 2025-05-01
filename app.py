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
from src.pdf.pdf_generator import generar_bytes_pdf_cotizacion, CotizacionPDF # Importar la nueva función helper y la clase

# Calculadoras
from src.logic.calculators.calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from src.logic.calculators.calculadora_litografia import CalculadoraLitografia

# UI Components - mover estas importaciones al final
from src.ui.auth_ui import handle_authentication, show_login, show_logout_button
from src.ui.calculator_view import show_calculator, show_quote_results, show_quote_summary
from src.ui.calculator.client_section import mostrar_seccion_cliente
# MODIFICADO: Importar funciones específicas
from src.ui.calculator.product_section import (_mostrar_material, _mostrar_adhesivo, 
                                             _mostrar_grafado_altura, mostrar_secciones_internas_formulario)
# --- INICIO CAMBIO ---
# ... (resto de importaciones sin cambios) ...

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
            st.rerun() # <-- DESCOMENTADO
            
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
        'calculator': "📝 Calculadora / Editar",
        'manage_quotes': "📂 Gestionar Cotizaciones",
        'reports': "📊 Reportes"
    }

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
             st.session_state.cotizacion_a_editar_id = None
             st.session_state.datos_cotizacion_editar = None
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
        with st.expander("⚙️ Ajustes Avanzados (Admin)", expanded=True):
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
            
            # Llamar a la función refactorizada para mostrar secciones internas
            mostrar_secciones_internas_formulario(
                es_manga=es_manga, 
                initial_data=st.session_state.initial_data, # Pasar datos necesarios
                datos_cargados=datos_cargados 
            )
                
            # --- Ajustes Admin YA NO ESTÁ AQUÍ --- 
                
            # --- El botón Calcular/Actualizar se mueve abajo --- 
                
        # --- MOVER AJUSTES ADMIN AQUÍ (DESPUÉS DEL FORM) --- 
        st.divider() # Añadir un divisor antes de los ajustes
        _mostrar_ajustes_admin() # Llamar a la función de ajustes aquí
        st.divider() # Añadir un divisor después de los ajustes

        # --- MOVER BOTÓN CALCULAR/ACTUALIZAR AQUÍ --- 
        if tipo_producto_seleccionado_id: # Solo mostrar si hay tipo producto
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
                            datos_formulario_enviado['tipo_grafado_nombre'] = grafado_obj.nombre # Para handle_calculation
                            if grafado_obj.id in [3, 4]: datos_formulario_enviado['altura_grafado'] = float(st.session_state.get('altura_grafado', 0.0))
                            else: datos_formulario_enviado['altura_grafado'] = None
                        else: validation_errors.append("Tipo de grafado no seleccionado.")
                        datos_formulario_enviado['acabado_id'] = None
                    else: # Etiqueta
                        acabado_obj = st.session_state.get('acabado_select')
                        if acabado_obj: datos_formulario_enviado['acabado_id'] = acabado_obj.id
                        else: validation_errors.append("Acabado no seleccionado.")
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
    if st.session_state.current_view == 'calculator':
        mostrar_calculadora()
    elif st.session_state.current_view == 'quote_results':
        show_quote_results()
    elif st.session_state.current_view == 'manage_quotes':
        show_manage_quotes()
    elif st.session_state.current_view == 'reports':
        show_reports()

def show_quote_results():
    """Muestra los resultados de la cotización calculada."""
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
    st.dataframe(resultados_df)
    
    # --- Formulario y Lógica de Guardado --- 
    is_edit_mode = st.session_state.get('modo_edicion', False)
    section_title = "Actualizar Cotización" if is_edit_mode else "Guardar Cotización"
    button_label = "💾 Actualizar" if is_edit_mode else "💾 Guardar Cotización"
    st.markdown(f"#### {section_title}")
    
    default_referencia = ""
    if is_edit_mode and 'datos_cotizacion_editar' in st.session_state and st.session_state.datos_cotizacion_editar:
        # Usar la descripción de la cotización que se está editando
        default_referencia = st.session_state.datos_cotizacion_editar.get('referencia_descripcion', "")
    elif 'referencia_guardar' in st.session_state:
        # Usar lo que se haya ingresado previamente en esta sesión (si no estamos editando)
        default_referencia = st.session_state.referencia_guardar
    
    with st.form("guardar_cotizacion_form"):
        referencia_desc = st.text_input(
            "Referencia / Descripción para guardar *",
            value=default_referencia,
            key="referencia_guardar_input", 
            help="Ingrese un nombre o descripción única para esta cotización (Ej: Etiqueta XYZ V1)"
        )
        
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
            error_guardado = False
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
            
            if not error_guardado:
                st.session_state.referencia_guardar = referencia_desc 
                spinner_text = "Actualizando cotización..." if is_edit_mode else "Guardando cotización..."
                with st.spinner(spinner_text):
                    try:
                        # Usar cliente del cálculo actual (no puede cambiar en edit mode)
                        cliente_id = calc['cliente'].id 
                        if not comercial_id_para_guardar or not cliente_id or not datos_calculo_persistir:
                             st.error("Error interno: Faltan datos (cliente, comercial o cálculos).")
                        else:
                            manager = st.session_state.cotizacion_manager
                            if is_edit_mode:
                                cotizacion_id_a_actualizar = st.session_state.get('cotizacion_id_editar')
                                if not cotizacion_id_a_actualizar:
                                     st.error("Error: ID de cotización a editar no encontrado.")
                                else:
                                    success, message = manager.actualizar_cotizacion_existente(
                                        cotizacion_id=cotizacion_id_a_actualizar,
                                        cotizacion_model=cotizacion_preparada, 
                                        cliente_id=cliente_id,
                                        referencia_descripcion=referencia_desc,
                                        comercial_id=comercial_id_para_guardar,
                                        datos_calculo=datos_calculo_persistir,
                                        modificado_por=st.session_state.user_id
                                    )
                                    if success:
                                        st.success(message)
                                        st.session_state.cotizacion_guardada = True
                                        st.session_state.cotizacion_id = cotizacion_id_a_actualizar
                                        st.session_state.modo_edicion = False
                                        st.session_state.cotizacion_a_editar_id = None
                                        st.session_state.datos_cotizacion_editar = None
                                        st.session_state.current_calculation = None 
                                        SessionManager.reset_calculator_widgets()
                                        st.rerun() # <-- DESCOMENTADO
                                    else:
                                        st.error(f"Error al actualizar: {message}")
                            else:
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
                                    st.session_state.current_calculation = None
                                    st.rerun() # <-- DESCOMENTADO
                                else:
                                    st.error(f"Error al guardar: {message}")
                    except CotizacionManagerError as cme:
                        st.error(f"Error en guardado/actualización: {cme}")
                    except Exception as e_save:
                        st.error(f"Error inesperado: {e_save}")
                        traceback.print_exc()
                                
    # Botón Nueva Cotización 
    if st.button("Nueva Cotización", key="new_quote_button_results"):
        # Resetear todo para una nueva cotización
        st.session_state.current_view = 'calculator'
        st.session_state.cotizacion_guardada = False
        st.session_state.referencia_guardar = ""
        st.session_state.cotizacion_model = None
        st.session_state.current_calculation = None
        st.session_state.modo_edicion = False
        st.session_state.cotizacion_a_editar_id = None
        st.session_state.datos_cotizacion_editar = None
        SessionManager.reset_calculator_widgets() # Resetear widgets
        st.rerun()

def show_manage_quotes():
    """Muestra la vista para gestionar (ver y modificar) cotizaciones."""
    st.title("Gestión de Cotizaciones")

    # Recuperar datos necesarios
    db_manager = st.session_state.db
    user_role = st.session_state.usuario_rol
    user_id = st.session_state.user_id

    # --- DEBUG PRINT ---
    print(f"DEBUG: show_manage_quotes - User Role: {user_role}")
    print(f"DEBUG: show_manage_quotes - User ID: {user_id}")
    # --- END DEBUG ---

    cotizaciones = []
    try:
        if user_role == 'administrador':
            # --- DEBUG PRINT ---
            print("DEBUG: show_manage_quotes - Calling db_manager.get_all_cotizaciones_overview()")
            # --- END DEBUG ---
            cotizaciones = db_manager.get_all_cotizaciones_overview()
        elif user_role == 'comercial':
            comercial_id = user_id
            # --- DEBUG PRINT ---
            print(f"DEBUG: show_manage_quotes - Calling db_manager.get_cotizaciones_overview_by_comercial(comercial_id='{comercial_id}')")
            # --- END DEBUG ---
            if comercial_id:
                cotizaciones = db_manager.get_cotizaciones_overview_by_comercial(comercial_id)
            else:
                st.warning("No se pudo identificar el ID del comercial.")
                cotizaciones = [] # Asegurar que cotizaciones es una lista vacía
        else:
             st.warning("Rol de usuario no reconocido para esta vista.")
             cotizaciones = [] # Asegurar que cotizaciones es una lista vacía

    except Exception as e:
        st.error(f"Error al cargar las cotizaciones: {e}")
        traceback.print_exc()
        cotizaciones = [] # Asegurar que cotizaciones es una lista vacía
        
    # --- Convertir a DataFrame para mostrar en tabla ---
    if cotizaciones:
        try:
            # Crear el DataFrame
            df = pd.DataFrame(cotizaciones)
            
            # Asegurar que columnas esperadas existen, añadir las que falten con valores default
            required_cols = ['id', 'numero_cotizacion', 'referencia', 'cliente', 'fecha_creacion', 'estado_id']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = None # O un valor default apropiado

            # Mapear estado_id a nombres
            estados_dict = {estado.id: estado.estado for estado in st.session_state.initial_data['estados_cotizacion']}
            df['Estado'] = df['estado_id'].map(estados_dict).fillna('Desconocido')

            # Formatear fecha_creacion (manejar posibles errores o NaT)
            df['fecha_creacion'] = pd.to_datetime(df['fecha_creacion'], errors='coerce')
            df['Fecha Creación'] = df['fecha_creacion'].dt.strftime('%Y-%m-%d %H:%M').fillna('Fecha inválida')
            
            # Renombrar y seleccionar columnas para mostrar
            df_display = df[['id', 'numero_cotizacion', 'referencia', 'cliente', 'Fecha Creación', 'Estado']].copy()
            df_display.rename(columns={
                'id': 'ID',
                'numero_cotizacion': 'Consecutivo',
                'referencia': 'Referencia',
                'cliente': 'Cliente'
            }, inplace=True)

            # --- Mostrar tabla y botones ---
            st.markdown("### Cotizaciones Existentes")
            
            # Usar st.columns para poner botones al lado de la tabla o encima/debajo
            cols = st.columns(len(df_display)) # Crear una columna para cada fila teóricamente
            
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # Añadir botones de acción (Editar, Ver PDF) - Ejemplo conceptual
            st.write("--- Acciones ---")
            
            selected_quote_id = st.selectbox("Selecciona una cotización para ver acciones:", 
                                             options=df_display['ID'].tolist(),
                                             format_func=lambda x: f"ID: {x} - {df_display[df_display['ID'] == x]['Consecutivo'].iloc[0]}" if not df_display[df_display['ID'] == x].empty else f"ID: {x}",
                                             index=None, # No seleccionar nada por defecto
                                             placeholder="Elige una cotización...")

            if selected_quote_id:
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✏️ Editar", key=f"edit_{selected_quote_id}"):
                        # --- Lógica para entrar en modo edición ---
                        st.session_state.modo_edicion = True
                        st.session_state.cotizacion_id_editar = selected_quote_id
                        st.session_state.current_view = 'calculator' # <--- Correcto
                        # Limpiar posibles datos de cálculo anterior
                        # (No es necesario si se limpia al entrar en modo edición en mostrar_calculadora)
                        st.rerun() # Forzar recarga para navegar y entrar en modo edición

                with col2:
                    # Botón para generar PDF
                    try:
                        # Obtener datos completos para el PDF seleccionado
                        datos_pdf = db_manager.get_datos_completos_cotizacion(selected_quote_id)
                        if datos_pdf:
                            
                            # --- INICIO CAMBIO: Usar la nueva función --- 
                            pdf_bytes = generar_bytes_pdf_cotizacion(datos_pdf) 
                            # --- FIN CAMBIO ---                            
                            
                            # --- Solo mostrar botón si se generó el PDF --- 
                            if pdf_bytes:
                                # Crear nombre de archivo
                                identificador_pdf = datos_pdf.get('identificador', f"cotizacion_{selected_quote_id}")
                                filename = f"{identificador_pdf}.pdf"
                                
                                st.download_button(
                                    label="📄 Ver PDF",
                                    data=pdf_bytes,
                                    file_name=filename,
                                    mime="application/pdf",
                                    key=f"pdf_{selected_quote_id}"
                                )
                            else:
                                 st.warning("No se generaron datos PDF (revisar logs).")
                        else:
                             st.warning("No se pudieron cargar los datos completos para el PDF.")
                             
                    except Exception as pdf_error:
                         st.error(f"Error generando PDF: {pdf_error}")
                         traceback.print_exc()
                
                # Podríamos añadir más botones (ej: Eliminar, Marcar como aprobada, etc.) aquí
                # with col3:
                #     if st.button("🗑️ Eliminar", key=f"delete_{selected_quote_id}"):
                #         # Lógica para eliminar cotización (con confirmación)
                #         st.warning(f"Funcionalidad de eliminar cotización {selected_quote_id} no implementada.")


        except KeyError as ke:
             st.error(f"Error: Falta una columna esperada en los datos de cotización: {ke}")
             print("--- ERROR DATAFRAME ---")
             print("Columnas recibidas:", cotizaciones[0].keys() if cotizaciones else "N/A")
             print("Columnas esperadas:", required_cols)
             traceback.print_exc()
        except Exception as df_error:
             st.error(f"Error al procesar y mostrar las cotizaciones: {df_error}")
             traceback.print_exc()
             
    else:
        st.info("No se encontraron cotizaciones.")
        
# --- Fin de la función show_manage_quotes ---

def show_reports():
    """Muestra la sección de reportes"""
    st.title("Reportes")
    st.write("Funcionalidad de reportes en desarrollo.")
    # Aquí se implementará la lógica para mostrar reportes

if __name__ == "__main__":
    main()
