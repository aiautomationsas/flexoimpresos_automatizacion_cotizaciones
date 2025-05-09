# src/utils/session_manager.py
from datetime import time
from typing import Any, Optional, Dict, TypeVar, Generic, List
from dataclasses import dataclass
import streamlit as st
from ..data.models import Cotizacion, Cliente, ReferenciaCliente

T = TypeVar('T')

@dataclass
class SessionData(Generic[T]):
    """Wrapper para datos en session_state con metadata"""
    data: T
    timestamp: float
    is_dirty: bool = False

class SessionManager:
    """Gestor centralizado del estado de la sesión"""
    
    @staticmethod
    def init_session() -> None:
        """Inicializa el estado básico de la sesión"""
        if 'is_initialized' not in st.session_state:
            st.session_state.is_initialized = True
            st.session_state.authenticated = False
            st.session_state.user_id = None
            st.session_state.user_role = None
            st.session_state.current_view = 'calculator'
            st.session_state.messages = []
    
    @staticmethod
    def set_auth_state(authenticated: bool, user_id: str, role: Optional[str] = None) -> None:
        """
        Establece el estado de autenticación y los datos del usuario.
        """
        st.session_state.authenticated = authenticated
        st.session_state.user_id = user_id
        st.session_state.usuario_rol = role  # Usamos usuario_rol para mantener consistencia
        st.session_state.usuario_verificado = authenticated
    
    @staticmethod
    def set_current_view(view: str) -> None:
        """Cambia la vista actual"""
        st.session_state.current_view = view
    
    @staticmethod
    def add_message(message: str, message_type: str = 'info') -> None:
        """Añade un mensaje al stack de mensajes"""
        if 'messages' not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append((message_type, message))
    
    @staticmethod
    def clear_messages() -> None:
        """Limpia todos los mensajes"""
        st.session_state.messages = []
    
    @staticmethod
    def set_cotizacion_state(cotizacion: Cotizacion) -> None:
        """Establece el estado de la cotización actual"""
        st.session_state.cotizacion_actual = SessionData(
            data=cotizacion,
            timestamp=time.time()
        )
    
    @staticmethod
    def get_cotizacion_state() -> Optional[Cotizacion]:
        """Obtiene la cotización actual"""
        if 'cotizacion_actual' in st.session_state:
            return st.session_state.cotizacion_actual.data
        return None
    
    @staticmethod
    def clear_cotizacion_state() -> None:
        """Limpia el estado de la cotización"""
        if 'cotizacion_actual' in st.session_state:
            del st.session_state.cotizacion_actual
        if 'pdf_data' in st.session_state:
            del st.session_state.pdf_data
        if 'materiales_pdf_data' in st.session_state:
            del st.session_state.materiales_pdf_data
    
    @staticmethod
    def set_calculation_results(results: Dict[str, Any]) -> None:
        """Guarda los resultados de cálculos"""
        st.session_state.calculation_results = SessionData(
            data=results,
            timestamp=time.time()
        )
    
    @staticmethod
    def get_calculation_results() -> Optional[Dict[str, Any]]:
        """Obtiene los resultados de cálculos"""
        if 'calculation_results' in st.session_state:
            return st.session_state.calculation_results.data
        return None

    @staticmethod
    def cache_pdf(pdf_type: str, pdf_data: bytes) -> None:
        """Cachea datos de PDF"""
        cache_key = f'{pdf_type}_pdf_data'
        st.session_state[cache_key] = SessionData(
            data=pdf_data,
            timestamp=time.time()
        )
    
    @staticmethod
    def get_cached_pdf(pdf_type: str) -> Optional[bytes]:
        """Obtiene datos de PDF cacheados"""
        cache_key = f'{pdf_type}_pdf_data'
        if cache_key in st.session_state:
            return st.session_state[cache_key].data
        return None

    @staticmethod
    def clear_pdf_data(quote_id) -> None:
        """
        Limpia los datos del PDF generado para una cotización específica.
        
        Args:
            quote_id: ID de la cotización cuyos datos de PDF se desean limpiar
        """
        bytes_key = f'pdf_bytes_{quote_id}'
        filename_key = f'pdf_filename_{quote_id}'
        if bytes_key in st.session_state:
            del st.session_state[bytes_key]
        if filename_key in st.session_state:
            del st.session_state[filename_key]
            print(f"Limpiando datos PDF para quote_id {quote_id}") # Mensaje de debug

    @staticmethod
    def verify_role(allowed_roles: List[str]) -> bool:
        """
        Verifica si el rol del usuario actual está en la lista de roles permitidos.
        """
        # Obtener el rol del usuario de la sesión
        current_role = st.session_state.get('usuario_rol')
        
        # Debug para ver qué está pasando
        print(f"Rol actual: {current_role}")
        print(f"Roles permitidos: {allowed_roles}")
        
        if current_role is None:
            # Si no hay rol, intentar obtenerlo del perfil
            perfil = st.session_state.get('perfil_usuario', {})
            current_role = perfil.get('rol_nombre')
            
            # Actualizar el rol en la sesión si lo encontramos
            if current_role:
                st.session_state.usuario_rol = current_role
        
        return current_role in allowed_roles

    @staticmethod
    def full_init(user_id=None, usuario_rol=None, perfil_usuario=None):
        """Inicializa todo el estado relevante de usuario y app."""
        st.session_state.is_initialized = True
        st.session_state.authenticated = user_id is not None
        st.session_state.user_id = user_id
        st.session_state.usuario_rol = usuario_rol
        st.session_state.perfil_usuario = perfil_usuario
        st.session_state.usuario_verificado = user_id is not None
        st.session_state.current_view = 'calculator'
        st.session_state.messages = []
        st.session_state.cotizacion_calculada = False
        st.session_state.datos_cotizacion = None
        st.session_state.cotizacion_model = None
        st.session_state.consecutivo = None
        st.session_state.cotizacion_guardada = False
        st.session_state.cotizacion_id = None
        st.session_state.pdf_path = None
        st.session_state.resultados = None
        st.session_state.pdf_data = None
        st.session_state.materiales_pdf_data = None
        st.session_state.nuevo_cliente_guardado = False
        st.session_state.nueva_referencia_guardada = False
        st.session_state.mostrar_form_referencia = False
        st.session_state.cotizacion_cargada = False
        st.session_state.paso_actual = 'calculadora'
        st.session_state.forma_pago_id = 1
        st.session_state.rentabilidad_ajustada = None
        st.session_state.ajustar_material = False
        st.session_state.valor_material_ajustado = 0.0
        st.session_state.ajustar_troquel = False
        st.session_state.precio_troquel = 0.0
        st.session_state.ajustar_planchas = False
        st.session_state.precio_planchas = 0.0
        st.session_state.modo_edicion = False
        st.session_state.cliente_seleccionado = None
        st.session_state.creando_referencia = False
        st.session_state.referencia_seleccionada = None
        st.session_state.material_seleccionado = None
        st.session_state.acabado_seleccionado = None
        st.session_state.comercial_seleccionado = None
        if 'tipo_producto_seleccionado' not in st.session_state:
            st.session_state.tipo_producto_seleccionado = None
        if 'tipo_producto_objeto' not in st.session_state:
            st.session_state.tipo_producto_objeto = None
        SessionManager.init_session()

    @staticmethod
    def full_clear():
        """Limpia todo el estado relevante de usuario y app, excepto servicios y gestor de autenticación."""
        keys_to_keep = {'supabase', 'auth_manager', 'db'}
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]

    @staticmethod
    def reset_calculator_widgets():
        """Resetea los valores de los widgets del formulario de calculadora en session_state."""
        keys_to_reset = [
            'escalas_texto_input', 'escalas', # Texto y lista procesada
            'ancho', 'avance', 'num_tintas',
            'num_pistas_manga', 'num_pistas_otro',
            'material_select', 'material_id',
            'adhesivo_select', 'adhesivo_id',
            'tipo_grafado_select', 'grafado_seleccionado_id',
            'altura_grafado',
            'acabado_select', 'acabado_seleccionado_id',
            'num_paquetes',
            'tiene_troquel',
            'planchas_separadas',
            'forma_pago_select', 'forma_pago_id',
            'es_manga', # Estado derivado
            'material_adhesivo_id', # Estado derivado
            'tipo_producto_seleccionado', # Forzar selección de nuevo
            'tipo_producto_objeto', # Forzar selección de nuevo
            # Ajustes Admin (si existen)
            'ajustar_material', 'valor_material_ajustado',
            'ajustar_troquel', 'precio_troquel',
            'ajustar_planchas', 'precio_planchas', 'precio_planchas_input',
            'ajustar_rentabilidad', 'rentabilidad_ajustada', 'rentabilidad_ajustada_input'
        ]
        
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
                
        # Opcional: Podríamos querer establecer algunos a valores por defecto en lugar de borrar
        # Ejemplo: st.session_state.num_tintas = 3
        # Por ahora, borrar es más simple y fuerza al usuario a rellenar.
        
        print("DEBUG: Calculator widgets reset in session state.") # Para confirmar