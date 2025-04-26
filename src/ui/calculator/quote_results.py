import streamlit as st
from ...logic.cotizacion_manager import CotizacionManager
from ...data.models.cotizacion import Cotizacion
from ...logic.utils import generar_tabla_resultados
from ...pdf.pdf_generator import CotizacionPDF
import tempfile
from typing import Dict, List

def mostrar_cotizacion():
    """
    Función principal que muestra la página de resultados de la cotización,
    igual que la función original mostrar_cotizacion()
    """
    # Verificar si hay cotización calculada
    if not st.session_state.cotizacion_calculada:
        st.warning("No hay cotización calculada. Por favor calcule una cotización primero.")
        st.button("Volver a la calculadora", 
                 on_click=lambda: setattr(st.session_state, 'paso_actual', 'calculadora'))
        return

    try:
        # Obtener datos de la cotización
        cotizacion = st.session_state.get('cotizacion_model')
        if not cotizacion:
            st.error("No hay cotización en session_state")
            return

        st.title("Detalles de la Cotización")

        # Mostrar mensajes guardados
        if 'mensajes' in st.session_state:
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
        informe_tecnico_str = st.session_state.get("informe_tecnico", "Aún no generado")
        st.markdown(informe_tecnico_str)

        # Sección de Acciones (Guardar, PDF)
        st.subheader("Acciones")
        col1, col2 = st.columns(2)

        with col1:
            # Botón de Guardar Cotización
            if not st.session_state.cotizacion_guardada:
                if st.button("Guardar Cotización", key="guardar_cotizacion", type="primary"):
                    cotizacion_manager = CotizacionManager(st.session_state.db)
                    
                    # Si hay una referencia nueva en memoria, se creará junto con la cotización
                    exito, mensaje = cotizacion_manager.guardar_cotizacion(
                        datos_calculados=st.session_state.cotizacion_model
                    )

                    if exito:
                        st.success(mensaje)
                        st.session_state.cotizacion_guardada = True
                        # Invalidar PDFs para forzar regeneración
                        st.session_state.pdf_data = None
                        st.session_state.materiales_pdf_data = None
                        st.rerun()
                    else:
                        st.error(mensaje)
            else:
                st.success("Cotización guardada ✓")

        with col2:
            # Botón de PDF (solo si la cotización está guardada)
            if st.session_state.cotizacion_guardada:
                mostrar_botones_pdf()

    except Exception as e:
        st.error(f"Error al mostrar la cotización: {str(e)}")
        return

def mostrar_botones_pdf():
    """Maneja la generación y descarga de PDFs"""
    # Generar PDF de Cotización si no existe
    if 'pdf_data' not in st.session_state or st.session_state.pdf_data is None:
        try:
            generar_pdf_cotizacion()
        except Exception as e:
            st.error(f"Error generando PDF: {str(e)}")
            return

    # Botón de descarga si el PDF está en memoria
    if st.session_state.pdf_data is not None:
        cotizacion_id = st.session_state.get('cotizacion_id') or \
                       getattr(st.session_state.get('cotizacion_model'), 'id', 'sin_id')
        
        st.download_button(
            label="Descargar Cotización (PDF)",
            data=st.session_state.pdf_data,
            file_name=f"cotizacion_{cotizacion_id}.pdf",
            mime="application/pdf",
            type="primary"
        )

def generar_pdf_cotizacion():
    """Genera el PDF de la cotización"""
    try:
        db = st.session_state.db
        cotizacion_id = st.session_state.get('cotizacion_id') or \
                       getattr(st.session_state.get('cotizacion_model'), 'id')

        if not cotizacion_id:
            raise ValueError("No se encontró un ID de cotización válido")

        datos_completos = db.get_datos_completos_cotizacion(cotizacion_id)
        if datos_completos:
            pdf_gen = CotizacionPDF()
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                pdf_gen.generar_pdf(datos_completos, tmp_file.name)
                with open(tmp_file.name, "rb") as pdf_file:
                    st.session_state.pdf_data = pdf_file.read()
        else:
            raise ValueError("No se pudieron obtener los datos completos")
    except Exception as e:
        raise Exception(f"Error generando PDF: {str(e)}")
