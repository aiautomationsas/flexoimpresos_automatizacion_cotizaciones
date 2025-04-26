import streamlit as st
from typing import Dict, Any, Optional, List
import pandas as pd
from datetime import datetime
import json
from ..utils.session_manager import SessionManager

def show_calculator() -> None:
    """
    Función principal que muestra la calculadora.
    Esta es la función que se importa en app.py
    """
    # Verificar rol y permisos
    if not SessionManager.verify_role(['comercial', 'administrador']):
        st.error("No tiene permisos para acceder a esta sección")
        return

    # Mostrar el formulario principal
    show_calculator_form()

    # Si hay resultados para mostrar, mostrarlos
    if st.session_state.get('mostrar_resultados', False):
        show_quote_results()

def show_calculator_form() -> None:
    """Muestra el formulario principal de la calculadora de cotizaciones."""
    st.markdown("""
        <h2 style='text-align: center;'>Calculadora de Cotizaciones</h2>
    """, unsafe_allow_html=True)

    with st.form("calculator_form"):
        # Información del cliente
        st.subheader("Información del Cliente")
        col1, col2 = st.columns(2)
        
        with col1:
            cliente = st.text_input("Nombre del Cliente")
            email_cliente = st.text_input("Email del Cliente")
        
        with col2:
            telefono = st.text_input("Teléfono")
            fecha_cotizacion = st.date_input("Fecha de Cotización", value=datetime.now())

        # Detalles del producto
        st.subheader("Detalles del Producto")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            nombre_producto = st.text_input("Nombre del Producto")
            cantidad = st.number_input("Cantidad", min_value=1, value=1000)
        
        with col2:
            ancho = st.number_input("Ancho (cm)", min_value=0.1, value=10.0)
            alto = st.number_input("Alto (cm)", min_value=0.1, value=10.0)
        
        with col3:
            materiales = SessionManager.get_materiales()
            material = st.selectbox(
                "Material",
                options=materiales,
                format_func=lambda x: x['nombre']
            )

        # Opciones de impresión
        st.subheader("Opciones de Impresión")
        col1, col2 = st.columns(2)
        
        with col1:
            colores = st.number_input("Número de Colores", min_value=1, max_value=4, value=1)
            acabados = SessionManager.get_acabados()
            acabados_seleccionados = st.multiselect(
                "Acabados",
                options=[acabado['nombre'] for acabado in acabados]
            )
        
        with col2:
            tipos_impresion = SessionManager.get_tipos_impresion()
            tipo_impresion = st.selectbox(
                "Tipo de Impresión",
                options=tipos_impresion,
                format_func=lambda x: x['nombre']
            )

        # Comentarios adicionales
        comentarios = st.text_area("Comentarios Adicionales")
    
        # Botón de cálculo
        submitted = st.form_submit_button("Calcular Cotización")
        
        if submitted:
            handle_form_submission(
                cliente=cliente,
                email_cliente=email_cliente,
                telefono=telefono,
                fecha_cotizacion=fecha_cotizacion,
                nombre_producto=nombre_producto,
                cantidad=cantidad,
                ancho=ancho,
                alto=alto,
                material=material,
                colores=colores,
                acabados=acabados_seleccionados,
                tipo_impresion=tipo_impresion,
                comentarios=comentarios
            )

def handle_form_submission(**form_data) -> None:
    """Maneja el envío del formulario y el cálculo de la cotización."""
    if not form_data['cliente'] or not form_data['email_cliente'] or not form_data['nombre_producto']:
        st.error("Por favor complete todos los campos obligatorios.")
        return
    
    try:
        # Preparar datos para el cálculo
        datos_cotizacion = {
            "cliente": {
                "nombre": form_data['cliente'],
                "email": form_data['email_cliente'],
                "telefono": form_data['telefono']
            },
            "producto": {
                "nombre": form_data['nombre_producto'],
                "cantidad": form_data['cantidad'],
                "dimensiones": {
                    "ancho": form_data['ancho'],
                    "alto": form_data['alto']
                },
                "material_id": form_data['material']['id'],
                "tipo_impresion_id": form_data['tipo_impresion']['id'],
                "colores": form_data['colores'],
                "acabados": form_data['acabados']
            },
            "fecha_cotizacion": form_data['fecha_cotizacion'].isoformat(),
            "comentarios": form_data['comentarios'],
            "usuario_id": SessionManager.get_user_id()
        }

        # Realizar cálculo
        with st.spinner("Calculando cotización..."):
            resultado = calcular_cotizacion(datos_cotizacion)
            if resultado:
                SessionManager.set_calculation_results(resultado)
                SessionManager.set_current_view('quote_results')
                st.rerun()
            else:
                st.error("No se pudo calcular la cotización. Por favor, verifique los datos.")
    
    except Exception as e:
        st.error(f"Error al calcular la cotización: {str(e)}")
        if SessionManager.is_admin():
            st.exception(e)

