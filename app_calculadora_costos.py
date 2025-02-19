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

def calcular_valor_plancha_separado(valor_plancha: float) -> float:
    """
    Calcula el valor de la plancha por separado según la fórmula de Excel:
    =REDONDEAR.MAS(M3/0.75, -3)
    
    Args:
        valor_plancha: Valor original de la plancha
    
    Returns:
        float: Valor de la plancha redondeado
    """
    # Dividir por 0.75
    valor_ajustado = valor_plancha / 0.75
    
    # Redondear hacia arriba al múltiplo de 1000 más cercano
    valor_redondeado = math.ceil(valor_ajustado / 1000) * 1000
    
    return valor_redondeado

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
    Genera una tabla formateada con los resultados
    """
    df = pd.DataFrame([
        {
            'Escala': f"{r['escala']:,}",
            'Valor Unidad': f"${r['valor_unidad']:.2f}",
            'Valor MM': f"${r['valor_mm']:.3f}",
            'Metros': f"{r['metros']:.2f}",
            'Tiempo (h)': f"{r['tiempo_horas']:.2f}",
            'Montaje': f"${r['montaje']:,.2f}",
            'MO y Maq': f"${r['mo_y_maq']:,.2f}",
            'Tintas': f"${r['tintas']:,.2f}",
            'Papel/lam': f"${r['papel_lam']:,.2f}",
            'Desperdicio': f"${r['desperdicio']:,.2f}"
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
            # Determinar si es manga
            es_manga = "MANGA" in tipo_impresion_seleccionado[1].upper()
            
            # Crear datos de litografía
            datos_lito = DatosLitografia(
                ancho=ancho,
                avance=avance,
                pistas=pistas,
                incluye_planchas=incluye_planchas == "Sí",
                incluye_troquel=True,
                troquel_existe=troquel_existe == "Sí",
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
            valor_plancha = reporte_lito.get('precio_plancha', 0)

            # Obtener valores de material y acabado
            valor_material = float(material_seleccionado[1].split('$')[1].split()[0].replace(')', ''))
            valor_acabado = 0 if es_manga else float(acabado_seleccionado[1].split('$')[1].split()[0].replace(')', ''))

            # Calcular costos usando el método correcto
            calculadora = CalculadoraCostosEscala()
            resultados = calculadora.calcular_costos_por_escala(
                datos=datos,
                num_tintas=num_tintas,
                valor_etiqueta=valor_etiqueta,
                valor_plancha=0 if incluye_planchas == "Sí" else valor_plancha,
                valor_troquel=reporte_lito.get('valor_troquel', 0),
                valor_material=valor_material,
                valor_acabado=valor_acabado,
                es_manga=es_manga
            )
            
            # Si se selecciona "Planchas por separado", calculamos el valor adicional
            valor_plancha_separado = None
            if incluye_planchas == "Sí" and valor_plancha > 0:
                valor_plancha_separado = calcular_valor_plancha_separado(valor_plancha)
            
            # Mostrar tabla de resultados
            st.subheader("Tabla de Resultados")
            df = generar_tabla_resultados(resultados)
            st.dataframe(
                df,
                column_config={
                    "Escala": st.column_config.TextColumn("Escala", help="Cantidad de unidades"),
                    "Valor Unidad": st.column_config.TextColumn("$/Unidad", help="Precio por unidad"),
                    "Valor MM": st.column_config.TextColumn("$MM", help="Valor en millones"),
                    "Metros": st.column_config.TextColumn("Metros", help="Metros lineales"),
                    "Tiempo (h)": st.column_config.TextColumn("Tiempo", help="Tiempo en horas"),
                    "Montaje": st.column_config.TextColumn("Montaje", help="Costo de montaje"),
                    "MO y Maq": st.column_config.TextColumn("MO y Maq", help="Mano de obra y maquinaria"),
                    "Tintas": st.column_config.TextColumn("Tintas", help="Costo de tintas"),
                    "Papel/lam": st.column_config.TextColumn("Papel/lam", help="Costo de papel y laminado"),
                    "Desperdicio": st.column_config.TextColumn("Desperdicio", help="Costo de desperdicio")
                },
                hide_index=True,
                use_container_width=True
            )

            # Separador visual
            st.divider()

            # Informe técnico
            st.subheader("Informe Técnico")
            # Generar un solo identificador
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
            
        except ValueError as e:
            st.error(f"Error: {str(e)}")
            st.info("Por favor revise los valores ingresados e intente nuevamente.")
        except Exception as e:
            st.error(f"Error inesperado: {str(e)}")
            st.info("Por favor contacte al soporte técnico.")

if __name__ == "__main__":
    main()
