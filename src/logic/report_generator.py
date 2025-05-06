import math
from typing import Dict, Any, Optional
import streamlit as st # Importar streamlit para acceder a session_state
import markdown
import base64
from weasyprint import HTML, CSS
import io

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

        info_materiales = f"""
### Información de Materiales
#### Material Base
- **Material**: {material_display}

#### Acabado
- **Tipo**: {acabado_display}
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
    Convierte texto Markdown a un archivo PDF y devuelve el enlace para descarga.
    
    Args:
        markdown_text: Texto en formato Markdown
        filename: Nombre base del archivo PDF a generar (sin extensión)
    
    Returns:
        str: Enlace HTML para descargar el PDF o None si hay error
    """
    try:
        # Convertir Markdown a HTML
        html_text = markdown.markdown(markdown_text)
        
        # Envolver el HTML en una estructura básica con estilos
        html_completo = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Informe Técnico</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                h2 {{ color: #2C3E50; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
                h3 {{ color: #3498DB; margin-top: 25px; }}
                h4 {{ color: #2980B9; margin-top: 20px; }}
                ul {{ padding-left: 20px; }}
            </style>
        </head>
        <body>
            {html_text}
        </body>
        </html>
        """
        
        # Crear un buffer para guardar el PDF
        buffer = io.BytesIO()
        HTML(string=html_completo).write_pdf(buffer)
        
        # Obtener bytes del PDF y codificar en base64
        pdf_data = buffer.getvalue()
        buffer.close()
        
        b64_pdf = base64.b64encode(pdf_data).decode()
        
        # Crear enlace de descarga en HTML
        href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{filename}.pdf" target="_blank">Descargar Informe Técnico PDF</a>'
        
        return href
    
    except Exception as e:
        print(f"Error generando PDF: {e}")
        import traceback
        traceback.print_exc()
        return None
