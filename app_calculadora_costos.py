import streamlit as st
import pandas as pd
import numpy as np
import os
import sys
import io
from calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from calculadora_litografia import CalculadoraLitografia, DatosLitografia
from db_manager import DBManager
import tempfile
from pdf_generator import CotizacionPDF
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
import math

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
db = DBManager()

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
        inicio = texto.find('($') + 2
        fin = texto.find(')')
        if inicio > 1 and fin > inicio:
            return float(texto[inicio:fin].strip())
        return 0.0
    except:
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

def generar_tabla_resultados(resultados: List[Dict]) -> pd.DataFrame:
    """Genera una tabla formateada con los resultados de la cotización"""
    print("\n=== DEPURACIÓN TABLA RESULTADOS ===")
    
    for r in resultados:
        r['desperdicio_total'] = r['desperdicio_tintas'] + r['desperdicio_porcentaje']
        print(f"Escala: {r['escala']:,}")
        print(f"Valor Unidad (sin formato): {r['valor_unidad']}")
        print(f"Valor Unidad (formateado): ${float(r['valor_unidad']):.2f}")
        print(f"Valor MM: ${float(r['valor_mm']):.3f}")
        print(f"Desperdicio total: ${r['desperdicio_total']:,.2f}")
        print(f"Desperdicio tintas: ${r['desperdicio_tintas']:,.2f}")
        print(f"Desperdicio porcentaje: ${r['desperdicio_porcentaje']:,.2f}")
        print("---")
    
    return pd.DataFrame([
        {
            'Escala': f"{r['escala']:,}",
            'Valor Unidad': f"${float(r['valor_unidad']):.2f}",
            'Valor MM': f"${float(r['valor_mm']):.3f}",
            'Metros': f"{r['metros']:.2f}",
            'Tiempo (h)': f"{r['tiempo_horas']:.2f}",
            'Montaje': f"${r['montaje']:,.2f}",
            'MO y Maq': f"${r['mo_y_maq']:,.2f}",
            'Tintas': f"${r['tintas']:,.2f}",
            'Papel/lam': f"${r['papel_lam']:,.2f}",
            'Desperdicio': f"${r['desperdicio_total']:,.2f}"
        }
        for r in resultados
    ])

def generar_informe_tecnico(datos_entrada: DatosEscala, resultados: List[Dict], reporte_lito: Dict, 
                           num_tintas: int, valor_plancha: float, valor_material: float, 
                           valor_acabado: float, reporte_troquel: Dict = None, 
                           valor_plancha_separado: Optional[float] = None, 
                           codigo_unico: Optional[str] = None,
                           es_manga: bool = False) -> str:
    """Genera un informe técnico detallado"""
    dientes = reporte_lito['desperdicio']['mejor_opcion'].get('dientes', 'N/A')
    gap_avance = datos_entrada.desperdicio + (0 if es_manga else 2.6)  # Gap avance solo para etiquetas
    
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
  - C3 (GAP) = 0 (siempre para mangas)
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
    
    codigo_unico_info = f"""
### Código Único
```
{codigo_unico}
```
""" if codigo_unico else ""
    
    return f"""
## Informe Técnico de Cotización
{codigo_unico_info}
### Parámetros de Impresión
- **Ancho**: {datos_entrada.ancho} mm
- **Avance**: {datos_entrada.avance} mm
- **Gap al avance**: {gap_avance:.2f} mm
- **Pistas**: {datos_entrada.pistas}
- **Número de Tintas**: {num_tintas}
- **Área de Etiqueta**: {reporte_lito['area_etiqueta']['area']:.2f} mm²
- **Dientes**: {dientes}

{debug_area}

### Información de Materiales
- **Valor Material**: ${valor_material:.2f}/mm²
- **Valor Acabado**: ${valor_acabado:.2f}/mm²
- **Valor Troquel**: ${valor_troquel:.2f}

{plancha_info}
"""

