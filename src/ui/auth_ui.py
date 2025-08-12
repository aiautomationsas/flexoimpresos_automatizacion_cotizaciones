import streamlit as st
from ..utils.session_manager import SessionManager
from ..auth.auth_manager import AuthManager
from typing import Tuple, Optional
import re

def validate_email(email: str) -> bool:
    """Valida el formato del email."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def show_login() -> None:
    """
    Muestra la interfaz de inicio de sesión y maneja el proceso de autenticación.
    """
    st.title("📊 Cotizador Flexo Impresos")
    
    # Crear columnas para centrar el formulario
    _, col2, _ = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("""
            <div style='text-align: center; padding: 20px;'>
                <h3>Iniciar Sesión</h3>
            </div>
        """, unsafe_allow_html=True)
        
        # Formulario de login
        with st.form("login_form"):
            email = st.text_input("Correo electrónico")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Iniciar Sesión")
            
            if submitted:
                success, message = authenticate_user(email, password)
                if success:
                    st.success(message)
                    st.rerun()  # Recargar la página después del login exitoso
                else:
                    st.error(message)

def authenticate_user(email: str, password: str) -> Tuple[bool, str]:
    """
    Maneja el proceso de autenticación con el AuthManager.
    
    Args:
        email: Correo electrónico del usuario
        password: Contraseña del usuario
        
    Returns:
        Tuple[bool, str]: (éxito de la autenticación, mensaje)
    """
    try:
        if 'auth_manager' not in st.session_state:
            return False, "Error: Sistema de autenticación no inicializado"
        auth_manager = st.session_state.auth_manager
        success, user_data = auth_manager.login(email, password)
        if success:
            # Ya se inicializó todo el estado relevante en SessionManager.full_init desde AuthManager
            return True, "Inicio de sesión exitoso"
        else:
            return False, "Credenciales inválidas"
    except Exception as e:
        print(f"Error en autenticación: {str(e)}")
        return False, f"Error durante la autenticación: {str(e)}"

def show_logout_button() -> None:
    """
    Muestra el botón de cerrar sesión en la interfaz.
    """
    if st.sidebar.button("Cerrar Sesión"):
        handle_logout()
        st.rerun()

def handle_logout() -> None:
    """
    Maneja el proceso de cierre de sesión.
    """
    try:
        if 'auth_manager' in st.session_state:
            st.session_state.auth_manager.logout()
        SessionManager.full_clear()
        SessionManager.add_message("Sesión cerrada exitosamente", "success")
    except Exception as e:
        print(f"Error en logout: {str(e)}")
        SessionManager.add_message(f"Error al cerrar sesión: {str(e)}", "error")

def show_user_info() -> None:
    """Muestra la información del usuario actual y el botón de cierre de sesión."""
    if not st.session_state.get('authenticated', False):
        return

    # Obtener información del usuario
    perfil = st.session_state.get('perfil_usuario', {})
    nombre = perfil.get('nombre', 'Usuario')
    rol = perfil.get('rol_nombre', 'No especificado')
    email = perfil.get('email', '')

    # Crear contenedor para información del usuario y botón de logout
    with st.sidebar:
        avatar_letter = (nombre or "?")[:1].upper()
        st.markdown(
            f"""
            <div style="display:flex; gap:12px; align-items:center; padding:12px; background: linear-gradient(180deg,#ffffff, #f7f9fc); border:1px solid #e6e9ef; border-radius:12px;">
                <div style="width:44px; height:44px; border-radius:50%; background:#2d7ff9; color:white; display:flex; align-items:center; justify-content:center; font-weight:700;">{avatar_letter}</div>
                <div>
                    <div style="font-weight:700; font-size:15px;">{nombre}</div>
                    <div style="font-size:13px; color:#566074;">🛡️ {rol}</div>
                    <div style="font-size:12px; color:#7a8699;">✉️ {email}</div>
                </div>
            </div>
            <div style="margin-top:6px; font-size:11px; color:#99a1b3; text-align:right;">Última sesión: {st.session_state.get('last_login', 'N/A')}</div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("\n")
        col_upd, col_out = st.columns(2)
        with col_upd:
            if st.button("🔧 Actualizar Perfil", key="update_profile_btn", type="primary", use_container_width=True):
                st.session_state.show_profile_update = True
                st.rerun()
        with col_out:
            if st.button("🚪 Cerrar Sesión", key="logout_button", use_container_width=True):
                logout_user()

