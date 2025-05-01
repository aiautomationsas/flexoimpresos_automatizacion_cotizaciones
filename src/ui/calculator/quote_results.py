import streamlit as st
from src.logic.cotizacion_manager import CotizacionManager
from src.data.models import Cotizacion
from src.logic.utils import generar_tabla_resultados
from src.pdf.pdf_generator import generar_bytes_pdf_cotizacion
import tempfile
import traceback
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
    pdf_bytes = None
    # Intentar obtener PDF cacheado o generar si no existe
    if 'pdf_data' in st.session_state and st.session_state.pdf_data is not None:
        pdf_bytes = st.session_state.pdf_data
        print("Usando PDF cacheado de session_state.")
    else:
        print("No hay PDF cacheado, intentando generar...")
        try:
            # --- INICIO CAMBIO: Usar nueva función --- 
            # generar_pdf_cotizacion() # Ya no existe esta función
            db = st.session_state.db
            cotizacion_id = st.session_state.get('cotizacion_id') or getattr(st.session_state.get('cotizacion_model'), 'id', None)
            if not cotizacion_id:
                raise ValueError("No se encontró ID para generar PDF.")
            
            datos_completos = db.get_datos_completos_cotizacion(cotizacion_id)
            if not datos_completos:
                 raise ValueError("No se pudieron obtener datos completos para PDF.")
                 
            pdf_bytes = generar_bytes_pdf_cotizacion(datos_completos)
            if pdf_bytes:
                 st.session_state.pdf_data = pdf_bytes # Guardar en caché si se generó
                 print("PDF generado y cacheado en session_state.")
            else:
                 st.warning("La generación de PDF no produjo datos.")
            # --- FIN CAMBIO --- 
        except Exception as e:
            st.error(f"Error generando PDF: {str(e)}")
            traceback.print_exc() # Mostrar traceback para depuración
            return # No mostrar botón si hay error

    # Botón de descarga si tenemos los bytes del PDF (cacheados o recién generados)
    if pdf_bytes is not None:
        cotizacion_id_nombre = st.session_state.get('cotizacion_id') or getattr(st.session_state.get('cotizacion_model'), 'id', 'sin_id')
        
        st.download_button(
            label="Descargar Cotización (PDF)",
            data=pdf_bytes,
            file_name=f"cotizacion_{cotizacion_id_nombre}.pdf",
            mime="application/pdf",
            type="primary",
            key="download_pdf_quote_results" # Añadir key única
        )
