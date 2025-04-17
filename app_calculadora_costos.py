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
from pdf_generator import CotizacionPDF
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

# Initialize Supabase client
if 'supabase' not in st.session_state:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_key = st.secrets["SUPABASE_KEY"]
    st.session_state.supabase = create_client(supabase_url, supabase_key)

# Configuración de página
st.set_page_config(
    page_title="Sistema de Cotización - Flexo Impresos",
    page_icon="🏭",
    layout="wide"
)

# Título principal con estilo
st.markdown("""
    <h1 style='text-align: center; color: #2c3e50;'>
        🏭 Sistema de Cotización - Flexo Impresos
    </h1>
    <p style='text-align: center; color: #7f8c8d; font-size: 1.2em;'>
        Calculadora de costos para productos flexográficos
    </p>
    <hr>
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
                           es_manga: bool = False) -> str:
    """Genera un informe técnico detallado"""
    dientes = reporte_lito['desperdicio']['mejor_opcion'].get('dientes', 'N/A')
    gap_avance = datos_entrada.desperdicio + (GAP_AVANCE_MANGAS if es_manga else GAP_AVANCE_ETIQUETAS)  # GAP al avance según el tipo
    
    # Obtener el valor del troquel del diccionario
    valor_troquel = reporte_troquel.get('valor', 0) if isinstance(reporte_troquel, dict) else 0
    
    # Obtener detalles del cálculo del área
    area_detalles = reporte_lito.get('area_etiqueta', {})
    if isinstance(area_detalles, dict) and 'detalles' in area_detalles:
        detalles = area_detalles['detalles']
        
        # Extraer información de Q3
        q3_info = ""
        if es_manga:
            q3_info = f"""
- **Cálculo de Q3 (Manga)**:
  - C3 (GAP) = {GAP_PISTAS_MANGAS} (siempre para mangas)
  - B3 (ancho) = {detalles.get('b3', 'N/A')} mm
  - D3 (ancho + C3) = {detalles.get('d3', 'N/A')} mm
  - E3 (pistas) = {detalles.get('e3', 'N/A')}
  - Q3 = D3 * E3 + C3 = {detalles.get('q3', 'N/A')} mm"""
        else:
            q3_info = f"""
- **Cálculo de Q3 (Etiqueta)**:
  - C3 (GAP) = {detalles.get('c3', 'N/A')} mm
  - D3 (ancho + C3) = {detalles.get('d3', 'N/A')} mm
  - E3 (pistas) = {detalles.get('e3', 'N/A')}
  - Q3 = (D3 * E3) + C3 = {detalles.get('q3', 'N/A')} mm"""
        
        # Extraer información de S3 y F3
        s3_info = ""
        f3_detalles = detalles.get('f3_detalles', {})
        if f3_detalles and not es_manga:
            s3_info = f"""
- **Cálculo de F3 (ancho total)**:
  - C3 para F3 = {f3_detalles.get('c3_f3', 'N/A')} mm
  - D3 para F3 = {f3_detalles.get('d3_f3', 'N/A')} mm
  - Base = (E3 * D3) - C3 = {f3_detalles.get('base_f3', 'N/A')} mm
  - Incremento = {f3_detalles.get('incremento_f3', 'N/A')} mm
  - F3 sin redondeo = Base + Incremento = {f3_detalles.get('f3_sin_redondeo', 'N/A')} mm
  - F3 redondeado = {f3_detalles.get('f3_redondeado', 'N/A')} mm
- **Cálculo de S3**:
  - GAP_FIJO (R3) = {detalles.get('gap_fijo', 'N/A')} mm
  - Q3 = {detalles.get('q3', 'N/A')} mm
  - S3 = GAP_FIJO + Q3 = {detalles.get('gap_fijo', 0) + detalles.get('q3', 0)} mm"""
        elif es_manga:
            s3_info = f"""
- **Cálculo de S3 (Manga)**:
  - GAP_FIJO (R3) = {detalles.get('gap_fijo', 'N/A')} mm
  - Q3 = {detalles.get('q3', 'N/A')} mm
  - S3 = GAP_FIJO + Q3 = {detalles.get('gap_fijo', 0) + detalles.get('q3', 0)} mm"""
        
        debug_area = f"""
### Detalles del Cálculo del Área
{q3_info}

{s3_info}

### Fórmula del Área
- **Fórmula usada**: {detalles.get('formula_usada', 'N/A')}
- **Cálculo detallado**: {detalles.get('calculo_detallado', 'N/A')}
- **Q4** (medida montaje): {detalles.get('q4', 'N/A')}
- **E4** (repeticiones): {detalles.get('e4', 'N/A')}
- **S3** (si aplica): {detalles.get('s3', 'N/A')}
- **Área ancho**: {detalles.get('area_ancho', 'N/A')}
- **Área largo**: {detalles.get('area_largo', 'N/A')}
"""
    else:
        debug_area = "No hay detalles disponibles del cálculo del área"
    
    plancha_info = f"""
### Información de Plancha Separada
- **Valor Plancha Original**: ${valor_plancha:.2f}
- **Valor Plancha Ajustado**: ${valor_plancha_separado:.2f}
""" if valor_plancha_separado is not None else ""
    
    return f"""
## Informe Técnico de Cotización
### Parámetros de Impresión
- **Ancho**: {datos_entrada.ancho} mm
- **Avance**: {datos_entrada.avance} mm
- **Gap al avance**: {gap_avance:.2f} mm
- **Pistas**: {datos_entrada.pistas}
- **Número de Tintas**: {num_tintas}
- **Área de Etiqueta**: {reporte_lito['area_etiqueta']['area']:.2f} mm²
- **Unidad (Z)**: {dientes}

{debug_area}

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

def main():
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
    cols = st.columns([1, 1, 1]) # Reducido a 3 columnas
    
    with cols[0]:
        if st.button("Calculadora", type="secondary", key="btn_calculadora"):
            # Limpiar todos los estados
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            
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
            st.session_state.mensajes = []
            st.session_state.pdf_data = None
            st.session_state.nuevo_cliente_guardado = False
            st.session_state.nueva_referencia_guardada = False
            st.session_state.mostrar_form_referencia = False
            st.session_state.cotizacion_cargada = False
            st.rerun()
    
    with cols[1]:
        if st.button("Crear Cliente", type="secondary", key="btn_crear_cliente"):
            st.session_state.paso_actual = 'crear_cliente'
            st.rerun()
    
    with cols[2]: # Movido a la tercera columna
        if st.session_state.cotizacion_calculada and st.button("Ver cotización", type="primary", key="btn_ver_cotizacion"):
            st.session_state.paso_actual = 'cotizacion'
            st.rerun()
    
    # Mostrar página según el paso actual
    if st.session_state.paso_actual == 'calculadora':
        mostrar_calculadora()
    elif st.session_state.paso_actual == 'cotizacion':
        mostrar_cotizacion()
    elif st.session_state.paso_actual == 'crear_cliente':
        crear_cliente()

def mostrar_calculadora():
    """Muestra la interfaz principal de la calculadora"""
    try:
        # Verificar que tenemos una instancia de Supabase
        if 'supabase' not in st.session_state:
            st.error("Error: No se ha inicializado la conexión a Supabase")
            return
            
        # Usar la instancia de DBManager de la sesión o crearla si no existe
        if 'db' not in st.session_state:
            st.session_state.db = DBManager(st.session_state.supabase)
            
        db = st.session_state.db
        
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
            
    except Exception as e:
        st.error(f"Error al mostrar la calculadora: {str(e)}")
        print(f"Error detallado: {traceback.format_exc()}")
        return
    
    # Inicializar variables
    referencia_seleccionada = None
    cliente_seleccionado = None
    comercial_seleccionado = None
    
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
        st.info(f"Editando cotización para la referencia: {st.session_state.referencia_seleccionada.descripcion}")
    
    # Si estamos en modo edición, ya tenemos el cliente seleccionado
    if modo_edicion:
        cliente_id = cotizacion_model.cliente_id
        cliente = db.get_cliente(cliente_id)
        st.write(f"**Cliente:** {cliente.nombre}")
        
        # Mostrar datos del comercial
        comercial_id = st.session_state.referencia_seleccionada.id_comercial
        comercial = db.get_comercial(comercial_id) if comercial_id else None
        if comercial:
            st.write(f"**Comercial:** {comercial.nombre}")
        else:
            st.write("**Comercial:** No especificado")
        
        # Mostrar datos de la referencia
        st.write(f"**Referencia:** {st.session_state.referencia_seleccionada.descripcion}")
        
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
                st.write(f"**Troquel existe:** {'Sí' if cotizacion_model.troquel_existe else 'No'}")
            
        with col3:
            if es_manga:
                st.write(f"**Tipo de Grafado:** {cotizacion_model.tipo_grafado or 'Sin grafado'}")
            st.write(f"**{'Mangas' if es_manga else 'Etiquetas'} por rollo:** {cotizacion_model.num_rollos}")
        
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
            # Obtener todos los comerciales disponibles
            if modo_edicion:
                # En modo edición, mostrar el comercial asociado a la referencia
                comercial_id = cotizacion_model.comercial_id
                comercial = db.get_comercial(comercial_id) if comercial_id else None
                if comercial:
                    comercial_seleccionado = (comercial.id, comercial.nombre, comercial.email, comercial.celular)
                    st.write(f"**Comercial:** {comercial.nombre}")
                else:
                    comercial_seleccionado = None
                    st.write("**Comercial:** No especificado")
            else:
                comerciales = db.get_comerciales()
                comercial_seleccionado = st.selectbox(
                    "Comercial",
                    options=[(c.id, c.nombre, c.email, c.celular) for c in comerciales],
                    format_func=lambda x: x[1]
                ) if comerciales else None
                
        # Control para definir si mostrar el formulario de creación de referencia
        mostrar_form_nueva_referencia = 'mostrar_form_referencia' in st.session_state and st.session_state.mostrar_form_referencia

        with col3:
            if modo_edicion:
                # En modo edición, mostrar la referencia existente
                st.write(f"**Referencia:** {st.session_state.referencia_seleccionada.descripcion}")
            else:
                # Campo simple para ingresar la referencia
                referencia_descripcion = st.text_input(
                    "Referencia",
                    key="nueva_referencia_input",
                    help="Ingrese una descripción para esta referencia"
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
                if cotizacion_existente:
                    # Load existing quotation without showing a message
                    st.session_state.cotizacion_model = cotizacion_existente
                    st.session_state.modo_edicion = True
                    if st.button("Continuar con la edición", key="btn_continuar_edicion"):
                        st.rerun()
            else:
                pass

    # Si estamos en modo edición, no seguimos con el formulario hasta que el usuario haga clic en "Continuar"
    if modo_edicion and "cotizacion_model" in st.session_state and not hasattr(st.session_state, "mostrar_formulario_edicion"):
        return
    
    # Obtener datos necesarios para el formulario
    materiales = db.get_materiales()
    acabados = db.get_acabados()
    tipos_producto = db.get_tipos_producto()
    
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
    
    # Si hay una referencia seleccionada o si acabamos de crear una nueva, continuamos con el formulario
    if ((not mostrar_form_nueva_referencia and "referencia_seleccionada" in st.session_state) or
        st.session_state.get("nueva_referencia_guardada", False)):
        
        # Si acabamos de crear una nueva referencia, mostrar un mensaje
        if st.session_state.get("nueva_referencia_guardada", False):
            st.success(f"Creando cotización para la referencia: {st.session_state.referencia_seleccionada.descripcion}")
            st.session_state.nueva_referencia_guardada = False  # Resetear el flag
        
        # Datos del producto
        st.write("### Datos del Producto")
        
        # Si estamos en modo edición, usar los valores del modelo
        if modo_edicion and cotizacion_model:
            tipo_producto_id_default = cotizacion_model.tipo_producto_id
            material_id_default = cotizacion_model.material_id
            acabado_id_default = cotizacion_model.acabado_id
            ancho_default = cotizacion_model.ancho
            avance_default = cotizacion_model.avance
            pistas_default = cotizacion_model.numero_pistas
            num_tintas_default = cotizacion_model.num_tintas
            planchas_por_separado_default = "Sí" if cotizacion_model.planchas_x_separado else "No"
            troquel_existe_default = "Sí" if cotizacion_model.troquel_existe else "No"
            tipo_grafado_default = cotizacion_model.tipo_grafado if cotizacion_model.tipo_grafado else "Sin grafado"
            num_rollos_default = cotizacion_model.num_rollos
            
            # Obtener escalas si existen
            if hasattr(cotizacion_model, 'escalas') and cotizacion_model.escalas:
                escalas_default = ", ".join([str(int(e.escala)) for e in cotizacion_model.escalas])
    
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
    
            # Medidas y propiedades
    col1, col2, col3 = st.columns(3)
    
    with col1:
        ancho = st.number_input("Ancho (mm)", 
                               min_value=10.0, 
                               max_value=ANCHO_MAXIMO_LITOGRAFIA, 
                                   value=float(ancho_default), 
                               step=10.0,
                               help=f"El ancho no puede exceder {ANCHO_MAXIMO_LITOGRAFIA}mm. Los valores deben ser múltiplos de 10mm.")
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
                tipo_grafado_options = [
                    "Sin grafado",
                    "Vertical Total",
                    "Horizontal Total",
                    "Horizontal Total + Vertical"
                ]
                tipo_grafado = st.selectbox(
                    "Tipo de Grafado",
                    options=tipo_grafado_options,
                    index=tipo_grafado_options.index(tipo_grafado_default) if tipo_grafado_default in tipo_grafado_options else 0
            )
        
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
            st.session_state.rentabilidad_ajustada = st.number_input(
                "Rentabilidad (%)",
                min_value=0.0,
                max_value=100.0,
                value=rentabilidad_default,
                step=1.0,
                help="Porcentaje de rentabilidad a aplicar en el cálculo",
                key="rentabilidad_input"
            )
            
            # Precio de material
            # Mostrar el valor actual como referencia
            valor_material_actual = extraer_valor_precio(material_seleccionado[1])
            st.text(f"Valor material actual: ${valor_material_actual:.2f}")
            st.session_state.ajustar_material = st.checkbox("Ajustar precio de material", key="ajustar_material_checkbox")
            st.session_state.valor_material_ajustado = st.number_input(
                "Valor material",
                min_value=0.0,
                value=valor_material_actual,
                step=0.01,
                disabled=not st.session_state.ajustar_material,
                key="valor_material_input"
            )
        
        with col2:
            # Precio de troquel
            st.session_state.ajustar_troquel = st.checkbox("Ajustar precio de troquel", key="ajustar_troquel_checkbox")
            st.session_state.precio_troquel = st.number_input(
                "Valor troquel",
                min_value=0.0,
                value=0.0,
                step=1000.0,
                disabled=not st.session_state.ajustar_troquel,
                key="precio_troquel_input"
            )
            
            # Precio de planchas
            st.session_state.ajustar_planchas = st.checkbox("Ajustar precio de planchas", key="ajustar_planchas_checkbox")
            st.session_state.precio_planchas = st.number_input(
                "Valor planchas",
                min_value=0.0,
                value=0.0,
                step=1000.0,
                disabled=not st.session_state.ajustar_planchas,
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
                datos_lito.tipo_grafado = tipo_grafado
                print(f"\n=== DEBUG MANGA ===")
                print(f"Tipo de grafado seleccionado: {tipo_grafado}")
                
                # Calcular valor del troquel según el tipo de grafado
                reporte_troquel = calculadora.calcular_valor_troquel(
                    datos=datos_lito,
                    repeticiones=reporte_lito['desperdicio']['mejor_opcion'].get("repeticiones", 1),
                    troquel_existe=False,  # Para mangas no importa si existe
                    valor_mm=100
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
            
            # Cálculo de plancha separada
            valor_plancha_separado = None
            valor_plancha_para_calculo = 0 if planchas_por_separado == "Sí" else valor_plancha
            if planchas_por_separado == "Sí":
                valor_plancha_separado = calcular_valor_plancha_separado(valor_plancha_dict)
            
            # Calcular costos
            calculadora = CalculadoraCostosEscala()
            
            # Ajustar datos con los valores personalizados
            if 'rentabilidad_ajustada' in st.session_state:
                datos_escala.rentabilidad = st.session_state.rentabilidad_ajustada

            # Ajustar valores de material, troquel y planchas
            if 'ajustar_material' in st.session_state and st.session_state.ajustar_material:
                valor_material = st.session_state.valor_material_ajustado

            # Valor troquel
            valor_troquel = st.session_state.precio_troquel if 'ajustar_troquel' in st.session_state and st.session_state.ajustar_troquel else obtener_valor_troquel(reporte_lito)

            # Valor plancha
            if 'ajustar_planchas' in st.session_state and st.session_state.ajustar_planchas:
                valor_plancha = st.session_state.precio_planchas
                valor_plancha_para_calculo = valor_plancha
            else:
                valor_plancha, valor_plancha_dict = obtener_valor_plancha(reporte_lito)
                valor_plancha_para_calculo = 0 if planchas_por_separado == "Sí" else valor_plancha
            
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
                
                # Guardar datos de cotización en el estado
                st.session_state.datos_cotizacion = crear_datos_cotizacion(
                    material=material_seleccionado[1].split(' - ')[1].split(' ($')[0],
                    acabado="Sin acabado" if es_manga else acabado_seleccionado[2],
                    num_tintas=num_tintas,
                    num_rollos=num_rollos,
                    valor_plancha=valor_plancha,
                    valor_material=valor_material,
                    valor_acabado=valor_acabado,
                    valor_troquel=valor_troquel,
                    valor_plancha_separado=valor_plancha_separado,
                    es_manga=es_manga
                )
                    
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
                
                st.session_state.cotizacion_model = crear_o_actualizar_cotizacion_model(
                    cliente_id=cliente_seleccionado[0],
                    referencia_id=None,  # Se establecerá al guardar
                    material_id=material_seleccionado[0],
                    acabado_id=acabado_seleccionado[0] if not es_manga else 10,
                    num_tintas=num_tintas,
                    num_rollos=num_rollos,
                    consecutivo=st.session_state.consecutivo,
                    es_manga=es_manga,
                    tipo_grafado=tipo_grafado if es_manga else None,
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
                    cotizacion_existente=st.session_state.cotizacion_model if modo_edicion else None
                )
                
                # Marcar que se ha calculado la cotización
                st.session_state.cotizacion_calculada = True
                st.session_state.cotizacion_guardada = False
                
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
    
    # Mostrar información técnica
    st.subheader("Información Técnica para Impresión")
    
    # Acciones de la cotización
    st.subheader("Acciones")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Botón para guardar cotización
        if not st.session_state.cotizacion_guardada:
            if st.button("Guardar Cotización", key="guardar_cotizacion", type="primary"):
                # Pass the cotization from session state
                success, message = guardar_cotizacion(st.session_state.cotizacion_model, st.session_state.db)
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(message)
        else:
            st.success("Cotización guardada ✓")
    
    with col2:
        # Botón para descargar PDF
        if st.session_state.cotizacion_guardada:
            # Si el PDF no está en memoria, intentar generarlo
            if 'pdf_data' not in st.session_state or st.session_state.pdf_data is None:
                try:
                    db = DBManager(st.session_state.supabase)  # Fixed: Pass supabase client
                    datos_completos = db.get_datos_completos_cotizacion(st.session_state.cotizacion_id)
                    if datos_completos:
                        pdf_gen = CotizacionPDF()
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                            pdf_gen.generar_pdf(datos_completos, tmp_file.name)
                            with open(tmp_file.name, "rb") as pdf_file:
                                st.session_state.pdf_data = pdf_file.read()
                            print(f"PDF regenerado y guardado en memoria: {len(st.session_state.pdf_data)} bytes")
                except Exception as e:
                    print(f"Error regenerando PDF: {str(e)}")
                    traceback.print_exc()
            
            if st.session_state.pdf_data is not None:
                st.download_button(
                    label="Descargar Cotización (PDF)",
                    data=st.session_state.pdf_data,
                    file_name=f"cotizacion_{st.session_state.cotizacion_id}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
            else:
                st.error("No se pudo generar el PDF. Por favor, intente guardar la cotización nuevamente.")

    with col3:
        # Botón para nueva cotización
        if st.button("Calcular Nueva Cotización", type="primary"):
            # Limpiar todos los estados
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.paso_actual = 'calculadora'
            st.rerun()
                    
        # Botón para calcular una nueva cotización después de guardar
        if st.session_state.cotizacion_guardada:
            if st.button("Calcular Nueva Cotización", key="nueva_cotizacion_post_guardado", type="primary"):
                # Reiniciar el state pero preservar mensajes y algunos valores
                preserved_messages = st.session_state.messages if "messages" in st.session_state else []
                
                # Limpiar session state pero conservar login y mensajes
                for key in list(st.session_state.keys()):
                    if key not in ['authentication_status', 'username', 'name', 'messages', 'role']:
                        del st.session_state[key]
                
                # Restaurar mensajes
                st.session_state.messages = preserved_messages
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
    cotizacion_existente=None
):
    """
    Crea o actualiza un modelo de cotización con los datos proporcionados.
    """
    print("\n=== DEBUG CREAR_O_ACTUALIZAR_COTIZACION_MODEL ===")
    print(f"tipo_producto_id recibido: {tipo_producto_id}")
    print(f"comercial_id recibido: {comercial_id}")
    print(f"referencia_descripcion recibida: {referencia_descripcion}")
    
    try:
        if cotizacion_existente:
            print("Actualizando cotización existente...")
            cotizacion = cotizacion_existente
        else:
            print("Creando nueva cotización...")
            cotizacion = Cotizacion()
        
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
        if cotizacion.escalas:
            print(f"  Número de escalas: {len(cotizacion.escalas)}")
            for e in cotizacion.escalas:
                print(f"    - Escala: {e.escala}, Valor unidad: {e.valor_unidad}")
        
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

def guardar_cotizacion(cotizacion, db):
    """Guarda una cotización en la base de datos"""
    try:
        print("\n=== DEBUG GUARDAR COTIZACIÓN ===")
        print(f"Datos de cotización:")
        print(f"  Cliente: {cotizacion.cliente_id}")
        
        # Si es una actualización, usar la referencia existente
        if cotizacion.id:
            print(f"  Referencia existente: {cotizacion.referencia_cliente_id}")
        else:
            # Crear nueva referencia
            print("Creando nueva referencia...")
            nueva_referencia = ReferenciaCliente(
                cliente_id=cotizacion.cliente_id,
                descripcion=cotizacion.descripcion,
                id_comercial=cotizacion.comercial_id
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
            'colores_tinta': getattr(cotizacion, 'colores_tinta', None)
        }
        
        # Si es una actualización, mantener el número de cotización existente
        if cotizacion.id and hasattr(cotizacion, 'numero_cotizacion') and cotizacion.numero_cotizacion is not None:
            datos_cotizacion['numero_cotizacion'] = int(cotizacion.numero_cotizacion)
        # Si es nueva, generar el siguiente número
        else:
            siguiente_numero = db.get_next_numero_cotizacion()
            if siguiente_numero is None:
                return (False, "No se pudo generar el siguiente número de cotización")
            datos_cotizacion['numero_cotizacion'] = siguiente_numero
            print(f"Nuevo número de cotización generado: {siguiente_numero}")
        
        # Limpiar datos antes de enviar
        datos_limpios = db._limpiar_datos(datos_cotizacion)
        
        # Si la cotización ya existe, actualizarla
        if cotizacion.id:
            print(f"\nActualizando cotización existente ID: {cotizacion.id}")
            result = db.actualizar_cotizacion(cotizacion.id, datos_limpios)
            if not result:
                return (False, "Error al actualizar la cotización")
            
            # Actualizar las escalas
            if hasattr(cotizacion, 'escalas') and cotizacion.escalas:
                print("\nActualizando escalas...")
                db.guardar_cotizacion_escalas(cotizacion.id, cotizacion.escalas)
            
            print("Cotización actualizada exitosamente")
            st.session_state.cotizacion_guardada = True
            st.session_state.cotizacion_id = cotizacion.id
            return (True, "Cotización actualizada exitosamente")
            
        # Si es una nueva cotización, crearla
        else:
            print("\nCreando nueva cotización...")
            result = db.crear_cotizacion(datos_limpios)
            if not result:
                return (False, "Error al crear la cotización")
            
            # Handle both dictionary and object return types
            cotizacion_id = result.id if hasattr(result, 'id') else result.get('id')
            
            # Guardar las escalas
            if hasattr(cotizacion, 'escalas') and cotizacion.escalas:
                print("\nGuardando escalas...")
                db.guardar_cotizacion_escalas(cotizacion_id, cotizacion.escalas)
            
            print("Cotización creada exitosamente")
            st.session_state.cotizacion_guardada = True
            st.session_state.cotizacion_id = cotizacion_id
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

if __name__ == "__main__":
    main()
