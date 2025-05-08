import math
from typing import Dict, Any, Optional
import streamlit as st # Importar streamlit para acceder a session_state
import markdown
import base64
import io
import sys
import os
import traceback

# Eliminar importación y verificación de WeasyPrint
# Importar solo ReportLab
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListItem, ListFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from src.config.constants import GAP_AVANCE_MANGAS, GAP_AVANCE_ETIQUETAS
# Importar DBManager si es necesario para type hinting, aunque lo usemos de session_state
from src.data.database import DBManager 

def generar_informe_tecnico_markdown(
    cotizacion_data: Dict[str, Any],
    calculos_guardados: Dict[str, Any]
) -> str:
    """
    Genera un informe técnico detallado en formato Markdown a partir de los
    datos completos de la cotización y los resultados del cálculo.

    Args:
        cotizacion_data: Diccionario con los datos completos de la cotización,
                         incluyendo IDs y otros campos planos.
        calculos_guardados: Diccionario con los resultados clave del cálculo.

    Returns:
        str: El informe técnico formateado en Markdown.
    """
    try:
        # Acceder a la instancia de DBManager desde session_state
        if 'db' not in st.session_state:
            return "Error: No se pudo acceder a la base de datos desde session_state."
        db: DBManager = st.session_state.db
        
        # Verificar el rol del usuario para determinar si se muestran los valores finales
        es_comercial = st.session_state.get('usuario_rol') == 'comercial'
        
        # --- Extracción Segura de Datos Clave de cotizacion_data ---
        es_manga = cotizacion_data.get('es_manga', False)
        identificador = cotizacion_data.get('identificador', 'N/A')
        numero_cotizacion = cotizacion_data.get('numero_cotizacion', 'N/A')
        cliente_nombre = cotizacion_data.get('cliente_nombre', 'N/A')
        referencia_desc = cotizacion_data.get('referencia_descripcion', 'N/A')
        comercial_nombre = cotizacion_data.get('comercial_nombre', 'N/A')
        ancho = cotizacion_data.get('ancho', 0.0)
        avance = cotizacion_data.get('avance', 0.0)
        pistas = cotizacion_data.get('numero_pistas', 1)
        num_tintas = cotizacion_data.get('num_tintas', 0)

        # --- Obtener Detalles de Material, Acabado, Adhesivo usando IDs --- 
        material_id = cotizacion_data.get('material_id')
        acabado_id = cotizacion_data.get('acabado_id')
        adhesivo_id = cotizacion_data.get('adhesivo_id') # Puede ser None
        tipo_foil_nombre = cotizacion_data.get('tipo_foil_nombre') # Obtener tipo_foil_nombre
        
        # +++ DEBUG: Imprimir ID de material +++
        print(f"\n--- DEBUG Report Generator ---")
        print(f"Material ID recibido: {material_id} (Tipo: {type(material_id)})")
        # +++ FIN DEBUG +++
        
        # Obtener Material
        material_obj = db.get_material(material_id) if material_id else None
        # +++ DEBUG: Imprimir objeto material obtenido +++
        print(f"Material Obj obtenido de DB: {material_obj}")
        if material_obj:
             print(f"Atributos de material_obj: {dir(material_obj)}")
        print("----------------------------\n")
        # +++ FIN DEBUG +++
        
        # material_code = getattr(material_obj, 'codigo', 'N/A') # Columna 'codigo' no existe en 'materiales'
        material_nombre = getattr(material_obj, 'nombre', 'N/A')
        material_display = material_nombre # Usar solo el nombre ya que no hay código
        # material_descripcion = getattr(material_obj, 'descripcion', '') # Columna no existe
        # material_proveedor = getattr(material_obj, 'proveedor', 'N/A') # Columna no existe
        
        # Obtener Acabado (solo si no es manga)
        acabado_obj = None
        acabado_display = 'N/A (Manga)'
        acabado_descripcion = ''
        if not es_manga and acabado_id:
            acabado_obj = db.get_acabado(acabado_id)
            acabado_code = getattr(acabado_obj, 'codigo', 'N/A')
            acabado_nombre = getattr(acabado_obj, 'nombre', 'N/A')
            acabado_display = f"{acabado_code} - {acabado_nombre}" if acabado_code != 'N/A' else acabado_nombre
            acabado_descripcion = getattr(acabado_obj, 'descripcion', '') # Asumiendo que esta sí existe en 'acabados'
            
        # Obtener Adhesivo (solo si no es manga y tiene ID)
        adhesivo_obj = None
        adhesivo_nombre = 'N/A (Manga)'
        # adhesivo_descripcion = '' # Columna no existe
        if not es_manga and adhesivo_id:
            try:
                todos_adhesivos = db.get_adhesivos()
                adhesivo_obj = next((ad for ad in todos_adhesivos if ad.id == adhesivo_id), None)
            except Exception as e_fetch_ad:
                print(f"Error obteniendo o filtrando adhesivos: {e_fetch_ad}")
                adhesivo_obj = None 
                
            if adhesivo_obj:
                # Usar la columna 'tipo' en lugar de 'nombre'
                adhesivo_nombre = getattr(adhesivo_obj, 'tipo', 'N/A') 
                # adhesivo_descripcion = getattr(adhesivo_obj, 'descripcion', '') # Columna no existe
            else:
                adhesivo_nombre = f"N/A (ID: {adhesivo_id} no encontrado)"
                # adhesivo_descripcion = ''

        # --- Datos del Cálculo (Usando calculos_guardados) ---
        dientes = calculos_guardados.get('unidad_z_dientes', 'N/A')
        valor_material = calculos_guardados.get('valor_material', 0.0)
        valor_acabado = calculos_guardados.get('valor_acabado', 0.0)
        valor_troquel = calculos_guardados.get('valor_troquel', 0.0)
        valor_plancha = calculos_guardados.get('valor_plancha', 0.0)
        valor_plancha_separado = calculos_guardados.get('valor_plancha_separado')

        # --- Cálculos Derivados para el Informe ---
        gap_avance = GAP_AVANCE_MANGAS if es_manga else GAP_AVANCE_ETIQUETAS
        area_etiqueta = ancho * avance

        # Formato para plancha separada
        plancha_info = ""
        if not es_comercial and valor_plancha_separado is not None and valor_plancha_separado > 0:
            valor_plancha_original_calculo = valor_plancha
            plancha_info = f"""
### Información de Plancha Separada
- **Valor Plancha Calculado (Incluido en Costo):** ${valor_plancha_original_calculo:,.2f}
- **Valor Plancha Cobrado por Separado:** ${valor_plancha_separado:,.2f}
"""

        # --- Construcción del Informe Markdown --- (Sin cambios en la estructura, solo usa los datos obtenidos arriba)
        header = f"""
## Informe Técnico de Cotización
- **Identificador Único**: {identificador}
- **Número Cotización**: {numero_cotizacion}
- **Cliente**: {cliente_nombre}
- **Referencia**: {referencia_desc}
- **Comercial**: {comercial_nombre}
"""

        params_impresion = f"""
### Parámetros de Impresión
- **Ancho**: {ancho:.2f} mm
- **Avance/Largo**: {avance:.2f} mm
- **Gap al avance**: {gap_avance:.2f} mm
- **Pistas**: {pistas}
- **Número de Tintas**: {num_tintas}
- **Área de Etiqueta/Manga**: {area_etiqueta:.2f} mm²
- **Unidad (Z - Dientes Cilindro)**: {dientes}
"""

        # --- Modificar info_materiales para incluir Tipo de Foil --- 
        foil_info_str = ""
        if acabado_id in [5, 6] and tipo_foil_nombre:
            foil_info_str = f"\n- **Tipo de Foil**: {tipo_foil_nombre}"

        info_materiales = f"""
### Información de Materiales
#### Material Base
- **Material**: {material_display}

#### Acabado
- **Tipo**: {acabado_display}{foil_info_str}
{f"- **Descripción**: {acabado_descripcion}" if acabado_descripcion and not es_manga else ""}

#### Adhesivo
- **Tipo**: {adhesivo_nombre}
"""

        # Sección de costos base - solo visible para administradores
        costos_base = ""
        if not es_comercial:
            costos_base = f"""
### Costos Base Utilizados
- **Valor Material Base (por m²)**: ${valor_material:,.2f}/m²
- **Valor Acabado (por m²)**: ${valor_acabado:,.2f}/m²
- **Valor Troquel (Total)**: ${valor_troquel:,.2f}
"""

        # Ensamblar informe final
        informe_completo = f"{header}\n{params_impresion}\n{info_materiales}\n{costos_base}\n{plancha_info}"

        return informe_completo

    except Exception as e:
        print(f"Error generando informe técnico markdown: {e}")
        import traceback
        traceback.print_exc()
        return f"Error al generar el informe técnico: {str(e)}"

