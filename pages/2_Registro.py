import streamlit as st
from supabase import Client, PostgrestAPIResponse
import traceback # Para imprimir errores detallados si es necesario

# --- Configuración de la Página ---
st.set_page_config(page_title="Registro por Invitación", layout="centered")
st.title("📝 Registro por Invitación")

# --- Helper para obtener el cliente Supabase ---
def get_supabase_client() -> Client | None:
    """Obtiene el cliente Supabase desde el session_state."""
    if 'supabase' not in st.session_state:
        st.error("Error: Cliente Supabase no inicializado.")
        st.warning("Por favor, inicie sesión primero o asegúrese de que la configuración inicial se haya ejecutado.")
        st.stop() # Detiene la ejecución si no hay cliente
    return st.session_state.supabase

# --- Función para validar el token ---
def validar_token_invitacion(supabase: Client, token: str) -> dict | None:
    """
    Valida un token en la tabla 'invitaciones'.
    Retorna los datos de la invitación si es válida y no usada, None si no.
    """
    try:
        response: PostgrestAPIResponse = supabase.table('invitaciones') \
            .select('*') \
            .eq('token', token) \
            .eq('usado', False) \
            .maybe_single() \
            .execute()

        if response.data:
            return response.data
        else:
            # Podría no existir o ya estar usado
            check_used: PostgrestAPIResponse = supabase.table('invitaciones') \
                .select('token') \
                .eq('token', token) \
                .eq('usado', True) \
                .maybe_single() \
                .execute()
            if check_used.data:
                st.error("Este enlace de invitación ya ha sido utilizado.")
            else:
                st.error("Enlace de invitación inválido o caducado.")
            return None
    except Exception as e:
        st.error(f"Error al validar el token: {e}")
        print(f"Error detallado al validar token: {traceback.format_exc()}")
        return None

# --- Función para marcar el token como usado ---
def marcar_token_usado(supabase: Client, token: str) -> bool:
    """Marca un token como usado en la base de datos."""
    try:
        supabase.table('invitaciones') \
            .update({'usado': True, 'usado_en': 'now()'}) \
            .eq('token', token) \
            .execute()
        return True
    except Exception as e:
        st.error(f"Error al actualizar el estado del token: {e}")
        print(f"Error detallado al marcar token usado: {traceback.format_exc()}")
        return False

# --- Lógica Principal de la Página ---
supabase_client = get_supabase_client()

if supabase_client:
    # 1. Leer el token de la URL
    query_params = st.query_params
    token_invitacion = query_params.get("token")

    if not token_invitacion:
        st.warning("No se proporcionó un token de invitación en la URL.")
        st.info("Si recibiste un enlace de invitación, asegúrate de usar el enlace completo.")
        st.stop()

    # 2. Validar el token
    invitacion_data = validar_token_invitacion(supabase_client, token_invitacion)

    if invitacion_data:
        st.success("¡Enlace de invitación válido!")
        st.markdown("---")
        st.subheader("Completa tus datos para registrarte:")

        email_prellenado = invitacion_data.get('email_invitado', '')

        with st.form("registro_form"):
            email = st.text_input("Email", value=email_prellenado, placeholder="tu@email.com", key="register_email")
            password = st.text_input("Contraseña", type="password", placeholder="Crea una contraseña segura", key="register_password")
            password_confirm = st.text_input("Confirmar Contraseña", type="password", placeholder="Repite tu contraseña", key="register_password_confirm")

            submitted = st.form_submit_button("Registrarse", use_container_width=True)

            if submitted:
                if not email:
                    st.error("Por favor, ingresa tu email.")
                elif not password:
                    st.error("Por favor, ingresa una contraseña.")
                elif password != password_confirm:
                    st.error("Las contraseñas no coinciden.")
                else:
                    # 3. Intentar registrar al usuario en Supabase Auth
                    try:
                        auth_response = supabase_client.auth.sign_up({
                            "email": email,
                            "password": password,
                            # Puedes añadir data adicional si tu trigger la usa
                            # "options": {
                            #    "data": {"nombre_inicial": "Usuario Invitado"}
                            # }
                        })

                        # Verificar si el sign_up fue exitoso (puede requerir confirmación por email)
                        # Nota: auth_response.user estará presente si la cuenta se crea
                        # y la confirmación está desactivada o ya se hizo.
                        # Si la confirmación está activada, auth_response.user será None
                        # hasta que el usuario confirme su email.

                        if auth_response.user or (not auth_response.user and auth_response.session is None): # Ajusta según tu config de confirmación
                            # 4. Marcar el token como usado SI el registro fue exitoso
                            if marcar_token_usado(supabase_client, token_invitacion):
                                st.success("¡Registro completado exitosamente!")
                                st.info("Ahora puedes ir a la página de Login para iniciar sesión.")
                                # Opcional: Añadir un botón/enlace para ir al login si tienes una app multipágina
                                # if st.button("Ir a Login"):
                                #    st.switch_page("pages/1_Login.py") # Ajusta el nombre del archivo
                                # Limpiar el formulario o estado si es necesario
                            else:
                                # Esto es un caso raro: usuario creado pero token no se marcó
                                st.error("Usuario registrado, pero hubo un problema al invalidar el enlace. Contacta soporte.")

                        # Manejar errores específicos de Supabase si es necesario
                        # (Supabase Python < 2.0 devolvía errores en un dict, >= 2.0 lanza excepciones)
                        # Esta parte puede necesitar ajustes según tu versión de supabase-py

                    except Exception as e:
                        # Captura excepciones genéricas y errores específicos de Supabase Auth
                        error_message = str(e)
                        if "User already registered" in error_message:
                             st.error("Ya existe una cuenta registrada con este email.")
                        elif "Password should be at least 6 characters" in error_message:
                            st.error("La contraseña debe tener al menos 6 caracteres.")
                        else:
                             st.error(f"Error durante el registro: {error_message}")
                        print(f"Error detallado en sign_up: {traceback.format_exc()}")

    # Si invitacion_data es None, el error ya se mostró en validar_token_invitacion
    # y la ejecución del formulario no ocurrirá.

