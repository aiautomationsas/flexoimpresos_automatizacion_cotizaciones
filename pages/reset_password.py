# pages/reset_password.py
import streamlit as st
from supabase import create_client, Client
import time # Para el manejo del evento de autenticación

st.set_page_config(page_title="Restablecer Contraseña", layout="centered")

st.title("🔑 Restablecer Contraseña")

# --- Inicialización del cliente Supabase ---
# (Asegúrate de que el cliente Supabase esté disponible, idealmente inicializado en la app principal
# y accesible a través de st.session_state si no se reinicia en cada página)
if 'supabase' not in st.session_state:
    try:
        supabase_url = st.secrets["SUPABASE_URL"]
        supabase_key = st.secrets["SUPABASE_KEY"]
        st.session_state.supabase = create_client(supabase_url, supabase_key)
    except Exception as e:
        st.error(f"Error al inicializar Supabase: {e}")
        st.stop()

supabase: Client = st.session_state.supabase

# --- NUEVO: Extraer tokens de la URL y establecer sesión --- 
access_token = st.query_params.get("access_token")
refresh_token = st.query_params.get("refresh_token")

user = None
is_recovery_session = False
error_message = None

if access_token and refresh_token:
    try:
        # Establecer la sesión usando los tokens de la URL
        session_response = supabase.auth.set_session(access_token, refresh_token)
        # Verificar si la sesión se estableció y obtener el usuario
        if session_response and session_response.user:
            user = session_response.user
            is_recovery_session = True
            st.info(f"Sesión de recuperación establecida para {user.email}. Introduce tu nueva contraseña.")
        else:
            # Esto no debería ocurrir si set_session tiene éxito con user
            error_message = "No se pudo verificar la sesión con los tokens proporcionados."
            print("Error: set_session no devolvió un usuario válido.")

    except Exception as e:
        error_message = f"Error al procesar los tokens de recuperación: {e}"
        print(f"Error en set_session: {e}")
        # Posibles causas: token inválido, expirado, error de red.
else:
    # No se encontraron tokens en la URL
    error_message = ("No se encontraron los tokens necesarios en la URL. " 
                    "Asegúrate de haber accedido a esta página directamente desde el enlace del correo electrónico.")

# --- Mostrar error si la sesión no se pudo establecer ---
if error_message and not is_recovery_session:
    st.error(error_message)
    # Opcional: Mantener el enlace para solicitar uno nuevo si falla
    st.markdown("Si necesitas un nuevo enlace, solicítalo [aquí](<URL_de_tu_pagina_solicitud_reset>)") # Reemplaza con tu URL real
    st.stop()

# --- Formulario de Nueva Contraseña (solo si la sesión es válida) ---
if is_recovery_session and user:
    # st.write(f"Estableciendo nueva contraseña para: **{user.email}**") # El st.info de arriba ya lo indica
    with st.form("reset_password_form"):
        new_password = st.text_input("Nueva Contraseña", type="password", key="new_pass")
        confirm_password = st.text_input("Confirmar Nueva Contraseña", type="password", key="confirm_pass")
        submitted = st.form_submit_button("Actualizar Contraseña")

        if submitted:
            if not new_password or not confirm_password:
                st.error("Por favor, completa ambos campos.")
            elif new_password != confirm_password:
                st.error("Las contraseñas no coinciden.")
            elif len(new_password) < 6: # Añade las validaciones que necesites
                 st.error("La contraseña debe tener al menos 6 caracteres.")
            else:
                try:
                    # Ahora que la sesión está establecida, update_user debería funcionar
                    supabase.auth.update_user({"password": new_password})
                    st.success("¡Contraseña actualizada con éxito! Ya puedes iniciar sesión con tu nueva contraseña.")
                    st.balloons()
                    # Limpiar query params para evitar re-procesamiento si el usuario navega atrás/adelante
                    st.query_params.clear()
                    # Opcional: Redirigir al login después de un momento
                    time.sleep(3)
                    # --- CAMBIO: Redirigir al script principal de la app ---
                    st.switch_page("app_calculadora_costos.py")

                except Exception as e:
                    st.error(f"Error al actualizar la contraseña: {e}")
                    # Podría ser un token inválido (quizás ya usado), expirado, etc.
                    print(f"Error Supabase update_user: {e}") # Log detallado

elif not is_recovery_session and not error_message:
     # Caso raro: no hay tokens, no hay error previo, pero tampoco sesión
     st.warning("Acceso inválido a la página de restablecimiento.")
     st.markdown("Si necesitas un nuevo enlace, solicítalo [aquí](<URL_de_tu_pagina_solicitud_reset>)") # Reemplaza con tu URL real
     st.stop() 