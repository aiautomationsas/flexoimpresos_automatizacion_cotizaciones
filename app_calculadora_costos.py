import streamlit as st
import pandas as pd
from calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from calculadora_litografia import CalculadoraLitografia, DatosLitografia
from db_manager import DBManager
import tempfile
from pdf_generator import CotizacionPDF
from typing import List, Dict, Optional, Tuple

# Configuración de página
st.set_page_config(
    page_title="Cotizador Flexoimpresos",
    layout="wide"
)

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
    for r in resultados:
        r['desperdicio_total'] = r['desperdicio_tintas'] + r['desperdicio_porcentaje']
    
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
                           valor_acabado: float, reporte_troquel: float = 0, 
                           valor_plancha_separado: Optional[float] = None, 
                           identificador: Optional[str] = None) -> str:
    """Genera un informe técnico detallado"""
    dientes = reporte_lito['desperdicio']['mejor_opcion'].get('dientes', 'N/A')
    gap_avance = datos_entrada.desperdicio + 2.6
    
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
- **Área de Etiqueta**: {reporte_lito['area_etiqueta']:.2f} mm²
- **Dientes**: {dientes}

### Información de Materiales
- **Valor Material**: ${valor_material:.2f}/mm²
- **Valor Acabado**: ${valor_acabado:.2f}/mm²
- **Valor Troquel**: ${reporte_troquel:.2f}

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
                          acabado: str, num_tintas: int, num_rollos: int, valor_troquel: float,
                          valor_plancha_separado: Optional[float], resultados: List[Dict]) -> Dict:
    """Crea el diccionario de datos para la cotización"""
    return {
        'consecutivo': 1984,
        'cliente': cliente,
        'referencia': referencia,
        'identificador': identificador,
        'material': material.split('(')[0].strip(),
        'acabado': acabado.split('(')[0].strip(),
        'num_tintas': num_tintas,
        'num_rollos': num_rollos,
        'valor_troquel': valor_troquel,
        'valor_plancha_separado': valor_plancha_separado,
        'resultados': resultados
    }

def main():
    st.title("Cotizador Flexoimpresos")
    
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
        incluye_planchas = st.radio("¿Planchas por separado?", 
                                    options=["Sí", "No"], 
                                    index=0, 
                                    horizontal=True)
        troquel_existe = st.radio("¿Existe troquel?", 
                                  options=["Sí", "No"], 
                                  index=1, 
                                  horizontal=True)
        num_rollos = st.number_input("Número de rollos", min_value=1, value=1000, step=100)
    
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
                incluye_planchas=incluye_planchas == "Sí",
                incluye_troquel=True,
                troquel_existe=troquel_existe == "Sí",
                gap=0 if es_manga else 3.0,
                gap_avance=0 if es_manga else 2.6
            )
            
            # Cálculos de litografía
            calculadora_lito = CalculadoraLitografia()
            reporte_lito = calculadora_lito.generar_reporte_completo(
                datos_lito, 
                num_tintas,
                es_manga=es_manga
            )
            
            if not reporte_lito['desperdicio'] or not reporte_lito['desperdicio']['mejor_opcion']:
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
                area_etiqueta=reporte_lito['area_etiqueta'] if reporte_lito['area_etiqueta'] else 0
            )
            
            # Obtener valores
            valor_etiqueta = reporte_lito.get('valor_tinta', 0)
            valor_plancha, valor_plancha_dict = obtener_valor_plancha(reporte_lito)
            valor_troquel = obtener_valor_troquel(reporte_lito)
            
            valor_material = extraer_valor_precio(material_seleccionado[1])
            valor_acabado = 0 if es_manga else extraer_valor_precio(acabado_seleccionado[1])
            
            # Cálculo de plancha separada
            valor_plancha_separado = None
            valor_plancha_para_calculo = 0 if incluye_planchas == "Sí" else valor_plancha
            if incluye_planchas == "Sí":
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
                    identificador
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
            
        except Exception as e:
            st.error(f"Error en el cálculo: {str(e)}")
            import traceback
            st.error(traceback.format_exc())

if __name__ == "__main__":
    main()
