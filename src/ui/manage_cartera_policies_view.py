import streamlit as st
import pandas as pd
from typing import Optional, Dict, Any, List
import traceback
from datetime import datetime

from src.data.database import DBManager
from src.data.models import PoliticasCartera
from src.utils.session_manager import SessionManager

def show_manage_cartera_policies():
    """Muestra la vista de gestión de políticas de cartera (solo para administradores)"""
    
    # Verificar permisos de administrador
    if not SessionManager.verify_role(['administrador']):
        st.error("❌ Acceso denegado. Solo los administradores pueden gestionar políticas de cartera.")
        return
    
    st.title("💰 Gestión de Políticas de Cartera")
    st.markdown("Administre las políticas de cartera para diferentes tipos de clientes.")
    
    if 'db' not in st.session_state:
        st.error("Error: La conexión a la base de datos no está inicializada.")
        return
    
    db = st.session_state.db
    
    # Tabs para diferentes acciones
    tab1, tab2, tab3 = st.tabs(["📋 Ver Políticas", "➕ Crear Nueva", "✏️ Editar"])
    
    with tab1:
        show_cartera_policies_list(db)
    
    with tab2:
        show_create_cartera_policy_form(db)
    
    with tab3:
        show_edit_cartera_policy_form(db)

def show_cartera_policies_list(db: DBManager):
    """Muestra la lista de políticas de cartera existentes"""
    st.markdown("### Políticas de Cartera Existentes")
    
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politicas_cartera'):
            st.error("❌ Error: El método 'get_politicas_cartera' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return
        
        # Prueba de estructura de tabla (opcional)
        if st.checkbox("🔍 Mostrar información de debug"):
            if hasattr(db, 'test_politicas_table_structure'):
                st.info("🔍 Probando estructura de tabla...")
                test_result = db.test_politicas_table_structure()
                st.json(test_result)
                
                # Verificar estado de la tabla y triggers
                if test_result.get('needs_setup', True):
                    st.warning("⚠️ La tabla o sus triggers necesitan configuración...")
                    
                    missing_components = []
                    if not test_result.get('table_exists', False):
                        missing_components.append("tabla")
                    if not test_result.get('trigger_exists', False):
                        missing_components.append("trigger de actualización")
                    if not test_result.get('function_exists', False):
                        missing_components.append("función de trigger")
                    if not test_result.get('select_policy_exists', False):
                        missing_components.append("política RLS para SELECT")
                    if not test_result.get('insert_policy_exists', False):
                        missing_components.append("política RLS para INSERT")
                    if not test_result.get('update_policy_exists', False):
                        missing_components.append("política RLS para UPDATE")
                    if not test_result.get('delete_policy_exists', False):
                        missing_components.append("política RLS para DELETE")
                    
                    st.info(f"💡 Componentes faltantes: {', '.join(missing_components)}")
                    
                    if hasattr(db, 'create_politicas_cartera_table_if_not_exists'):
                        if st.button("🔧 Configurar Tabla y Triggers"):
                            with st.spinner("Configurando..."):
                                success = db.create_politicas_cartera_table_if_not_exists()
                                if success:
                                    st.success("✅ Tabla y triggers configurados exitosamente")
                                    st.rerun()
                                else:
                                    st.error("❌ Error en la configuración")
                                    return
                    else:
                        st.error("❌ Método de configuración no disponible")
                        return
        
        # Obtener todas las políticas
        politicas = db.get_politicas_cartera()
        
        if not politicas:
            st.info("No hay políticas de cartera configuradas en la base de datos.")
            st.info("💡 Puede crear nuevas políticas usando la pestaña '➕ Crear Nueva'")
            return
        
        # Crear DataFrame para mostrar
        data = []
        for politica in politicas:
            data.append({
                'ID': politica.id,
                'Descripción': politica.descripcion,
                'Creado': politica.created_at.strftime('%d/%m/%Y %H:%M') if politica.created_at else 'N/A',
                'Actualizado': politica.updated_at.strftime('%d/%m/%Y %H:%M') if politica.updated_at else 'N/A'
            })
        
        st.success(f"✅ Se encontraron {len(politicas)} políticas de cartera")
        
        df = pd.DataFrame(data)
        
        # Mostrar tabla con opciones de acción
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", width="small"),
                "Descripción": st.column_config.TextColumn("Descripción", width="large"),
                "Creado": st.column_config.TextColumn("Creado", width="medium"),
                "Actualizado": st.column_config.TextColumn("Actualizado", width="medium")
            }
        )
        
        # Mostrar detalles expandibles
        st.markdown("### Detalles de Políticas")
        for politica in politicas:
            with st.expander(f"Política #{politica.id} - {politica.descripcion[:50]}..."):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.text_area(
                        "Descripción completa:",
                        value=politica.descripcion,
                        height=150,
                        disabled=True,
                        key=f"view_desc_{politica.id}"
                    )
                with col2:
                    st.write("**Información:**")
                    st.write(f"**ID:** {politica.id}")
                    if politica.created_at:
                        st.write(f"**Creado:** {politica.created_at.strftime('%d/%m/%Y %H:%M')}")
                    if politica.updated_at:
                        st.write(f"**Actualizado:** {politica.updated_at.strftime('%d/%m/%Y %H:%M')}")
                    
                    # Botón para eliminar
                    if st.button("🗑️ Eliminar", key=f"delete_btn_{politica.id}", type="secondary"):
                        if delete_cartera_policy(db, politica.id):
                            st.success("✅ Política eliminada exitosamente")
                            st.rerun()
                        else:
                            st.error("❌ Error al eliminar la política")
                            st.info("💡 La política puede estar en uso por cotizaciones existentes")
                
    except Exception as e:
        st.error(f"Error al cargar las políticas: {str(e)}")
        traceback.print_exc()

