import streamlit as st
from supabase import create_client, Client
from typing import Optional, Dict, Any, Tuple
import traceback

class AuthManager:
    def __init__(self, supabase_client: Client):
        """Initialize the AuthManager with an existing Supabase client."""
        self.supabase = supabase_client # Use the passed client
        self.initialize_session_state()
        
    def initialize_session_state(self) -> None:
        """Initialize session state variables for authentication."""
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        if 'user' not in st.session_state:
            st.session_state.user = None
        if 'user_id' not in st.session_state:
            st.session_state.user_id = None
        if 'user_profile' not in st.session_state:
            st.session_state.user_profile = None
        if 'login_form_submitted' not in st.session_state:
            st.session_state.login_form_submitted = False

    def login(self, email: str, password: str) -> Tuple[bool, str]:
        """
        Authenticate user with email and password.
        Returns: (success: bool, message: str)
        """
        try:
            if not email or not password:
                return False, "Por favor ingrese email y contraseña"

            response = self.supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user:
                user_id = response.user.id
                profile_response = self.supabase.rpc('get_current_user_profile').execute()
                if profile_response.data and len(profile_response.data) > 0:
                    profile = profile_response.data[0]
                    from src.utils.session_manager import SessionManager
                    SessionManager.full_init(user_id=user_id, usuario_rol=profile.get('rol_nombre'), perfil_usuario=profile)
                    st.session_state.user = email
                    st.session_state.login_form_submitted = True
                    st.session_state.comercial_id = user_id
                    print(f"Login exitoso: Usuario={email}, ID={user_id}")
                    return True, "Login successful"
                else:
                    self.logout()
                    print(f"Error: Login exitoso para {email}, pero no se encontró perfil asociado.")
                    return False, "Error interno: Perfil de usuario no encontrado."
            else:
                from src.utils.session_manager import SessionManager
                SessionManager.full_clear()
                st.session_state.login_form_submitted = True
                return False, "Credenciales inválidas"
                
        except Exception as e:
            print(f"Error during login: {str(e)}")
            traceback.print_exc()
            from src.utils.session_manager import SessionManager
            SessionManager.full_clear()
            st.session_state.login_form_submitted = True
            return False, f"Error durante el login: {str(e)}"

    def logout(self) -> None:
        """Sign out the current user."""
        try:
            self.supabase.auth.sign_out()
            from src.utils.session_manager import SessionManager
            SessionManager.full_clear()
        except Exception as e:
            print(f"Error during logout: {str(e)}")
            traceback.print_exc()

    def update_profile(self, nombre: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Actualiza el perfil del usuario autenticado.

        - Actualiza campos en la tabla `perfiles` (nombre, email) para auth.uid()
        - Actualiza la contraseña a través de Supabase Auth si se proporciona

        Returns: True si al menos una actualización fue exitosa
        """
        try:
            # Obtener sesión/usuario actual
            session = self.supabase.auth.get_session()
            if not session or not session.user:
                print("update_profile: No hay sesión de usuario activa")
                return False

            user_id = session.user.id
            current_email = getattr(session.user, 'email', None)

            print(f"update_profile: Iniciando actualización para user_id={user_id}")

            any_success = False

            # 1) Actualización de contraseña en Auth
            if password:
                try:
                    print("update_profile: Actualizando contraseña en Supabase Auth...")
                    auth_resp = self.supabase.auth.update_user({
                        "password": password
                    })
                    # auth_resp puede no lanzar excepción aunque falle; registramos por si acaso
                    print(f"update_profile: Respuesta update_user password: {auth_resp}")
                    any_success = True
                except Exception as e_pass:
                    print(f"update_profile: Error actualizando contraseña: {e_pass}")
                    traceback.print_exc()

            # 2) Preparar actualización en tabla perfiles (solo si hay nombre/email)
            update_fields = {}
            if nombre is not None:
                update_fields['nombre'] = nombre
            if email is not None and email != current_email:
                update_fields['email'] = email

            if update_fields:
                try:
                    print(f"update_profile: Actualizando perfiles con: {update_fields}")
                    resp = self.supabase.from_('perfiles') \
                        .update(update_fields) \
                        .eq('id', user_id) \
                        .execute()
                    print(f"update_profile: Respuesta update perfiles: {resp}")
                    any_success = True or any_success
                except Exception as e_db:
                    print(f"update_profile: Error actualizando tabla perfiles: {e_db}")
                    traceback.print_exc()

                # Si el email cambió, también intentar actualizarlo en Auth para mantener consistencia
                if 'email' in update_fields:
                    try:
                        print("update_profile: Actualizando email en Supabase Auth...")
                        auth_resp_email = self.supabase.auth.update_user({
                            "email": update_fields['email']
                        })
                        print(f"update_profile: Respuesta update_user email: {auth_resp_email}")
                    except Exception as e_email:
                        print(f"update_profile: Error actualizando email en Auth: {e_email}")
                        traceback.print_exc()

            # 3) Refrescar perfil en sesión
            try:
                profile_response = self.supabase.rpc('get_current_user_profile').execute()
                if profile_response and profile_response.data:
                    profile = profile_response.data[0]
                    from src.utils.session_manager import SessionManager
                    # Mantener email consistente en sesión si lo tenemos
                    new_email = update_fields.get('email', current_email)
                    SessionManager.full_init(user_id=user_id, usuario_rol=profile.get('rol_nombre'), perfil_usuario=profile)
                    # Guardar también email visible en sesión
                    st.session_state.user = new_email or st.session_state.get('user')
                    print("update_profile: Perfil en sesión actualizado")
            except Exception as e_profile:
                print(f"update_profile: Error refrescando perfil en sesión: {e_profile}")
                traceback.print_exc()

            return any_success

        except Exception as e:
            print(f"update_profile: Error general: {e}")
            traceback.print_exc()
            return False

    def check_auth_status(self) -> bool:
        """Check if user is authenticated."""
        return st.session_state.get('authenticated', False)

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get current authenticated user details."""
        if self.check_auth_status():
            return {
                'id': st.session_state.user_id,
                'email': st.session_state.user,
            }
        return None

    def verify_user_role(self, user_id: str) -> Optional[Dict]:
        """Verifica y obtiene el rol del usuario"""
        try:
            perfil = self.supabase.table('perfiles')\
                .select('*')\
                .eq('id', user_id)\
                .single()\
                .execute()
            return perfil.data if perfil else None
        except Exception as e:
            print(f"Error verificando rol: {str(e)}")
            return None

def create_login_ui() -> None:
    """Create the login user interface."""
    st.title("🔐 Login")
    
    # Center the form using custom HTML/CSS
    st.markdown("""
        <style>
        .login-container {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100%;
            padding: 2rem;
        }
        .stButton>button {
            width: 100%;
        }
        </style>
        <div class="login-container">
        </div>
        """, unsafe_allow_html=True)
    
    # Create three columns for centering
    col1, col2, col3 = st.columns([1,2,1])
    
    with col2:
        # Initialize auth manager if not already done
        if 'auth_manager' not in st.session_state:
            # Ensure supabase client exists in session state first
            if 'supabase' not in st.session_state:
                try:
                    supabase_url = st.secrets["SUPABASE_URL"]
                    supabase_key = st.secrets["SUPABASE_KEY"]
                    # Create client if not present (should ideally be created earlier)
                    st.session_state.supabase = create_client(supabase_url, supabase_key)
                except KeyError:
                    st.error("Error: Credenciales de Supabase no encontradas. Verifique su archivo .streamlit/secrets.toml")
                    # Provide fallback for development if needed, but this path might indicate an issue
                    supabase_url = st.text_input("SUPABASE_URL", key="supabase_url_input_fallback")
                    supabase_key = st.text_input("SUPABASE_KEY", key="supabase_key_input_fallback", type="password")
                    if not supabase_url or not supabase_key:
                        return # Cannot proceed without credentials
                    st.session_state.supabase = create_client(supabase_url, supabase_key)
                except Exception as e:
                     st.error(f"Error inicializando cliente Supabase en UI: {e}")
                     return


            # Pass the existing client from session state
            st.session_state.auth_manager = AuthManager(st.session_state.supabase)

        # Login form
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Contraseña", type="password", key="login_password")
        
        # Use a regular button instead of a form
        if st.button("Iniciar Sesión", key="login_button", use_container_width=True):
            if not email or not password:
                st.error("Por favor ingrese email y contraseña")
            else:
                success, message = st.session_state.auth_manager.login(email, password)
                if not success:
                    st.error(message)
                else:
                    st.rerun() 