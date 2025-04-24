import streamlit as st
import os
from typing import Optional
from src.auth.auth_manager import AuthManager
from src.data.database import DBManager
from src.ui.auth_ui import show_login_ui
from src.ui.calculator_view import show_calculator
from src.ui.quote_view import show_quote_view
from supabase import create_client, Client

def setup_page():
    """Configura la página de Streamlit y carga los estilos CSS"""
    st.set_page_config(
        page_title="Sistema de Cotización - Flexo Impresos",
        page_icon="🏭",
        layout="wide"
    )
    
    # Cargar CSS desde el archivo
    css_path = os.path.join(os.path.dirname(__file__), 'static', 'styles.css')
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    else:
        st.warning("No se pudo cargar el archivo de estilos")

def initialize_services():
    """Inicializa los servicios principales (Supabase, Auth, DB)"""
    try:
        # Inicializar Supabase si no existe
        if 'supabase' not in st.session_state:
            supabase_url = st.secrets["SUPABASE_URL"]
            supabase_key = st.secrets["SUPABASE_KEY"]
            st.session_state.supabase = create_client(supabase_url, supabase_key)
        
        # Inicializar AuthManager si no existe
        if 'auth_manager' not in st.session_state:
            st.session_state.auth_manager = AuthManager(st.session_state.supabase)
            st.session_state.auth_manager.initialize_session_state()
        
        # Inicializar DBManager si no existe
        if 'db' not in st.session_state:
            st.session_state.db = DBManager(st.session_state.supabase)
            
        return True
    except Exception as e:
        st.error(f"Error crítico inicializando servicios: {str(e)}")
        return False

def main():
    """Función principal de la aplicación"""
    # Configurar la página
    setup_page()
    
    # Inicializar servicios
    if not initialize_services():
        st.stop()
    
    # Verificar autenticación
    if not show_login_ui():
        st.stop()
    
    # Gestionar navegación
    if 'paso_actual' not in st.session_state:
        st.session_state.paso_actual = 'calculadora'
    
    # Mostrar la vista correspondiente
    if st.session_state.paso_actual == 'calculadora':
        show_calculator()
    elif st.session_state.paso_actual == 'cotizacion':
        show_quote_view()

if __name__ == "__main__":
    main()