def markdown_a_pdf(markdown_text: str, filename: str) -> Optional[str]:
    """
    Convierte texto Markdown a un archivo PDF usando ReportLab
    y devuelve el enlace para descarga.
    
    Args:
        markdown_text: Texto en formato Markdown
        filename: Nombre base del archivo PDF a generar (sin extensión)
    
    Returns:
        str: Enlace HTML para descargar el PDF o None si hay error
    """
    try:
        # Usar directamente la implementación de ReportLab
        return _generar_pdf_reportlab(markdown_text, filename)
    except Exception as e:
        print(f"Error generando PDF: {e}")
        traceback.print_exc()
        return None

def _generar_pdf_reportlab(markdown_text: str, filename: str) -> Optional[str]:
    """
    Implementación usando ReportLab para generar PDF.
    
    Esta función convierte el Markdown a formato ReportLab simplificado.
    No es una conversión completa pero funciona para informes básicos.
    """
    try:
        # Crear un buffer para guardar el PDF
        buffer = io.BytesIO()
        
        # Configurar el documento PDF
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            title="Informe Técnico",
            author="Sistema de Cotización Flexo Impresos"
        )
        
        # Obtener los estilos base y modificarlos en lugar de intentar agregarlos
        styles = getSampleStyleSheet()
        
        # Modificar el estilo Heading2 existente
        styles['Heading2'].fontSize = 14
        styles['Heading2'].textColor = colors.HexColor('#2C3E50')
        styles['Heading2'].spaceAfter = 10
        styles['Heading2'].borderColor = colors.HexColor('#EEEEEE')
        styles['Heading2'].borderWidth = 1
        styles['Heading2'].borderPadding = (0, 0, 5, 0)

        # Modificar el estilo Heading3 existente
        styles['Heading3'].fontSize = 12
        styles['Heading3'].textColor = colors.HexColor('#3498DB')
        styles['Heading3'].spaceAfter = 8
        styles['Heading3'].spaceBefore = 15
        
        # Modificar el estilo Heading4 existente
        styles['Heading4'].fontSize = 10
        styles['Heading4'].textColor = colors.HexColor('#2980B9')
        styles['Heading4'].spaceAfter = 6
        styles['Heading4'].spaceBefore = 12
        
        # Modificar el estilo Normal existente
        styles['Normal'].fontSize = 10
        styles['Normal'].leading = 14
        
        # Crear un nuevo estilo para elementos de lista
        styles.add(ParagraphStyle(
            name='ListItemStyle',  # Nombre único para evitar conflictos
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            leftIndent=20
        ))
        
        # Procesar el markdown línea por línea para convertirlo a elementos ReportLab
        elements = []
        
        # Procesar el Markdown de forma básica
        lines = markdown_text.split('\n')
        in_list = False
        list_items = []
        
        for line in lines:
            line = line.strip()
            if not line:
                # Espacio en blanco
                if in_list:
                    # Finalizar lista anterior
                    list_flowable = ListFlowable(
                        list_items,
                        bulletType='bullet',
                        leftIndent=20
                    )
                    elements.append(list_flowable)
                    list_items = []
                    in_list = False
                elements.append(Spacer(1, 10))
                continue
                
            # Procesar encabezados
            if line.startswith('## '):
                if in_list:
                    # Finalizar lista anterior
                    list_flowable = ListFlowable(
                        list_items,
                        bulletType='bullet',
                        leftIndent=20
                    )
                    elements.append(list_flowable)
                    list_items = []
                    in_list = False
                    
                text = line[3:]
                elements.append(Paragraph(text, styles['Heading2']))
            elif line.startswith('### '):
                if in_list:
                    # Finalizar lista anterior
                    list_flowable = ListFlowable(
                        list_items,
                        bulletType='bullet',
                        leftIndent=20
                    )
                    elements.append(list_flowable)
                    list_items = []
                    in_list = False
                    
                text = line[4:]
                elements.append(Paragraph(text, styles['Heading3']))
            elif line.startswith('#### '):
                if in_list:
                    # Finalizar lista anterior
                    list_flowable = ListFlowable(
                        list_items,
                        bulletType='bullet',
                        leftIndent=20
                    )
                    elements.append(list_flowable)
                    list_items = []
                    in_list = False
                    
                text = line[5:]
                elements.append(Paragraph(text, styles['Heading4']))
            # Procesar elementos de lista
            elif line.startswith('- '):
                text = line[2:]
                # Convertir formato markdown para negrita en rich text reportlab
                text = text.replace('**', '<b>', 1)
                text = text.replace('**', '</b>', 1)
                list_items.append(ListItem(Paragraph(text, styles['ListItemStyle'])))
                in_list = True
            else:
                if in_list:
                    # Finalizar lista anterior
                    list_flowable = ListFlowable(
                        list_items,
                        bulletType='bullet',
                        leftIndent=20
                    )
                    elements.append(list_flowable)
                    list_items = []
                    in_list = False
                # Párrafo normal
                elements.append(Paragraph(line, styles['Normal']))
        
        # Verificar si hay una lista pendiente al final
        if in_list and list_items:
            list_flowable = ListFlowable(
                list_items,
                bulletType='bullet',
                leftIndent=20
            )
            elements.append(list_flowable)
        
        # Construir el documento
        doc.build(elements)
        
        # Obtener bytes del PDF y codificar en base64
        pdf_data = buffer.getvalue()
        buffer.close()
        
        b64_pdf = base64.b64encode(pdf_data).decode()
        
        # Crear enlace de descarga en HTML
        href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{filename}.pdf" target="_blank">Descargar Informe Técnico PDF</a>'
        
        return href
    
    except Exception as e:
        print(f"Error generando PDF con ReportLab: {e}")
        traceback.print_exc()
        return None
