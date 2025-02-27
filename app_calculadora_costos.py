import streamlit as st
import pandas as pd
from calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from calculadora_litografia import CalculadoraLitografia, DatosLitografia
import math  # Añadir al inicio del archivo
from db_manager import DBManager
from models import Cotizacion, Escala, Cliente, ReferenciaCliente, TipoImpresion
from decimal import Decimal
import os
from typing import List, Dict
from datetime import datetime
import time
from pdf_generator import CotizacionPDF
import tempfile

# Configuración de página
st.set_page_config(
    page_title="Calculadora de Costos",
    layout="wide"
)

def mostrar_valores_entrada(datos):
    """Muestra los valores de entrada en la interfaz"""
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"- Ancho: {datos.ancho}mm")
        st.write(f"- Avance: {datos.avance_total}mm")
        st.write(f"- Pistas: {datos.pistas}")
    with col2:
        st.write(f"- Área etiqueta: {math.ceil(datos.area_etiqueta)}mm²")
        st.write(f"- Gap al avance: {datos.desperdicio + 2.6:.2f}mm")

def crear_cliente(db: DBManager):
    with st.form("nuevo_cliente"):
        st.subheader("Crear Nuevo Cliente")
        nombre = st.text_input("Nombre del Cliente")
        codigo = st.text_input("Código (opcional)")
        persona_contacto = st.text_input("Persona de Contacto (opcional)")
        correo = st.text_input("Correo Electrónico (opcional)")
        telefono = st.text_input("Teléfono (opcional)")
        
        submitted = st.form_submit_button("Crear Cliente")
        
        if submitted:
            try:
                st.write("=== INICIO PROCESO CREAR CLIENTE ===")
                
                # Validación manual
                if not nombre:
                    st.error("El nombre del cliente es obligatorio")
                    return None
                
                # Generar código único si no se proporciona uno
                if not codigo:
                    codigo = f"CLI_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                
                # Preparar datos RPC
                rpc_data = {
                    'p_nombre': nombre,
                    'p_codigo': codigo,
                    'p_persona_contacto': persona_contacto if persona_contacto else None,
                    'p_correo_electronico': correo if correo else None,
                    'p_telefono': telefono if telefono else None
                }
                
                # Mostrar datos que se enviarán
                st.write("Datos que se enviarán a RPC:")
                st.json(rpc_data)
                
                st.write("Llamando a función RPC 'insertar_cliente'...")
                
                # Llamar directamente a RPC
                response = db.client.rpc('insertar_cliente', rpc_data).execute()
                
                # Mostrar respuesta
                st.write("Respuesta recibida de RPC:")
                st.write(f"Tipo de respuesta: {type(response)}")
                st.write("Datos de respuesta:", response.data if hasattr(response, 'data') else None)
                
                if response.data:
                    nuevo_cliente = Cliente(**response.data[0])
                    st.success(f"✅ Cliente {nuevo_cliente.nombre} creado exitosamente con ID: {nuevo_cliente.id}")
                    
                    # Verificar que el cliente existe
                    verify = db.client.rpc('obtener_clientes').execute()
                    st.write(f"Verificación en base de datos: {verify.data}")
                    
                    time.sleep(1)
                    st.rerun()
                    return nuevo_cliente
                else:
                    st.error("❌ No se pudo crear el cliente - Sin datos en la respuesta")
                    return None
                
            except Exception as e:
                st.error("❌ Error al crear cliente:")
                st.error(str(e))
                st.exception(e)
                return None
            finally:
                st.write("=== FIN PROCESO CREAR CLIENTE ===")

