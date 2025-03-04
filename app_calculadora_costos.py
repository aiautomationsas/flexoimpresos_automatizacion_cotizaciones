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

# Configuración de página
st.set_page_config(
    page_title="Cotizador Flexo Impresos",
    layout="wide"
)

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
                           identificador: Optional[str] = None,
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
    
    id_info = f"""
### Identificador
```
{identificador}
```
""" if identificador else ""
    
    return f"""
## Informe Técnico de Cotización
{id_info}
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

def generar_identificador(tipo_impresion: str, material_code: str, ancho: float, avance: float,
                         num_tintas: int, acabado_code: str, nombre_cliente: str, referencia: str,
                         num_rollos: int, consecutivo: int = 1984) -> str:
    """Genera el identificador único para la cotización"""
    tipo = "ET" if "ETIQUETA" in tipo_impresion.upper() else "MT"
    material = material_code.upper()
    medidas = f"{int(ancho)}X{int(avance)}MM"
    
    if "FOIL" in acabado_code.upper():
        tintas = f"{num_tintas}T+FOIL"
        acabado = acabado_code.upper().replace("FOIL", "").replace("+", "").strip()
    else:
        tintas = f"{num_tintas}T"
        acabado = acabado_code.upper()
    
    return f"{tipo} {material} {medidas} {tintas} {acabado} RX{num_rollos} {nombre_cliente.upper()} {referencia.upper()} {consecutivo}"

def calcular_valor_plancha_separado(valor_plancha_dict: Dict) -> float:
    """Calcula el valor de la plancha cuando se cobra por separado"""
    if isinstance(valor_plancha_dict, dict) and 'detalles' in valor_plancha_dict:
        detalles = valor_plancha_dict['detalles']
        if 'precio_sin_constante' in detalles:
            return detalles['precio_sin_constante']
    return 0

def crear_datos_cotizacion(cliente: str, referencia: str, identificador: str, material: str,
                          acabado: str, num_tintas: int, num_rollos: int, valor_troquel: Dict,
                          valor_plancha_separado: Optional[float], resultados: List[Dict]) -> Dict:
    """Crea el diccionario de datos para la cotización"""
    # Extraer el valor numérico del troquel del diccionario
    valor_troquel_final = valor_troquel.get('valor', 0) if isinstance(valor_troquel, dict) else 0
    
    return {
        'consecutivo': 1984,
        'cliente': cliente,
        'referencia': referencia,
        'identificador': identificador,
        'material': material.split('(')[0].strip(),
        'acabado': acabado.split('(')[0].strip(),
        'num_tintas': num_tintas,
        'num_rollos': num_rollos,
        'valor_troquel': valor_troquel_final,
        'valor_plancha_separado': valor_plancha_separado,
        'resultados': resultados
    }

def main():
    st.title("Cotizador Flexo Impresos")
    
    try:
        db = DBManager()
        materiales = db.get_materiales()
        acabados = db.get_acabados()
        tipos_impresion = db.get_tipos_impresion()
        
    except Exception as e:
        st.error(f"Error al conectar con la base de datos: {str(e)}")
        return
    
    # Sección de datos de litografía
    st.header("Datos de la etiquetas o mangas a cotizar")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        ancho = st.number_input("Ancho (mm)", min_value=0.1, max_value=335.0, value=100.0, step=0.1,
                               help="El ancho no puede exceder 335mm")
        avance = st.number_input("Avance/Largo (mm)", min_value=0.1, value=100.0, step=0.1)
        pistas = st.number_input("Número de pistas", min_value=1, value=1, step=1)
        
    with col2:
        num_tintas = st.number_input("Número de tintas", min_value=0, value=4, step=1)
        planchas_por_separado = st.radio("¿Planchas por separado?", 
                                    options=["Sí", "No"], 
                                    index=0, 
                                    horizontal=True)
        troquel_existe = st.radio("¿Existe troquel?", 
                                  options=["Sí", "No"], 
                                  index=1, 
                                  horizontal=True)
        num_rollos = st.number_input("Número de etiquetas por rollo", min_value=1, value=1000, step=100)
    
    with col3:
        tipo_impresion_seleccionado = st.selectbox(
            "Tipo de Impresión",
            options=[(t.id, t.nombre) for t in tipos_impresion],
            format_func=lambda x: x[1]
        )
    
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
                options=[(r.id, r.codigo_referencia) for r in referencias] if referencias else [],
                format_func=lambda x: x[1]
            ) if referencias else None

    # Sección de materiales y acabados
    st.header("Materiales y Acabados")
    col1, col2 = st.columns(2)
    
    with col1:
        es_manga = "MANGA" in tipo_impresion_seleccionado[1].upper()
        materiales_filtrados = [
            m for m in materiales 
            if es_manga and any(code in m.code.upper() for code in ['PVC', 'PETG'])
            or not es_manga
        ]
        
        material_seleccionado = st.selectbox(
            "Material",
            options=[(m.id, f"{m.code} - {m.nombre} (${m.valor:.2f})") for m in materiales_filtrados],
            format_func=lambda x: x[1]
        )

    with col2:
        acabado_seleccionado = (0, "Sin acabado ($0.00)") if es_manga else st.selectbox(
            "Acabado",
            options=[(a.id, f"{a.code} - {a.nombre} (${a.valor:.2f})") for a in acabados],
            format_func=lambda x: x[1]
        )
    
    # Botón para calcular
    if st.button("Calcular", type="primary"):
        try:
            # Configuración inicial
            datos_lito = DatosLitografia(
                ancho=ancho,
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
            
            print("\n=== DEPURACIÓN VALORES PLANCHA Y TROQUEL ===")
            print(f"valor_plancha (original): {valor_plancha}")
            print(f"valor_plancha (tipo): {type(valor_plancha)}")
            print(f"valor_troquel (original): {valor_troquel}")
            print(f"valor_troquel (tipo): {type(valor_troquel)}")
            
            valor_material = extraer_valor_precio(material_seleccionado[1])
            valor_acabado = 0 if es_manga else extraer_valor_precio(acabado_seleccionado[1])
            
            # Cálculo de plancha separada
            valor_plancha_separado = None
            valor_plancha_para_calculo = 0 if planchas_por_separado == "Sí" else valor_plancha
            if planchas_por_separado == "Sí":
                valor_plancha_separado = calcular_valor_plancha_separado(valor_plancha_dict)
                print(f"planchas_por_separado = Sí, valor_plancha_para_calculo = 0")
                print(f"valor_plancha_separado: {valor_plancha_separado}")
            else:
                print(f"planchas_por_separado = No, valor_plancha_para_calculo = {valor_plancha_para_calculo}")
            
            print(f"valor_plancha_para_calculo (final): {valor_plancha_para_calculo}")
            print(f"valor_plancha_para_calculo (tipo): {type(valor_plancha_para_calculo)}")
            
            # Calcular costos
            calculadora = CalculadoraCostosEscala()
            
            # Iniciar captura de la consola
            console_capture.clear()
            console_capture.start()
            
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
            
            # Detener captura de la consola
            console_capture.stop()
            
            if resultados:
                # Mostrar tabla de resultados
                st.subheader("Tabla de Resultados")
                df = generar_tabla_resultados(resultados)
                st.dataframe(df, hide_index=True, use_container_width=True)

                # Agregar sección para mostrar los logs de la consola
                with st.expander("Logs de Depuración (Consola)"):
                    tabs = st.tabs(["Cálculo de Costos", "Cálculo de Litografía"])
                    
                    with tabs[0]:  # Cálculo de Costos
                        logs = console_capture.get_logs()
                        if logs:
                            for log_type, log_content in logs:
                                if log_type == "stderr":
                                    st.error(log_content)
                                else:
                                    # Dividir el log en secciones para mejor visualización
                                    sections = log_content.split("===")
                                    for i, section in enumerate(sections):
                                        if i > 0:  # Ignorar la primera sección vacía
                                            section_title = section.split("\n")[0].strip()
                                            section_content = "\n".join(section.split("\n")[1:])
                                            if section_title:
                                                st.markdown(f"### {section_title}")
                                                st.code(section_content)
                                                st.markdown("---")
                        else:
                            st.write("No hay logs de cálculo de costos disponibles.")
                    
                    with tabs[1]:  # Cálculo de Litografía
                        if logs_litografia:
                            for log_type, log_content in logs_litografia:
                                if log_type == "stderr":
                                    st.error(log_content)
                                else:
                                    # Dividir el log en secciones para mejor visualización
                                    sections = log_content.split("===")
                                    for i, section in enumerate(sections):
                                        if i > 0:  # Ignorar la primera sección vacía
                                            section_title = section.split("\n")[0].strip()
                                            section_content = "\n".join(section.split("\n")[1:])
                                            if section_title:
                                                st.markdown(f"### {section_title}")
                                                st.code(section_content)
                                                st.markdown("---")
                        else:
                            st.write("No hay logs de cálculo de litografía disponibles.")

                # Agregar sección de depuración para el valor de la plancha
                with st.expander("Depuración del Valor de la Plancha"):
                    cols = st.columns(2)
                    
                    with cols[0]:
                        st.subheader("Datos de Entrada")
                        st.write(f"**Tipo de Impresión:** {'Manga' if es_manga else 'Etiqueta'}")
                        st.write(f"**Número de Tintas:** {num_tintas}")
                        st.write(f"**Pistas:** {datos.pistas}")
                        st.write(f"**Ancho:** {datos.ancho} mm")
                        st.write(f"**Avance:** {datos.avance} mm")
                        st.write(f"**Incluye Planchas:** {planchas_por_separado}")
                    
                    with cols[1]:
                        st.subheader("Valores de la Plancha")
                        st.write(f"**Valor Plancha (Original):** ${valor_plancha}")
                        st.write(f"**Valor Plancha (Para Cálculo):** ${valor_plancha_para_calculo}")
                        
                        if planchas_por_separado == "Sí":
                            if valor_plancha_separado is not None:
                                st.write(f"**Valor Plancha Separado:** ${valor_plancha_separado}")
                                st.info("Como 'Planchas por Separado' está configurado como 'Sí', el valor de la plancha para el cálculo es 0, y se utiliza el valor separado para mostrar al cliente.")
                            else:
                                st.error("No se pudo calcular el valor de la plancha separado.")
                    
                    # Mostrar detalles del cálculo de la plancha
                    st.subheader("Detalles del Cálculo de la Plancha")
                    if isinstance(valor_plancha_dict, dict) and 'detalles' in valor_plancha_dict:
                        detalles = valor_plancha_dict['detalles']
                        
                        # Crear una tabla con los detalles
                        detalles_list = []
                        for k, v in detalles.items():
                            if isinstance(v, (int, float)):
                                valor_formateado = f"{v:.2f}" if k != 'constante' else f"{v}"
                            else:
                                valor_formateado = str(v)
                            detalles_list.append({"Parámetro": k, "Valor": valor_formateado})
                        
                        df_detalles = pd.DataFrame(detalles_list)
                        st.table(df_detalles)
                        
                        # Verificar si precio_sin_constante existe
                        if 'precio_sin_constante' in detalles:
                            cols2 = st.columns(2)
                            with cols2[0]:
                                st.write(f"**Precio sin constante:** ${detalles['precio_sin_constante']:.2f}")
                            
                            # Recalcular el precio
                            if 'constante' in detalles and detalles['constante'] != 0:
                                precio_recalculado = detalles['precio_sin_constante'] / detalles['constante']
                                with cols2[1]:
                                    st.write(f"**Precio recalculado:** ${precio_recalculado:.2f}")
                                
                                # Verificar si coincide con el valor original
                                if abs(precio_recalculado - valor_plancha) > 0.01:
                                    st.error(f"**¡Discrepancia en el precio de la plancha!** Recalculado: ${precio_recalculado:.2f}, Original: ${valor_plancha:.2f}")
                    else:
                        st.write("No hay detalles disponibles para el cálculo de la plancha.")
                    
                    # Mostrar la fórmula de cálculo
                    st.subheader("Fórmula de Cálculo")
                    formula = """
                    Precio Plancha = (VALOR_MM * S3 * S4 * num_tintas) / constante
                    
                    Donde:
                    - VALOR_MM = $1.5/mm
                    - S3 = GAP_FIJO + Q3
                    - Q3 = D3 * E3 + C3
                    - D3 = B3 + C3
                    - B3 = ancho
                    - C3 = 0 para mangas o etiquetas con 1 pista, 3 para etiquetas con más de 1 pista
                    - E3 = número de pistas
                    - GAP_FIJO = 50 mm
                    - S4 = mm_unidad_montaje + AVANCE_FIJO
                    - AVANCE_FIJO = 30 mm
                    - constante = 10000000 si planchas_por_separado es True, 1 si no
                    """
                    st.code(formula)
                
                # Agregar sección de depuración para el valor unitario
                with st.expander("Depuración del Valor Unitario"):
                    # Usar tabs para organizar la información
                    tabs_unitario = st.tabs(["Datos de Entrada", "Cálculos por Escala", "Recálculo"])
                    
                    with tabs_unitario[0]:  # Datos de Entrada
                        st.write(f"**Tipo de Impresión:** {'Manga' if es_manga else 'Etiqueta'}")
                        st.write(f"**Número de Tintas:** {num_tintas}")
                        st.write(f"**Pistas:** {datos.pistas}")
                        st.write(f"**Ancho:** {datos.ancho} mm")
                        st.write(f"**Avance:** {datos.avance} mm")
                        st.write(f"**Área Etiqueta:** {datos.area_etiqueta} mm²")
                        st.write(f"**Valor Material:** ${valor_material}/mm²")
                        st.write(f"**Valor Acabado:** ${valor_acabado}/mm²")
                        st.write(f"**Valor Plancha:** ${valor_plancha_para_calculo}")
                        st.write(f"**Valor Troquel:** ${valor_troquel}")
                        st.write(f"**Rentabilidad:** {datos.rentabilidad}%")
                    
                    with tabs_unitario[1]:  # Cálculos por Escala
                        for i, r in enumerate(resultados):
                            st.markdown(f"### Escala: {r['escala']:,}")
                            
                            # Componentes de costos
                            st.write("**Componentes de Costos:**")
                            componentes = {
                                "Montaje": r['montaje'],
                                "MO y Maq": r['mo_y_maq'],
                                "Tintas": r['tintas'],
                                "Papel/lam": r['papel_lam'],
                                "Desperdicio": r['desperdicio'],
                            }
                            
                            # Crear DataFrame para mostrar componentes
                            df_componentes = pd.DataFrame([
                                {"Componente": k, "Valor": f"${v:,.2f}"} 
                                for k, v in componentes.items()
                            ])
                            st.table(df_componentes)
                            
                            # Desglose del desperdicio
                            st.write("**Desglose del Desperdicio:**")
                            desperdicio_info = {
                                "Desperdicio por Tintas": r['desperdicio_tintas'],
                                "Desperdicio por Porcentaje": r['desperdicio_porcentaje'],
                                "Desperdicio Total": r['desperdicio']
                            }
                            df_desperdicio = pd.DataFrame([
                                {"Componente": k, "Valor": f"${v:,.2f}"} 
                                for k, v in desperdicio_info.items()
                            ])
                            st.table(df_desperdicio)
                            
                            # Suma de costos
                            suma_costos = r['montaje'] + r['mo_y_maq'] + r['tintas'] + r['papel_lam'] + r['desperdicio']
                            st.write(f"**Suma de Costos:** ${suma_costos:,.2f}")
                            
                            # Cálculo del valor unitario
                            factor_rentabilidad = (100 - datos.rentabilidad) / 100
                            costos_indirectos = suma_costos / factor_rentabilidad
                            costos_fijos = valor_plancha_para_calculo + valor_troquel
                            costos_totales = costos_indirectos + costos_fijos
                            valor_unidad_calculado = costos_totales / r['escala']
                            
                            st.write("**Cálculo del Valor Unitario:**")
                            st.write(f"Factor Rentabilidad (100 - {datos.rentabilidad})/100: {factor_rentabilidad:.4f}")
                            st.write(f"Costos Indirectos (Suma Costos / Factor Rentabilidad): ${costos_indirectos:,.2f}")
                            st.write(f"Costos Fijos (Valor Plancha + Valor Troquel): ${costos_fijos:,.2f}")
                            st.write(f"Costos Totales (Costos Indirectos + Costos Fijos): ${costos_totales:,.2f}")
                            st.write(f"Valor Unitario (Costos Totales / Escala): ${valor_unidad_calculado:.6f}")
                            st.write(f"Valor Unitario (Almacenado): ${r['valor_unidad']:.6f}")
                            
                            # Verificar si hay discrepancia
                            if abs(valor_unidad_calculado - r['valor_unidad']) > 0.000001:
                                st.error(f"¡Discrepancia detectada! La diferencia es: {valor_unidad_calculado - r['valor_unidad']:.6f}")
                            
                            # Mostrar la fórmula completa
                            st.write("**Fórmula Completa:**")
                            formula = f"""
                            Valor Unitario = (((Suma de Costos) / ((100 - Rentabilidad) / 100)) + (Valor Troquel + Valor Plancha)) / Escala
                            
                            Valor Unitario = ((({suma_costos:,.2f}) / ((100 - {datos.rentabilidad}) / 100)) + ({valor_troquel:,.2f} + {valor_plancha_para_calculo:,.2f})) / {r['escala']:,}
                            
                            Valor Unitario = ((({suma_costos:,.2f}) / {factor_rentabilidad:.4f}) + {costos_fijos:,.2f}) / {r['escala']:,}
                            
                            Valor Unitario = ({costos_indirectos:,.2f} + {costos_fijos:,.2f}) / {r['escala']:,}
                            
                            Valor Unitario = {costos_totales:,.2f} / {r['escala']:,}
                            
                            Valor Unitario = {valor_unidad_calculado:.6f}
                            """
                            st.code(formula)
                            
                            st.markdown("---")
                    
                    with tabs_unitario[2]:  # Recálculo
                        if st.button("Recalcular Valores Unitarios"):
                            st.write("Recalculando valores unitarios con los datos actuales...")
                            
                            # Crear una nueva instancia de la calculadora
                            calculadora_recalculo = CalculadoraCostosEscala()
                            resultados_recalculo = calculadora_recalculo.calcular_costos_por_escala(
                                datos=datos,
                                num_tintas=num_tintas,
                                valor_etiqueta=valor_etiqueta,
                                valor_plancha=valor_plancha_para_calculo,
                                valor_troquel=valor_troquel,
                                valor_material=valor_material,
                                valor_acabado=valor_acabado,
                                es_manga=es_manga
                            )
                            
                            # Mostrar resultados recalculados
                            if resultados_recalculo:
                                df_recalculo = generar_tabla_resultados(resultados_recalculo)
                                st.write("**Tabla de Resultados Recalculados:**")
                                st.dataframe(df_recalculo, hide_index=True, use_container_width=True)
                                
                                # Comparar resultados
                                st.write("**Comparación de Resultados:**")
                                for i, (r_orig, r_recalc) in enumerate(zip(resultados, resultados_recalculo)):
                                    st.write(f"**Escala {r_orig['escala']:,}:**")
                                    st.write(f"Valor Unitario Original: ${r_orig['valor_unidad']:.6f}")
                                    st.write(f"Valor Unitario Recalculado: ${r_recalc['valor_unidad']:.6f}")
                                    st.write(f"Diferencia: ${r_recalc['valor_unidad'] - r_orig['valor_unidad']:.6f}")
                                    st.write("---")
                        else:
                            st.write("Haz clic en el botón para recalcular los valores unitarios.")

                # Separador visual
                st.divider()

                # Informe técnico
                st.subheader("Informe Técnico")
                identificador = generar_identificador(
                    tipo_impresion=tipo_impresion_seleccionado[1],
                    material_code=db.get_material_code(material_seleccionado[0]),
                    ancho=ancho,
                    avance=avance,
                    num_tintas=num_tintas,
                    acabado_code=db.get_acabado_code(acabado_seleccionado[0]),
                    nombre_cliente=cliente_seleccionado[1],
                    referencia=referencia_seleccionada[1],
                    num_rollos=num_rollos,
                    consecutivo=1984
                )
                st.markdown(generar_informe_tecnico(
                    datos, 
                    resultados, 
                    reporte_lito, 
                    num_tintas, 
                    valor_plancha, 
                    valor_material, 
                    valor_acabado, 
                    reporte_lito.get('valor_troquel', 0),
                    valor_plancha_separado,
                    identificador,
                    es_manga=es_manga
                ))
            
                # Generar PDF
                pdf_gen = CotizacionPDF()
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                    datos_cotizacion = crear_datos_cotizacion(
                        cliente=cliente_seleccionado[1],
                        referencia=referencia_seleccionada[1],
                        identificador=identificador,
                        material=material_seleccionado[1],
                        acabado=acabado_seleccionado[1],
                        num_tintas=num_tintas,
                        num_rollos=num_rollos,
                        valor_troquel=reporte_lito.get('valor_troquel', 0),
                        valor_plancha_separado=valor_plancha_separado,
                        resultados=resultados
                    )
                    pdf_gen.generar_pdf(datos_cotizacion, tmp_file.name)
                    
                    with open(tmp_file.name, "rb") as pdf_file:
                        st.download_button(
                            label="Descargar Cotización (PDF)",
                            data=pdf_file,
                            file_name=f"cotizacion_{datos_cotizacion['consecutivo']}.pdf",
                            mime="application/pdf"
                        )
            
            # Calculate the area of the label using the central method
            calculadora_litografia = CalculadoraLitografia()
            calculo_area = calculadora_litografia.calcular_area_etiqueta(datos_lito, num_tintas, datos_lito.avance, datos.pistas, es_manga)
            
            # Set the area in DatosEscala if present
            if 'area' in calculo_area:
                datos.set_area_etiqueta(calculo_area['area'])
            
        except Exception as e:
            st.error(f"Error en el cálculo: {str(e)}")
            import traceback
            st.error(traceback.format_exc())

if __name__ == "__main__":
    main()