def generar_identificador(tipo_producto: str, material_code: str, ancho: float, avance: float,
                       num_pistas: int, num_tintas: int, acabado_code: str, etiquetas_rollo: int,
                       cliente: str, referencia: str, consecutivo: int) -> str:
    """Genera un identificador único para la cotización con el siguiente formato:
    TIPO MATERIAL ANCHO_x_AVANCE TINTAS [ACABADO] [RX/MX_ETIQUETAS] CLIENTE REFERENCIA CONSECUTIVO"""
    # 1. Tipo de producto
    es_manga = "MANGA" in tipo_producto.upper()
    tipo = "ET"  # Por defecto es ET
    
    # 2. Código de material ya viene como parámetro
    material_code = material_code.split('-')[0].strip()
    
    # 3. Formato ancho x avance
    dimensiones = f"{ancho:.0f}x{avance:.0f}"
    
    # 4. Número de tintas
    tintas = f"{num_tintas}T"
    
    # 7. Cliente (nombre completo, eliminando texto entre paréntesis)
    cliente_limpio = cliente.split('(')[0].strip().upper()
    
    # 8. Referencia (descripción completa, eliminando texto entre paréntesis)
    referencia_limpia = referencia.split('(')[0].strip().upper()
    
    # 9. Consecutivo con 4 dígitos
    cons = f"{consecutivo:04d}"
    
    # Construir el identificador según sea manga o etiqueta
    if es_manga:
        # Para mangas: TIPO MATERIAL ANCHO_x_AVANCE TINTAS MX_ETIQUETAS CLIENTE REFERENCIA CONSECUTIVO
        etiquetas = f"MX{etiquetas_rollo}"
        identificador = f"{tipo} {material_code} {dimensiones} {tintas} {etiquetas} {cliente_limpio} {referencia_limpia} {cons}"
    else:
        # Para etiquetas: TIPO MATERIAL ANCHO_x_AVANCE TINTAS ACABADO RX_ETIQUETAS CLIENTE REFERENCIA CONSECUTIVO
        # Extraer solo la parte antes del guión para el acabado
        if acabado_code:
            acabado_code = acabado_code.split('-')[0].strip()
        etiquetas = f"RX{etiquetas_rollo}"
        # Si hay código de acabado, incluirlo en el identificador
        if acabado_code:
            identificador = f"{tipo} {material_code} {dimensiones} {tintas} {acabado_code} {etiquetas} {cliente_limpio} {referencia_limpia} {cons}"
        else:
            # Si no hay código de acabado, omitirlo completamente
            identificador = f"{tipo} {material_code} {dimensiones} {tintas} {etiquetas} {cliente_limpio} {referencia_limpia} {cons}"
    
    # Convertir a mayúsculas
    return identificador.upper()

def calcular_valor_plancha_separado(valor_plancha_dict: Dict) -> float:
    """Calcula el valor de la plancha cuando se cobra por separado"""
    if isinstance(valor_plancha_dict, dict) and 'detalles' in valor_plancha_dict:
        detalles = valor_plancha_dict['detalles']
        if 'precio_sin_constante' in detalles:
            # Calcular el valor base
            valor_base = detalles['precio_sin_constante'] / 0.75
            # Redondear al múltiplo de 1000 más cercano hacia arriba
            return math.ceil(valor_base / 1000) * 1000
    return 0

def crear_datos_cotizacion(cliente: str, referencia: str, codigo_unico: str, material: str,
                          acabado: str, num_tintas: int, num_rollos: int, valor_troquel: Dict,
                          valor_plancha_separado: Optional[float], resultados: List[Dict],
                          es_manga: bool = False, tipo_grafado: Optional[str] = None,
                          adhesivo_tipo: Optional[str] = None, comercial_nombre: Optional[str] = None,
                          comercial_email: Optional[str] = None, comercial_telefono: Optional[str] = None) -> Dict:
    """Crea el diccionario de datos para la cotización"""
    # Extraer el valor numérico del troquel del diccionario
    valor_troquel_final = valor_troquel.get('valor', 0) if isinstance(valor_troquel, dict) else 0
    
    return {
        'consecutivo': 1984,
        'cliente': cliente,
        'referencia': referencia,
        'identificador': codigo_unico,
        'material': material,
        'acabado': acabado,
        'num_tintas': num_tintas,
        'num_rollos': num_rollos,
        'valor_troquel': valor_troquel_final,
        'valor_plancha_separado': valor_plancha_separado,
        'resultados': resultados,
        'es_manga': es_manga,
        'tipo_grafado': tipo_grafado,
        'adhesivo_tipo': adhesivo_tipo,
        'comercial_nombre': comercial_nombre,
        'comercial_email': comercial_email,
        'comercial_telefono': comercial_telefono
    }

