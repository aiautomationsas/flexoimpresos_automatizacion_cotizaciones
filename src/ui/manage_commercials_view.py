import streamlit as st
import pandas as pd
from typing import Optional

from src.data.database import DBManager
from src.utils.session_manager import SessionManager


ROLE_ID_COMERCIAL = "104cdddc-c6b2-456d-8836-f0b130c30b2b"


def show_manage_commercials() -> None:
    """Vista para que el administrador gestione comerciales (tabla perfiles)."""
    if not SessionManager.verify_role(['administrador']):
        st.error("❌ Acceso denegado. Solo administradores.")
        return

    if 'db' not in st.session_state:
        st.error("Conexión a BD no inicializada.")
        return

    db: DBManager = st.session_state.db

    st.title("👔 Gestionar Comerciales")
    st.caption("Administre los comerciales (perfiles) asociados al rol especificado.")

    tab_list, tab_create, tab_edit = st.tabs(["📋 Lista", "➕ Crear", "✏️ Editar/Eliminar"])

    with tab_list:
        _list_commercials(db)

    with tab_create:
        _create_commercial_form(db)

    with tab_edit:
        _edit_delete_commercial(db)


def _list_commercials(db: DBManager) -> None:
    st.subheader("Comerciales actuales")
    comerciales = db.get_comerciales_by_role_id(ROLE_ID_COMERCIAL)
    if not comerciales:
        st.info("No hay comerciales registrados para el rol especificado.")
        return
    df = pd.DataFrame([
        {
            "ID": c.get("id"),
            "Nombre": c.get("nombre"),
            "Email": c.get("email") or "",
            "Celular": c.get("celular") or "",
            "Actualizado": c.get("updated_at") or ""
        }
        for c in comerciales
    ])
    st.dataframe(df, hide_index=True, use_container_width=True)


def _create_commercial_form(db: DBManager) -> None:
    st.subheader("Crear nuevo comercial")
    with st.form("create_comercial_form"):
        nombre = st.text_input("Nombre *")
        email = st.text_input("Email")
        celular = st.text_input("Celular (solo números)")
        submitted = st.form_submit_button("Crear", type="primary")

        if submitted:
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
                return
            celular_val: Optional[int] = None
            if celular.strip():
                if not celular.isdigit():
                    st.error("El celular debe contener solo números.")
                    return
                celular_val = int(celular)

            created = db.create_comercial(nombre=nombre.strip(), email=email.strip() or None, celular=celular_val, role_id=ROLE_ID_COMERCIAL)
            if created:
                st.success("✅ Comercial creado.")
                st.rerun()
            else:
                st.error("❌ No se pudo crear el comercial.")


def _edit_delete_commercial(db: DBManager) -> None:
    st.subheader("Editar / Eliminar comercial")
    comerciales = db.get_comerciales_by_role_id(ROLE_ID_COMERCIAL)
    if not comerciales:
        st.info("No hay comerciales para editar.")
        return

    opciones = {f"{c.get('nombre')} ({c.get('email') or ''})": c.get('id') for c in comerciales}
    sel_key = st.selectbox("Seleccione un comercial:", options=list(opciones.keys()))
    perfil_id = opciones.get(sel_key)
    seleccionado = next((c for c in comerciales if c.get('id') == perfil_id), None)
    if not seleccionado:
        st.warning("No se encontró el comercial seleccionado.")
        return

    with st.form("edit_comercial_form"):
        nombre = st.text_input("Nombre *", value=seleccionado.get("nombre") or "")
        email = st.text_input("Email", value=seleccionado.get("email") or "")
        celular_val = seleccionado.get("celular")
        celular_str = str(celular_val) if celular_val is not None else ""
        celular = st.text_input("Celular (solo números)", value=celular_str)

        col1, col2 = st.columns(2)
        guardar = col1.form_submit_button("Guardar cambios", type="primary")
        eliminar = col2.form_submit_button("Eliminar", type="secondary")

        if guardar:
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
                return
            if celular.strip() and not celular.isdigit():
                st.error("El celular debe contener solo números.")
                return
            celular_num = int(celular) if celular.strip() else None
            ok = db.update_comercial(perfil_id=perfil_id, nombre=nombre.strip(), email=email.strip() or None, celular=celular_num)
            if ok:
                st.success("✅ Cambios guardados.")
                st.rerun()
            else:
                st.error("❌ No se pudieron guardar los cambios.")

        if eliminar:
            if st.checkbox("Confirmar eliminación", key="confirm_delete_comercial"):
                ok = db.delete_comercial(perfil_id)
                if ok:
                    st.success("✅ Comercial eliminado.")
                    st.rerun()
                else:
                    st.error("❌ No se pudo eliminar el comercial.")


