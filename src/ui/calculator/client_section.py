import streamlit as st
from typing import Optional
from src.data.models import Cliente

# Ahora solo retorna el cliente seleccionado, no referencia

def mostrar_seccion_cliente(db) -> Optional[Cliente]:
    """
    Muestra la sección de selección de cliente
    Retorna: cliente_seleccionado
    """
    # Obtener clientes según rol (RLS aplicado en DB)
    if st.session_state.usuario_rol == 'administrador':
        clientes = db.get_clientes()
    else:
        clientes = db.get_clientes_by_comercial(st.session_state.comercial_id)

    if not clientes:
        st.warning("No se encontraron clientes disponibles")
        return None

    # Ordenar clientes por nombre
    clientes.sort(key=lambda x: x.nombre)

    # Ordenar clientes por nombre
    clientes.sort(key=lambda x: x.nombre)

    # Mostrar comercial (no editable)
    st.write(f"**Comercial:** {st.session_state.perfil_usuario['nombre']}")

    # Selector de cliente
    cliente_seleccionado = st.selectbox(
        "Cliente",
        options=clientes,
        format_func=lambda x: f"{x.codigo} - {x.nombre}"
    )

    return cliente_seleccionado