def calcular_cotizacion(datos_cotizacion: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Realiza el cálculo de la cotización."""
    try:
        cotizacion_service = SessionManager.get_cotizacion_service()
        return cotizacion_service.calcular_cotizacion(datos_cotizacion)
    except Exception as e:
        print(f"Error en cálculo de cotización: {str(e)}")  # Para debugging
        return None

def show_quote_results() -> None:
    """Muestra los resultados de la cotización calculada."""
    results = SessionManager.get_calculation_results()
    if not results:
        SessionManager.add_message(
            "No hay resultados para mostrar. Por favor, realice un cálculo primero.",
            "error"
        )
        SessionManager.set_current_view('calculator')
        st.rerun()

    st.markdown("""
        <h3 style='text-align: center;'>Resumen de Cotización</h3>
    """, unsafe_allow_html=True)

    # Crear columnas para mostrar la información
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Detalles del Cliente")
        st.write(f"**Cliente:** {results['cliente']['nombre']}")
        st.write(f"**Email:** {results['cliente']['email']}")
        st.write(f"**Teléfono:** {results['cliente']['telefono']}")
        
        st.markdown("#### Detalles del Producto")
        st.write(f"**Producto:** {results['producto']['nombre']}")
        st.write(f"**Cantidad:** {results['producto']['cantidad']} unidades")
        st.write(f"**Dimensiones:** {results['producto']['dimensiones']['ancho']}cm x {results['producto']['dimensiones']['alto']}cm")
    
    with col2:
        st.markdown("#### Costos")
        st.write(f"**Costo Material:** ${results['costos']['material']:.2f}")
        st.write(f"**Costo Impresión:** ${results['costos']['impresion']:.2f}")
        st.write(f"**Costo Acabados:** ${results['costos']['acabados']:.2f}")
        st.write(f"**Subtotal:** ${results['costos']['subtotal']:.2f}")
        st.write(f"**IVA (16%):** ${results['costos']['iva']:.2f}")
        st.markdown(f"**Total:** ${results['costos']['total']:.2f}")

    show_action_buttons(results)

def show_action_buttons(results: Dict[str, Any]) -> None:
    """Muestra los botones de acción para la cotización."""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("Generar PDF"):
            handle_pdf_generation(results)

    with col2:
        if st.button("Enviar por Email"):
            handle_email_sending(results)

    with col3:
        if st.button("Nueva Cotización"):
            SessionManager.clear_calculation_results()
            SessionManager.set_current_view('calculator')
            st.rerun()

def handle_pdf_generation(results: Dict[str, Any]) -> None:
    """Maneja la generación del PDF."""
    try:
        with st.spinner("Generando PDF..."):
            pdf_service = SessionManager.get_pdf_service()
            pdf_data = pdf_service.generar_pdf_cotizacion(results)
            if pdf_data:
                SessionManager.cache_pdf('cotizacion', pdf_data)
                st.success("PDF generado exitosamente")
                st.download_button(
                    label="Descargar PDF",
                    data=pdf_data,
                    file_name=f"cotizacion_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
    except Exception as e:
        st.error(f"Error al generar PDF: {str(e)}")

def handle_email_sending(results: Dict[str, Any]) -> None:
    """Maneja el envío del email."""
    try:
        with st.spinner("Enviando email..."):
            email_service = SessionManager.get_email_service()
            if email_service.enviar_cotizacion(results):
                st.success("Cotización enviada exitosamente")
            else:
                st.error("No se pudo enviar el email")
    except Exception as e:
        st.error(f"Error al enviar email: {str(e)}")

def show_quote_history() -> None:
    """Muestra el historial de cotizaciones."""
    st.markdown("### Historial de Cotizaciones")

    try:
        # Obtener historial de cotizaciones
        cotizacion_service = st.session_state.cotizacion_service
        historial = cotizacion_service.obtener_historial(
            usuario_id=st.session_state.get('user_id')
        )

        if not historial:
            st.info("No hay cotizaciones registradas.")
            return

        # Convertir a DataFrame para mejor visualización
        df = pd.DataFrame(historial)
        
        # Formatear fechas y valores monetarios
        df['fecha_cotizacion'] = pd.to_datetime(df['fecha_cotizacion']).dt.strftime('%Y-%m-%d')
        columnas_monetarias = ['total', 'subtotal']
        for col in columnas_monetarias:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: f"${x:,.2f}")

        # Mostrar tabla con filtros
        st.dataframe(
            df,
            column_config={
                "id": "ID",
                "cliente": "Cliente",
                "producto": "Producto",
                "fecha_cotizacion": "Fecha",
                "total": "Total",
                "estado": "Estado"
            },
            hide_index=True
        )

        # Permitir descargar como CSV
        if st.button("Descargar CSV"):
            csv = df.to_csv(index=False)
            st.download_button(
                label="Confirmar Descarga CSV",
                data=csv,
                file_name=f"cotizaciones_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Error al cargar el historial: {str(e)}")
        if st.session_state.get('usuario_rol') == 'administrador':
            st.exception(e)

def show_quote_summary(form_data: Dict[str, Any], results: Dict[str, Any], is_manga: bool) -> None:
    """Muestra un resumen compacto de la cotización."""
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Detalles del Producto**")
        st.write(f"- Tipo: {'Manga' if is_manga else 'Etiqueta'}")
        st.write(f"- Dimensiones: {form_data['ancho']}cm x {form_data['avance']}cm")
        st.write(f"- Cantidad: {form_data['num_paquetes']} paquetes")
        st.write(f"- Tintas: {form_data['num_tintas']}")
    
    with col2:
        st.write("**Costos**")
        st.write(f"- Subtotal: ${results['subtotal']:.2f}")
        st.write(f"- IVA: ${results['iva']:.2f}")
        st.write(f"- Total: ${results['total']:.2f}")