def crear_referencia(db: DBManager, cliente_id: int, tipos_impresion: List[TipoImpresion]):
    with st.form("nueva_referencia"):
        st.subheader("Crear Nueva Referencia")
        
        # Campos obligatorios
        codigo = st.text_input(
            "Código de Referencia *", 
            help="Código único para identificar esta referencia"
        )
        
        # Campos opcionales
        descripcion = st.text_area(
            "Descripción",
            help="Descripción detallada de la referencia"
        )
        
        tipo_impresion = st.selectbox(
            "Tipo de Impresión *",
            options=[(t.id, t.nombre) for t in tipos_impresion],
            format_func=lambda x: x[1],
            help="Seleccione el tipo de impresión para esta referencia"
        )
        
        # Mostrar cliente seleccionado (no editable)
        st.info(f"Cliente ID: {cliente_id}")
        
        # Nota sobre campos requeridos
        st.markdown("*Campo requerido")
        
        # Botón de submit
        submitted = st.form_submit_button("Crear Referencia")
        
        if submitted:
            try:
                st.write("=== INICIO PROCESO CREAR REFERENCIA ===")
                
                # Validación manual
                if not codigo:
                    st.error("El código de referencia es obligatorio")
                    return None
                
                if not tipo_impresion:
                    st.error("El tipo de impresión es obligatorio")
                    return None
                
                # Crear objeto ReferenciaCliente solo con los campos necesarios
                nueva_referencia = ReferenciaCliente(
                    cliente_id=cliente_id,
                    codigo_referencia=codigo,
                    descripcion=descripcion if descripcion else None,
                    tipo_impresion_id=tipo_impresion[0] if tipo_impresion else None,
                    id=None  # Se asignará automáticamente
                )
                
                # Mostrar datos que se van a guardar
                st.write("Datos de la referencia a crear:")
                st.json({
                    'cliente_id': cliente_id,
                    'codigo_referencia': codigo,
                    'descripcion': descripcion,
                    'tipo_impresion_id': tipo_impresion[0] if tipo_impresion else None
                })
                
                # Intentar crear la referencia
                referencia_creada = db.crear_referencia(nueva_referencia)
                
                if referencia_creada:
                    st.success(f"✅ Referencia {referencia_creada.codigo_referencia} creada exitosamente")
                    time.sleep(1)
                    st.rerun()
                    return referencia_creada
                else:
                    st.error("❌ No se pudo crear la referencia")
                    return None
                    
            except Exception as e:
                st.error("❌ Error al crear referencia:")
                st.error(str(e))
                st.exception(e)
                return None
            finally:
                st.write("=== FIN PROCESO CREAR REFERENCIA ===")

def calcular_valor_plancha_separado(valor_plancha_dict):
    """
    Calcula el valor de la plancha cuando se cobra por separado.
    Extrae el precio_sin_constante del diccionario de detalles.
    """
    if isinstance(valor_plancha_dict, dict) and 'detalles' in valor_plancha_dict:
        detalles = valor_plancha_dict['detalles']
        if 'precio_sin_constante' in detalles:
            return detalles['precio_sin_constante']
    return 0

def generar_informe_tecnico(
    datos_entrada, 
    resultados, 
    reporte_lito, 
    num_tintas, 
    valor_plancha, 
    valor_material, 
    valor_acabado, 
    reporte_troquel=0,
    valor_plancha_separado=None,
    identificador=None
):
    """
    Genera un informe técnico detallado con todas las variables usadas
    """
    # Obtener información de dientes
    dientes = reporte_lito['desperdicio']['mejor_opcion'].get('dientes', 'N/A')
    
    # Calcular gap al avance
    gap_avance = datos_entrada.desperdicio + 2.6
    
    # Agregar sección de plancha separada si aplica
    plancha_separada_info = ""
    if valor_plancha_separado is not None:
        plancha_separada_info = f"""
### Información de Plancha Separada
- **Valor Plancha Original**: ${valor_plancha:.2f}
- **Valor Plancha Ajustado**: ${valor_plancha_separado:.2f}
"""
    
    # Generar sección de identificador
    identificador_info = ""
    if identificador:
        identificador_info = f"""
### Identificador
```
{identificador}
```
"""
    
    informe = f"""
## Informe Técnico de Cotización
{identificador_info}
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

{plancha_separada_info}
"""
    return informe

def generar_tabla_resultados(resultados: List[Dict]) -> pd.DataFrame:
    """
    Genera una tabla formateada con los resultados de la cotización
    
    Args:
        resultados: Lista de diccionarios con los resultados por escala
        
    Returns:
        DataFrame: Tabla formateada para mostrar en la interfaz
    """
    # Asegurar que desperdicio_total sea la suma correcta
    for r in resultados:
        r['desperdicio_total'] = r['desperdicio_tintas'] + r['desperdicio_porcentaje']
    
    df = pd.DataFrame([
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
            'Desperdicio': f"${r['desperdicio_tintas']:,.2f} + ${r['desperdicio_porcentaje']:,.2f} = ${r['desperdicio_total']:,.2f}"
        }
        for r in resultados
    ])
    
    return df

