import streamlit as st
import pandas as pd
from typing import Optional, Dict, Any, List
import traceback
from datetime import datetime

from src.data.database import DBManager
from src.data.models import PoliticasEntrega
from src.utils.session_manager import SessionManager

def show_manage_policies():
    """Muestra la vista de gestión de políticas de entrega (solo para administradores)"""
    
    # Verificar permisos de administrador
    if not SessionManager.verify_role(['administrador']):
        st.error("❌ Acceso denegado. Solo los administradores pueden gestionar políticas de entrega.")
        return
    
    st.title("📋 Gestión de Políticas de Entrega")
    st.markdown("Administre las políticas de entrega para diferentes tipos de pedidos.")
    
    if 'db' not in st.session_state:
        st.error("Error: La conexión a la base de datos no está inicializada.")
        return
    
    db = st.session_state.db
    
    # Solo mostramos una pestaña para editar la política única
    st.markdown("### 📋 Política de Entrega")
    show_edit_single_policy(db)

def show_policies_list(db: DBManager):
    """Muestra la lista de políticas de entrega existentes"""
    st.markdown("### Políticas de Entrega Existentes")
    
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politicas_entrega'):
            st.error("❌ Error: El método 'get_politicas_entrega' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return
        

        
        # Obtener todas las políticas
        politicas = db.get_politicas_entrega()
        
        if not politicas:
            st.info("No hay políticas de entrega configuradas en la base de datos.")
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
        
        st.success(f"✅ Se encontraron {len(politicas)} políticas de entrega")
        
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
                        if delete_policy(db, politica.id):
                            st.success("✅ Política eliminada exitosamente")
                            st.rerun()
                        else:
                            st.error("❌ Error al eliminar la política")
                            st.info("💡 La política puede estar en uso por cotizaciones existentes")
                
    except Exception as e:
        st.error(f"Error al cargar las políticas: {str(e)}")
        traceback.print_exc()

def show_create_policy_form(db: DBManager):
    """Muestra el formulario para crear una nueva política"""
    st.markdown("### Crear Nueva Política de Entrega")
    
    with st.form("create_policy_form"):
        st.markdown("""
        **Formato sugerido para la descripción:**
        - Repeticiones: X días calendario desde el envío de la OC
        - Cambios: X días calendario desde la aprobación de la sherpa
        - Nuevas: X días calendario desde la aprobación de la sherpa
        """)
        
        descripcion = st.text_area(
            "Descripción de la política:",
            height=200,
            placeholder="Ejemplo:\nRepeticiones: 8 días calendario desde el envío de la OC\nCambios: 13 días calendario desde la aprobación de la sherpa\nNuevas: 15 días calendario desde la aprobación de la sherpa",
            help="Describa los tiempos de entrega para diferentes tipos de pedidos"
        )
        
        submitted = st.form_submit_button("Crear Política", type="primary")
        
        if submitted:
            if not descripcion.strip():
                st.error("La descripción no puede estar vacía.")
                return
            
            try:
                # Crear la nueva política
                nueva_politica = PoliticasEntrega(
                    id=None,
                    descripcion=descripcion.strip(),
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                
                success = db.create_politica_entrega(nueva_politica)
                
                if success:
                    st.success("✅ Política de entrega creada exitosamente.")
                    st.rerun()
                else:
                    st.error("❌ Error al crear la política de entrega.")
                    
            except Exception as e:
                st.error(f"Error al crear la política: {str(e)}")
                traceback.print_exc()

def show_edit_policy_form(db: DBManager):
    """Muestra el formulario para editar una política existente"""
    st.markdown("### Editar Política de Entrega")
    
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politicas_entrega'):
            st.error("❌ Error: El método 'get_politicas_entrega' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return
        
        # Obtener políticas para el selector
        politicas = db.get_politicas_entrega()
        
        if not politicas:
            st.info("No hay políticas disponibles para editar.")
            return
        
        # Selector de política
        opciones = {f"{p.id} - {p.descripcion[:50]}...": p.id for p in politicas}
        politica_seleccionada = st.selectbox(
            "Seleccionar política a editar:",
            options=list(opciones.keys()),
            key="edit_policy_selector"
        )
        
        if politica_seleccionada:
            politica_id = opciones[politica_seleccionada]
            politica = next((p for p in politicas if p.id == politica_id), None)
            
            if politica:
                with st.form("edit_policy_form"):
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
                            print(f"Actualizando política {politica.id}...")
                            print(f"Descripción original: {politica.descripcion}")
                            print(f"Descripción editada: {descripcion_editada.strip()}")
                            
                            politica_actualizada = PoliticasEntrega(
                                id=politica.id,
                                descripcion=descripcion_editada.strip(),
                                created_at=politica.created_at,
                                updated_at=datetime.now()
                            )
                            
                            print(f"Objeto PoliticasEntrega creado: {vars(politica_actualizada)}")
                            success = db.update_politica_entrega(politica_actualizada)
                            
                            if success:
                                st.success("✅ Política de entrega actualizada exitosamente.")
                                # Verificar que la actualización fue exitosa
                                politica_verificada = db.get_politica_entrega(politica.id)
                                if politica_verificada and politica_verificada.descripcion == descripcion_editada.strip():
                                    st.success("✅ Verificación exitosa - Los cambios se guardaron correctamente.")
                                    st.rerun()
                                else:
                                    st.warning("⚠️ La actualización parece haber fallado. Por favor, verifique los cambios.")
                            else:
                                st.error("❌ Error al actualizar la política de entrega.")
                                st.info("💡 Intente nuevamente o contacte al administrador del sistema.")
                                
                        except Exception as e:
                            st.error(f"Error al actualizar la política: {str(e)}")
                            traceback.print_exc()
                    
                    elif cancel:
                        st.rerun()
                        
    except Exception as e:
        st.error(f"Error al cargar las políticas para edición: {str(e)}")
        traceback.print_exc()

def delete_policy(db: DBManager, politica_id: int) -> bool:
    """Elimina una política de entrega"""
    try:
        # Verificar si la política está siendo usada en cotizaciones
        cotizaciones_con_politica = db.get_cotizaciones_by_politica(politica_id)
        
        if cotizaciones_con_politica:
            st.warning(f"⚠️ No se puede eliminar la política porque está siendo utilizada en {len(cotizaciones_con_politica)} cotización(es).")
            return False
        
        # Eliminar la política
        success = db.delete_politica_entrega(politica_id)
        return success
        
    except Exception as e:
        st.error(f"Error al eliminar la política: {str(e)}")
        traceback.print_exc()
        return False

def show_policy_selection(db: DBManager, selected_policy_id: Optional[int] = None, key: str = "policy_selection") -> Optional[int]:
    """Muestra un selector de políticas de entrega para usar en otros formularios"""
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politicas_entrega'):
            st.error("❌ Error: El método 'get_politicas_entrega' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return None
        
        politicas = db.get_politicas_entrega()
        
        if not politicas:
            st.info("No hay políticas de entrega configuradas.")
            return None
        
        # Crear opciones para el selector
        opciones = [(None, "Sin política de entrega")]
        opciones.extend([(p.id, f"Política #{p.id} - {p.descripcion[:50]}...") for p in politicas])
        
        # Encontrar el índice de la política seleccionada
        selected_index = 0
        for i, (policy_id, _) in enumerate(opciones):
            if policy_id == selected_policy_id:
                selected_index = i
                break
        
        selected_option = st.selectbox(
            "Política de Entrega:",
            options=opciones,
            index=selected_index,
            format_func=lambda x: x[1],
            key=key
        )
        
        return selected_option[0] if selected_option else None
        
    except Exception as e:
        st.error(f"Error al cargar las políticas de entrega: {str(e)}")
        return None

def show_edit_single_policy(db: DBManager):
    """Muestra el formulario para editar la única política de entrega"""
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politica_entrega'):
            st.error("❌ Error: El método 'get_politica_entrega' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return
        
        # Obtener la política única (siempre ID=1)
        politica = db.get_politica_entrega(1)
        
        if politica:
            with st.form("edit_single_policy_form"):
                st.markdown("**Editar Política de Entrega**")
                
                descripcion_editada = st.text_area(
                    "Descripción:",
                    value=politica.descripcion,
                    height=200,
                    help="Esta política se aplicará a todas las cotizaciones. Use saltos de línea para separar diferentes puntos."
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    submitted = st.form_submit_button("Guardar Cambios", type="primary")
                
                if submitted:
                    if not descripcion_editada.strip():
                        st.error("La descripción no puede estar vacía.")
                        return
                    
                    try:
                        # Actualizar la política
                        print(f"Actualizando política {politica.id}...")
                        print(f"Descripción original: {politica.descripcion}")
                        print(f"Descripción editada: {descripcion_editada.strip()}")
                        
                        politica_actualizada = PoliticasEntrega(
                            id=politica.id,
                            descripcion=descripcion_editada.strip(),
                            created_at=politica.created_at,
                            updated_at=datetime.now()
                        )
                        
                        print(f"Objeto PoliticasEntrega creado: {vars(politica_actualizada)}")
                        success = db.update_politica_entrega(politica_actualizada)
                        
                        if success:
                            st.success("✅ Política de entrega actualizada exitosamente.")
                            st.rerun()
                        else:
                            st.error("❌ Error al actualizar la política de entrega.")
                            st.info("💡 Intente nuevamente o contacte al administrador del sistema.")
                            
                    except Exception as e:
                        st.error(f"Error al actualizar la política: {str(e)}")
                        traceback.print_exc()
        else:
            # Si no existe la política, mostrar formulario para crearla
            with st.form("create_single_policy_form"):
                st.markdown("**Crear Política de Entrega**")
                st.info("No existe una política de entrega. Por favor, cree una.")
                
                descripcion = st.text_area(
                    "Descripción:",
                    height=200,
                    placeholder="Ejemplo:\nRepeticiones: 8 días calendario desde el envío de la OC\nCambios: 13 días calendario desde la aprobación de la sherpa\nNuevas: 15 días calendario desde la aprobación de la sherpa",
                    help="Esta política se aplicará a todas las cotizaciones. Use saltos de línea para separar diferentes puntos."
                )
                
                submitted = st.form_submit_button("Crear Política", type="primary")
                
                if submitted:
                    if not descripcion.strip():
                        st.error("La descripción no puede estar vacía.")
                        return
                    
                    try:
                        # Crear la nueva política
                        nueva_politica = PoliticasEntrega(
                            id=1,  # Siempre ID=1
                            descripcion=descripcion.strip(),
                            created_at=datetime.now(),
                            updated_at=datetime.now()
                        )
                        
                        success = db.create_politica_entrega(nueva_politica)
                        
                        if success:
                            st.success("✅ Política de entrega creada exitosamente.")
                            st.rerun()
                        else:
                            st.error("❌ Error al crear la política de entrega.")
                            
                    except Exception as e:
                        st.error(f"Error al crear la política: {str(e)}")
                        traceback.print_exc()
    except Exception as e:
        st.error(f"Error al cargar la política de entrega: {str(e)}")
        traceback.print_exc()

def show_policy_details(politica_id: int, db: DBManager):
    """Muestra los detalles de una política de entrega específica"""
    try:
        # Verificar que el DBManager tiene los métodos necesarios
        if not hasattr(db, 'get_politica_entrega'):
            st.error("❌ Error: El método 'get_politica_entrega' no está disponible en DBManager.")
            st.info("💡 Solución: Reinicie la aplicación completamente para cargar los nuevos métodos.")
            return
        
        politica = db.get_politica_entrega(politica_id)
        if politica:
            with st.expander(f"📋 Política de Entrega #{politica.id}", expanded=True):
                st.text_area(
                    "Descripción:",
                    value=politica.descripcion,
                    height=100,
                    disabled=True,
                    key=f"policy_details_{politica.id}"
                )
        else:
            st.warning("Política de entrega no encontrada.")
    except Exception as e:
        st.error(f"Error al cargar los detalles de la política: {str(e)}")