def show_create_cartera_policy_form(db: DBManager):
    """Muestra el formulario para crear una nueva política de cartera"""
    st.markdown("### Crear Nueva Política de Cartera")
    
    with st.form("create_cartera_policy_form"):
        st.markdown("""
        **Formato sugerido para la descripción:**
        - Condiciones de pago
        - Plazos y términos
        - Requisitos especiales
        """)
        
        descripcion = st.text_area(
            "Descripción de la política:",
            height=200,
            placeholder="Ejemplo:\nPago a 30 días\nRequiere orden de compra\nLímite de crédito: $10,000,000",
            help="Describa las condiciones y términos de la política de cartera"
        )
        
        submitted = st.form_submit_button("Crear Política", type="primary")
        
        if submitted:
            if not descripcion.strip():
                st.error("La descripción no puede estar vacía.")
                return
            
            try:
                # Crear la nueva política
                nueva_politica = PoliticasCartera(
                    id=None,
                    descripcion=descripcion.strip(),
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                success = db.create_politica_cartera(nueva_politica)
                
                if success:
                    st.success("✅ Política de cartera creada exitosamente.")
                    st.rerun()
                else:
                    st.error("❌ Error al crear la política de cartera.")
                    
            except Exception as e:
                st.error(f"Error al crear la política: {str(e)}")
                traceback.print_exc()

def show_edit_cartera_policy_form(db: DBManager):
    """Muestra el formulario para editar una política de cartera existente"""
    st.markdown("### Editar Política de Cartera")
    
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politicas_cartera'):
            st.error("❌ Error: El método 'get_politicas_cartera' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return
        
        # Obtener políticas para el selector
        politicas = db.get_politicas_cartera()
        
        if not politicas:
            st.info("No hay políticas disponibles para editar.")
            return
        
        # Selector de política
        opciones = {f"{p.id} - {p.descripcion[:50]}...": p.id for p in politicas}
        politica_seleccionada = st.selectbox(
            "Seleccionar política a editar:",
            options=list(opciones.keys()),
            key="edit_cartera_policy_selector"
        )
        
        if politica_seleccionada:
            politica_id = opciones[politica_seleccionada]
            politica = next((p for p in politicas if p.id == politica_id), None)
            
            if politica:
                with st.form("edit_cartera_policy_form"):
                    st.markdown(f"**Editando Política #{politica.id}**")
                    
                    descripcion_editada = st.text_area(
                        "Descripción:",
                        value=politica.descripcion,
                        height=200,
                        key=f"edit_desc_{politica.id}"
                    )
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        submitted = st.form_submit_button("Guardar Cambios", type="primary")
                    with col2:
                        cancel = st.form_submit_button("Cancelar", type="secondary")
                    
                    if submitted:
                        if not descripcion_editada.strip():
                            st.error("La descripción no puede estar vacía.")
                            return
                        
                        try:
                            # Actualizar la política
                            politica_actualizada = PoliticasCartera(
                                id=politica.id,
                                descripcion=descripcion_editada.strip(),
                                created_at=politica.created_at,
                                updated_at=datetime.now()
                            )
                            
                            success = db.update_politica_cartera(politica_actualizada)
                            
                            if success:
                                st.success("✅ Política de cartera actualizada exitosamente.")
                                st.rerun()
                            else:
                                st.error("❌ Error al actualizar la política de cartera.")
                                
                        except Exception as e:
                            st.error(f"Error al actualizar la política: {str(e)}")
                            traceback.print_exc()
                    
                    elif cancel:
                        st.rerun()
                        
    except Exception as e:
        st.error(f"Error al cargar las políticas para edición: {str(e)}")
        traceback.print_exc()

def delete_cartera_policy(db: DBManager, politica_id: int) -> bool:
    """Elimina una política de cartera"""
    try:
        # Verificar si la política está siendo usada en cotizaciones
        # TODO: Implementar verificación de uso en cotizaciones si es necesario
        
        # Eliminar la política
        success = db.delete_politica_cartera(politica_id)
        return success
        
    except Exception as e:
        st.error(f"Error al eliminar la política: {str(e)}")
        traceback.print_exc()
        return False

def show_cartera_policy_selection(db: DBManager, selected_policy_id: Optional[int] = None, key: str = "cartera_policy_selection") -> Optional[int]:
    """Muestra un selector de políticas de cartera para usar en otros formularios"""
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politicas_cartera'):
            st.error("❌ Error: El método 'get_politicas_cartera' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return None
        
        politicas = db.get_politicas_cartera()
        
        if not politicas:
            st.info("No hay políticas de cartera configuradas.")
            return None
        
        # Crear opciones para el selector
        opciones = [(None, "Sin política de cartera")]
        opciones.extend([(p.id, f"Política #{p.id} - {p.descripcion[:50]}...") for p in politicas])
        
        # Encontrar el índice de la política seleccionada
        selected_index = 0
        for i, (policy_id, _) in enumerate(opciones):
            if policy_id == selected_policy_id:
                selected_index = i
                break
        
        selected_option = st.selectbox(
            "Política de Cartera:",
            options=opciones,
            index=selected_index,
            format_func=lambda x: x[1],
            key=key
        )
        
        return selected_option[0] if selected_option else None
        
    except Exception as e:
        st.error(f"Error al cargar las políticas de cartera: {str(e)}")
        return None

def show_cartera_policy_details(politica_id: int, db: DBManager):
    """Muestra los detalles de una política de cartera específica"""
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politica_cartera'):
            st.error("❌ Error: El método 'get_politica_cartera' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return
        
        politica = db.get_politica_cartera(politica_id)
        if politica:
            with st.expander(f"💰 Política de Cartera #{politica.id}", expanded=True):
                st.text_area(
                    "Descripción:",
                    value=politica.descripcion,
                    height=100,
                    disabled=True,
                    key=f"cartera_policy_details_{politica.id}"
                )
        else:
            st.warning("Política de cartera no encontrada.")
    except Exception as e:
        st.error(f"Error al cargar los detalles de la política: {str(e)}")