def generar_identificador(
    tipo_impresion: str,
    material_code: str,
    ancho: float,
    avance: float,
    num_tintas: int,
    acabado_code: str,
    nombre_cliente: str,
    referencia: str,
    num_rollos: int,
    consecutivo: int = 1984
) -> str:
    """
    Genera el identificador único según las reglas especificadas
    
    Ejemplo: ET BOPP 100X81MM 4T LAM RX1000 CLIENTE REF 1984
    """
    # 1. Tipo de impresión (ET o MT)
    tipo = "ET" if "ETIQUETA" in tipo_impresion.upper() else "MT"
    
    # 2. Material code
    material = material_code.upper()
    
    # 3. Medidas
    medidas = f"{int(ancho)}X{int(avance)}MM"
    
    # 4. Tintas y acabado
    if "FOIL" in acabado_code.upper():
        tintas = f"{num_tintas}T+FOIL"
        # Remover FOIL del código de acabado
        acabado = acabado_code.upper().replace("FOIL", "").replace("+", "").strip()
    else:
        tintas = f"{num_tintas}T"
        acabado = acabado_code.upper()
    
    # 5. Rollos (usando el valor del usuario)
    rollos_str = f"RX{num_rollos}"
    
    # 6. Cliente y referencia
    cliente = nombre_cliente.upper()
    ref = referencia.upper()
    
    # Construir identificador
    identificador = f"{tipo} {material} {medidas} {tintas} {acabado} {rollos_str} {cliente} {ref} {consecutivo}"
    
    return identificador

# Obtener valores de material y acabado de forma más segura
def extraer_valor_precio(texto: str) -> float:
    """Extrae el valor numérico de un string con formato 'nombre ($valor)'"""
    try:
        # Encuentra el valor entre paréntesis
        inicio = texto.find('($') + 2
        fin = texto.find(')')
        if inicio > 1 and fin > inicio:
            return float(texto[inicio:fin].strip())
        return 0.0
    except:
        return 0.0

def calcular_ancho_total(num_tintas: int, pistas: int, ancho: float, gap_constante: float = 3.0) -> float:
    """
    Calcula el ancho total según la fórmula de Excel:
    =REDONDEAR.MAS(SI(tintas=0;((pistas*(ancho+gap)-gap)+10);((pistas*(ancho+gap)-gap)+20));-1)
    """
    # Primero calculamos ancho + gap
    ancho_con_gap = ancho + gap_constante
    
    if num_tintas == 0:
        # ((pistas * (ancho + gap) - gap) + 10)
        ancho_total = ((pistas * ancho_con_gap - gap_constante) + 10)
    else:
        # ((pistas * (ancho + gap) - gap) + 20)
        ancho_total = ((pistas * ancho_con_gap - gap_constante) + 20)
    
    # Redondear hacia arriba a la decena más cercana
    return math.ceil(ancho_total / 10) * 10