# Mensaje si el cliente Supabase no se pudo obtener inicialmente
else:
    st.error("No se pudo establecer la conexión con la base de datos.")

def crear_enlace_invitacion(supabase: Client, email_invitado: str | None = None) -> str | None:
    """
    Crea una nueva entrada en la tabla 'invitaciones', recupera el token
    generado por la DB y construye el enlace de invitación completo.

    Args:
        supabase: El cliente Supabase inicializado.
        email_invitado: El email del usuario a invitar (opcional).

    Returns:
        El enlace de invitación completo (str) o None si hubo un error.
    """
    try:
        insert_data = {}
        if email_invitado:
            insert_data['email_invitado'] = email_invitado

        # Inserta la fila (token se genera automáticamente) y pide que devuelva los datos ('*')
        response: PostgrestAPIResponse = supabase.table('invitaciones') \
            .insert(insert_data, returning='representation') \
            .execute()

        # La respuesta debería contener los datos de la fila insertada
        if response.data and len(response.data) > 0:
            nuevo_token = response.data[0].get('token')
            if nuevo_token:
                # Construye la URL base de tu app Streamlit
                # TODO: Ajusta esta URL si tu app corre en otro lugar que no sea localhost:8501
                base_url = "http://localhost:8501"
                # Asegúrate de que la ruta coincida con el nombre de tu archivo de página
                # Si es pages/2_Registro.py, la ruta es /Registro
                pagina_registro = "Registro" # O el nombre que le diste a la página
                
                enlace = f"{base_url}/{pagina_registro}?token={nuevo_token}"
                print(f"Enlace de invitación generado: {enlace}") # Log para debugging
                return enlace
            else:
                st.error("Error: La inserción fue exitosa pero no se pudo obtener el token generado.")
                return None
        else:
            # st.error(f"Error al crear la invitación en la base de datos. Respuesta: {response}")
            print(f"Error en la respuesta de Supabase al insertar invitación: {response}")
            st.error("Error al crear la invitación en la base de datos.")
            return None

    except Exception as e:
        st.error(f"Error inesperado al crear la invitación: {e}")
        print(f"Error detallado al crear invitación: {traceback.format_exc()}")
        return None

# --- Ejemplo de uso (en una página de admin, por ejemplo) ---
# if 'supabase' in st.session_state:
#     supabase_client = st.session_state['supabase']
#     st.subheader("Generar Invitación")
#     email_a_invitar = st.text_input("Email del invitado (opcional)")
#     if st.button("Generar Enlace"):
#         enlace = crear_enlace_invitacion(supabase_client, email_a_invitar if email_a_invitar else None)
#         if enlace:
#             st.success("Enlace de invitación generado:")
#             st.code(enlace, language=None) # Muestra el enlace para copiar/enviar
#         # Si enlace es None, la función crear_enlace_invitacion ya mostró el error
# else:
#     st.warning("Cliente Supabase no disponible.")
