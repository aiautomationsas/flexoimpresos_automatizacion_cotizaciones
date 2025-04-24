import streamlit as st
import pandas as pd
import numpy as np
import os
import sys
import io
import traceback
from dataclasses import dataclass, field
from calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from calculadora_litografia import CalculadoraLitografia, DatosLitografia
from db_manager import DBManager
import tempfile
from pdf_generator import CotizacionPDF, MaterialesPDF
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import math
from constants import (
    RENTABILIDAD_MANGAS, RENTABILIDAD_ETIQUETAS,
    DESPERDICIO_MANGAS, DESPERDICIO_ETIQUETAS,
    VELOCIDAD_MAQUINA_NORMAL, VELOCIDAD_MAQUINA_MANGAS_7_TINTAS,
    GAP_AVANCE_ETIQUETAS, GAP_AVANCE_MANGAS,
    GAP_PISTAS_ETIQUETAS, GAP_PISTAS_MANGAS,
    FACTOR_ANCHO_MANGAS, INCREMENTO_ANCHO_MANGAS,
    ANCHO_MAXIMO_LITOGRAFIA
)
from model_classes.cotizacion_model import (
    Cotizacion, Escala, Cliente, ReferenciaCliente,
    PrecioEscala, TipoProducto
)
import inspect
from supabase import create_client, Client
from auth_manager import AuthManager, create_login_ui

# Initialize Supabase client
if 'supabase' not in st.session_state:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    st.session_state.supabase = create_client(supabase_url, supabase_key)

# Initialize AuthManager
if 'auth_manager' not in st.session_state:
    # Ensure the supabase client is initialized first
    if 'supabase' not in st.session_state:
        try:
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
            st.session_state.supabase = create_client(supabase_url, supabase_key)
        except Exception as e:
            st.error(f"Error crítico inicializando Supabase: {e}")
            st.stop() # Stop execution if Supabase can't be initialized
    
    # Pass the shared client instance
    st.session_state.auth_manager = AuthManager(st.session_state.supabase)
    st.session_state.auth_manager.initialize_session_state()

# Configuración de página
st.set_page_config(
    page_title="Sistema de Cotización - Flexo Impresos",
    page_icon="🏭",
    layout="wide"
)

# Título principal con estilo
st.markdown("""
    <style>
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
    </style>
    <h1 style='text-align: center; background-color: #0F4C81; color: white; padding: 1rem; border-radius: 10px;'>
        🏭 Sistema de Cotización - Flexo Impresos
    </h1>
    <p style='text-align: center; color: #7f8c8d; font-size: 1.2em;'>
        Calculadora de costos para productos flexográficos
    </p>
    <hr>
""", unsafe_allow_html=True)

# Add CSS for radio buttons within the existing style tag
st.markdown("""
<style>
    /* Enhanced Radio Buttons */
    div[data-testid="stRadio"] > label {
        /* Improve spacing and alignment */
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        cursor: pointer;
    }
    div[data-testid="stRadio"] > label > div[data-baseweb="radio"] > div:first-child {
        /* Style the outer radio circle */
        width: 1.1em !important; /* Slightly larger */
        height: 1.1em !important;
        border-width: 2px !important; /* Thicker border */
        border-color: #0F4C81 !important;
        transition: border-color 0.2s ease; /* Smooth transition */
    }
    div[data-testid="stRadio"] > label > div[data-baseweb="radio"] > div:first-child > div {
         /* Style the inner selected circle */
        background-color: #0F4C81 !important;
        border-color: #0F4C81 !important; /* Match border */
        transition: background-color 0.2s ease, border-color 0.2s ease; /* Smooth transition */
        width: 0.6em !important; /* Adjust inner size */
        height: 0.6em !important;
    }
    /* Hover state for the outer circle */
    div[data-testid="stRadio"] > label:hover > div[data-baseweb="radio"] > div:first-child {
        border-color: #0B3A65 !important; /* Darker blue on hover */
    }
    /* Style the label text */
    div[data-testid="stRadio"] label span {
        color: #2c3e50; /* Ensure consistent text color */
        padding-left: 0.5rem; /* Space between radio and label */
        line-height: 1.1em; /* Align text with larger radio */
    }
</style>
""", unsafe_allow_html=True)

# Inicializar la base de datos
if 'db' not in st.session_state:
    st.session_state.db = DBManager(st.session_state.supabase)

# Función para capturar la salida de la consola
class StreamlitCapture:
    def __init__(self):
        self.logs = []
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        self.stdout_buffer = io.StringIO()
        self.stderr_buffer = io.StringIO()
    
    def start(self):
        sys.stdout = self.stdout_buffer
        sys.stderr = self.stderr_buffer
    
    def stop(self):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr
        
        stdout_value = self.stdout_buffer.getvalue()
        stderr_value = self.stderr_buffer.getvalue()
        
        if stdout_value:
            self.logs.append(("stdout", stdout_value))
        if stderr_value:
            self.logs.append(("stderr", stderr_value))
        
        self.stdout_buffer = io.StringIO()
        self.stderr_buffer = io.StringIO()
    
    def get_logs(self):
        return self.logs
    
    def clear(self):
        self.logs = []
        self.stdout_buffer = io.StringIO()
        self.stderr_buffer = io.StringIO()

# Crear una instancia global para capturar la salida
console_capture = StreamlitCapture()

def extraer_valor_precio(texto: str) -> float:
    """Extrae el valor numérico de un string con formato 'nombre ($valor)'"""
    try:
        # Buscar el patrón ($X.XX) donde X son dígitos
        inicio = texto.find('($') + 2
        fin = texto.find(')', inicio)
        
        if inicio > 1 and fin > inicio:
            # Extraer el valor y quitar posibles espacios, comas, etc.
            valor_texto = texto[inicio:fin].strip()
            # Eliminar comas que puedan existir en el formato numérico
            valor_texto = valor_texto.replace(',', '')
            # Convertir a float
            return float(valor_texto)
        
        # Si no encontramos el patrón esperado, intentar buscar solo números
        import re
        numeros = re.findall(r'(\d+\.\d+)', texto)
        if numeros:
            return float(numeros[0])
            
        print(f"No se pudo extraer valor de: '{texto}'")
        return 0.0
    except Exception as e:
        print(f"Error extrayendo valor de '{texto}': {str(e)}")
        return 0.0

def procesar_escalas(escalas_text: str) -> Optional[List[int]]:
    """Procesa el texto de escalas y retorna una lista de enteros"""
    try:
        return [int(x.strip()) for x in escalas_text.split(",")]
    except ValueError:
        return None

def obtener_valor_plancha(reporte_lito: Dict) -> Tuple[float, Dict]:
    """Extrae el valor de plancha del reporte de litografía"""
    valor_plancha_dict = reporte_lito.get('precio_plancha', {'precio': 0})
    valor_plancha = valor_plancha_dict['precio'] if isinstance(valor_plancha_dict, dict) else valor_plancha_dict
    return valor_plancha, valor_plancha_dict

def obtener_valor_troquel(reporte_lito: Dict) -> float:
    """Extrae el valor del troquel del reporte de litografía"""
    valor_troquel = reporte_lito.get('valor_troquel', {'valor': 0})
    return valor_troquel['valor'] if isinstance(valor_troquel, dict) else valor_troquel

def generar_tabla_resultados(resultados: List[Dict], es_manga: bool = False) -> pd.DataFrame:
    """Genera una tabla formateada con los resultados de la cotización"""
    return pd.DataFrame([
        {
            'Escala': f"{r['escala']:,}",
            'Valor Unidad': f"${float(r['valor_unidad']):.2f}",
            'Metros': f"{r['metros']:.2f}",
            'Tiempo (h)': f"{r['tiempo_horas']:.2f}",
            'Montaje': f"${r['montaje']:,.2f}",
            'MO y Maq': f"${r['mo_y_maq']:,.2f}",
            'Tintas': f"${r['tintas']:,.2f}",
            'Papel/lam': f"${r['papel_lam']:,.2f}",
            'Desperdicio': f"${r.get('desperdicio_total', 0):,.2f}"
        }
        for r in resultados
    ])

def generar_informe_tecnico(datos_entrada: DatosEscala, resultados: List[Dict], reporte_lito: Dict, 
                           num_tintas: int, valor_plancha: float, valor_material: float, 
                           valor_acabado: float, reporte_troquel: Dict = None, 
                           valor_plancha_separado: Optional[float] = None,
                           es_manga: bool = False,
                           identificador: str = "N/A", 
                           nombre_cliente: str = "N/A", 
                           referencia: str = "N/A", 
                           nombre_comercial: str = "N/A") -> str:
    """Genera un informe técnico detallado con encabezado y sin detalles de área"""
    dientes = reporte_lito['desperdicio']['mejor_opcion'].get('dientes', 'N/A')
    gap_avance = datos_entrada.desperdicio + (GAP_AVANCE_MANGAS if es_manga else GAP_AVANCE_ETIQUETAS)  # GAP al avance según el tipo
    
    # Obtener el valor del troquel del diccionario
    valor_troquel = reporte_troquel.get('valor', 0) if isinstance(reporte_troquel, dict) else 0
    
    plancha_info = f"""
### Información de Plancha Separada
- **Valor Plancha Original**: ${valor_plancha:.2f}
- **Valor Plancha Ajustado**: ${valor_plancha_separado:.2f}
""" if valor_plancha_separado is not None else ""
    
    # Crear encabezado
    header = f"""
## Informe Técnico de Cotización
- **Identificador**: {identificador}
- **Cliente**: {nombre_cliente}
- **Referencia**: {referencia}
- **Comercial**: {nombre_comercial}
"""

    return f"""
{header}
### Parámetros de Impresión
- **Ancho**: {datos_entrada.ancho} mm
- **Avance**: {datos_entrada.avance} mm
- **Gap al avance**: {gap_avance:.2f} mm
- **Pistas**: {datos_entrada.pistas}
- **Número de Tintas**: {num_tintas}
- **Área de Etiqueta**: {reporte_lito['area_etiqueta']['area']:.2f} mm²
- **Unidad (Z)**: {dientes}

### Información de Materiales
- **Valor Material**: ${valor_material:.2f}/mm²
- **Valor Acabado**: ${valor_acabado:.2f}/mm²
- **Valor Troquel**: ${valor_troquel:.2f}

{plancha_info}
"""

def calcular_valor_plancha_separado(valor_plancha_dict: Dict) -> float:
    """Calcula el valor de la plancha cuando se cobra por separado"""
    if isinstance(valor_plancha_dict, dict) and 'detalles' in valor_plancha_dict:
        detalles = valor_plancha_dict['detalles']
        if 'precio_sin_constante' in detalles:
            # Calcular el valor base
            valor_base = detalles['precio_sin_constante'] / 0.7
            # Redondear al múltiplo de 10000 más cercano hacia arriba
            return math.ceil(valor_base / 10000) * 10000
    return 0

def crear_datos_cotizacion(
    material,
    acabado,
    ancho=0,
    avance=0,
    pistas=1,
    num_tintas=0,
    num_rollos=1,
    valor_plancha=0,
    valor_material=0,
    valor_acabado=0,
    valor_troquel=0,
    valor_plancha_separado=0,
    es_manga=False
):
    """
    Crea un diccionario con los datos de la cotización
    """
    datos = {
        'material': material,
        'acabado': acabado,
        'ancho': ancho,
        'avance': avance,
        'pistas': pistas,
        'num_tintas': num_tintas,
        'num_rollos': num_rollos,
        'valor_plancha': valor_plancha,
        'valor_material': valor_material,
        'valor_acabado': valor_acabado,
        'valor_troquel': valor_troquel,
        'valor_plancha_separado': valor_plancha_separado,
        'es_manga': es_manga
    }
    return datos

def crear_cliente():
    """Función para crear un nuevo cliente"""
    st.title("Crear Nuevo Cliente")
    
    with st.form("formulario_cliente"):
        # Campos requeridos
        nombre = st.text_input("Nombre del Cliente *", help="Campo obligatorio")
        codigo = st.text_input("NIT *", help="Campo obligatorio")
        
        # Campos opcionales
        telefono = st.text_input("Teléfono", help="Número de contacto")
        persona_contacto = st.text_input("Persona de Contacto", help="Nombre de la persona de contacto")
        correo_electronico = st.text_input("Correo Electrónico", help="Correo de contacto")
        
        submitted = st.form_submit_button("Guardar Cliente")
        
        if submitted:
            if not nombre or not codigo:
                st.error("El nombre y el NIT son campos obligatorios")
                return
            
            try:
                # Inicializar la base de datos
                db = DBManager(st.session_state.supabase)
                
                # Crear el objeto Cliente con los datos del formulario
                nuevo_cliente = Cliente(
                    nombre=nombre,
                    codigo=codigo,
                    telefono=telefono,
                    persona_contacto=persona_contacto,
                    correo_electronico=correo_electronico
                )
                
                # Guardar el cliente en la base de datos
                cliente_guardado = db.crear_cliente(nuevo_cliente)
                
                if cliente_guardado and cliente_guardado.id:
                    st.success(f"Cliente {nombre} guardado exitosamente con ID: {cliente_guardado.id}")
                    # Limpiar el formulario o redirigir
                    st.session_state.nuevo_cliente_guardado = True
                    st.rerun()
                else:
                    st.error("No se pudo guardar el cliente. Verifique los datos e intente nuevamente.")
                    
            except Exception as e:
                st.error(f"Error al guardar el cliente: {str(e)}")
                import traceback
                st.error(traceback.format_exc())

