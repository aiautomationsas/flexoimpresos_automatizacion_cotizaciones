from src.data.database import DBManager
import streamlit as st
from typing import Tuple

class CotizacionManager:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager

    def guardar_cotizacion(self, datos_calculados: dict) -> Tuple[bool, str]:
        """
        Guarda la cotización y, si es necesario, la nueva referencia
        """
        try:
            # Verificar si es referencia nueva o existente
            if 'nueva_referencia_temp' in st.session_state:
                # Crear referencia y cotización en una transacción
                datos_referencia = st.session_state.nueva_referencia_temp
                resultado = self.db.crear_referencia_y_cotizacion(
                    datos_referencia=datos_referencia,
                    datos_cotizacion=datos_calculados
                )
                
                if not resultado:
                    return False, "Error al crear la referencia y la cotización"
                
                # Limpiar la referencia temporal
                del st.session_state.nueva_referencia_temp
                
                return True, "Cotización y nueva referencia guardadas exitosamente"
            else:
                # Solo guardar la cotización
                response = self.db.guardar_cotizacion(datos_calculados)
                if not response:
                    return False, "Error al guardar la cotización"
                return True, "Cotización guardada exitosamente"
                
        except Exception as e:
            return False, f"Error al guardar: {str(e)}"