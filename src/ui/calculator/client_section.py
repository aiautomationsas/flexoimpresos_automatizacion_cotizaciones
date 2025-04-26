import streamlit as st
from typing import Optional, Tuple
from ...data.models.cliente import Cliente
from ...data.models.referencia import ReferenciaCliente

def mostrar_seccion_cliente(db) -> Optional[Tuple[Cliente, Optional[ReferenciaCliente], Optional[str]]]:
    """
    Muestra la sección de selección de cliente y referencia
    Retorna: (cliente_seleccionado, referencia_seleccionada, nueva_referencia_descripcion)
    donde referencia_seleccionada puede ser None si es nueva referencia
    y nueva_referencia_descripcion contiene la descripción si es referencia nueva
    """
    # Obtener clientes según rol
    if st.session_state.usuario_rol == 'administrador':
        clientes = db.get_clientes()
    else:
        clientes = db.get_clientes_by_comercial(st.session_state.comercial_id)

    if not clientes:
        st.warning("No se encontraron clientes disponibles")
        return None

    # Mostrar comercial (no editable)
    st.write(f"**Comercial:** {st.session_state.perfil_usuario['nombre']}")

    # Selector de cliente
    cliente_seleccionado = st.selectbox(
        "Cliente",
        options=clientes,
        format_func=lambda x: f"{x.codigo} - {x.nombre}"
    )

    if cliente_seleccionado:
        # Obtener referencias existentes del cliente
        referencias = db.get_referencias_by_cliente(cliente_seleccionado.id)
        
        # Radio button para elegir entre referencia existente o nueva
        opcion_referencia = st.radio(
            "Seleccione una opción:",
            ["Usar referencia existente", "Crear nueva referencia"],
            index=0 if referencias else 1  # Default a nueva si no hay existentes
        )

        if opcion_referencia == "Usar referencia existente" and referencias:
            # Mostrar selector de referencias existentes
            referencia_seleccionada = st.selectbox(
                "Referencia",
                options=referencias,
                format_func=lambda x: x.descripcion
            )
            return cliente_seleccionado, referencia_seleccionada, None
        else:
            # Campo para nueva referencia
            nueva_referencia = st.text_input(
                "Descripción de la nueva referencia",
                key="nueva_referencia_input"
            )
            if nueva_referencia:
                # Guardamos la descripción en session_state para usarla después
                st.session_state.nueva_referencia_temp = {
                    'cliente_id': cliente_seleccionado.id,
                    'descripcion': nueva_referencia,
                    'id_usuario': st.session_state.comercial_id
                }
                return cliente_seleccionado, None, nueva_referencia
    
    return None
