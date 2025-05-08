import streamlit as st
import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import tempfile
from decimal import Decimal

from src.logic.report_generator import generar_informe_tecnico
# --- Temporarily removed import as the module doesn't exist yet ---
# from src.logic.calculation_helpers import (
#     generar_tabla_resultados,
#     calcular_totales_cotizacion,
#     formatear_moneda
# )
from src.pdf.pdf_generator import CotizacionPDF, MaterialesPDF

def show_quote_header(cotizacion_data: Dict) -> None:
    """Muestra el encabezado de la cotización con información básica."""
    # Crear contenedor con estilo para el encabezado
    with st.container():
        st.markdown("""
            <style>
            .quote-header {
                background-color: #f8f9fa;
                padding: 1rem;
                border-radius: 5px;
                margin-bottom: 1rem;
            }
            </style>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("### Información del Cliente")
            st.write(f"**Cliente:** {cotizacion_data['cliente']['nombre']}")
            st.write(f"**Contacto:** {cotizacion_data['cliente']['persona_contacto']}")
            st.write(f"**Referencia:** {cotizacion_data['referencia']['descripcion']}")
        
        with col2:
            st.markdown("### Detalles del Producto")
            st.write(f"**Tipo:** {cotizacion_data['tipo_producto']['nombre']}")
            st.write(f"**Material:** {cotizacion_data['material']['nombre']}")
            if not cotizacion_data.get('es_manga'):
                st.write(f"**Acabado:** {cotizacion_data['acabado']['nombre']}")
                # --- INICIO: Mostrar Tipo de Foil --- 
                tipo_foil_nombre = cotizacion_data.get('tipo_foil_nombre')
                acabado_id = cotizacion_data.get('acabado_id')
                if acabado_id in [5, 6] and tipo_foil_nombre:
                    st.write(f"**Tipo de Foil:** {tipo_foil_nombre}")
                # --- FIN: Mostrar Tipo de Foil ---
        
        with col3:
            st.markdown("### Información de Cotización")
            fecha = datetime.now().strftime("%d/%m/%Y")
            st.write(f"**Fecha:** {fecha}")
            st.write(f"**Comercial:** {cotizacion_data['comercial']['nombre']}")
            if cotizacion_data.get('numero_cotizacion'):
                st.write(f"**Cotización #:** {cotizacion_data['numero_cotizacion']}")

def show_results_table(resultados: List[Dict], es_manga: bool) -> None:
    """Muestra la tabla de resultados con formato mejorado."""
    st.subheader("Resultados por Escala")
    
    # Generar tabla de resultados
    # tabla = generar_tabla_resultados(resultados, es_manga) # TODO: Uncomment when calculation_helpers exists
    tabla = pd.DataFrame(resultados) # Placeholder: Display raw data for now
    
    # Aplicar formato condicional
    def highlight_row(row):
        """Aplica formato condicional a las filas."""
        mejor_precio = row['Valor Unidad'] == row['Valor Unidad'].min()
        return ['background-color: #e6ffe6' if mejor_precio else '' for _ in row]
    
    # Mostrar tabla con estilo
    st.dataframe(
        tabla.style.apply(highlight_row, axis=1),
        hide_index=True,
        use_container_width=True
    )
    
    # Mostrar totales
    # totales = calcular_totales_cotizacion(resultados) # TODO: Uncomment when calculation_helpers exists
    totales = {'mejor_precio_unitario': 0, 'escala_optima': 0, 'margen_promedio': 0} # Placeholder
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Mejor Precio Unitario", 
                 f"${totales['mejor_precio_unitario']:,.2f}") # Placeholder format
                 # formatear_moneda(totales['mejor_precio_unitario'])) # TODO: Uncomment when calculation_helpers exists
    with col2:
        st.metric("Escala Óptima", 
                 f"{totales['escala_optima']:,}")
    with col3:
        st.metric("Margen Promedio", 
                 f"{totales['margen_promedio']:.1f}%")

def show_technical_info(informe_tecnico: str) -> None:
    """Muestra la información técnica en un formato estructurado."""
    with st.expander("Información Técnica", expanded=True):
        st.markdown(informe_tecnico)

def show_action_buttons(cotizacion_id: Optional[int] = None) -> None:
    """Muestra y maneja los botones de acción de la cotización."""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if not st.session_state.get('cotizacion_guardada'):
            if st.button("Guardar Cotización", type="primary", key="guardar_btn"):
                with st.spinner("Guardando cotización..."):
                    success = guardar_cotizacion()
                    if success:
                        st.success("✅ Cotización guardada exitosamente")
                        st.session_state.cotizacion_guardada = True
                        # Limpiar cache de PDFs para forzar regeneración
                        st.session_state.pdf_data = None
                        st.session_state.materiales_pdf_data = None
                        st.rerun()
        else:
            st.success("Cotización guardada ✓")
    
    with col2:
        if st.session_state.get('cotizacion_guardada'):
            if st.button("Descargar PDF Cliente", key="pdf_cliente_btn"):
                with st.spinner("Generando PDF..."):
                    pdf_data = generar_pdf_cliente()
                    if pdf_data:
                        st.download_button(
                            label="Descargar PDF",
                            data=pdf_data,
                            file_name=f"cotizacion_{cotizacion_id or 'nueva'}.pdf",
                            mime="application/pdf"
                        )
    
    with col3:
        if st.session_state.get('cotizacion_guardada'):
            if st.button("Descargar PDF Materiales", key="pdf_materiales_btn"):
                with st.spinner("Generando PDF de materiales..."):
                    pdf_data = generar_pdf_materiales()
                    if pdf_data:
                        st.download_button(
                            label="Descargar PDF Materiales",
                            data=pdf_data,
                            file_name=f"materiales_{cotizacion_id or 'nueva'}.pdf",
                            mime="application/pdf"
                        )
    
    with col4:
        if st.button("Nueva Cotización", key="nueva_cotizacion_btn"):
            reset_cotizacion_state()
            st.session_state.paso_actual = 'calculadora'
            st.rerun()

def show_quote_view() -> None:
    """Muestra la vista completa de la cotización con resultados."""
    if not st.session_state.get('datos_cotizacion'):
        st.warning("No hay cotización calculada. Por favor calcule una cotización primero.")
        if st.button("Volver a la calculadora"):
            st.session_state.paso_actual = 'calculadora'
            st.rerun()
        return

    try:
        # Obtener datos necesarios
        cotizacion_data = st.session_state.datos_cotizacion
        resultados = st.session_state.resultados
        informe_tecnico = st.session_state.get('informe_tecnico', '')
        cotizacion_id = st.session_state.get('cotizacion_id')

        # Mostrar encabezado
        show_quote_header(cotizacion_data)
        
        # Mostrar tabla de resultados
        show_results_table(resultados, cotizacion_data.get('es_manga', False))
        
        # Mostrar información técnica
        show_technical_info(informe_tecnico)
        
        # Mostrar botones de acción
        show_action_buttons(cotizacion_id)

    except Exception as e:
        st.error(f"Error mostrando la cotización: {str(e)}")
        if st.session_state.get('usuario_rol') == 'administrador':
            st.exception(e)

def guardar_cotizacion() -> bool:
    """
    Guarda o actualiza la cotización en la base de datos.
    Siempre mantiene solo la última versión.
    
    Returns:
        bool: True si se guardó exitosamente, False en caso contrario.
    """
    try:
        db = st.session_state.db
        datos_cotizacion = st.session_state.datos_cotizacion
        
        # Validar datos requeridos
        campos_requeridos = ['cliente_id', 'material_id', 'num_tintas', 'escalas']
        if not all(campo in datos_cotizacion for campo in campos_requeridos):
            st.error("Faltan datos requeridos para guardar la cotización")
            return False
        
        # Siempre actualizar si existe, crear si no existe
        cotizacion_id = st.session_state.get('cotizacion_id')
        if cotizacion_id:
            # Actualizar la cotización existente (sobrescribir)
            success = db.actualizar_cotizacion(
                cotizacion_id,
                datos_cotizacion,
                st.session_state.resultados
            )
        else:
            # Crear nueva cotización
            cotizacion_id = db.crear_cotizacion(
                datos_cotizacion,
                st.session_state.resultados
            )
            success = bool(cotizacion_id)
            if success:
                st.session_state.cotizacion_id = cotizacion_id
        
        return success

    except Exception as e:
        st.error(f"Error al guardar la cotización: {str(e)}")
        if st.session_state.get('usuario_rol') == 'administrador':
            st.exception(e)
        return False

def generar_pdf_cliente() -> Optional[bytes]:
    """
    Genera el PDF de la cotización para el cliente.
    
    Returns:
        Optional[bytes]: Datos del PDF o None si hay error
    """
    try:
        # Usar PDF cacheado si existe y la cotización no ha cambiado
        if st.session_state.get('pdf_data'):
            return st.session_state.pdf_data
        
        # Obtener datos completos de la cotización
        cotizacion_id = st.session_state.get('cotizacion_id')
        if cotizacion_id:
            datos_completos = st.session_state.db.get_datos_completos_cotizacion(cotizacion_id)
        else:
            datos_completos = st.session_state.datos_cotizacion
        
        # Generar PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            pdf_gen = CotizacionPDF()
            pdf_gen.generar_pdf(datos_completos, tmp_file.name)
            
            with open(tmp_file.name, "rb") as pdf_file:
                pdf_data = pdf_file.read()
            
            # Cachear PDF
            st.session_state.pdf_data = pdf_data
            return pdf_data

    except Exception as e:
        st.error(f"Error generando PDF: {str(e)}")
        if st.session_state.get('usuario_rol') == 'administrador':
            st.exception(e)
        return None

def generar_pdf_materiales() -> Optional[bytes]:
    """
    Genera el PDF de materiales.
    
    Returns:
        Optional[bytes]: Datos del PDF o None si hay error
    """
    try:
        # Similar a generar_pdf_cliente pero para el PDF de materiales
        if st.session_state.get('materiales_pdf_data'):
            return st.session_state.materiales_pdf_data
        
        cotizacion_id = st.session_state.get('cotizacion_id')
        if not cotizacion_id:
            st.error("Debe guardar la cotización antes de generar el PDF de materiales")
            return None
        
        datos_completos = st.session_state.db.get_datos_completos_cotizacion(cotizacion_id)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            pdf_gen = MaterialesPDF()
            pdf_gen.generar_pdf(datos_completos, tmp_file.name)
            
            with open(tmp_file.name, "rb") as pdf_file:
                pdf_data = pdf_file.read()
            
            st.session_state.materiales_pdf_data = pdf_data
            return pdf_data

    except Exception as e:
        st.error(f"Error generando PDF de materiales: {str(e)}")
        if st.session_state.get('usuario_rol') == 'administrador':
            st.exception(e)
        return None

def reset_cotizacion_state() -> None:
    """Reinicia el estado de la cotización."""
    keys_to_remove = [
        'datos_cotizacion',
        'resultados',
        'informe_tecnico',
        'cotizacion_guardada',
        'cotizacion_id',
        'pdf_data',
        'materiales_pdf_data'
    ]
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]