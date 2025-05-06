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
        st.markdown(f"""
            <div style='padding: 1rem; background-color: #f8f9fa; border-radius: 5px;'>
                <p><strong>Usuario:</strong> {nombre}</p>
                <p><strong>Rol:</strong> {rol}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><small>Última sesión: {st.session_state.get('last_login', 'N/A')}</small></p>
            </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Cerrar Sesión", key="logout_button", type="primary"):
                logout_user()
        
        with col2:
            if st.button("Actualizar Perfil", key="update_profile"):
                st.session_state.show_profile_update = True
                st.rerun()

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

    st.sidebar.markdown("### Actualizar Perfil")
    with st.sidebar.form("profile_update_form"):
        perfil = st.session_state.get('perfil_usuario', {})
        
        nuevo_nombre = st.text_input("Nombre", value=perfil.get('nombre', ''))
        nuevo_email = st.text_input("Email", value=perfil.get('email', ''))
        nueva_password = st.text_input("Nueva Contraseña (opcional)", type="password")
        confirmar_password = st.text_input("Confirmar Contraseña", type="password") if nueva_password else None
        
        submitted = st.form_submit_button("Actualizar")
        if submitted:
            try:
                with st.spinner("Actualizando perfil..."):
                    # Validar email si fue modificado
                    if nuevo_email != perfil.get('email') and not validate_email(nuevo_email):
                        st.error("Por favor ingrese un email válido.")
                        return
                    
                    # Validar contraseñas si se está actualizando
                    if nueva_password:
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
                        password=nueva_password if nueva_password else None
                    )
                    
                    if success:
                        st.success("Perfil actualizado exitosamente")
                        st.session_state.show_profile_update = False
                        st.rerun()
                    else:
                        st.error("No se pudo actualizar el perfil")
            
            except Exception as e:
                st.error(f"Error actualizando perfil: {str(e)}")