def main():
    st.title("Cotizador Flexoimpresos")
    
    # Inicializar DBManager y cargar datos
    try:
        db = DBManager()
        materiales = db.get_materiales()
        acabados = db.get_acabados()
        comerciales = db.get_comerciales()
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
    
    try:
        escalas = [int(x.strip()) for x in escalas_text.split(",")]
    except ValueError:
        st.error("Por favor ingrese números válidos separados por comas")
        return
    
    # Sección de cliente y referencia
    st.header("Datos del Cliente")
    col1, col2 = st.columns(2)
    
    with col1:
        clientes = db.get_clientes()
        if clientes:
            cliente_seleccionado = st.selectbox(
                "Cliente",
                options=[(c.id, c.nombre) for c in clientes],
                format_func=lambda x: x[1]
            )
        else:
            st.warning("No hay clientes registrados")
            cliente_seleccionado = None
        
        # Botón deshabilitado
        st.button("Crear Nuevo Cliente", disabled=True)

    with col2:
        if cliente_seleccionado:
            referencias = db.get_referencias_cliente(cliente_seleccionado[0])
            if referencias:
                referencia_seleccionada = st.selectbox(
                    "Referencia",
                    options=[(r.id, r.codigo_referencia) for r in referencias],
                    format_func=lambda x: x[1]
                )
            else:
                st.info("Este cliente no tiene referencias")
                referencia_seleccionada = None
            
            # Botón deshabilitado
            st.button("Crear Nueva Referencia", disabled=True)

    # Sección de materiales y acabados
    st.header("Materiales y Acabados")
    col1, col2 = st.columns(2)
    
    with col1:
        # Determinar si es manga
        es_manga = "MANGA" in tipo_impresion_seleccionado[1].upper()
        
        # Filtrar materiales según el tipo de impresión
        materiales_filtrados = []
        if es_manga:
            # Solo PVC y PETG para mangas
            materiales_filtrados = [
                m for m in materiales 
                if any(code in m.code.upper() for code in ['PVC', 'PETG'])
            ]
        else:
            # Todos los materiales para etiquetas
            materiales_filtrados = materiales
        
        material_seleccionado = st.selectbox(
            "Material",
            options=[(m.id, f"{m.code} - {m.nombre} (${m.valor:.2f})") for m in materiales_filtrados],
            format_func=lambda x: x[1]
        )
        
        num_rollos = st.selectbox(
            "Número de Rollos",
            options=[200, 500, 1000, 2000, 5000, 10000]
        )

    with col2:
        if es_manga:
            st.text("Acabado: No aplica para mangas")
            acabado_seleccionado = (0, "Sin acabado ($0.00)")  # Valor por defecto para mangas
        else:
            acabado_seleccionado = st.selectbox(
                "Acabado",
                options=[(a.id, f"{a.code} - {a.nombre} (${a.valor:.2f})") for a in acabados],
                format_func=lambda x: x[1]
            )
    
    # Botón para calcular
    if st.button("Calcular", type="primary"):
        try:
            # Inicializar resultados
            resultados = None
            
            # Determinar si es manga
            es_manga = "MANGA" in tipo_impresion_seleccionado[1].upper()
            
            # Crear datos de litografía
            datos_lito = DatosLitografia(
                ancho=ancho,
                avance=avance,
                pistas=pistas,
                incluye_planchas=incluye_planchas == "Sí",
                incluye_troquel=True,  # Siempre incluir el cálculo del troquel
                troquel_existe=troquel_existe == "Sí",  # Indicar si el troquel ya existe
                gap=0 if es_manga else 3.0,  # Gap 0 para mangas
                gap_avance=0 if es_manga else 2.6  # Gap avance 0 para mangas
            )
            
            # Generar reporte de litografía
            calculadora_lito = CalculadoraLitografia()
            reporte_lito = calculadora_lito.generar_reporte_completo(
                datos_lito, 
                num_tintas,
                es_manga=es_manga
            )
            
            # Verificar si tenemos la mejor opción de desperdicio
            if not reporte_lito['desperdicio'] or not reporte_lito['desperdicio']['mejor_opcion']:
                st.error("No se pudo calcular el desperdicio. Por favor revise los valores de ancho y avance.")
                return
            
            mejor_opcion = reporte_lito['desperdicio']['mejor_opcion']
            
            # Crear datos para calculadora de costos
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
            
            # Obtener valor de plancha del reporte
            valor_plancha_dict = reporte_lito.get('precio_plancha', {'precio': 0})
            valor_plancha = valor_plancha_dict['precio'] if isinstance(valor_plancha_dict, dict) else valor_plancha_dict
            
            # Obtener valor del troquel del reporte
            valor_troquel_dict = reporte_lito.get('valor_troquel', {'valor': 0})
            valor_troquel_base = valor_troquel_dict['valor'] if isinstance(valor_troquel_dict, dict) else valor_troquel_dict
            valor_troquel = valor_troquel_base

            # Obtener valores de material y acabado
            valor_material = extraer_valor_precio(material_seleccionado[1])
            valor_acabado = 0 if es_manga else extraer_valor_precio(acabado_seleccionado[1])

            # Si se selecciona "Planchas por separado", calculamos el valor adicional
            valor_plancha_separado = None
            if incluye_planchas == "Sí":
                # Calcular el valor de la plancha por separado
                valor_plancha_separado = calcular_valor_plancha_separado(valor_plancha_dict)
                # Pasar 0 como valor de plancha al cálculo (ya que se cobrará por separado)
                valor_plancha_para_calculo = 0
            else:
                # Incluir el valor de la plancha en el cálculo
                valor_plancha_para_calculo = valor_plancha

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
            
            # Solo mostrar resultados si se calcularon correctamente
            if resultados:
                # Mostrar tabla de resultados
                st.subheader("Tabla de Resultados")
                df = generar_tabla_resultados(resultados)
                st.dataframe(df, hide_index=True, use_container_width=True)

                # Análisis detallado de desperdicio
                r = resultados[0]
                
                st.subheader("Análisis Detallado de Desperdicio")
                
                # Campos para ingresar valores de referencia y métricas
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    desperdicio_tintas_esperado = st.number_input(
                        "Desperdicio Tintas Esperado ($)", 
                        value=0.0, 
                        format="%.2f"
                    )
                    st.metric("Desperdicio Tintas Calculado", f"${r['desperdicio_tintas']:.2f}")
                
                with col2:
                    desperdicio_porcentaje_esperado = st.number_input(
                        "Desperdicio Porcentaje Esperado ($)", 
                        value=0.0, 
                        format="%.2f"
                    )
                    st.metric("Desperdicio Porcentaje Calculado", f"${r['desperdicio_porcentaje']:.2f}")
                
                with col3:
                    desperdicio_total_esperado = st.number_input(
                        "Desperdicio Total Esperado ($)", 
                        value=0.0, 
                        format="%.2f"
                    )
                    st.metric("Desperdicio Total Calculado", f"${r['desperdicio']:.2f}")

                # 2. Luego mostrar la fórmula y el desglose
                st.subheader("Fórmula de Desperdicio de Tintas")
                
                # Calcular valores
                mm_totales = 30000 * r['num_tintas']
                ancho_total = calcular_ancho_total(r['num_tintas'], datos.pistas, r['ancho'])
                
                # Mostrar el cálculo paso a paso
                st.markdown("### Cálculo Paso a Paso")
                ancho_con_gap = r['ancho'] + 3  # gap constante de 3

                if r['num_tintas'] == 0:
                    formula = f"((pistas * (ancho + gap) - gap) + 10)"
                    calculo = f"(({datos.pistas} * ({r['ancho']} + 3) - 3) + 10)"
                else:
                    formula = f"((pistas * (ancho + gap) - gap) + 20)"
                    calculo = f"(({datos.pistas} * ({r['ancho']} + 3) - 3) + 20)"
                
                st.markdown(f"""
                1. MM Totales = 30,000 × {r['num_tintas']} = {mm_totales}
                2. Ancho Total = {ancho_total} mm (redondeado hacia arriba)
                3. Desperdicio = (MM Totales × Valor Material × (Ancho Total + 40)) ÷ 1,000,000
                   = ({mm_totales} × {valor_material:.6f} × ({ancho_total} + 40)) ÷ 1,000,000
                   = ${r['desperdicio_tintas']:.2f}
                """)

                # Actualizar la tabla de desglose
                calculo_data = {
                    "Componente": [
                        "MM por Color", 
                        "Número de Tintas", 
                        "MM Totales",
                        "Ancho Total",
                        "Gap Planchas",
                        "Ancho Total + Gap",
                        "Valor Material", 
                        "Fórmula",
                        "Desperdicio Tintas"
                    ],
                    "Valor": [
                        f"{30000}", 
                        f"{r['num_tintas']}", 
                        f"{mm_totales}",
                        f"{ancho_total} mm",
                        f"{40} mm",
                        f"{ancho_total + 40} mm",
                        f"${valor_material:.6f}/mm²", 
                        f"({mm_totales} × {valor_material:.6f} × ({ancho_total} + 40)) ÷ 1,000,000",
                        f"${r['desperdicio_tintas']:.2f}"
                    ]
                }
                
                st.dataframe(pd.DataFrame(calculo_data), hide_index=True, use_container_width=True)
                
                # Explicación de la fórmula
                st.markdown("""
                **Fórmula de Ancho Total:**
                ```
                Si tintas = 0:
                    Ancho Total = ((pistas * (ancho + gap - gap)) + 10)
                Si no:
                    Ancho Total = ((pistas * ancho + gap - gap) + 20)
                ```
                donde:
                - gap constante = 3 mm
                - El resultado se redondea hacia arriba
                """)

            # Separador visual
            st.divider()

            # Informe técnico
            st.subheader("Informe Técnico")
            # Generar identificador
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
                datos_cotizacion = {
                    'consecutivo': 1984,
                    'cliente': cliente_seleccionado[1],
                    'referencia': referencia_seleccionada[1],
                    'identificador': identificador,
                    'material': material_seleccionado[1].split('(')[0].strip(),
                    'acabado': acabado_seleccionado[1].split('(')[0].strip(),
                    'num_tintas': num_tintas,
                    'num_rollos': num_rollos,
                    'valor_troquel': reporte_lito.get('valor_troquel', 0),
                    'valor_plancha_separado': valor_plancha_separado,
                    'resultados': resultados
                }
                pdf_gen.generar_pdf(datos_cotizacion, tmp_file.name)
                
                # Botón para descargar PDF
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
