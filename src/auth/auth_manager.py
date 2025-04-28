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