def mostrar_actualizar_cotizacion():
    """Función para mostrar la interfaz de actualización de cotización"""
    st.title("Actualizar Cotización")
    
    # --- DEBUGGING: Verificar Usuario y Rol desde la App --- 
    print("\n--- DEBUG: mostrar_actualizar_cotizacion --- ")
    user_id_app = st.session_state.get('user_id')
    print(f"ID de Usuario en Sesión (st.session_state.user_id): {user_id_app}")
    
    if user_id_app:
        try:
            if 'db' not in st.session_state:
                 st.session_state.db = DBManager(st.session_state.supabase)
            db = st.session_state.db
            perfil_app = db.get_perfil(user_id_app)
            print(f"Perfil obtenido para el usuario desde la app: {perfil_app}")
            if perfil_app:
                print(f"Rol detectado para el usuario desde la app: {perfil_app.get('rol_nombre')}")
            else:
                print("ADVERTENCIA: No se encontró perfil para el usuario logueado.")
        except Exception as e_debug:
            print(f"ERROR al obtener perfil para depuración: {e_debug}")
    else:
        print("ADVERTENCIA: No hay user_id en st.session_state.")
    print("--- FIN DEBUG ---\n")
    # --- FIN DEBUGGING ---
    
    # --- INICIO: Verificación de Rol --- 
    if 'usuario_verificado' not in st.session_state or not st.session_state.usuario_verificado:
        # Forzar verificación si no se hizo antes
        st.error("Error de verificación de usuario. Volviendo a la calculadora.")
        st.session_state.paso_actual = 'calculadora' # O redirigir a login
        st.rerun()
        return
        
    if st.session_state.usuario_rol != 'comercial':
        st.error("Acceso denegado. Se requiere el rol de 'comercial'.")
        return
    # --- FIN: Verificación de Rol --- 
    
    try:
        # Verificar autenticación (redundante si la verificación de rol ya pasó, pero seguro)
        if not st.session_state.auth_manager.check_auth_status():
            st.error("Debe iniciar sesión para acceder a esta funcionalidad")
            return
            
        # Obtener cotizaciones visibles para el usuario actual (Admin o Comercial)
        cotizaciones = st.session_state.db.get_visible_cotizaciones_list()
        
        if not cotizaciones:
            st.info("No se encontraron cotizaciones visibles asociadas a tu usuario.")
            return
        
        # Crear DataFrame con las cotizaciones filtradas
        df = pd.DataFrame(cotizaciones)
        # Convertir numero_cotizacion a string para evitar problemas de formato
        df['numero_cotizacion'] = df['numero_cotizacion'].astype(str)
        df['Fecha'] = pd.to_datetime(df['fecha_creacion']).dt.strftime('%Y-%m-%d %H:%M')
        
        # --- NUEVO: Obtener nombres de estados --- 
        db = st.session_state.db
        estados_db = db.get_estados_cotizacion()
        estados_dict = {e.id: e.estado for e in estados_db}
        df['Estado'] = df['estado_id'].map(estados_dict).fillna('Desconocido')
        # ------------------------------------------
        
        # Mostrar las cotizaciones en una tabla
        st.write("### Cotizaciones existentes")
        st.dataframe(
            df[['numero_cotizacion', 'referencia', 'cliente', 'Fecha', 'Estado']].rename(columns={
                'numero_cotizacion': 'Número',
                'referencia': 'Referencia',
                'cliente': 'Cliente'
            }),
            hide_index=True,
            use_container_width=True
        )
        
        # Permitir seleccionar una cotización para editar
        opciones_selectbox = df['numero_cotizacion'].tolist()
        cotizacion_seleccionada_num = st.selectbox(
            "Seleccione una cotización",
            options=opciones_selectbox,
            format_func=lambda x: f"Cotización #{x}",
            index=None,
            placeholder="Elija una opción...",
            key="select_cotizacion_actualizar"
        )
        
        # --- INICIO NUEVA INTERFAZ PARA ACTUALIZAR ESTADO ---
        if cotizacion_seleccionada_num:
            try:
                # Encontrar el ID de la cotización seleccionada usando el número
                cotizacion_data = df[df['numero_cotizacion'] == cotizacion_seleccionada_num].iloc[0]
                cotizacion_id = int(cotizacion_data['id'])
                
                # Obtener la cotización completa para saber el estado actual
                cotizacion_actual = db.obtener_cotizacion(cotizacion_id)
                
                if cotizacion_actual:
                    estado_actual_id = cotizacion_actual.estado_id
                    estado_actual_nombre = estados_dict.get(estado_actual_id, "Desconocido")
                    
                    st.write(f"**Estado Actual:** {estado_actual_nombre}")
                    
                    # Obtener estados y motivos para los selectores
                    estados_disponibles = db.get_estados_cotizacion()
                    motivos_rechazo_disponibles = db.get_motivos_rechazo()
                    
                    # Selector para nuevo estado
                    nuevo_estado_id = st.selectbox(
                        "Seleccione el nuevo estado",
                        options=[e.id for e in estados_disponibles],
                        format_func=lambda x: estados_dict.get(x, "Desconocido"),
                        index=[i for i, e in enumerate(estados_disponibles) if e.id == estado_actual_id][0]
                    )
                    
                    # Selector condicional para motivo de rechazo
                    nuevo_motivo_rechazo_id = None
                    if nuevo_estado_id == 3: # Asumiendo 3 = Rechazado
                        nuevo_motivo_rechazo_id = st.selectbox(
                            "Seleccione el motivo de rechazo",
                            options=[m.id for m in motivos_rechazo_disponibles],
                            format_func=lambda x: next((m.motivo for m in motivos_rechazo_disponibles if m.id == x), "Desconocido")
                        )
                    
                    # Botón para actualizar estado
                    if st.button("Actualizar Estado", key=f"btn_actualizar_estado_{cotizacion_id}"):
                        if nuevo_estado_id == 3 and nuevo_motivo_rechazo_id is None:
                            st.error("Debe seleccionar un motivo de rechazo cuando el estado es 'Rechazado'")
                        else:
                            success = db.actualizar_estado_cotizacion(
                                cotizacion_id, 
                                nuevo_estado_id, 
                                nuevo_motivo_rechazo_id
                            )
                            if success:
                                st.success("Estado actualizado exitosamente!")
                                # Limpiar selección y refrescar para ver cambio
                                st.rerun()
                            else:
                                st.error("No se pudo actualizar el estado. Revise los logs para más detalles.")
                else:
                    st.error("No se pudo cargar la cotización seleccionada.")
                    
            except IndexError:
                 st.error(f"No se encontró la cotización con número {cotizacion_seleccionada_num} en los datos cargados.")
            except Exception as e:
                st.error(f"Error al procesar la cotización: {str(e)}")
                print(f"Error detallado: {traceback.format_exc()}")
        # --- FIN NUEVA INTERFAZ --- 
                
        st.divider() # Separador visual
        
        # Botón original para editar inputs (mantener separado)
        if cotizacion_seleccionada_num:
            if st.button("Editar Inputs de la Cotización", key="btn_editar_inputs_seleccionada"):
                try:
                    cotizacion_data = df[df['numero_cotizacion'] == cotizacion_seleccionada_num].iloc[0]
                    cotizacion_id = int(cotizacion_data['id'])
                    
                    try:
                        cotizacion_obj = st.session_state.db.obtener_cotizacion(cotizacion_id)
                    except ValueError as ve:
                        st.error(str(ve))
                        return
                    except Exception as e:
                        st.error(f"Error al obtener la cotización: {str(e)}")
                        return
                    
                    if cotizacion_obj:
                        datos_calculo_guardados = st.session_state.db.get_calculos_escala_cotizacion(cotizacion_id)
                        st.session_state.cotizacion_model = cotizacion_obj
                        st.session_state.datos_cotizacion = datos_calculo_guardados if datos_calculo_guardados else {}
                        st.session_state.modo_edicion = True
                        st.session_state.paso_actual = 'calculadora'
                        st.rerun()
                    else:
                        st.error(f"No se pudo cargar la cotización con ID {cotizacion_id} para edición.")
                        
                except IndexError:
                     st.error(f"No se encontró la cotización con número {cotizacion_seleccionada_num} en los datos cargados.")
                except Exception as e:
                    st.error(f"Error al procesar la cotización para edición: {str(e)}")
                    print(f"Error detallado: {traceback.format_exc()}")
            
    except Exception as e:
        st.error(f"Error al cargar las cotizaciones: {str(e)}")
        print(f"Error detallado: {traceback.format_exc()}")

def main():
    # Check authentication status
    if not st.session_state.auth_manager.check_auth_status():
        create_login_ui()
        return
    
    # Show logout button in the sidebar
    with st.sidebar:
        st.write(f"👤 Usuario: {st.session_state.name}")
        if st.button("Cerrar Sesión"):
            st.session_state.auth_manager.logout()
            st.rerun()
    
    # Inicializar DBManager si no existe
    if 'db' not in st.session_state:
        st.session_state.db = DBManager(st.session_state.supabase)
    db = st.session_state.db
    
    # Inicializar variables de estado si no existen
    if 'cotizacion_calculada' not in st.session_state:
        st.session_state.cotizacion_calculada = False
    if 'datos_cotizacion' not in st.session_state:
        st.session_state.datos_cotizacion = None
    if 'cotizacion_model' not in st.session_state:
        st.session_state.cotizacion_model = None
    if 'consecutivo' not in st.session_state:
        st.session_state.consecutivo = None
    if 'cotizacion_guardada' not in st.session_state:
        st.session_state.cotizacion_guardada = False
    if 'cotizacion_id' not in st.session_state:
        st.session_state.cotizacion_id = None
    if 'pdf_path' not in st.session_state:
        st.session_state.pdf_path = None
    if 'resultados' not in st.session_state:
        st.session_state.resultados = None
    if 'mensajes' not in st.session_state:
        st.session_state.mensajes = []
    if 'pdf_data' not in st.session_state:
        st.session_state.pdf_data = None
    if 'materiales_pdf_data' not in st.session_state:
        st.session_state.materiales_pdf_data = None
    if 'paso_actual' not in st.session_state:
        st.session_state.paso_actual = 'calculadora'
    if 'nuevo_cliente_guardado' not in st.session_state:
        st.session_state.nuevo_cliente_guardado = False
    if 'nueva_referencia_guardada' not in st.session_state:
        st.session_state.nueva_referencia_guardada = False
    if 'cliente_seleccionado' not in st.session_state:
        st.session_state.cliente_seleccionado = None
    if 'creando_referencia' not in st.session_state:
        st.session_state.creando_referencia = False
    if 'referencia_seleccionada' not in st.session_state:
        st.session_state.referencia_seleccionada = None
    if 'cotizacion_cargada' not in st.session_state:
        st.session_state.cotizacion_cargada = False
    if 'material_seleccionado' not in st.session_state:
        st.session_state.material_seleccionado = None
    if 'acabado_seleccionado' not in st.session_state:
        st.session_state.acabado_seleccionado = None
    if 'comercial_seleccionado' not in st.session_state:
        st.session_state.comercial_seleccionado = None
    if 'modo_edicion' not in st.session_state:
        st.session_state.modo_edicion = False
    
    # Nuevo estado para forma de pago
    if 'forma_pago_id' not in st.session_state:
        st.session_state.forma_pago_id = 1  # Establecer ID 1 como valor por defecto
    
    # Inicializar variables para ajustes avanzados
    if 'rentabilidad_ajustada' not in st.session_state:
        st.session_state.rentabilidad_ajustada = None
    if 'ajustar_material' not in st.session_state:
        st.session_state.ajustar_material = False
    if 'valor_material_ajustado' not in st.session_state:
        st.session_state.valor_material_ajustado = 0.0
    if 'ajustar_troquel' not in st.session_state:
        st.session_state.ajustar_troquel = False
    if 'precio_troquel' not in st.session_state:
        st.session_state.precio_troquel = 0.0
    if 'ajustar_planchas' not in st.session_state:
        st.session_state.ajustar_planchas = False
    if 'precio_planchas' not in st.session_state:
        st.session_state.precio_planchas = 0.0
    
    # Botones para cambiar entre páginas
    cols = st.columns([1, 1, 1, 1])
    
    with cols[0]:
        if st.button("Calculadora", type="secondary", key="btn_calculadora"):
            # Guardar variables de autenticación
            auth_vars = {
                'authentication_status': st.session_state.get('authentication_status'),
                'username': st.session_state.get('username'),
                'name': st.session_state.get('name'),
                'role': st.session_state.get('role'),
                'user_id': st.session_state.get('user_id'),
                'user_profile': st.session_state.get('user_profile'), # <-- Añadir user_profile aquí
                'auth_manager': st.session_state.get('auth_manager'),
                'supabase': st.session_state.get('supabase')
            }
            
            # Limpiar todos los estados
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            
            # Restaurar variables de autenticación
            for key, value in auth_vars.items():
                if value is not None:
                    st.session_state[key] = value
            
            # Reinicializar solo las variables necesarias
            st.session_state.paso_actual = 'calculadora'
            st.session_state.cotizacion_calculada = False
            st.session_state.datos_cotizacion = None
            st.session_state.cotizacion_model = None
            st.session_state.consecutivo = None
            st.session_state.cotizacion_guardada = False
            st.session_state.cotizacion_id = None
            st.session_state.pdf_path = None
            st.session_state.resultados = None
            st.session_state.pdf_data = None
            st.session_state.materiales_pdf_data = None
            st.session_state.nuevo_cliente_guardado = False
            st.session_state.nueva_referencia_guardada = False
            st.session_state.mostrar_form_referencia = False
            st.session_state.cotizacion_cargada = False
            st.rerun()
    
    with cols[1]:
        if st.button("Crear Cliente", type="secondary", key="btn_crear_cliente"):
            st.session_state.paso_actual = 'crear_cliente'
            st.rerun()
    
    with cols[2]:
        if st.button("Actualizar Cotización", type="secondary", key="btn_actualizar_cotizacion"):
            st.session_state.paso_actual = 'actualizar_cotizacion'
            st.rerun()
    
    with cols[3]: # Movido a la cuarta columna
        # Obtener el valor de modo_edicion del session_state
        modo_edicion = st.session_state.modo_edicion
        if (st.session_state.cotizacion_calculada or 
            (modo_edicion and st.session_state.cotizacion_model)) and \
            st.button("Ver cotización", type="primary", key="btn_ver_cotizacion"):
            st.session_state.paso_actual = 'cotizacion'
            st.rerun()
    
    # Mostrar página según el paso actual
    if st.session_state.paso_actual == 'calculadora':
        mostrar_calculadora()
    elif st.session_state.paso_actual == 'cotizacion':
        mostrar_cotizacion()
    elif st.session_state.paso_actual == 'crear_cliente':
        crear_cliente()
    elif st.session_state.paso_actual == 'actualizar_cotizacion':
        mostrar_actualizar_cotizacion()

