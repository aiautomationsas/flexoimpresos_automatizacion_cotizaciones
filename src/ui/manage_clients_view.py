import streamlit as st
import pandas as pd
import time
import traceback

# Importaciones del proyecto
from src.data.database import DBManager
from src.data.models import Cliente # Importar el modelo Cliente

def show_manage_clients():
    """Muestra la vista para gestionar clientes."""
    st.title("Gestión de Clientes")

    # Botón para crear nuevo cliente
    if st.button("➕ Crear Nuevo Cliente"):
        # Cambiar la vista en session_state para que app.py la maneje
        st.session_state.current_view = 'crear_cliente'
        st.rerun()
        # No retornar aquí directamente, dejar que el flujo principal maneje la vista

    st.divider()
    st.subheader("Clientes Existentes")

    if 'db' not in st.session_state:
        st.error("Error: La conexión a la base de datos no está inicializada.")
        return

    db_manager: DBManager = st.session_state.db
    # user_role = st.session_state.usuario_rol # Rol no se usa aquí directamente

    try:
        clientes = db_manager.get_clientes()
        if clientes:
            # Crear DataFrame para mostrar los clientes
            df_clientes = pd.DataFrame([{
                'NIT': c.codigo,
                'Nombre': c.nombre,
                'Contacto': c.persona_contacto or '-', # Usar '-' si es None
                'Correo': c.correo_electronico or '-',
                'Teléfono': c.telefono or '-'
            } for c in clientes])

            st.dataframe(
                df_clientes,
                hide_index=True,
                use_container_width=True,
                # Configuración adicional de la tabla si se desea
                # column_config={
                #     "NIT": st.column_config.TextColumn(width="small"),
                #     "Nombre": st.column_config.TextColumn(width="large"),
                # }
            )
        else:
            st.info("No hay clientes registrados.")

    except Exception as e:
        st.error(f"Error al cargar los clientes: {str(e)}")
        traceback.print_exc()

def show_create_client():
    """Muestra el formulario para crear un nuevo cliente."""
    st.title("Crear Nuevo Cliente")

    # Botón para volver a la lista de clientes
    if st.button("← Volver a la lista de clientes"):
        st.session_state.current_view = 'manage_clients'
        st.rerun()
        # No retornar, dejar que el flujo principal maneje la vista

    # Formulario de creación de cliente
    with st.form("crear_cliente_form"):
        st.write("### Información del Cliente")

        # Campos del formulario
        nit = st.text_input("NIT/CC *",
                           help="Identificador único del cliente (solo números)",
                           key="create_client_nit")
        nombre = st.text_input("Nombre del Cliente *",
                             help="Nombre completo o razón social",
                             key="create_client_nombre")

        col1, col2 = st.columns(2)
        with col1:
            contacto = st.text_input("Persona de Contacto",
                                   help="Nombre de la persona de contacto",
                                   key="create_client_contacto")
            telefono = st.text_input("Teléfono",
                                   help="Número de teléfono del cliente",
                                   key="create_client_telefono")

        with col2:
            email = st.text_input("Correo Electrónico",
                                help="Correo electrónico de contacto",
                                key="create_client_email")

        # Botón de submit
        submitted = st.form_submit_button("Crear Cliente")

        if submitted:
            error_creacion = False
            # Validaciones básicas
            if not nit or not nombre:
                st.error("Los campos NIT y Nombre son obligatorios.")
                error_creacion = True

            # Validar que el NIT sea numérico
            if not error_creacion and not nit.isdigit():
                st.error("El NIT debe contener solo números.")
                error_creacion = True

            # Validar formato de correo si se proporciona
            if not error_creacion and email and '@' not in email:
                st.error("Por favor ingrese un correo electrónico válido.")
                error_creacion = True

            if not error_creacion:
                try:
                    # Crear objeto Cliente (usando el modelo importado)
                    nuevo_cliente = Cliente(
                        id=None,  # El ID será asignado por la base de datos
                        codigo=nit, # Guardar como string, la DB lo manejará si es bigint
                        nombre=nombre,
                        persona_contacto=contacto if contacto else None,
                        correo_electronico=email if email else None,
                        telefono=telefono if telefono else None
                        # creado_en y actualizado_en se manejan en DB
                    )

                    # Intentar crear el cliente
                    if 'db' not in st.session_state:
                         st.error("Error crítico: Conexión DB no disponible.")
                         return # Salir si no hay DB

                    db = st.session_state.db
                    cliente_creado = db.crear_cliente(nuevo_cliente)

                    if cliente_creado:
                        st.success("¡Cliente creado exitosamente!")
                        # Esperar un momento y cambiar vista para redirigir
                        time.sleep(1.5)
                        st.session_state.current_view = 'manage_clients'
                        st.rerun()
                    else:
                        # DBManager debería idealmente lanzar una excepción o devolver False con un error
                        st.error("No se pudo crear el cliente (DB devolvió False o None). Por favor, revise los logs o la implementación de DBManager.")

                except Exception as e:
                    error_msg = str(e)
                    if "duplicate key value violates unique constraint" in error_msg.lower() and 'clientes_codigo_key' in error_msg.lower():
                        st.error(f"Error: Ya existe un cliente con el NIT {nit}.")
                    elif "check constraint" in error_msg.lower(): # Ejemplo de otra restricción
                         st.error(f"Error de validación en la base de datos: {error_msg}")
                    else:
                        st.error(f"Error inesperado al crear el cliente: {error_msg}")

                    print(f"Error detallado creando cliente: {e}")
                    traceback.print_exc()
                    # No hacer rerun aquí, permitir al usuario corregir 