import streamlit as st
from typing import Optional, Tuple

def show_login_ui() -> bool:
    """
    Muestra la interfaz de inicio de sesión y maneja el proceso de autenticación.
    Returns:
        bool: True si el usuario está autenticado, False en caso contrario.
    """
    if st.session_state.get('authenticated'):
        show_user_info()
        return True

    st.markdown("""
        <h2 style='text-align: center; margin-bottom: 2rem;'>
            Iniciar Sesión
        </h2>
    """, unsafe_allow_html=True)

    # Crear columnas para centrar el formulario
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Formulario de login
        with st.form("login_form"):
            email = st.text_input("Correo electrónico", key="login_email")
            password = st.text_input("Contraseña", type="password", key="login_password")
            submitted = st.form_submit_button("Iniciar Sesión")
            
            if submitted:
                try:
                    # Intentar autenticar usando el AuthManager
                    auth_manager = st.session_state.auth_manager
                    success = auth_manager.login(email, password)
                    
                    if success:
                        # Actualizar el estado de la sesión
                        st.session_state.authenticated = True
                        st.success("¡Inicio de sesión exitoso!")
                        st.rerun()
                    else:
                        st.error("Credenciales inválidas. Por favor, intente nuevamente.")
                
                except Exception as e:
                    st.error(f"Error durante el inicio de sesión: {str(e)}")
                    return False
    
    return False

def show_user_info() -> None:
    """Muestra la información del usuario actual y el botón de cierre de sesión."""
    # Obtener información del usuario
    perfil = st.session_state.get('perfil_usuario', {})
    nombre = perfil.get('nombre', 'Usuario')
    rol = perfil.get('rol_nombre', 'No especificado')

    # Crear contenedor para información del usuario y botón de logout
    with st.sidebar:
        st.markdown(f"""
            <div style='padding: 1rem; background-color: #f8f9fa; border-radius: 5px;'>
                <p><strong>Usuario:</strong> {nombre}</p>
                <p><strong>Rol:</strong> {rol}</p>
            </div>
        """, unsafe_allow_html=True)
        
        if st.button("Cerrar Sesión", key="logout_button"):
            # Limpiar el estado de la sesión
            auth_manager = st.session_state.auth_manager
            auth_manager.logout()
            # Limpiar variables de sesión relacionadas con la autenticación
            for key in ['authenticated', 'user_id', 'perfil_usuario', 'usuario_verificado', 'usuario_rol']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()