def main():
    st.title("Cotizador Flexo Impresos")
    
    try:
        db = DBManager()
        materiales = db.get_materiales()
        acabados = db.get_acabados()
        tipos_producto = db.get_tipos_producto()
        
    except Exception as e:
        st.error(f"Error al conectar con la base de datos: {str(e)}")
        return
    
    # Definir tipo de producto primero
    tipo_producto_seleccionado = st.selectbox(
        "Tipo de Producto",
        options=[(t.id, t.nombre) for t in tipos_producto],
        format_func=lambda x: x[1]
    )
    es_manga = "MANGA" in tipo_producto_seleccionado[1].upper()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        ancho = st.number_input("Ancho (mm)", min_value=0.1, max_value=335.0, value=100.0, step=0.1,
                               help="El ancho no puede exceder 335mm")
        avance = st.number_input("Avance/Largo (mm)", min_value=0.1, value=100.0, step=0.1)
        pistas = st.number_input("Número de pistas", min_value=1, value=1, step=1)
        
        # Mover materiales aquí
        materiales_filtrados = [
            m for m in materiales 
            if es_manga and any(code in m.code.upper() for code in ['PVC', 'PETG'])
            or not es_manga
        ]
        
        material_seleccionado = st.selectbox(
            "Material",
            options=[(m.id, f"{m.code} - {m.nombre} (${m.valor:.2f})", m.nombre, m.adhesivo_tipo) for m in materiales_filtrados],
            format_func=lambda x: x[2]
        )
        
    with col2:
        num_tintas = st.number_input("Número de tintas", min_value=0, value=4, step=1)
        planchas_por_separado = st.radio("¿Planchas por separado?", 
                                    options=["Sí", "No"], 
                                    index=1,
                                    horizontal=True)
        troquel_existe = st.radio("¿Existe troquel?", 
                                  options=["Sí", "No"], 
                                  index=0,
                                  horizontal=True)
        
        # Mover acabados aquí
        acabado_seleccionado = (10, "SA - Sin acabado ($0.00)", "Sin acabado") if es_manga else st.selectbox(
            "Acabado",
            options=[(a.id, f"{a.code} - {a.nombre} (${a.valor:.2f})", a.nombre) for a in acabados],
            format_func=lambda x: x[2]
        )

    with col3:
        # Agregar selección de grafado para mangas
        tipo_grafado = None
        if es_manga:
            tipo_grafado = st.selectbox(
                "Tipo de Grafado",
                options=[
                    "Sin grafado",
                    "Vertical Total",
                    "Horizontal Total",
                    "Horizontal + Vertical Total"
                ]
            )
        
        num_rollos = st.number_input("Número de etiquetas por rollo", min_value=1, value=1000, step=100)

    # Sección de escalas
    st.header("Escalas de Producción")
    escalas_text = st.text_input(
        "Ingrese las escalas separadas por comas",
        value="1000, 2000, 3000, 5000",
        help="Ejemplo: 1000, 2000, 3000, 5000"
    )
    
    escalas = procesar_escalas(escalas_text)
    if not escalas:
        st.error("Por favor ingrese números válidos separados por comas")
        return
    
    # Sección de cliente y referencia
    st.header("Datos del Cliente")
    col1, col2 = st.columns(2)
    
    with col1:
        clientes = db.get_clientes()
        cliente_seleccionado = st.selectbox(
            "Cliente",
            options=[(c.id, c.nombre) for c in clientes] if clientes else [],
            format_func=lambda x: x[1]
        ) if clientes else None
        
    with col2:
        if cliente_seleccionado:
            referencias = db.get_referencias_cliente(cliente_seleccionado[0])
            referencia_seleccionada = st.selectbox(
                "Referencia",
                options=[(r.id, r.descripcion, r.comercial_nombre, r.comercial_email, r.comercial_telefono) for r in referencias] if referencias else [],
                format_func=lambda x: x[1]
            ) if referencias else None

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

    # Botón para calcular
    if st.button("Calcular", type="primary"):
        try:
            # Configuración inicial
            datos_lito = DatosLitografia(
                ancho=ancho * 2 + 20 if es_manga else ancho,  # Multiplicar por 2 y sumar 20 solo para mangas
                avance=avance,
                pistas=pistas,
                planchas_por_separado=planchas_por_separado == "Sí",
                incluye_troquel=True,
                troquel_existe=troquel_existe == "Sí",
                gap=0 if es_manga else 3.0,
                gap_avance=0 if es_manga else 2.6
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
            if es_manga and tipo_grafado == "Horizontal + Vertical Total":
                mejor_opcion = reporte_lito.get('desperdicio', {}).get('mejor_opcion', {})
                if mejor_opcion and mejor_opcion.get('desperdicio', 0) > 2:
                    # Forzar troquel_existe a False si el desperdicio es mayor a 2mm
                    datos_lito.troquel_existe = False
                    # Regenerar el reporte con el nuevo valor de troquel
                    reporte_lito = calculadora.generar_reporte_completo(datos_lito, num_tintas, es_manga)
            
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
            
            # Configuración de datos para cálculo
            datos = DatosEscala(
                escalas=escalas,
                pistas=datos_lito.pistas,
                ancho=datos_lito.ancho,
                avance=datos_lito.avance,
                avance_total=datos_lito.avance,
                desperdicio=mejor_opcion['desperdicio'],
                area_etiqueta=reporte_lito['area_etiqueta']['area'] if isinstance(reporte_lito['area_etiqueta'], dict) else 0
            )
            
            # Obtener valores
            valor_etiqueta = reporte_lito.get('valor_tinta', 0)
            valor_plancha, valor_plancha_dict = obtener_valor_plancha(reporte_lito)
            valor_troquel = obtener_valor_troquel(reporte_lito)
            
            valor_material = extraer_valor_precio(material_seleccionado[1])
            valor_acabado = 0 if es_manga else extraer_valor_precio(acabado_seleccionado[1])
            
            # Cálculo de plancha separada
            valor_plancha_separado = None
            valor_plancha_para_calculo = 0 if planchas_por_separado == "Sí" else valor_plancha
            if planchas_por_separado == "Sí":
                valor_plancha_separado = calcular_valor_plancha_separado(valor_plancha_dict)
            
            # Calcular costos
            calculadora = CalculadoraCostosEscala()
            
            resultados = calculadora.calcular_costos_por_escala(
                datos=datos,
                num_tintas=num_tintas,
                valor_etiqueta=valor_etiqueta,
                valor_plancha=valor_plancha_para_calculo,
                valor_troquel=valor_troquel,
                valor_material=valor_material,
                valor_acabado=valor_acabado,
                es_manga=es_manga
            )
            
            if resultados:
                # Mostrar tabla de resultados
                st.subheader("Tabla de Resultados")
                df = generar_tabla_resultados(resultados)
                st.dataframe(df, hide_index=True, use_container_width=True)

                # Generar identificador una sola vez y reutilizarlo
                acabado_code = "" if es_manga or acabado_seleccionado[0] == 10 else acabado_seleccionado[1]
                codigo_unico = generar_identificador(
                    tipo_producto=tipo_producto_seleccionado[1],
                    material_code=material_seleccionado[1].split('-')[0].strip(),
                    ancho=ancho,
                    avance=avance,
                    num_pistas=pistas,
                    num_tintas=num_tintas,
                    acabado_code=acabado_code,
                    etiquetas_rollo=num_rollos,
                    cliente=cliente_seleccionado[1],
                    referencia=referencia_seleccionada[1],
                    consecutivo=1984
                )

                # Mostrar información técnica para impresión
                st.subheader("Información Técnica para Impresión")
                
                # Crear columnas para la información técnica
                col_info1, col_info2 = st.columns(2)
                
                with col_info1:
                    st.markdown("#### Identificador")
                    
                    # Destacar visualmente el código único
                    st.markdown(f"""
<div style='
    background-color: #f0f2f6; 
    border: 2px solid #3498db; 
    border-radius: 10px; 
    padding: 10px; 
    text-align: center; 
    margin-bottom: 10px;
'>
    <p style='
        font-size: 16px; 
        font-weight: bold; 
        color: #2980b9; 
        word-wrap: break-word;
        margin: 0;
    '>{codigo_unico}</p>
</div>
""", unsafe_allow_html=True)
                    
                    st.write(f"**Ancho:** {ancho} mm")
                    st.write(f"**Avance:** {avance} mm")
                    st.write(f"**Pistas:** {pistas}")
                    st.write(f"**Área de Etiqueta:** {reporte_lito['area_etiqueta']['area']:.2f} mm²")
                    st.write(f"**Etiquetas por Rollo:** {num_rollos}")
                    
                    if es_manga:
                        st.markdown("#### Información de Manga")
                        st.write(f"**Tipo de Grafado:** {tipo_grafado}")
                        if tipo_grafado == "Horizontal + Vertical Total":
                            mejor_opcion = reporte_lito.get('desperdicio', {}).get('mejor_opcion', {})
                            st.write(f"**Desperdicio:** {mejor_opcion.get('desperdicio', 0):.2f} mm")
                
                with col_info2:
                    st.markdown("#### Detalles de Producción")
                    st.write(f"**Material:** {material_seleccionado[2]}")
                    if not es_manga:
                        st.write(f"**Acabado:** {acabado_seleccionado[2]}")
                    st.write(f"**Número de Tintas:** {num_tintas}")
                    st.write(f"**Planchas por Separado:** {planchas_por_separado}")
                    if planchas_por_separado == "Sí":
                        st.write(f"**Valor Plancha:** ${valor_plancha_separado:,.2f}")
                    st.write(f"**Troquel Existe:** {troquel_existe}")
                    if troquel_existe == "Sí":
                        valor_troquel_final = reporte_lito.get('valor_troquel', {}).get('valor', 0)
                        st.write(f"**Valor Troquel:** ${valor_troquel_final:,.2f}")
                
                # Mostrar detalles del desperdicio
                st.markdown("#### Detalles de Desperdicio")
                st.write(f"**Desperdicio Total:** {mejor_opcion['desperdicio']:.2f} mm")
                if 'dientes' in mejor_opcion:
                    st.write(f"**Dientes:** {mejor_opcion['dientes']}")

                # Generar PDF
                pdf_gen = CotizacionPDF()
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    datos_cotizacion = crear_datos_cotizacion(
                        cliente=cliente_seleccionado[1],
                        referencia=referencia_seleccionada[1],
                        codigo_unico=codigo_unico,
                        material=material_seleccionado[1].split(' - ')[1].split(' ($')[0],  # Extraer solo el nombre
                        acabado="Sin acabado" if es_manga else acabado_seleccionado[2],   # Usar el nombre del acabado directamente
                        num_tintas=num_tintas,
                        num_rollos=num_rollos,
                        valor_troquel=reporte_lito.get('valor_troquel', 0),
                        valor_plancha_separado=valor_plancha_separado,
                        resultados=resultados,
                        es_manga=es_manga,
                        tipo_grafado=tipo_grafado if es_manga else None,
                        adhesivo_tipo=material_seleccionado[3] if len(material_seleccionado) > 3 and material_seleccionado[3] else "No aplica",
                        comercial_nombre=referencia_seleccionada[2] if len(referencia_seleccionada) > 2 else None,
                        comercial_email=referencia_seleccionada[3] if len(referencia_seleccionada) > 3 else None,
                        comercial_telefono=referencia_seleccionada[4] if len(referencia_seleccionada) > 4 else None
                    )
                    pdf_gen.generar_pdf(datos_cotizacion, tmp_file.name)
                    
                    with open(tmp_file.name, "rb") as pdf_file:
                        st.download_button(
                            label="Descargar Cotización (PDF)",
                            data=pdf_file,
                            file_name=f"cotizacion_{datos_cotizacion['consecutivo']}.pdf",
                            mime="application/pdf"
                        )
            
        except Exception as e:
            st.error(f"Error en el cálculo: {str(e)}")
            import traceback
            st.error(traceback.format_exc())

if __name__ == "__main__":
    main()