def mostrar_calculadora():
    """Muestra la interfaz principal de la calculadora"""
    # --- INICIO: Verificación de Rol --- 
    if 'usuario_verificado' not in st.session_state:
        st.session_state.usuario_verificado = False
        st.session_state.usuario_rol = None

    if not st.session_state.usuario_verificado:
        try:
            if 'db' not in st.session_state:
                 st.session_state.db = DBManager(st.session_state.supabase)
            db = st.session_state.db
            user_id = st.session_state.user_id
            perfil = db.get_perfil(user_id) 
            if perfil:
                st.session_state.usuario_verificado = True
                st.session_state.usuario_rol = perfil.get('rol_nombre')
                st.session_state.perfil_usuario = perfil # Guardar perfil completo
            else:
                st.error("No se pudo verificar el perfil del usuario.")
                return # Detener ejecución si no se encuentra perfil
        except Exception as e:
            st.error(f"Error al verificar perfil: {str(e)}")
            return

    # Verificar si el rol es 'comercial'
    if st.session_state.usuario_rol != 'comercial':
        st.error("Acceso denegado. Se requiere el rol de 'comercial'.")
        st.warning(f"Rol detectado: {st.session_state.usuario_rol}")
        return # Detener ejecución si el rol no es correcto
    # --- FIN: Verificación de Rol --- 
    
    # --- INICIO: Cargar Formas de Pago --- 
    if 'formas_pago' not in st.session_state:
        try:
            st.session_state.formas_pago = db.get_formas_pago()
        except Exception as e:
            st.error(f"Error al cargar formas de pago: {str(e)}")
            st.session_state.formas_pago = []
            
    formas_pago = st.session_state.formas_pago
    # --- FIN: Cargar Formas de Pago --- 
    
    try:
        # Verificar que tenemos una instancia de Supabase
        if 'supabase' not in st.session_state:
            st.error("Error: No se ha inicializado la conexión a Supabase")
            return
            
        # Usar la instancia de DBManager de la sesión o crearla si no existe
        if 'db' not in st.session_state:
            st.session_state.db = DBManager(st.session_state.supabase)
            
        db = st.session_state.db
        
        # Obtener el comercial actual
        comercial_id = st.session_state.user_id
        if not comercial_id:
            st.error("No se pudo identificar al comercial actual")
            return
            
        # Obtener materiales
        materiales = db.get_materiales()
        if not materiales:
            st.error("No se pudieron cargar los materiales")
            return
            
        # Obtener acabados
        acabados = db.get_acabados()
        if not acabados:
            st.error("No se pudieron cargar los acabados")
            return
            
        # Obtener tipos de producto
        tipos_producto = db.get_tipos_producto()
        if not tipos_producto:
            st.error("No se pudieron cargar los tipos de producto")
            return
            
        # Obtener clientes (solo los asociados al comercial actual)
        clientes = db.get_clientes()
        if not clientes:
            st.error("No se pudieron cargar los clientes")
            return
            
        # Resto del código de mostrar_calculadora()...
        # Las políticas RLS se encargarán de filtrar los datos automáticamente
        
    except Exception as e:
        st.error(f"Error al mostrar la calculadora: {str(e)}")
        print(f"Error detallado: {traceback.format_exc()}")
        return
    
    # Inicializar variables
    referencia_seleccionada = None
    cliente_seleccionado = None
    comercial_seleccionado = None
    mostrar_form_nueva_referencia = st.session_state.get('mostrar_form_referencia', False)
    
    # Inicializar session_state si no existe
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Mostrar mensajes si hay
    if "messages" in st.session_state and st.session_state.messages:
        for message in st.session_state.messages:
            if "✅" in message:
                st.success(message)
            elif "⚠️" in message:
                st.error(message)
            else:
                st.info(message)
        
        # Botón para limpiar todos los mensajes
        if st.button("Limpiar mensajes"):
            st.session_state.messages = []
            st.rerun()

    # Verificar si estamos en modo edición
    modo_edicion = "modo_edicion" in st.session_state and st.session_state.modo_edicion
    cotizacion_model = None
    
    if modo_edicion and "cotizacion_model" in st.session_state:
        cotizacion_model = st.session_state.cotizacion_model
        # Verificar que tenemos una referencia válida antes de mostrar el mensaje
        if ("referencia_seleccionada" in st.session_state and 
            st.session_state.referencia_seleccionada is not None and 
            hasattr(st.session_state.referencia_seleccionada, "descripcion")):
            st.info(f"Editando cotización para la referencia: {st.session_state.referencia_seleccionada.descripcion}")
        else:
            st.info("Editando cotización")
    
    # Si estamos en modo edición, ya tenemos el cliente seleccionado
    if modo_edicion:
        # Obtener la referencia del cliente primero
        referencia_id = cotizacion_model.referencia_cliente_id
        if referencia_id:
            # Obtener la referencia completa
            referencia = db.get_referencia_cliente(referencia_id)
            if referencia:
                cliente_id = referencia.cliente_id
                # --- MODIFICACIÓN: Usar el cliente directamente de la referencia --- 
                cliente = referencia.cliente 
                # -----------------------------------------------------------
                # --- ASIGNAR cliente_seleccionado --- 
                # --- MODIFICACIÓN: Verificar si cliente existe antes de usarlo --- 
                if cliente:
                    cliente_seleccionado = (cliente.id, cliente.nombre)
                    st.write(f"**Cliente:** {cliente.nombre}")
                else:
                    st.error(f"Error: No se encontraron datos del cliente asociados a la referencia ID {referencia_id}")
                    # Detener ejecución si no hay cliente
                    return 
                # -----------------------------------------------------------
                
                
                perfil_id_ref = referencia.id_usuario
                # --- CAMBIO: Llamar a get_perfil en lugar de get_comercial ---
                perfil_comercial = db.get_perfil(comercial_id) if comercial_id else None
                if perfil_comercial:
                    # --- CAMBIO: Usar datos del perfil --- 
                    comercial_seleccionado = (
                        perfil_comercial.get('id'), 
                        perfil_comercial.get('nombre'), 
                        perfil_comercial.get('email'), 
                        perfil_comercial.get('celular')
                    )
                    st.write(f"**Comercial:** {comercial_seleccionado[1]}") # Mostrar nombre del perfil
                else:
                    comercial_seleccionado = None
                    st.write("**Comercial:** No especificado")
                # --- FIN CAMBIO ---
                
                # Mostrar datos de la referencia
                st.write(f"**Descripción de la cotización:** {referencia.descripcion}")
                # --- GUARDAR descripción en session_state ---
                st.session_state.referencia_descripcion = referencia.descripcion
                # -------------------------------------------
                
                # Mostrar datos del producto
                st.write("### Datos del Producto")
                
                # Obtener y mostrar tipo de producto
                tipo_producto = db.get_tipo_producto(cotizacion_model.tipo_producto_id)
                st.write(f"**Tipo de Producto:** {tipo_producto.nombre}")
                
                # Obtener y mostrar material
                material = db.get_material(cotizacion_model.material_id)
                st.write(f"**Material:** {material.code} - {material.nombre}")
                
                # Obtener y mostrar acabado si no es manga
                es_manga = "MANGA" in tipo_producto.nombre.upper()
                if not es_manga:
                    acabado = db.get_acabado(cotizacion_model.acabado_id)
                    st.write(f"**Acabado:** {acabado.code} - {acabado.nombre}")
                
                # Mostrar medidas y propiedades en columnas
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**Ancho:** {cotizacion_model.ancho} mm")
                    st.write(f"**Avance/Largo:** {cotizacion_model.avance} mm")
                    st.write(f"**Número de pistas:** {cotizacion_model.numero_pistas}")
                    
                with col2:
                    st.write(f"**Número de tintas:** {cotizacion_model.num_tintas}")
                    st.write(f"**Planchas por separado:** {'Sí' if cotizacion_model.planchas_x_separado else 'No'}")
                    if not es_manga:
                        st.write(f"**Troquel existe:** {'Sí' if cotizacion_model.existe_troquel else 'No'}")
                    
                with col3:
                    if es_manga:
                        # Fetch tipos_grafado directly from the database
                        tipos_grafado = db.get_tipos_grafado()
                        
                        # Create a Streamlit selectbox using the database data directly
                        tipo_grafado_seleccionado = st.selectbox(
                            "Tipo de Grafado",
                            options=tipos_grafado,  # Use the database objects directly
                            format_func=lambda tg: tg.nombre,  # Display the name
                            index=0  # Optional: set a default index if needed
                        )
                    st.write(f"**{'Mangas' if es_manga else 'Etiquetas'} por rollo:** {cotizacion_model.num_paquetes_rollos}")
                
                # Mostrar escalas
                if hasattr(cotizacion_model, 'escalas') and cotizacion_model.escalas:
                    st.write("### Escalas de Producción")
                    escalas_str = ", ".join([str(int(e.escala)) for e in cotizacion_model.escalas])
                    st.write(f"**Escalas:** {escalas_str}")
                
                # Botón para habilitar edición
                if st.button("Editar Cotización"):
                    st.session_state.mostrar_formulario_edicion = True
                    st.rerun()
            else:
                st.error("No se pudo cargar la información de la referencia")
                return
        else:
            st.error("No se encontró la referencia asociada a la cotización")
            return
    
    else:
        # Obtener datos de referencia
        st.write("### Datos del Cliente")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Si estamos en modo edición, ya tenemos el cliente seleccionado
            if modo_edicion:
                cliente_id = cotizacion_model.cliente_id
                cliente = db.get_cliente(cliente_id)
                cliente_seleccionado = (cliente.id, cliente.nombre)
                st.write(f"**Cliente:** {cliente.nombre}")
            else:
                # Obtener todos los clientes 
                clientes = db.get_clientes()
                cliente_seleccionado = st.selectbox(
                    "Cliente",
                    options=[(c.id, c.nombre) for c in clientes],
                    format_func=lambda x: x[1]
                ) if clientes else None
        
        with col2:
            # Mostrar el comercial logueado (ahora perfil)
            if modo_edicion:
                # En modo edición, obtener el perfil asociado a la referencia
                # --- CAMBIO: Usar id_usuario en lugar de id_comercial ---
                perfil_id_ref = referencia.id_usuario
                # -----------------------------------------------------
                perfil_comercial_ref = db.get_perfil(perfil_id_ref) if perfil_id_ref else None
                if perfil_comercial_ref:
                    # --- CAMBIO: Guardar info completa del perfil --- 
                    comercial_seleccionado = (
                        perfil_comercial_ref.get('id'), 
                        perfil_comercial_ref.get('nombre'),
                        perfil_comercial_ref.get('email'), # Asumiendo que get_perfil devuelve email
                        perfil_comercial_ref.get('celular') # Asumiendo que get_perfil devuelve celular
                    )
                    st.write(f"**Comercial:** {comercial_seleccionado[1]}") # Mostrar nombre
                else:
                    comercial_seleccionado = None
                    st.write("**Comercial:** No especificado")
            else:
                # Obtener los datos del perfil del comercial logueado (ya guardado en st.session_state.perfil_usuario)
                perfil_actual = st.session_state.get('perfil_usuario')
                if perfil_actual:
                    # --- CAMBIO: Guardar info completa del perfil --- 
                    comercial_seleccionado = (
                        perfil_actual.get('id'), 
                        perfil_actual.get('nombre'),
                        perfil_actual.get('email'), # Asumiendo que el perfil guardado tiene email
                        perfil_actual.get('celular') # Asumiendo que el perfil guardado tiene celular
                    )
                    # Mostrar el nombre como texto fijo
                    st.text_input("Comercial", value=comercial_seleccionado[1], disabled=True) # Mostrar nombre
                else:
                    # Esto no debería ocurrir si la verificación inicial pasó
                    comercial_seleccionado = None
                    st.error("No se pudieron cargar los datos del comercial actual")

        with col3:
            if modo_edicion:
                # En modo edición, mostrar la referencia existente
                st.write(f"**Descripción de la cotización:** {st.session_state.referencia_seleccionada.descripcion}")
            else:
                # Campo simple para ingresar la referencia
                referencia_descripcion = st.text_input(
                    "Descripción de la cotización",
                    key="nueva_referencia_input",
                    help="Ingrese una descripción para esta cotización"
                )
                if referencia_descripcion:
                    st.session_state.referencia_descripcion = referencia_descripcion

        # Continuar con el resto del código solo si no estamos en modo edición y hay un cliente seleccionado
        if not modo_edicion and cliente_seleccionado:
            # Verificar si hay una cotización existente para esta referencia
            if ('referencia_seleccionada' in st.session_state and 
                st.session_state.referencia_seleccionada and 
                st.session_state.referencia_seleccionada.id):
                
                cotizacion_existente = db.get_cotizacion_by_referencia(st.session_state.referencia_seleccionada.id)
                if cotizacion_existente: # <-- Added check here
                    # Load existing quotation without showing a message
                    st.session_state.cotizacion_model = cotizacion_existente
                    st.session_state.modo_edicion = True
                    if st.button("Continuar con la edición", key="btn_continuar_edicion"):
                        st.rerun()
            else:
                pass

    # Si estamos en modo edición, no seguimos con el formulario hasta que el usuario haga clic en "Continuar"
    if modo_edicion and "cotizacion_model" in st.session_state and not st.session_state.get("mostrar_formulario_edicion", False):
        return
    
    # Obtener datos necesarios para el formulario
    materiales = db.get_materiales()
    acabados = db.get_acabados()
    tipos_producto = db.get_tipos_producto()
    # +++ NUEVO: Obtener tipos de grafado aquí +++
    tipos_grafado = db.get_tipos_grafado()
    
    # Definir valores por defecto - siempre definir estas variables
    tipo_producto_id_default = 1
    material_id_default = 1
    acabado_id_default = 10  # Sin acabado
    ancho_default = 100.0
    avance_default = 100.0
    pistas_default = 1
    num_tintas_default = 4
    planchas_por_separado_default = "No"
    troquel_existe_default = "No"
    tipo_grafado_default = "Sin grafado"
    num_rollos_default = 1000
    escalas_default = "1000, 2000, 3000, 5000"
    
    # +++ NUEVO: Inicializar tipo_grafado_id_default aquí +++
    tipo_grafado_id_default = None # Default para nuevas cotizaciones
    
    # Si hay una referencia seleccionada o si acabamos de crear una nueva, continuamos con el formulario
    if ((not mostrar_form_nueva_referencia and "referencia_seleccionada" in st.session_state) or
        st.session_state.get("nueva_referencia_guardada", False)):
        
        # Si acabamos de crear una nueva referencia, mostrar un mensaje
        if st.session_state.get("nueva_referencia_guardada", False):
            st.success(f"Creando cotización para la referencia: {st.session_state.referencia_seleccionada.descripcion}")
            st.session_state.nueva_referencia_guardada = False  # Resetear el flag
        
        # Datos del producto
        st.write("### Datos del Producto")
        
        # Si estamos en modo edición, usar los valores del modelo y los datos de cálculo
        if modo_edicion and cotizacion_model:
            datos_calculo = st.session_state.get('datos_cotizacion', {})
            tipo_producto_id_default = cotizacion_model.tipo_producto_id
            material_id_default = cotizacion_model.material_id
            acabado_id_default = cotizacion_model.acabado_id
            ancho_default = datos_calculo.get('ancho', 100.0)
            avance_default = datos_calculo.get('avance', 100.0)
            pistas_default = datos_calculo.get('numero_pistas', 1)
            num_tintas_default = datos_calculo.get('num_tintas', 4)
            planchas_por_separado_default = "Sí" if datos_calculo.get('planchas_x_separado', False) else "No"
            troquel_existe_default = "Sí" if datos_calculo.get('existe_troquel', False) else "No"
            tipo_grafado_id_default = datos_calculo.get('tipo_grafado_id')
            num_rollos_default = datos_calculo.get('num_paquetes_rollos', 1000) # Use num_paquetes_rollos from DB
            
            # Establecer valores para ajustes avanzados
            st.session_state.rentabilidad_ajustada = datos_calculo.get('rentabilidad')
            
            # Almacenar los valores originales pero sin activar los checkboxes
            st.session_state.valor_material_original = datos_calculo.get('valor_material')
            st.session_state.valor_troquel_original = datos_calculo.get('valor_troquel')
            st.session_state.valor_planchas_original = datos_calculo.get('valor_plancha')
            
            # Resetear los estados de ajuste
            st.session_state.ajustar_material = False
            st.session_state.ajustar_troquel = False
            st.session_state.ajustar_planchas = False
            
            # Establecer los valores de los inputs sin activar los checkboxes
            st.session_state.valor_material_input = datos_calculo.get('valor_material', 0)
            st.session_state.precio_troquel_input = datos_calculo.get('valor_troquel', 0)
            st.session_state.precio_planchas_input = datos_calculo.get('valor_plancha', 0)
            
            # Obtener escalas si existen
            if hasattr(cotizacion_model, 'escalas') and cotizacion_model.escalas:
                escalas_default = ", ".join([str(int(e.escala)) for e in cotizacion_model.escalas])
        else:
            # Valores por defecto para nueva cotización
            tipo_producto_id_default = 1
            material_id_default = 1
            acabado_id_default = 10  # Sin acabado
            ancho_default = 100.0
            avance_default = 100.0
            pistas_default = 1
            num_tintas_default = 4
            planchas_por_separado_default = "No"
            troquel_existe_default = "No"
            tipo_grafado_id_default = None
            num_rollos_default = 1000
            escalas_default = "1000, 2000, 3000, 5000"
    
    # Tipo de producto - inicializar siempre esta variable
    tipo_producto_seleccionado = None
    for tp in tipos_producto:
        if tp.id == tipo_producto_id_default:
            tipo_producto_seleccionado = (tp.id, tp.nombre)
            break
    
    if not tipo_producto_seleccionado and tipos_producto:
        tipo_producto_seleccionado = (tipos_producto[0].id, tipos_producto[0].nombre)
    
    # Selección del tipo de producto
    tipo_producto_seleccionado = st.selectbox(
        "Tipo de Producto",
        options=[(t.id, t.nombre) for t in tipos_producto],
        format_func=lambda x: x[1],
        index=[i for i, t in enumerate(tipos_producto) if t.id == tipo_producto_id_default][0] if tipo_producto_id_default in [t.id for t in tipos_producto] else 0
    )
                
    # Guardar el tipo de producto seleccionado en session_state para asegurar que se use correctamente
    st.session_state.tipo_producto_seleccionado = tipo_producto_seleccionado
    
    # Imprimir debug para verificar el tipo de producto seleccionado
    print("\n=== DEBUG TIPO DE PRODUCTO SELECCIONADO ===")
    print(f"ID: {tipo_producto_seleccionado[0]}, Nombre: {tipo_producto_seleccionado[1]}")
    print("===================================\n")
                
    es_manga = "MANGA" in tipo_producto_seleccionado[1].upper()
    
    # Filtrar materiales según el tipo de producto
    materiales_filtrados = [
        m for m in materiales 
        if es_manga and any(code in m.code.upper() for code in ['PVC', 'PETG'])
        or not es_manga
    ]
    
            # Material
    material_seleccionado = st.selectbox(
        "Material",
        options=[(m.id, f"{m.code} - {m.nombre} (${m.valor:.2f})", m.nombre, m.adhesivo_tipo) for m in materiales_filtrados],
            format_func=lambda x: x[1],  # Mostrar todo el texto
            index=[i for i, m in enumerate(materiales_filtrados) if m.id == material_id_default][0] if material_id_default in [m.id for m in materiales_filtrados] else 0
    )
    
            # Acabado (solo para etiquetas)
    if not es_manga:
        acabado_seleccionado = st.selectbox(
            "Acabado",
            options=[(a.id, f"{a.code} - {a.nombre} (${a.valor:.2f})", a.nombre) for a in acabados],
                format_func=lambda x: x[1],  # Mostrar todo el texto
                index=[i for i, a in enumerate(acabados) if a.id == acabado_id_default][0] if acabado_id_default in [a.id for a in acabados] else 0
        )
    else:
        acabado_seleccionado = (10, "SA - Sin acabado ($0.00)", "Sin acabado")
    
    # Selección de Forma de Pago
    if not formas_pago:
        st.error("Error: No se pudieron cargar las formas de pago")
        return
        
    default_fp_index = next((i for i, fp in enumerate(formas_pago) if fp.id == st.session_state.get('forma_pago_id', 1)), 0)
    forma_pago_seleccionada = st.selectbox(
        "Forma de Pago *",  # Añadir asterisco para indicar que es obligatorio
        options=formas_pago,
        format_func=lambda x: x.descripcion,
        index=default_fp_index,
        key="forma_pago_selectbox",
        on_change=lambda: st.session_state.update(forma_pago_id=st.session_state.forma_pago_selectbox.id)
    )
    st.session_state.forma_pago_id = forma_pago_seleccionada.id if forma_pago_seleccionada else 1

    # Medidas y propiedades
    col1, col2, col3 = st.columns(3)
    with col1:
        ancho = st.number_input(
            "Ancho (mm)", 
            min_value=10.0, 
            max_value=ANCHO_MAXIMO_LITOGRAFIA, 
            value=float(ancho_default), 
            step=10.0,
            help=f"El ancho no puede exceder {ANCHO_MAXIMO_LITOGRAFIA}mm. Los valores deben ser múltiplos de 10mm."
        )
        avance = st.number_input("Avance/Largo (mm)", 
                               min_value=10.0, 
                                   value=float(avance_default), 
                               step=10.0,
                               help="Los valores deben ser múltiplos de 10mm.")
        pistas = st.number_input("Número de pistas", min_value=1, value=int(pistas_default), step=1)
        
    with col2:
        num_tintas = st.number_input("Número de tintas", 
                                   min_value=0, 
                                   max_value=7, 
                                       value=int(num_tintas_default), 
                                   step=1,
                                   help="Máximo 7 tintas")
        planchas_por_separado = st.radio("¿Planchas por separado?", 
                                    options=["Sí", "No"], 
                                        index=0 if planchas_por_separado_default == "Sí" else 1,
                                    horizontal=True)
        
        # Solo mostrar la pregunta del troquel si NO es manga
        if not es_manga:
            troquel_existe = st.radio("¿Existe troquel?", 
                                    options=["Sí", "No"], 
                                        index=0 if troquel_existe_default == "Sí" else 1,
                                    horizontal=True)
        else:
            # Para mangas, el valor dependerá del tipo de grafado
                troquel_existe = troquel_existe_default

    with col3:
        # Agregar selección de grafado para mangas
        tipo_grafado = None
        if es_manga:
                # --- NUEVA LÓGICA PARA SELECTBOX GRAFADO ---
                # Fetch tipos_grafado directly from the database
                # Ensure db.get_tipos_grafado() returns a list of TipoGrafado objects
                tipos_grafado_db = db.get_tipos_grafado() 
                
                # Encontrar el índice del valor por defecto (si existe)
                default_grafado_index = 0
                if tipo_grafado_id_default is not None:
                    for i, tg in enumerate(tipos_grafado_db):
                        if tg.id == tipo_grafado_id_default:
                            default_grafado_index = i
                            break
                        
                tipo_grafado_seleccionado = st.selectbox(
                    "Tipo de Grafado",
                    options=tipos_grafado_db, # Use the fetched objects directly
                    format_func=lambda tg: tg.nombre, # Display the name attribute
                    index=default_grafado_index, # Set default index
                    key="selectbox_tipo_grafado_manga" # +++ ADD UNIQUE KEY +++
                )
                # --- FIN NUEVA LÓGICA ---
        
        # Cambiar el label según el tipo de producto
        label_rollos = "Número de mangas por rollo" if es_manga else "Número de etiquetas por rollo"
        num_rollos = st.number_input(label_rollos, min_value=1, value=int(num_rollos_default), step=100)

    # Sección de escalas
    st.header("Escalas de Producción")
    escalas_text = st.text_input(
        "Ingrese las escalas separadas por comas",
            value=escalas_default,
        help="Ejemplo: 1000, 2000, 3000, 5000"
    )
    
    escalas = procesar_escalas(escalas_text)
    if not escalas:
        st.error("Por favor ingrese números válidos separados por comas")
        return
    

    # Sección de ajustes avanzados con un expander
    with st.expander("Ajustes Avanzados"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Rentabilidad
            rentabilidad_default = RENTABILIDAD_MANGAS if es_manga else RENTABILIDAD_ETIQUETAS
            # --- MODIFICADO: Usar valor cargado si existe ---
            # --- Get value directly from datos_calculo if in edit mode ---
            rentabilidad_value = float(datos_calculo.get('rentabilidad', rentabilidad_default)) if modo_edicion else rentabilidad_default

            st.number_input(
                "Rentabilidad (%)",
                min_value=0.0,
                max_value=100.0,
                value=rentabilidad_value,
                step=1.0,
                help="Porcentaje de rentabilidad a aplicar en el cálculo",
                key="rentabilidad_input" # Streamlit usa esta key para el estado
            )

            # Precio de material
            valor_material_actual = extraer_valor_precio(material_seleccionado[1])
            st.text(f"Valor material actual: ${valor_material_actual:.2f}")
            
            # Mostrar checkbox de ajuste de material
            ajustar_material_checked = st.session_state.get('ajustar_material_checkbox', False)
            st.checkbox("Ajustar precio de material",
                       value=ajustar_material_checked,
                       key="ajustar_material_checkbox")

            # Mostrar input de valor material
            valor_material_mostrar = (
                st.session_state.get('valor_material_input', valor_material_actual)
                if not ajustar_material_checked
                else st.session_state.get('valor_material_input', valor_material_actual)
            )
            st.number_input(
                "Valor material",
                min_value=0.0,
                value=valor_material_mostrar,
                step=0.01,
                disabled=not ajustar_material_checked,
                key="valor_material_input"
            )
        
        with col2:
            # Precio de troquel
            ajustar_troquel_checked = st.session_state.get('ajustar_troquel_checkbox', False)
            st.checkbox("Ajustar precio de troquel",
                       value=ajustar_troquel_checked,
                       key="ajustar_troquel_checkbox")

            # Mostrar input de valor troquel
            valor_troquel_mostrar = (
                st.session_state.get('precio_troquel_input', 0.0)
                if not ajustar_troquel_checked
                else st.session_state.get('precio_troquel_input', 0.0)
            )
            st.number_input(
                "Valor troquel",
                min_value=0.0,
                value=valor_troquel_mostrar,
                step=1000.0,
                disabled=not ajustar_troquel_checked,
                key="precio_troquel_input"
            )
            
            # Precio de planchas
            ajustar_planchas_checked = st.session_state.get('ajustar_planchas_checkbox', False)
            st.checkbox("Ajustar precio de planchas",
                       value=ajustar_planchas_checked,
                       key="ajustar_planchas_checkbox")

            # Mostrar input de valor planchas
            valor_planchas_mostrar = (
                st.session_state.get('precio_planchas_input', 0.0)
                if not ajustar_planchas_checked
                else st.session_state.get('precio_planchas_input', 0.0)
            )
            st.number_input(
                "Valor planchas",
                min_value=0.0,
                value=valor_planchas_mostrar,
                step=1000.0,
                disabled=not ajustar_planchas_checked,
                key="precio_planchas_input"
            )

    # Validación de ancho total antes de calcular
    calculadora_lito = CalculadoraLitografia()
    f3, mensaje_ancho = calculadora_lito.calcular_ancho_total(num_tintas, pistas, ancho)
    
    if mensaje_ancho:
        st.error(mensaje_ancho)
        if "ERROR" in mensaje_ancho:
            return  # Stop further processing if it's a critical error
        else:
            # Show a warning but allow continuation
            st.warning("Por favor ajuste el número de pistas o el ancho para continuar.")

        # Si estamos en modo edición, marcar la sesión para mostrar el formulario completo la próxima vez
        if modo_edicion and not hasattr(st.session_state, "mostrar_formulario_edicion"):
            st.session_state.mostrar_formulario_edicion = True

    # Botón para calcular
    if st.button("Calcular", type="primary"):
        # +++ DEBUGGING POINT 0: Check if button logic is entered +++
        print("DEBUG: 'Calcular' button pressed. Entering calculation logic...") 
        try:
            # Verificar que tenemos los datos necesarios
            if not cliente_seleccionado:
                st.error("Por favor seleccione un cliente")
                return
                
            if not comercial_seleccionado:
                st.error("Por favor seleccione un comercial")
                return
                
            if not modo_edicion and (not 'referencia_descripcion' in st.session_state or not st.session_state.referencia_descripcion):
                st.error("Por favor ingrese una descripción para la referencia")
                return
                
            # Configuración inicial
            datos_lito = DatosLitografia(
                ancho=ancho * FACTOR_ANCHO_MANGAS + INCREMENTO_ANCHO_MANGAS if es_manga else ancho,
                avance=avance,
                pistas=pistas,
                planchas_por_separado=planchas_por_separado == "Sí",
                incluye_troquel=True,
                troquel_existe=troquel_existe == "Sí",
                gap=GAP_PISTAS_MANGAS if es_manga else GAP_PISTAS_ETIQUETAS,
                gap_avance=GAP_AVANCE_MANGAS if es_manga else GAP_AVANCE_ETIQUETAS,
                ancho_maximo=ANCHO_MAXIMO_LITOGRAFIA
            )
            
            # Crear calculadora de litografía
            calculadora = CalculadoraLitografia()
            
            # Iniciar captura de la consola para el cálculo de litografía
            console_capture.clear()
            console_capture.start()
            
            # Generar reporte completo
            reporte_lito = calculadora.generar_reporte_completo(datos_lito, num_tintas, es_manga)
            
            # Detener captura de la consola
            console_capture.stop()
            
            # Verificar condiciones especiales para el troquel en mangas
            if es_manga:
                # Asegurarnos de que el tipo de grafado se pasa correctamente
                # Access the 'nombre' attribute instead of using index [1]
                datos_lito.tipo_grafado = tipo_grafado_seleccionado.nombre
                print(f"\n=== DEBUG MANGA ===")
                print(f"Tipo de grafado seleccionado: {tipo_grafado_seleccionado.nombre}") # Also update print statement

                # Calcular valor del troquel según el tipo de grafado
                reporte_troquel = calculadora.calcular_valor_troquel(
                    datos=datos_lito,
                    repeticiones=reporte_lito['desperdicio']['mejor_opcion'].get("repeticiones", 1),
                    troquel_existe=False,  # Para mangas no importa si existe
                    valor_mm=100,
                    tipo_grafado_id=tipo_grafado_seleccionado.id # <<< Pass the ID
                )
                
                print(f"Valor troquel calculado: ${reporte_troquel.get('valor', 0):,.2f}")
                print(f"Factor división usado: {reporte_troquel.get('detalles', {}).get('factor_division')}")
                
                # Actualizar el reporte con el nuevo valor de troquel
                reporte_lito['valor_troquel'] = reporte_troquel
            else:
                # Lógica existente para etiquetas
                if datos_lito.incluye_troquel:
                    reporte_lito['valor_troquel'] = calculadora.calcular_valor_troquel(
                        datos=datos_lito,
                        repeticiones=reporte_lito['desperdicio']['mejor_opcion'].get("repeticiones", 1),
                        troquel_existe=datos_lito.troquel_existe
                    )
            
            # Guardar logs de litografía
            logs_litografia = console_capture.get_logs()
            
            # Verificar si hay errores en el reporte
            if 'error' in reporte_lito:
                st.error(f"Error: {reporte_lito['error']}")
                if 'detalles' in reporte_lito:
                    st.error(f"Detalles: {reporte_lito['detalles']}")
                return
            
            if not reporte_lito.get('desperdicio') or not reporte_lito['desperdicio'].get('mejor_opcion'):
                st.error("No se pudo calcular el desperdicio. Por favor revise los valores de ancho y avance.")
                return
            
            mejor_opcion = reporte_lito['desperdicio']['mejor_opcion']
            
            # +++ NUEVO: Capturar dientes de la mejor opción +++
            dientes_seleccionados = mejor_opcion.get('dientes')
            print(f"DEBUG: Dientes seleccionados automáticamente: {dientes_seleccionados}")
            
            # Configurar datos de escala
            datos_escala = DatosEscala(
                escalas=escalas,
                pistas=pistas,
                ancho=ancho,
                avance=avance,
                avance_total=avance + (GAP_AVANCE_MANGAS if es_manga else GAP_AVANCE_ETIQUETAS),
                desperdicio=mejor_opcion['desperdicio'],
                velocidad_maquina=VELOCIDAD_MAQUINA_MANGAS_7_TINTAS if es_manga and num_tintas == 7 else VELOCIDAD_MAQUINA_NORMAL,
                rentabilidad=RENTABILIDAD_MANGAS if es_manga else RENTABILIDAD_ETIQUETAS,
                porcentaje_desperdicio=DESPERDICIO_MANGAS if es_manga else DESPERDICIO_ETIQUETAS
            )
            
            # Establecer el área de etiqueta
            area_etiqueta = reporte_lito['area_etiqueta']['area'] if isinstance(reporte_lito['area_etiqueta'], dict) else 0
            datos_escala.set_area_etiqueta(area_etiqueta)
            
            # --- Guardar datos para informe técnico --- 
            st.session_state.reporte_lito = reporte_lito
            st.session_state.reporte_troquel = reporte_troquel if es_manga else reporte_lito.get('valor_troquel', {})
            st.session_state.datos_entrada = datos_escala # Guardar objeto DatosEscala
            # --- Fin Guardar datos para informe técnico --- 

            # Obtener valores
            valor_etiqueta = reporte_lito.get('valor_tinta', 0)
            valor_plancha, valor_plancha_dict = obtener_valor_plancha(reporte_lito)
            valor_troquel = obtener_valor_troquel(reporte_lito)
            
            # Extraer valores correctos para material y acabado
            valor_material = extraer_valor_precio(material_seleccionado[1])
            valor_acabado = 0 if es_manga else extraer_valor_precio(acabado_seleccionado[1])
            
            # Imprimir información de debug para valores de material y acabado
            print(f"\n=== DEBUG VALORES DE MATERIAL Y ACABADO ===")
            print(f"Material seleccionado: {material_seleccionado[1]}")
            print(f"Valor material extraído: ${valor_material:.2f}")
            print(f"Acabado seleccionado: {acabado_seleccionado[1] if not es_manga else 'N/A (manga)'}")
            print(f"Valor acabado extraído: ${valor_acabado:.2f}")
            print(f"Área etiqueta: {area_etiqueta:.2f} mm²")
            
            # Calcular costos
            calculadora = CalculadoraCostosEscala()
            
            # Ajustar datos con los valores personalizados
            # --- MODIFICADO: Leer rentabilidad desde el widget ---
            if 'rentabilidad_input' in st.session_state:
                datos_escala.rentabilidad = st.session_state.rentabilidad_input

            # Ajustar valores de material, troquel y planchas
            # --- MODIFICADO: Leer estado de ajuste y valor desde los widgets ---
            if 'ajustar_material_checkbox' in st.session_state and st.session_state.ajustar_material_checkbox:
                if 'valor_material_input' in st.session_state:
                    valor_material = st.session_state.valor_material_input

            # Valor troquel
            # --- MODIFICADO: Leer estado de ajuste y valor desde los widgets ---
            if es_manga:
                # Para mangas, el valor del troquel depende del tipo de grafado
                if 'ajustar_troquel_checkbox' in st.session_state and st.session_state.ajustar_troquel_checkbox:
                    if 'precio_troquel_input' in st.session_state:
                        # Si se ajusta manualmente, aplicar el factor de división según el tipo de grafado
                        factor_division = 1 if tipo_grafado_seleccionado.id == 4 else 2
                        valor_troquel = st.session_state.precio_troquel_input / factor_division
                        print(f"\n=== DEBUG VALOR TROQUEL MANGA (AJUSTADO) ===")
                        print(f"Valor troquel original: ${st.session_state.precio_troquel_input:,.2f}")
                        print(f"Factor división aplicado: {factor_division}")
                        print(f"Valor troquel final: ${valor_troquel:,.2f}")
                else:
                    # Si no se ajusta, usar el valor ya calculado que tiene en cuenta el tipo de grafado
                    valor_troquel = obtener_valor_troquel(reporte_lito)
                    print(f"\n=== DEBUG VALOR TROQUEL MANGA ===")
                    print(f"Tipo grafado ID: {tipo_grafado_seleccionado.id}")
                    print(f"Valor troquel usado: ${valor_troquel:,.2f}")
            else:
                # Para etiquetas, mantener la lógica existente
                if 'ajustar_troquel_checkbox' in st.session_state and st.session_state.ajustar_troquel_checkbox:
                    if 'precio_troquel_input' in st.session_state:
                        # Para etiquetas, aplicar factor de división = 2 si el troquel existe
                        factor_division = 2 if troquel_existe == "Sí" else 1
                        valor_troquel = st.session_state.precio_troquel_input / factor_division
                        print(f"\n=== DEBUG VALOR TROQUEL ETIQUETA (AJUSTADO) ===")
                        print(f"Valor troquel original: ${st.session_state.precio_troquel_input:,.2f}")
                        print(f"Factor división aplicado: {factor_division}")
                        print(f"Valor troquel final: ${valor_troquel:,.2f}")
                else:
                    valor_troquel = obtener_valor_troquel(reporte_lito)

            # Valor plancha
            # --- MODIFICADO: Leer estado de ajuste y valor desde los widgets ---
            if 'ajustar_planchas_checkbox' in st.session_state and st.session_state.ajustar_planchas_checkbox:
                if 'precio_planchas_input' in st.session_state:
                    valor_plancha = st.session_state.precio_planchas_input # Actualizar valor_plancha original
                    # Si las planchas se cobran por separado, el valor para cálculo es 0
                    # Si no, el valor para cálculo es el ajustado.
                    valor_plancha_para_calculo = 0 if planchas_por_separado == "Sí" else valor_plancha
                # Si se ajustan planchas pero se cobran por separado, el valor para cálculo sigue siendo 0
                # Si se ajustan planchas y NO se cobran por separado, valor_plancha_para_calculo ya tiene el valor ajustado.
            else:
                # Si no se ajustan planchas, obtener valor de litografía y determinar valor para cálculo
                valor_plancha, valor_plancha_dict = obtener_valor_plancha(reporte_lito)
                valor_plancha_para_calculo = 0 if planchas_por_separado == "Sí" else valor_plancha
            
            # Recalcular valor_plancha_separado si las planchas se cobran por separado (podría depender del valor ajustado)
            if planchas_por_separado == "Sí":
                # Necesitamos el valor_plancha_dict que corresponde al valor_plancha (sea original o ajustado)
                # Si se ajustó, el dict original no aplica. Asumimos que el valor ajustado es el que se cobra.
                if 'ajustar_planchas_checkbox' in st.session_state and st.session_state.ajustar_planchas_checkbox:
                     # Simplificación: Usar el valor ajustado directamente como base para redondear
                     # Esto puede no ser perfecto si la fórmula original era compleja
                     valor_base = valor_plancha / 0.7 
                     valor_plancha_separado = math.ceil(valor_base / 10000) * 10000
                else:
                    # Usar el dict original si no se ajustó
                     valor_plancha_separado = calcular_valor_plancha_separado(valor_plancha_dict)
            else:
                valor_plancha_separado = None # Asegurarse que sea None si no aplica

            # --- FIN MODIFICACIONES LECTURA AJUSTES AVANZADOS ---

            resultados = calculadora.calcular_costos_por_escala(
                datos=datos_escala,
                num_tintas=num_tintas,
                valor_etiqueta=valor_etiqueta,
                valor_plancha=valor_plancha_para_calculo,
                valor_troquel=valor_troquel,
                valor_material=valor_material,
                valor_acabado=valor_acabado,
                es_manga=es_manga
            )
            
            if resultados:
                # Guardar resultados en el estado
                st.session_state.resultados = resultados
                
                # Usar un valor temporal para el consecutivo, será reemplazado por el ID después
                st.session_state.consecutivo = 0
                
                # Obtener ID de grafado directamente de la selección (si es manga)
                # Access the .id attribute instead of index [0]
                tipo_grafado_id = tipo_grafado_seleccionado.id if es_manga else None

                # Guardar datos de cotización en el estado, asegurando que se usen los valores FINALES
                datos_para_guardar = {
                    'material': material_seleccionado[1].split(' - ')[1].split(' ($')[0],
                    'acabado': "Sin acabado" if es_manga else acabado_seleccionado[2],
                    # --- Campos originales y necesarios para calculos_escala_cotizacion ---
                    'num_tintas': num_tintas, 
                    'num_rollos': num_rollos, # num_paquetes_rollos
                    'valor_plancha': valor_plancha, # Valor original de plancha (antes de ajustes)
                    'valor_plancha_separado': valor_plancha_separado, # Valor calculado si se cobra por separado
                    'es_manga': es_manga,
                    'valor_troquel': valor_troquel, # Valor final del troquel (potencialmente ajustado)
                    'valor_material': valor_material, # Valor final de material (potencialmente ajustado)
                    'valor_plancha_para_calculo': valor_plancha_para_calculo, # Valor final de plancha usado en cálculo
                    'rentabilidad': datos_escala.rentabilidad, # Rentabilidad final usada
                    'valor_acabado': valor_acabado, # Valor final de acabado (viene de extracción o 0 si es manga)
                    'avance': avance, # Valor de entrada
                    'ancho': ancho, # Valor de entrada
                    'existe_troquel': troquel_existe == "Sí", # Valor de entrada booleano
                    'planchas_x_separado': planchas_por_separado == "Sí", # Valor de entrada booleano
                    'numero_pistas': pistas, # Valor de entrada
                    'tipo_producto_id': tipo_producto_seleccionado[0], # ID del tipo de producto
                    'tipo_grafado_id': tipo_grafado_id, # ID del tipo de grafado (puede ser None)
                    'unidad_z_dientes': dientes_seleccionados 
                }
                st.session_state.datos_cotizacion = datos_para_guardar
                    
                print("\n=== DEBUG DATOS COMERCIAL AL CREAR COTIZACIÓN ===")
                print(f"Comercial seleccionado: {comercial_seleccionado}")
                print(f"Nombre: {comercial_seleccionado[1] if comercial_seleccionado else None}")
                print(f"Email: {comercial_seleccionado[2] if comercial_seleccionado else None}")
                print(f"Teléfono: {comercial_seleccionado[3] if comercial_seleccionado else None}")
                print("=================================")
                
                # Crear modelo de cotización y guardarlo en el estado
                print("\n=== DEBUG COMERCIAL SELECCIONADO ===")
                print(f"Comercial seleccionado: {comercial_seleccionado}")
                comercial_id = comercial_seleccionado[0] if comercial_seleccionado else None
                print(f"ID del comercial a usar: {comercial_id}")
                print("=================================\n")
                
                # --- MODIFICACIÓN: Determinar cliente_id y referencia_id según modo_edicion ---
                if modo_edicion and st.session_state.cotizacion_model:
                    # Acceder al ID a través del objeto relacionado
                    cliente_id_para_modelo = st.session_state.cotizacion_model.cliente.id if st.session_state.cotizacion_model.cliente else None 
                    referencia_id_para_modelo = st.session_state.cotizacion_model.referencia_cliente.id if st.session_state.cotizacion_model.referencia_cliente else None
                    # Añadir verificación por si el objeto no existe
                    if cliente_id_para_modelo is None:
                         st.error("Error: No se pudo obtener el ID del cliente de la cotización cargada.")
                         return # Salir si no podemos obtener el ID
                    if referencia_id_para_modelo is None:
                        st.error("Error: No se pudo obtener el ID de la referencia de la cotización cargada.")
                        # Considerar si se debe salir aquí también, o si es recuperable
                        # return
                        
                    print(f"DEBUG (Edición): Usando cliente_id={cliente_id_para_modelo}, referencia_id={referencia_id_para_modelo}")
                else:
                    cliente_id_para_modelo = cliente_seleccionado[0] if cliente_seleccionado else None
                    referencia_id_para_modelo = None # Para nuevas cotizaciones, la referencia se crea al guardar
                    print(f"DEBUG (Nuevo): Usando cliente_id={cliente_id_para_modelo}, referencia_id={referencia_id_para_modelo}")
                # --------------------------------------------------------------------------
                
                st.session_state.cotizacion_model = crear_o_actualizar_cotizacion_model(
                    cliente_id=cliente_id_para_modelo, # Usar la variable determinada arriba
                    referencia_id=referencia_id_para_modelo, # Usar la variable determinada arriba
                    material_id=material_seleccionado[0],
                    acabado_id=acabado_seleccionado[0] if not es_manga else 10,
                    num_tintas=num_tintas,
                    num_rollos=num_rollos,
                    consecutivo=st.session_state.consecutivo,
                    es_manga=es_manga,
                    tipo_grafado=tipo_grafado_seleccionado.nombre if es_manga else None,
                    valor_troquel=st.session_state.datos_cotizacion.get('valor_troquel', 0),
                    valor_plancha_separado=st.session_state.datos_cotizacion.get('valor_plancha_separado', 0),
                    pistas=pistas,
                    avance=avance,
                    ancho=ancho,
                    planchas_por_separado=planchas_por_separado == "Sí",
                    troquel_existe=troquel_existe == "Sí",
                    cliente_nombre=cliente_seleccionado[1],
                    referencia_descripcion=st.session_state.referencia_descripcion,
                    tipo_producto_id=tipo_producto_seleccionado[0],
                    comercial_id=comercial_id,
                    escalas_resultados=resultados,
                    cotizacion_existente=st.session_state.cotizacion_model if modo_edicion else None,
                    forma_pago_id=st.session_state.forma_pago_id
                )
                
                # Marcar que se ha calculado la cotización
                st.session_state.cotizacion_calculada = True
                st.session_state.cotizacion_guardada = False
                
                # --- DEBUG: Verificar perfil ANTES del rerun ---
                print("DEBUG: Verificando st.session_state.user_profile ANTES del rerun:")
                print(st.session_state.get('user_profile'))
                # --- FIN DEBUG ---
                
                # Pasar automáticamente a la página de cotización
                st.session_state.paso_actual = 'cotizacion'
                st.rerun()
                
        except Exception as e:
            st.error(f"Error en el cálculo: {str(e)}")
            st.error(traceback.format_exc())
            return
                
            # Continuando con el resto del código después del try-except
            # Verificar si hay errores en el reporte
            if 'error' in reporte_lito:
                st.error(f"Error: {reporte_lito['error']}")
                if 'detalles' in reporte_lito:
                    st.error(f"Detalles: {reporte_lito['detalles']}")
                return
    
    # Mostrar resultados de la última cotización si existen
    if st.session_state.resultados is not None and st.session_state.paso_actual == 'calculadora':
        st.subheader("Última cotización calculada")
        es_manga = st.session_state.datos_cotizacion.get('es_manga', False) if st.session_state.datos_cotizacion else False
        st.dataframe(
            generar_tabla_resultados(st.session_state.resultados, es_manga),
            hide_index=True, 
            use_container_width=True
        )
        
        # Botón para ver la cotización completa
        st.button("Ver detalles de la cotización", 
                 on_click=lambda: setattr(st.session_state, 'paso_actual', 'cotizacion'))

def mostrar_cotizacion():
    """Muestra la página de detalles de la cotización, guardado y descarga"""
    if not st.session_state.cotizacion_calculada:
        st.warning("No hay cotización calculada. Por favor calcule una cotización primero.")
        st.button("Volver a la calculadora", 
                 on_click=lambda: setattr(st.session_state, 'paso_actual', 'calculadora'))
        return
    
    try:
        print("\n=== DEBUG MOSTRAR COTIZACIÓN ===")
        
        # Obtener datos de la cotización
        cotizacion = st.session_state.get('cotizacion_model')
        if not cotizacion:
            print("No hay cotización en session_state")
            return
        
        print("\nDatos de cotización:")
        print(f"  Cliente: {cotizacion.cliente_id}")
        print(f"  Referencia: {cotizacion.referencia_cliente_id}")
        
        # Mostrar escalas si existen
        if hasattr(cotizacion, 'escalas') and cotizacion.escalas:
            print(f"  Número de escalas: {len(cotizacion.escalas)}")
            for e in cotizacion.escalas:
                if isinstance(e, dict):
                    # Si es un diccionario, acceder a las claves
                    print(f"  Escala: {e.get('escala')}, Valor unidad: {e.get('valor_unidad')}")
                else:
                    # Si es un objeto Escala, acceder a los atributos
                    print(f"  Escala: {e.escala}, Valor unidad: {e.valor_unidad}")
        else:
            print("  No hay escalas")
        
        # Resto del código de mostrar_cotizacion...
        
    except Exception as e:
        print(f"Error detallado: {str(e)}")
        traceback.print_exc()
        st.error(f"Error al mostrar la cotización: {str(e)}")
        return
    
    st.title("Detalles de la Cotización")
    
    # Mostrar mensajes guardados
    for msg_type, msg in st.session_state.mensajes:
        if msg_type == "success":
            st.success(msg)
        elif msg_type == "error":
            st.error(msg)
    
    # Limpiar mensajes después de mostrarlos
    st.session_state.mensajes = []
    
    # Mostrar tabla de resultados
    st.subheader("Tabla de Resultados")
    tabla_resultados = generar_tabla_resultados(
        st.session_state.resultados, 
        st.session_state.datos_cotizacion.get('es_manga', False)
    )
    st.dataframe(tabla_resultados, hide_index=True, use_container_width=True)
    
    # Mostrar información técnica directamente en la página
    st.subheader("Información Técnica para Impresión")
    informe_tecnico_str = st.session_state.get("informe_tecnico", "Aún no generado. Guarde la cotización primero.")
    # Usar st.markdown para interpretar el formato Markdown
    st.markdown(informe_tecnico_str)
    
    # Acciones de la cotización
    st.subheader("Acciones")
    col1, col2, col3, col4 = st.columns(4) # Añadir una columna más para el nuevo botón
    
    with col1:
        # Botón para guardar cotización
        if not st.session_state.cotizacion_guardada:
            if st.button("Guardar Cotización", key="guardar_cotizacion", type="primary"):
                # Pass the cotization from session state
                success, message = guardar_cotizacion(st.session_state.cotizacion_model, st.session_state.db)
                if success:
                    st.success(f"✅ {message}")
                    # --- NUEVO: Invalidar PDF guardado para forzar regeneración ---
                    st.session_state.pdf_data = None 
                    st.session_state.materiales_pdf_data = None
                    # -------------------------------------------------------------
                    # Forzar rerun para actualizar estado y mostrar botón de descarga con PDF actualizado
                    st.rerun()
                else:
                    st.error(message)
        else:
            st.success("Cotización guardada ✓")
    
    with col2:
        # Botón para descargar PDF Cotización (Cliente)
        if st.session_state.cotizacion_guardada:
            # Si el PDF no está en memoria, intentar generarlo
            if 'pdf_data' not in st.session_state or st.session_state.pdf_data is None:
                try:
                    db = DBManager(st.session_state.supabase)
                    
                    # Verificar que tenemos un ID de cotización válido
                    cotizacion_id = st.session_state.get('cotizacion_id')
                    if not cotizacion_id:
                        # Si no tenemos ID pero tenemos el modelo, intentar obtener el ID del modelo
                        cotizacion_model = st.session_state.get('cotizacion_model')
                        if cotizacion_model and hasattr(cotizacion_model, 'id'):
                            cotizacion_id = cotizacion_model.id
                            
                    if not cotizacion_id:
                        raise ValueError("No se encontró un ID de cotización válido para generar el PDF")
                        
                    print(f"Generando PDF para cotización ID: {cotizacion_id}")
                    datos_completos = db.get_datos_completos_cotizacion(cotizacion_id)
                    if datos_completos:
                        pdf_gen = CotizacionPDF()
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                            # Recuperar informe técnico para el PDF
                            # informe_tecnico_pdf = st.session_state.get("informe_tecnico", "Informe técnico no disponible.")
                            pdf_gen.generar_pdf(datos_completos, tmp_file.name) # <--- Argumento eliminado
                            with open(tmp_file.name, "rb") as pdf_file:
                                st.session_state.pdf_data = pdf_file.read()
                            print(f"PDF regenerado y guardado en memoria: {len(st.session_state.pdf_data)} bytes")
                    else:
                        raise ValueError("No se pudieron obtener los datos completos de la cotización")
                except ValueError as ve:
                    print(f"Error al generar PDF: {str(ve)}")
                    st.error(str(ve))
                except Exception as e:
                    print(f"Error regenerando PDF: {str(e)}")
                    traceback.print_exc()
                    st.error(f"Error al generar el PDF: {str(e)}")
            
            if st.session_state.pdf_data is not None:
                # Obtener el ID de cotización para el nombre del archivo
                cotizacion_id = st.session_state.get('cotizacion_id') or getattr(st.session_state.get('cotizacion_model'), 'id', 'sin_id')
                st.download_button(
                    label="Descargar Cotización (PDF)",
                    data=st.session_state.pdf_data,
                    file_name=f"cotizacion_{cotizacion_id}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
            else:
                st.error("No se pudo generar el PDF. Por favor, intente guardar la cotización nuevamente.")

            # Generar y descargar PDF de Información de Materiales
            if 'materiales_pdf_data' not in st.session_state or st.session_state.materiales_pdf_data is None:
                try:
                    # --- INICIO: Modificación para cargar datos frescos ---
                    db = DBManager(st.session_state.supabase)
                    cotizacion_id = st.session_state.get('cotizacion_id') or getattr(st.session_state.get('cotizacion_model'), 'id', None)

                    if not cotizacion_id:
                        st.error("No se pudo obtener el ID de la cotización para generar el PDF de materiales.")
                        st.session_state.materiales_pdf_data = None
                        # Considerar si salir aquí con 'return' o continuar puede ser mejor
                        raise ValueError("ID de cotización no encontrado") # Lanza error para que el bloque except lo maneje

                    print(f"Obteniendo datos frescos para PDF Materiales - Cotización ID: {cotizacion_id}")
                    # Usar obtener_cotizacion para traer el objeto completo y actualizado
                    cotizacion_actualizada = db.obtener_cotizacion(cotizacion_id)

                    if not cotizacion_actualizada:
                        st.error(f"No se pudo recuperar la cotización actualizada (ID: {cotizacion_id}) para generar el PDF de materiales.")
                        st.session_state.materiales_pdf_data = None
                        raise ValueError("Cotización actualizada no encontrada")

                    # Extraer datos necesarios explícitamente, similar a la generación del Markdown
                    identificador_final = cotizacion_actualizada.identificador or "N/A"
                    consecutivo_final = cotizacion_actualizada.numero_cotizacion or "N/A"
                    descripcion_final = "N/A"
                    nombre_cliente_final = "N/A"
                    cliente_dict_final = {}
                    comercial_dict_final = {}
                    nombre_comercial_final = "N/A" # Variable para el nombre dentro del PDF

                    if cotizacion_actualizada.referencia_cliente:
                        referencia_obj = cotizacion_actualizada.referencia_cliente # Ya viene cargado
                        descripcion_final = referencia_obj.descripcion or "N/A"
                        if referencia_obj.cliente:
                            cliente_obj = referencia_obj.cliente # Ya viene cargado
                            nombre_cliente_final = cliente_obj.nombre or "N/A"
                            cliente_dict_final = {
                                'id': cliente_obj.id,
                                'nombre': cliente_obj.nombre,
                                'codigo': cliente_obj.codigo,
                                'persona_contacto': cliente_obj.persona_contacto,
                                'correo_electronico': cliente_obj.correo_electronico,
                                'telefono': cliente_obj.telefono
                            }
                        if referencia_obj.perfil: # 'perfil' contiene los datos del comercial
                            comercial_dict_final = referencia_obj.perfil
                            nombre_comercial_final = comercial_dict_final.get('nombre', "N/A")

                    # Extraer información del material y acabado (asegurando que sean diccionarios para el PDF)
                    material_obj = cotizacion_actualizada.material
                    acabado_obj = cotizacion_actualizada.acabado
                    material_dict_final = material_obj.__dict__ if material_obj else {}
                    acabado_dict_final = acabado_obj.__dict__ if acabado_obj else {}

                    # Obtener cálculos adicionales si es necesario (ej: valor_material, ancho, avance)
                    # Esto podría venir de `db.get_calculos_escala_cotizacion` o de `cotizacion_actualizada` si los campos existen
                    calculos = db.get_calculos_escala_cotizacion(cotizacion_id)
                    valor_material_final = calculos.get('valor_material', 0) if calculos else 0
                    valor_acabado_final = calculos.get('valor_acabado', 0) if calculos else 0
                    valor_troquel_final = calculos.get('valor_troquel', 0) if calculos else 0
                    ancho_final = calculos.get('ancho', 0) if calculos else cotizacion_actualizada.ancho or 0
                    avance_final = calculos.get('avance', 0) if calculos else cotizacion_actualizada.avance or 0
                    pistas_final = calculos.get('numero_pistas', 0) if calculos else cotizacion_actualizada.numero_pistas or 0

                    # Obtener resultados de las escalas
                    resultados_finales = []
                    if cotizacion_actualizada.escalas:
                         resultados_finales = [{
                            'escala': esc.escala,
                            'valor_unidad': esc.valor_unidad,
                            'metros': esc.metros,
                            'tiempo_horas': esc.tiempo_horas,
                            'montaje': esc.montaje,
                            'mo_y_maq': esc.mo_y_maq,
                            'tintas': esc.tintas,
                            'papel_lam': esc.papel_lam,
                            'desperdicio': esc.desperdicio_total # Usar el campo correcto
                         } for esc in cotizacion_actualizada.escalas]

                    # --- FIN: Modificación para cargar datos frescos ---

                    # Debug logging for datos_cotizacion (ahora usando datos frescos)
                    print("\n=== DEBUG DATOS FRESCOS COTIZACIÓN PDF MATERIALES ===")
                    print(f"ID: {cotizacion_id}")
                    print(f"Identificador: {identificador_final}")
                    print(f"Cliente: {nombre_cliente_final}")
                    print(f"Comercial: {nombre_comercial_final}")
                    print(f"Material Dict: {material_dict_final}")
                    print(f"Acabado Dict: {acabado_dict_final}")
                    print(f"Ancho: {ancho_final}, Avance: {avance_final}, Pistas: {pistas_final}")
                    print("==================================================\n")

                    # Preparar datos específicos para el PDF de materiales usando los datos frescos
                    datos_materiales = {
                        'identificador': identificador_final,
                        'consecutivo': consecutivo_final,
                        'nombre_cliente': nombre_cliente_final, # Usar el nombre extraído
                        'descripcion': descripcion_final, # Usar la descripción extraída
                        'cliente': cliente_dict_final, # Pasar el diccionario ya construido
                        'comercial': comercial_dict_final, # Pasar el diccionario ya construido
                        # --- Datos del objeto cotizacion_actualizada ---
                        'material': material_dict_final, # Usar el diccionario preparado
                        'acabado': acabado_dict_final, # Usar el diccionario preparado
                        'num_tintas': cotizacion_actualizada.num_tintas,
                        'num_rollos': cotizacion_actualizada.num_paquetes_rollos,
                        'es_manga': cotizacion_actualizada.es_manga,
                        'tipo_grafado': cotizacion_actualizada.tipo_grafado_id, # Pasar el ID
                        'valor_plancha': getattr(cotizacion_actualizada, 'valor_plancha', 0), # Obtener si existe
                        'valor_plancha_separado': cotizacion_actualizada.valor_plancha_separado or 0,
                        # --- Datos de cálculos ---
                        'valor_material': valor_material_final,
                        'valor_acabado': valor_acabado_final,
                        'valor_troquel': valor_troquel_final,
                        'ancho': ancho_final,
                        'avance': avance_final,
                        'numero_pistas': pistas_final,
                        'resultados': resultados_finales, # Usar los resultados extraídos
                        # --- NUEVO: Agregar flags de plancha y troquel ---
                        'planchas_x_separado': cotizacion_actualizada.planchas_x_separado,
                        'existe_troquel': cotizacion_actualizada.existe_troquel,
                        # --- Valores fijos o por defecto (mantener como antes) ---
                        'gap_avance': 7.95,
                        'area_etiqueta': ancho_final * avance_final,
                        'unidad_z': 102.0,
                    }

                    # Debug logging
                    print("\n=== DEBUG DATOS MATERIALES PDF (FINAL) ===")
                    print(f"Material type: {type(datos_materiales.get('material'))}")
                    print(f"Material: {datos_materiales.get('material')}")
                    print(f"Acabado type: {type(datos_materiales.get('acabado'))}")
                    print(f"Acabado: {datos_materiales.get('acabado')}")
                    print("=================================\n")

                    # Generar el PDF de materiales
                    materiales_pdf_gen = MaterialesPDF()
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                        print(f"\n=== DEBUG PDF MATERIALES ===")
                        print(f"Ruta del archivo temporal: {tmp_file.name}")
                        print(f"Datos para PDF: {list(datos_materiales.keys())}")
                        
                        # Extensive logging of key data
                        for key in ['material', 'acabado', 'resultados']:
                            print(f"{key.capitalize()} data: {datos_materiales.get(key)}")
                        
                        try:
                            # Generate PDF with more detailed error handling
                            pdf_generated = materiales_pdf_gen.generar_pdf(datos_materiales, tmp_file.name)
                            
                            print(f"PDF generation result: {pdf_generated}")
                            
                            # Reopen the file to read its contents
                            with open(tmp_file.name, 'rb') as pdf_file:
                                pdf_content = pdf_file.read()
                                pdf_size = len(pdf_content)
                            
                            print(f"PDF file size: {pdf_size} bytes")
                            
                            if pdf_size == 0:
                                print("WARNING: Generated PDF is 0 bytes")
                                st.error("No se pudo generar el PDF de materiales. El archivo está vacío.")
                                st.session_state.materiales_pdf_data = None
                            else:
                                st.session_state.materiales_pdf_data = pdf_content
                                print(f"PDF regenerado y guardado en memoria: {pdf_size} bytes")
                        
                        except Exception as e:
                            print(f"Detailed error generating PDF de materiales: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            st.error(f"Error al generar el PDF de materiales: {str(e)}")
                            st.session_state.materiales_pdf_data = None
                except Exception as e:
                    print(f"Error generando PDF de materiales: {str(e)}")
                    traceback.print_exc()
                    st.error(f"Error al generar el PDF de materiales: {str(e)}")
            
            if st.session_state.get('materiales_pdf_data') is not None:
                cotizacion_id = st.session_state.get('cotizacion_id') or getattr(st.session_state.get('cotizacion_model'), 'id', 'sin_id')
                st.download_button(
                    label="Descargar Información Materiales (PDF)",
                    data=st.session_state.materiales_pdf_data,
                    file_name=f"materiales_{cotizacion_id}.pdf",
                    mime="application/pdf",
                    key="btn_materiales_pdf"
                )

    with col3:
        # Botón para descargar Informe Técnico (.md)
        if st.session_state.cotizacion_guardada and "informe_tecnico" in st.session_state:
            informe_tecnico_data = st.session_state.informe_tecnico
            if informe_tecnico_data and not informe_tecnico_data.startswith("Error"):
                cotizacion_id_inf = st.session_state.get('cotizacion_id', 'sin_id')
                st.download_button(
                    label="Descargar Informe Técnico (.md)",
                    data=informe_tecnico_data.encode('utf-8'), # Codificar a bytes
                    file_name=f"informe_tecnico_{cotizacion_id_inf}.md",
                    mime="text/markdown",
                    type="secondary" # Usar tipo secundario para diferenciarlo
                )
            else:
                st.warning("Informe técnico no disponible o contiene errores.")
        elif st.session_state.cotizacion_guardada:
             st.warning("Informe técnico aún no generado.") # Mensaje si la cotización está guardada pero el informe no

    with col4: # Usar la nueva cuarta columna
        # Botón para nueva cotización
        if st.button("Calcular Nueva Cotización", type="primary"):
            # Guardar variables de autenticación
            auth_vars = {
                'authentication_status': st.session_state.get('authentication_status'),
                'username': st.session_state.get('username'),
                'name': st.session_state.get('name'),
                'role': st.session_state.get('role'),
                'user_id': st.session_state.get('user_id'),
                'auth_manager': st.session_state.get('auth_manager'),
                'supabase': st.session_state.get('supabase')
            }
            
            # Limpiar todos los estados
            for key in list(st.session_state.keys()):
                del st.session_state[key]
                
            # Restaurar variables de autenticación
            for key, value in auth_vars.items():
                if value is not None:
                    st.session_state[key] = value
                    
            st.session_state.paso_actual = 'calculadora'
            st.rerun()
                    
        # Botón para calcular una nueva cotización después de guardar
        if st.session_state.cotizacion_guardada:
            if st.button("Calcular Nueva Cotización", key="nueva_cotizacion_post_guardado", type="primary"):
                # Guardar variables de autenticación y mensajes
                auth_vars = {
                    'authentication_status': st.session_state.get('authentication_status'),
                    'username': st.session_state.get('username'),
                    'name': st.session_state.get('name'),
                    'role': st.session_state.get('role'),
                    'user_id': st.session_state.get('user_id'),
                    'auth_manager': st.session_state.get('auth_manager'),
                    'supabase': st.session_state.get('supabase'),
                    'messages': st.session_state.get('messages', [])
                }
                
                # Limpiar session state
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                
                # Restaurar variables de autenticación y mensajes
                for key, value in auth_vars.items():
                    if value is not None:
                        st.session_state[key] = value
                
                st.session_state.paso_actual = 'calculadora'
                st.rerun()

def crear_o_actualizar_cotizacion_model(
    cliente_id, 
    referencia_id, 
    material_id, 
    acabado_id, 
    num_tintas, 
    num_rollos, 
    consecutivo, 
    es_manga, 
    tipo_grafado, 
    valor_troquel, 
    valor_plancha_separado, 
    pistas, 
    avance,
    ancho,
    planchas_por_separado, 
    troquel_existe, 
    cliente_nombre, 
    referencia_descripcion, 
    tipo_producto_id, 
    comercial_id=None, 
    escalas_resultados=None,
    cotizacion_existente=None,
    forma_pago_id: Optional[int] = None
):
    """
    Crea o actualiza un modelo de cotización con los datos proporcionados.
    """
    print("\n=== DEBUG CREAR_O_ACTUALIZAR_COTIZACION_MODEL ===")
    print(f"tipo_producto_id recibido: {tipo_producto_id}")
    print(f"comercial_id recibido: {comercial_id}")
    print(f"referencia_descripcion recibida: {referencia_descripcion}")
    print(f"forma_pago_id recibido: {forma_pago_id}")
    
    try:
        if cotizacion_existente:
            print("Actualizando cotización existente...")
            cotizacion = cotizacion_existente
        else:
            print("Creando nueva cotización...")
            cotizacion = Cotizacion()
            cotizacion.id = None
            cotizacion.estado_id = 1  # Estado por defecto
            cotizacion.forma_pago_id = forma_pago_id if forma_pago_id is not None else st.session_state.get('forma_pago_id', 1)
        
        # Asegurar que forma_pago_id tenga un valor válido
        if forma_pago_id is None:
            forma_pago_id = st.session_state.get('forma_pago_id', 1)
            print(f"Usando forma_pago_id desde session_state: {forma_pago_id}")
        
        # Actualizar campos básicos
        cotizacion.cliente_id = cliente_id
        # Para nuevas cotizaciones, referencia_cliente_id se establecerá al guardar
        if cotizacion_existente:
            cotizacion.referencia_cliente_id = referencia_id
        cotizacion.material_id = material_id
        cotizacion.acabado_id = acabado_id
        cotizacion.num_tintas = num_tintas
        cotizacion.num_rollos = num_rollos
        cotizacion.etiquetas_por_rollo = num_rollos
        cotizacion.unidades_por_rollo = num_rollos
        cotizacion.consecutivo = consecutivo
        cotizacion.es_manga = es_manga
        cotizacion.tipo_grafado = tipo_grafado
        cotizacion.valor_troquel = valor_troquel
        cotizacion.valor_plancha_separado = valor_plancha_separado
        cotizacion.planchas_x_separado = planchas_por_separado
        cotizacion.troquel_existe = troquel_existe
        cotizacion.nombre_cliente = cliente_nombre
        cotizacion.descripcion = referencia_descripcion
        cotizacion.comercial_id = comercial_id
        cotizacion.tipo_producto_id = tipo_producto_id
        cotizacion.numero_pistas = pistas
        cotizacion.avance = avance
        cotizacion.ancho = ancho
        # cotizacion.forma_pago_id = forma_pago_id  # Asignar forma_pago_id <-- This line was overwriting the default
        
        # Ensure the final assignment uses the value that includes the default
        cotizacion.forma_pago_id = forma_pago_id if forma_pago_id is not None else st.session_state.get('forma_pago_id', 1)
        
        # Procesar escalas si existen
        if escalas_resultados:
            print(f"\nProcesando {len(escalas_resultados)} escalas:")
            cotizacion.escalas = []
            for resultado in escalas_resultados:
                print(f"\nDatos de escala recibidos:")
                for k, v in resultado.items():
                    print(f"  {k}: {v}")
                
                # Crear objeto Escala
                escala = Escala(
                    escala=resultado['escala'],
                    valor_unidad=resultado['valor_unidad'],
                    metros=resultado['metros'],
                    tiempo_horas=resultado['tiempo_horas'],
                    montaje=resultado['montaje'],
                    mo_y_maq=resultado['mo_y_maq'],
                    tintas=resultado['tintas'],
                    papel_lam=resultado['papel_lam'],
                    desperdicio_total=resultado['desperdicio']
                )
                print(f"Escala creada: {escala.escala}, Valor unidad: {escala.valor_unidad}")
                cotizacion.escalas.append(escala)
            
            print(f"\nTotal de escalas agregadas al modelo: {len(cotizacion.escalas)}")
        else:
            print("\nNo hay escalas para procesar")
        
        print("\nDatos finales de la cotización:")
        print(f"  Cliente ID: {cotizacion.cliente_id}")
        print(f"  Referencia descripción: {cotizacion.descripcion}")
        print(f"  Tipo Producto ID: {cotizacion.tipo_producto_id}")
        print(f"  Comercial ID: {cotizacion.comercial_id}")
        print(f"  Forma Pago ID: {cotizacion.forma_pago_id}") # Debug forma pago ID
        if cotizacion.escalas:
            print(f"  Número de escalas: {len(cotizacion.escalas)}")
            for e in cotizacion.escalas:
                print(f"    - Escala: {e.escala}, Valor unidad: {e.valor_unidad}")
        
        # --- ADD THIS LINE: Set the ID on the model --- 
        cotizacion.tipo_grafado_id = st.session_state.db.get_tipos_grafado_id_by_name(tipo_grafado) if es_manga and tipo_grafado else None
        # --- END ADD --- 
        
        return cotizacion
        
    except Exception as e:
        print(f"Error en crear_o_actualizar_cotizacion_model: {str(e)}")
        traceback.print_exc()
        raise

def print_cotizacion_fields():
    """Imprime todos los campos disponibles en la clase Cotizacion para depuración."""
    print("\n=== ESTRUCTURA DE LA CLASE COTIZACION ===")
    try:
        # Obtener todos los atributos y tipos anotados
        if hasattr(Cotizacion, '__annotations__'):
            for field, field_type in Cotizacion.__annotations__.items():
                print(f"{field}: {field_type}")
        else:
            # Alternativa si no hay anotaciones
            print("No se encontraron anotaciones de tipo. Usando inspect:")
            for name, value in inspect.getmembers(Cotizacion):
                if not name.startswith('_'):  # Excluir atributos privados
                    print(f"{name}: {type(value)}")
    except Exception as e:
        print(f"Error al obtener la estructura de Cotizacion: {e}")
    print("=======================================\n")

def limpiar_estado():
    st.session_state.datos_cotizacion = None
    st.session_state.resultados = None
    st.session_state.cliente_seleccionado = None
    st.session_state.referencia_seleccionada = None
    st.session_state.material_seleccionado = None
    st.session_state.acabado_seleccionado = None
    st.session_state.comercial_seleccionado = None
    # Asegurar que forma_pago_id tenga un valor por defecto al limpiar el estado
    st.session_state.forma_pago_id = 1

def guardar_cotizacion(cotizacion, db):
    """Guarda una cotización en la base de datos"""
    try:
        print("\n=== DEBUG GUARDAR COTIZACIÓN ===")
        print(f"Datos de cotización:")
        print(f"  Cliente: {cotizacion.cliente_id}")
        print(f"  Forma Pago ID: {cotizacion.forma_pago_id}") # Debug forma pago
        
        # Asegurar que forma_pago_id tenga un valor válido
        if not hasattr(cotizacion, 'forma_pago_id') or cotizacion.forma_pago_id is None:
            forma_pago_id = st.session_state.get('forma_pago_id', 1)
            print(f"Estableciendo forma_pago_id a {forma_pago_id}")
            cotizacion.forma_pago_id = forma_pago_id
        
        # Si es una actualización, usar la referencia existente
        if cotizacion.id:
            print(f"  Referencia existente: {cotizacion.referencia_cliente_id}")
        else:
            # Crear nueva referencia
            print("Creando nueva referencia...")
            
            # --- Obtener user_id directamente de session_state --- 
            current_user_id = st.session_state.get('user_id')
            if not current_user_id:
                 # Manejar error: no se puede crear referencia sin ID de comercial
                 return (False, "Error crítico: No se encontró el ID del usuario en la sesión.")
            
            print(f"DEBUG: ID del usuario actual para id_usuario: {current_user_id}") # Cambiado id_comercial a id_usuario
            
            nueva_referencia = ReferenciaCliente(
                cliente_id=cotizacion.cliente_id,
                descripcion=cotizacion.descripcion,
                id_usuario=current_user_id # Corrected keyword argument to id_usuario
            )
            
            try:
                referencia_guardada = db.crear_referencia(nueva_referencia)
                if not referencia_guardada:
                    return (False, "Error al crear la referencia")
                
                cotizacion.referencia_cliente_id = referencia_guardada.id
                print(f"  Nueva referencia creada: {referencia_guardada.id}")
            except ValueError as ve:
                # Devolver directamente el mensaje de error de la excepción
                return (False, str(ve))
            except Exception as e:
                # Manejar otros errores inesperados al crear la referencia
                error_msg = f"❌ Error inesperado al crear la referencia asociada: {str(e)}"
                print(error_msg)
                traceback.print_exc()
                return (False, error_msg)
        
        # Obtener el número de escalas
        num_escalas = len(cotizacion.escalas) if hasattr(cotizacion, 'escalas') else 0
        print(f"  Número de escalas: {num_escalas}")
        
        if hasattr(cotizacion, 'escalas'):
            for escala in cotizacion.escalas:
                print(f"  Escala: {escala.escala}, Valor unidad: {escala.valor_unidad}")
        
        # Preparar datos para la base de datos
        datos_cotizacion = {
            'referencia_cliente_id': cotizacion.referencia_cliente_id,
            'material_id': cotizacion.material_id,
            'acabado_id': cotizacion.acabado_id,
            'num_tintas': cotizacion.num_tintas,
            'num_paquetes_rollos': cotizacion.num_rollos,
            'es_manga': cotizacion.es_manga,
            'tipo_grafado_id': cotizacion.tipo_grafado_id,
            'valor_troquel': cotizacion.valor_troquel,
            'valor_plancha_separado': cotizacion.valor_plancha_separado,
            'estado_id': cotizacion.estado_id,
            'planchas_x_separado': cotizacion.planchas_x_separado,
            'existe_troquel': cotizacion.existe_troquel,
            'numero_pistas': cotizacion.numero_pistas,
            'tipo_producto_id': cotizacion.tipo_producto_id,
            'es_recotizacion': cotizacion.es_recotizacion,
            'ancho': cotizacion.ancho,
            'avance': cotizacion.avance,
            'fecha_creacion': datetime.now().isoformat(),
            'identificador': cotizacion.identificador,
            'colores_tinta': getattr(cotizacion, 'colores_tinta', None),
            'forma_pago_id': cotizacion.forma_pago_id
        }
        
        # Si es una actualización, mantener el número de cotización existente
        if cotizacion.id and hasattr(cotizacion, 'numero_cotizacion') and cotizacion.numero_cotizacion is not None:
            datos_cotizacion['numero_cotizacion'] = int(cotizacion.numero_cotizacion)
        # Si es nueva, no asignamos número de cotización para que la BD lo haga automáticamente
        else:
            # Ya no generamos aquí el número de cotización
            # La base de datos lo asignará usando la secuencia
            print("Nueva cotización: el número será asignado por la base de datos")
        
        # Limpiar datos antes de enviar
        datos_limpios = db._limpiar_datos(datos_cotizacion)

        # --- Añadir id_usuario a los datos limpios ANTES de llamar a crear/actualizar --- 
        current_user_id = st.session_state.get('user_id')
        if not current_user_id:
            # Debería haberse capturado antes al crear la referencia, pero doble check
            return (False, "Error crítico: No se encontró el ID del usuario en la sesión para guardar la cotización.")
        datos_limpios['id_usuario'] = current_user_id
        print(f"Añadiendo id_usuario={current_user_id} a datos_limpios para guardar/actualizar.")
        # --- Fin Añadir id_usuario ---

        # --- Añadir campos de cálculo a datos_limpios SI es una nueva cotización ---
        if not cotizacion.id: # Asegurar que solo se añaden para nuevas cotizaciones
            try:
                # Obtener datos del cálculo desde session_state (donde se guardan los resultados del cálculo)
                datos_calculo_state = st.session_state.get('datos_cotizacion', {})
                print(f"Recuperando datos de cálculo desde st.session_state para añadir a datos_limpios: {datos_calculo_state}")

                # Campos necesarios para la tabla calculos_escala_cotizacion
                campos_calculo = [
                    'valor_material', 'valor_plancha', 'valor_acabado', 'valor_troquel',
                    'rentabilidad', 'avance', 'ancho', 'unidad_z_dientes',
                    'existe_troquel', 'planchas_x_separado', 'num_tintas',
                    'numero_pistas', 'num_paquetes_rollos', 'tipo_producto_id',
                    'tipo_grafado_id'
                ]

                # Añadir los campos a datos_limpios si existen en datos_calculo_state
                for campo in campos_calculo:
                    if campo in datos_calculo_state:
                        valor = datos_calculo_state[campo]
                        # Ajustar el nombre del campo para valor_plancha
                        if campo == 'valor_plancha_para_calculo':
                            datos_limpios['valor_plancha'] = valor
                        else:
                            datos_limpios[campo] = valor
                        print(f"  Añadiendo campo '{campo}' con valor '{valor}' a datos_limpios")
                    else:
                        print(f"  Advertencia: Campo '{campo}' no encontrado en st.session_state['datos_cotizacion']")
                
                # Corrección específica para valor_plancha si viene como valor_plancha_para_calculo
                if 'valor_plancha_para_calculo' in datos_calculo_state:
                    datos_limpios['valor_plancha'] = datos_calculo_state['valor_plancha_para_calculo']
                    print(f"  Añadiendo campo 'valor_plancha' desde 'valor_plancha_para_calculo' con valor '{datos_limpios['valor_plancha']}'")

            except Exception as e_calc:
                print(f"Error al intentar añadir campos de cálculo a datos_limpios: {e_calc}")
                # Continuar igualmente, la función SQL podría manejarlo si los campos son opcionales

        # Si la cotización ya existe, actualizarla
        if cotizacion.id:
            print("\nActualizando cotización existente...")
            # --- DEBUG PRINT BEFORE UPDATE --- 
            print(f"DEBUG (Update): datos_limpios being passed to actualizar_cotizacion: {datos_limpios}")
            # --------------------------------
            # --- CORRECCIÓN: Pasar cotizacion.id como primer argumento --- 
            result = db.actualizar_cotizacion(cotizacion.id, datos_limpios)
            # ----------------------------------------------------------
            if not result:
                return (False, "Error al actualizar la cotización")
            
            # === REVERTIDO: No pasar cotizacion.referencia_cliente_id ===
            db.guardar_cotizacion_escalas(cotizacion.id, cotizacion.escalas)
            
            # +++ AGREGAR: Guardar/Actualizar cálculos de escala también en update +++
            try:
                # Obtener datos de cálculo más recientes (reflejando la edición actual)
                # Estos deberían estar en st.session_state.datos_cotizacion si el cálculo se rehizo
                # O en el objeto cotizacion que se pasa a esta función.
                # Vamos a priorizar el objeto cotizacion, ya que debería ser el más actualizado.

                print(f"\nDEBUG (Update): Intentando guardar cálculos para cotización {cotizacion.id}")
                datos_calculo_state = st.session_state.get('datos_cotizacion', {})
                print(f"DEBUG (Update): datos_calculo_state: {datos_calculo_state}")
                print(f"DEBUG (Update): cotizacion object: {cotizacion.__dict__}")

                # Extraer los argumentos necesarios para guardar_calculos_escala
                # Priorizar los valores del objeto 'cotizacion' ya que refleja el estado actual
                # --- CORRECCIÓN: Obtener valores de cálculo desde datos_calculo_state --- 
                success_calculos = db.guardar_calculos_escala(
                    cotizacion_id=cotizacion.id,
                    # Obtener valores de cálculo desde el diccionario del estado
                    valor_material=float(datos_calculo_state.get('valor_material', 0.0)),
                    valor_plancha=float(datos_calculo_state.get('valor_plancha_para_calculo', 0.0)),
                    valor_troquel=float(datos_calculo_state.get('valor_troquel', 0.0)),
                    rentabilidad=float(datos_calculo_state.get('rentabilidad', RENTABILIDAD_ETIQUETAS)), # Usar default si falta
                    # Obtener valores básicos desde el objeto cotizacion
                    avance=float(cotizacion.avance),
                    ancho=float(cotizacion.ancho),
                    existe_troquel=cotizacion.existe_troquel,
                    planchas_x_separado=cotizacion.planchas_x_separado,
                    num_tintas=cotizacion.num_tintas,
                    numero_pistas=cotizacion.numero_pistas,
                    num_paquetes_rollos=cotizacion.num_paquetes_rollos, # Correct attribute is num_paquetes_rollos
                    tipo_producto_id=cotizacion.tipo_producto_id,
                    tipo_grafado_id=cotizacion.tipo_grafado_id,
                    # Obtener otros valores de cálculo desde el diccionario del estado
                    valor_acabado=float(datos_calculo_state.get('valor_acabado', 0.0)),
                    unidad_z_dientes=float(datos_calculo_state.get('unidad_z_dientes', 0.0))
                )
                # --- FIN CORRECCIÓN ---
                if not success_calculos:
                     # Registrar advertencia pero no fallar toda la operación
                     st.warning("⚠️ Cotización actualizada, pero hubo un error al guardar los parámetros de cálculo.")
                     print(f"Advertencia: Falló guardar_calculos_escala para cotización {cotizacion.id} durante la actualización.")
                else:
                     print(f"✅ Cálculos de escala actualizados para cotización {cotizacion.id}")

            except Exception as e_calc_update:
                st.warning(f"⚠️ Error inesperado al guardar cálculos de escala durante la actualización: {str(e_calc_update)}")
                print(f"Error detallado guardando cálculos escala (update): {traceback.format_exc()}")
            # +++ FIN AGREGAR +++

            print("Cotización actualizada exitosamente")
            st.session_state.cotizacion_guardada = True
            st.session_state.cotizacion_id = cotizacion.id
            
            return (True, "Cotización actualizada exitosamente")
            
        # Si es una nueva cotización, crearla
        else:
            print("\nCreando nueva cotización...")
            # --- DEBUG PRINT BEFORE CREATE --- 
            print(f"DEBUG (Create): cotizacion.forma_pago_id before db call: {cotizacion.forma_pago_id}")
            print(f"DEBUG (Create): datos_limpios being passed to crear_cotizacion: {datos_limpios}")
            # --------------------------------
            result = db.crear_cotizacion(datos_limpios)
            if not result:
                return (False, "Error al crear la cotización")
            
            print(f"Resultado de crear_cotizacion: {result}")
            
            # Extraer el ID de la cotización del resultado
            cotizacion_id = None
            if isinstance(result, dict):
                cotizacion_id = result.get('id')
            elif hasattr(result, 'id'):
                cotizacion_id = result.id
            
            if not cotizacion_id:
                print("Error: No se pudo obtener el ID de la cotización creada")
                print(f"Tipo de resultado: {type(result)}")
                print(f"Contenido del resultado: {result}")
                return (False, "Error: No se pudo obtener el ID de la cotización creada")
            
            print(f"ID de cotización creada: {cotizacion_id}")
            
            # Guardar las escalas
            if hasattr(cotizacion, 'escalas') and cotizacion.escalas:
                print("\nGuardando escalas...")
                if not db.guardar_cotizacion_escalas(cotizacion_id, cotizacion.escalas):
                    return (False, "⚠️ La cotización se guardó, pero hubo un error al guardar las escalas")
            
            # --- Generar y guardar informe técnico --- 
            try:
                # Recuperar datos necesarios del session_state o del objeto cotizacion
                datos_calculo = st.session_state.get('datos_cotizacion', {})
                reporte_lito = st.session_state.get('reporte_lito', {})
                reporte_troquel = st.session_state.get('reporte_troquel', {})
                datos_entrada = st.session_state.get('datos_entrada') # Objeto DatosEscala
                
                # Obtener el identificador y otros datos del objeto cotización recién guardado/actualizado
                # Necesitamos recargar la cotización para obtener el identificador generado por la DB
                cotizacion_actualizada = db.obtener_cotizacion(cotizacion_id)
                if not cotizacion_actualizada:
                     raise ValueError("No se pudo recuperar la cotización recién guardada para generar el informe.")
                     
                identificador_final = cotizacion_actualizada.identificador
                cliente_obj = db.get_cliente(cotizacion_actualizada.referencia_cliente.cliente_id) if cotizacion_actualizada.referencia_cliente else None
                referencia_obj = db.get_referencia_cliente(cotizacion_actualizada.referencia_cliente_id)
                # --- FIX: Use get_perfil and the correct user ID field --- 
                comercial_obj = db.get_perfil(cotizacion_actualizada.referencia_cliente.id_usuario) if cotizacion_actualizada.referencia_cliente else None
                
                nombre_cliente_final = cliente_obj.nombre if cliente_obj else "N/A"
                referencia_final = referencia_obj.descripcion if referencia_obj else "N/A"
                nombre_comercial_final = comercial_obj.get('nombre') if comercial_obj else "N/A"

                informe_tecnico_str = generar_informe_tecnico(
                    datos_entrada=datos_entrada,
                    resultados=st.session_state.get('resultados', []),
                    reporte_lito=reporte_lito,
                    num_tintas=cotizacion_actualizada.num_tintas,
                    valor_plancha=datos_calculo.get('valor_plancha_para_calculo', 0.0),
                    valor_material=datos_calculo.get('valor_material', 0.0),
                    valor_acabado=datos_calculo.get('valor_acabado', 0.0),
                    reporte_troquel=reporte_troquel,
                    valor_plancha_separado=cotizacion_actualizada.valor_plancha_separado,
                    es_manga=cotizacion_actualizada.es_manga,
                    identificador=identificador_final,
                    nombre_cliente=nombre_cliente_final,
                    referencia=referencia_final,
                    nombre_comercial=nombre_comercial_final
                )
                st.session_state.informe_tecnico = informe_tecnico_str
                print("Informe técnico generado y guardado en session_state.")
                
            except Exception as e_informe:
                print(f"Error generando informe técnico: {str(e_informe)}")
                traceback.print_exc()
                st.warning("Cotización guardada, pero no se pudo generar el informe técnico.")
                st.session_state.informe_tecnico = "Error al generar informe técnico."
            # --- Fin Generar y guardar informe técnico ---

            print("Cotización creada exitosamente")
            st.session_state.cotizacion_guardada = True
            st.session_state.cotizacion_id = cotizacion_id
            # Actualizar el ID en el modelo de cotización también
            cotizacion.id = cotizacion_id
            st.session_state.cotizacion_model = cotizacion
            
            return (True, "Cotización creada exitosamente")
            
    except Exception as e:
        print(f"Error al guardar cotización: {str(e)}")
        traceback.print_exc()
        # Mantener el mensaje genérico para otros errores
        return (False, f"❌ Error al guardar la cotización: {str(e)}")

def reset_selecciones():
    """
    Reinicia todas las selecciones en el estado de la sesión
    """
    st.session_state.cliente_seleccionado = None
    st.session_state.referencia_seleccionada = None
    st.session_state.material_seleccionado = None
    st.session_state.acabado_seleccionado = None
    st.session_state.comercial_seleccionado = None

class CotizacionModel():
    def __init__(self,
                 cliente_id: int,
                 referencia_cliente_id: int,
                 material_id: int,
                 acabado_id: Optional[int] = None,
                 comercial_id: Optional[int] = None):
        self.cliente_id = cliente_id
        self.referencia_cliente_id = referencia_cliente_id
        self.material_id = material_id
        self.acabado_id = acabado_id
        self.comercial_id = comercial_id

def inicializar_cotizacion():
    """Inicializa una nueva cotización en el session_state"""
    try:
        # Inicializar la base de datos
        db = DBManager(st.session_state.supabase)
        
        # Obtener el comercial por defecto
        comercial_default = db.get_comercial_default()
        comercial_id = comercial_default.id if comercial_default else None
        
        # Crear un nuevo modelo de cotización
        cotizacion = Cotizacion(
            cliente_id=None,
            referencia_cliente_id=None,
            material_id=None,
            acabado_id=None,
            comercial_id=comercial_id,
            tipo_producto_id=None,
            num_tintas=4,
            num_rollos=1,
            numero_cotizacion=None,  # Se generará al guardar
            es_manga=False,
            tipo_grafado_id=None,
            valor_troquel=0,
            valor_plancha_separado=0,
            estado='borrador',
            nombre_cliente=None,
            descripcion=None,
            planchas_x_separado=False,
            existe_troquel=False,
            numero_pistas=1,
            colores_tinta=None,
            unidades_por_rollo=1000,
            etiquetas_por_rollo=1000,
            es_recotizacion=False,
            ancho=0,
            avance=0,
            escalas=[]
        )
        
        # Guardar en session_state
        st.session_state.cotizacion_model = cotizacion
        st.session_state.modo_edicion = False
        st.session_state.cotizacion_guardada = False
        st.session_state.cotizacion_id = None
        
        # Limpiar otros estados relacionados
        if 'referencia_seleccionada' in st.session_state:
            del st.session_state.referencia_seleccionada
        if 'cliente_seleccionado' in st.session_state:
            del st.session_state.cliente_seleccionado
        if 'material_seleccionado' in st.session_state:
            del st.session_state.material_seleccionado
        if 'acabado_seleccionado' in st.session_state:
            del st.session_state.acabado_seleccionado
        if 'tipo_producto_seleccionado' in st.session_state:
            del st.session_state.tipo_producto_seleccionado
        if 'tipo_grafado_seleccionado' in st.session_state:
            del st.session_state.tipo_grafado_seleccionado
        if 'messages' in st.session_state:
            del st.session_state.messages
            
    except Exception as e:
        st.error(f"Error al inicializar la cotización: {str(e)}")
        print(f"Error detallado: {e}")
        traceback.print_exc()

def cargar_datos_cliente(cliente_id: int):
    """Carga los datos del cliente seleccionado"""
    try:
        # Inicializar la base de datos
        db = DBManager(st.session_state.supabase)
        
        # Obtener el cliente
        cliente = db.get_cliente(cliente_id)
        
        if cliente:
            # Guardar el cliente en session_state
            st.session_state.cliente_seleccionado = cliente
            
            # Obtener las referencias del cliente
            referencias = db.get_referencias_cliente(cliente_id)
            
            # Guardar las referencias en session_state
            st.session_state.referencias_cliente = referencias
            
            # Limpiar la referencia seleccionada si existe
            if 'referencia_seleccionada' in st.session_state:
                del st.session_state.referencia_seleccionada
            
            return True
        else:
            st.error(f"No se encontró el cliente con ID {cliente_id}")
            return False
            
    except Exception as e:
        st.error(f"Error al cargar datos del cliente: {str(e)}")
        return False

def cargar_cotizacion(cotizacion_id: int):
    """Carga una cotización existente"""
    try:
        # Inicializar la base de datos
        db = DBManager(st.session_state.supabase)
        
        # Obtener la cotización
        cotizacion = db.get_cotizacion(cotizacion_id)
        
        if cotizacion:
            # Guardar la cotización en session_state
            st.session_state.cotizacion_model = cotizacion
            st.session_state.modo_edicion = True
            st.session_state.cotizacion_id = cotizacion_id
            st.session_state.cotizacion_guardada = True
            st.session_state.forma_pago_id = cotizacion.forma_pago_id # Cargar forma de pago
            
            # Cargar datos del cliente
            if cotizacion.cliente_id:
                cargar_datos_cliente(cotizacion.cliente_id)
            
            # Cargar datos de la referencia
            if cotizacion.referencia_cliente_id:
                cargar_datos_referencia(cotizacion.referencia_cliente_id)
            
            return True
        else:
            st.error(f"No se encontró la cotización con ID {cotizacion_id}")
            return False
            
    except Exception as e:
        st.error(f"Error al cargar la cotización: {str(e)}")
        return False

def cargar_datos_referencia(referencia_id: int):
    """Carga los datos de la referencia seleccionada"""
    try:
        # Inicializar la base de datos
        db = DBManager(st.session_state.supabase)
        
        # Obtener la referencia
        referencia = db.get_referencia_cliente(referencia_id)
        
        if referencia:
            # Guardar la referencia en session_state
            st.session_state.referencia_seleccionada = referencia
            return True
        else:
            st.error(f"No se encontró la referencia con ID {referencia_id}")
            return False
            
    except Exception as e:
        st.error(f"Error al cargar datos de la referencia: {str(e)}")
        return False

def verificar_acceso_cotizacion(cotizacion_id):
    result = st.session_state.supabase.rpc(
        'can_access_quotation', 
        {'quotation_id': cotizacion_id}
    ).execute()
    return result.data[0] if result.data else False

def crear_referencia_cliente(cliente_id: int, descripcion: str) -> Optional[ReferenciaCliente]:
    """
    Crea una nueva referencia de cliente asignándola al comercial actual.
    """
    try:
        # Obtener el ID del comercial actual (auth.uid())
        comercial_id = st.session_state.user_id
        
        if not comercial_id:
            st.error("No se pudo identificar al comercial actual")
            return None
            
        # Crear la nueva referencia asignándola automáticamente al comercial actual
        nueva_referencia = ReferenciaCliente(
            cliente_id=cliente_id,
            descripcion=descripcion,
            id_usuario=comercial_id  # Asignar el id_usuario (renombrado de comercial_id)
        )
        
        # Guardar la referencia
        referencia_guardada = st.session_state.db.crear_referencia(nueva_referencia)
        
        if referencia_guardada:
            st.success(f"Referencia '{descripcion}' creada exitosamente")
            return referencia_guardada
        else:
            st.error("No se pudo crear la referencia")
            return None
            
    except Exception as e:
        st.error(f"Error al crear la referencia: {str(e)}")
        print(f"Error detallado: {traceback.format_exc()}")
        return None

def obtener_referencias_comercial() -> List[ReferenciaCliente]:
    """
    Obtiene todas las referencias asociadas al comercial actual.
    Las políticas RLS se encargarán de filtrar automáticamente.
    """
    try:
        # La consulta ya está filtrada por RLS
        response = st.session_state.supabase.from_('referencias_cliente').select('*').execute()
        
        if response.data:
            return [ReferenciaCliente(**ref) for ref in response.data]
        return []
        
    except Exception as e:
        st.error(f"Error al obtener referencias: {str(e)}")
        print(f"Error detallado: {traceback.format_exc()}")
        return []

if __name__ == "__main__":
    main()