def logout_user() -> None:
    """Maneja el proceso de cierre de sesión."""
    try:
        with st.spinner("Cerrando sesión..."):
            if 'auth_manager' in st.session_state:
                st.session_state.auth_manager.logout()
            SessionManager.full_clear()
            st.success("Sesión cerrada exitosamente")
            st.rerun()
    except Exception as e:
        st.error(f"Error al cerrar sesión: {str(e)}")

def handle_authentication() -> Tuple[bool, Optional[str]]:
    """
    Maneja el proceso completo de autenticación y devuelve el estado.
    
    Returns:
        Tuple[bool, Optional[str]]: (está_autenticado, mensaje_error)
    """
    if not st.session_state.get('authenticated', False):
        show_login()
        return False, None
    
    # Mostrar información del usuario y botón de logout
    show_user_info()
    
    # Verificar rol del usuario
    rol = st.session_state.get('usuario_rol')
    if rol not in ['comercial', 'administrador']:
        return False, f"Acceso denegado. Rol actual: {rol}"
    
    return True, None

def show_profile_update() -> None:
    """Muestra el formulario de actualización de perfil."""
    if not st.session_state.get('show_profile_update'):
        return

    st.sidebar.markdown("""
        <div style="padding:6px 0 2px 0;">
            <span style="font-weight:700; font-size:16px;">🔧 Actualizar Perfil</span>
            <div style="font-size:12px; color:#566074;">Modifica tu nombre, email o cambia tu contraseña.</div>
        </div>
    """, unsafe_allow_html=True)

    with st.sidebar.form("profile_update_form"):
        perfil = st.session_state.get('perfil_usuario', {})
        
        nuevo_nombre = st.text_input("Nombre", value=perfil.get('nombre', ''), placeholder="Tu nombre completo")
        nuevo_email = st.text_input("Email", value=perfil.get('email', ''), placeholder="tu@email.com")

        st.caption("El email se usa para iniciar sesión y recibir notificaciones.")

        cambiar_password = st.checkbox("Cambiar contraseña")
        nueva_password = None
        confirmar_password = None
        if cambiar_password:
            col1, col2 = st.columns(2)
            with col1:
                nueva_password = st.text_input("Nueva contraseña", type="password", placeholder="Mínimo 8 caracteres")
            with col2:
                confirmar_password = st.text_input("Confirmar", type="password", placeholder="Repite la contraseña")
            st.caption("Recomendación: usa una contraseña de 12+ caracteres, con mayúsculas, minúsculas y números.")
        
        col_ok, col_cancel = st.columns(2)
        submitted = col_ok.form_submit_button("Guardar cambios", type="primary", use_container_width=True)
        cancel = col_cancel.form_submit_button("Cancelar", use_container_width=True)
        if cancel:
            st.session_state.show_profile_update = False
            st.rerun()
        if submitted:
            try:
                with st.spinner("Actualizando perfil..."):
                    # Validar email si fue modificado
                    if nuevo_email != perfil.get('email') and not validate_email(nuevo_email):
                        st.error("Por favor ingrese un email válido.")
                        return
                    
                    # Validar contraseñas si se está actualizando
                    if cambiar_password:
                        if not nueva_password or not confirmar_password:
                            st.error("Debes ingresar y confirmar la nueva contraseña.")
                            return
                        if nueva_password != confirmar_password:
                            st.error("Las contraseñas no coinciden.")
                            return
                        if len(nueva_password) < 8:
                            st.error("La contraseña debe tener al menos 8 caracteres.")
                            return
                    
                    # Actualizar perfil
                    auth_manager = st.session_state.auth_manager
                    success = auth_manager.update_profile(
                        nombre=nuevo_nombre,
                        email=nuevo_email,
                        password=nueva_password if cambiar_password else None
                    )
                    
                    if success:
                        st.success("Perfil actualizado exitosamente")
                        st.session_state.show_profile_update = False
                        st.rerun()
                    else:
                        st.error("No se pudo actualizar el perfil")
            
            except Exception as e:
                st.error(f"Error actualizando perfil: {str(e)}")