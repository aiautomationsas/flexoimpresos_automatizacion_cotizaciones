import streamlit as st
from typing import Dict, Any, List, Optional
from src.data.models.cliente import Cliente  # Asumiendo que Cliente está definido aquí
from src.data.database import DBManager  # Asumiendo que DBManager está definido aquí

# --- Helper Functions for Input Sections ---

def _mostrar_escalas(datos: Dict[str, Any]):
    """Muestra y procesa el input de escalas."""
    st.subheader("Cantidades a Cotizar")
    default_escalas_texto = st.session_state.get('escalas_texto_value', "1000, 2500, 5000")
    escalas_texto = st.text_input(
        "Escalas (separadas por comas)",
        value=default_escalas_texto,
        key="escalas_texto_input",
        help="Ingrese múltiples cantidades separadas por comas. Ejemplo: 1000, 2500, 5000"
    )

    try:
        escalas_usuario = [int(e.strip()) for e in escalas_texto.split(",") if e.strip()]
        escalas_usuario = sorted(list(set(escalas_usuario))) # Asegurar lista única y ordenada

        # Guardar el valor en session_state si cambia
        if st.session_state.get('escalas_texto_value', "") != escalas_texto:
            st.session_state['escalas_texto_value'] = escalas_texto
            st.rerun() # Forzar rerun para actualizar la UI si es necesario

        if not escalas_usuario:
             st.warning("Ingrese al menos una escala.")
             datos['escalas'] = []
        elif any(e < 100 for e in escalas_usuario):
            raise ValueError("Las escalas deben ser mayores o iguales a 100.")
        else:
            datos['escalas'] = escalas_usuario

    except ValueError as e:
        st.error(f"Error en las escalas: {e}")
        datos['escalas'] = []
    except Exception:
        st.error("Por favor ingrese las escalas como números enteros separados por comas.")
        datos['escalas'] = []

def _mostrar_dimensiones_y_tintas(datos: Dict[str, Any], es_manga: bool):
    """Muestra los inputs de dimensiones (ancho, avance, pistas) y número de tintas."""
    st.subheader("Dimensiones y Colores")
    col1, col2 = st.columns(2)
    with col1:
        datos['ancho'] = st.number_input("Ancho (mm)", min_value=1.00, format="%.2f", key="ancho", value=st.session_state.get("ancho", 100.0))
        datos['avance'] = st.number_input("Avance (mm)", min_value=1.00, format="%.2f", key="avance", value=st.session_state.get("avance", 150.0))
    with col2:
        # --- Pistas ---
        usuario_rol = st.session_state.get('usuario_rol', '')
        if es_manga:
            if usuario_rol == 'comercial':
                # Mostrar como texto no editable para comercial en manga
                st.markdown('<label style="font-size: 0.875rem; color: #555;">Número de pistas</label>', unsafe_allow_html=True)
                st.markdown('<div style="padding: 0.5rem 0; color: #333; font-weight: bold;">1</div>', unsafe_allow_html=True)
                datos['pistas'] = 1
                st.session_state['num_pistas_manga'] = 1 # Guardar en session state también
            else:
                # Input numérico para admin/otros en manga
                datos['pistas'] = st.number_input(
                    "Número de pistas",
                    min_value=1,
                    step=1,
                    key="num_pistas_manga",
                    value=st.session_state.get("num_pistas_manga", 1)
                )
        else:
            # Input numérico para no-manga (todos los roles)
            datos['pistas'] = st.number_input(
                "Número de pistas",
                min_value=1,
                step=1,
                key="num_pistas_otro",
                 value=st.session_state.get("num_pistas_otro", 1)
            )

        # --- Tintas ---
        datos['num_tintas'] = st.number_input("Número de tintas", min_value=0, step=1, key="num_tintas", value=st.session_state.get("num_tintas", 3))


def _mostrar_material(datos: Dict[str, Any], es_manga: bool, materiales: List[Any]):
    """
    Muestra el selector de material, filtrando si es manga.

    Args:
        datos: Diccionario para almacenar los datos del formulario.
        es_manga: Boolean indicando si el producto es manga.
        materiales: Lista completa de objetos de material.
    """
    st.subheader("Material")
    # No acceder a st.session_state.db aquí

    if es_manga:
        materiales_filtrados = [m for m in materiales if m.id in [17, 18]] # IDs específicos para manga
    else:
        materiales_filtrados = materiales # Todos los materiales para otros productos

    # Guardar el ID seleccionado previamente para mantener la selección
    selected_material_id = st.session_state.get("material_id", None)

    # Encontrar el índice del material seleccionado previamente
    try:
        index = next(i for i, m in enumerate(materiales_filtrados) if m.id == selected_material_id)
    except StopIteration:
        index = 0 # Default al primero si no se encuentra o es la primera vez

    material_seleccionado = st.selectbox(
        "Seleccione el Material",
        options=materiales_filtrados,
        format_func=lambda m: m.nombre,
        key="material_select",
        index=index
    )

    if material_seleccionado:
        datos['material_id'] = material_seleccionado.id
        st.session_state["material_id"] = material_seleccionado.id # Guardar para persistencia
    else:
        datos['material_id'] = None
        st.session_state["material_id"] = None
        st.warning("Por favor seleccione un material.")


def _mostrar_acabados_y_empaque(datos: Dict[str, Any], es_manga: bool, tipos_grafado: List[Any], acabados: List[Any]):
    """
    Muestra los inputs relacionados con acabados, grafado y empaque.

    Args:
        datos: Diccionario para almacenar los datos del formulario.
        es_manga: Boolean indicando si el producto es manga.
        tipos_grafado: Lista de objetos de tipo grafado.
        acabados: Lista de objetos de acabado.
    """
    st.subheader("Acabados y Empaque")
    col1, col2 = st.columns(2)
    # No acceder a st.session_state.db aquí

    with col1:
        if es_manga:
            # --- Grafado (Solo Manga) ---
            # tipos_grafado ya viene como argumento
            selected_grafado_id = st.session_state.get("grafado_seleccionado_id", 1) # Default a "Sin grafado" (ID 1)

            try:
                index_grafado = next(i for i, tg in enumerate(tipos_grafado) if tg.id == selected_grafado_id)
            except StopIteration:
                index_grafado = 0

            tipo_grafado_seleccionado = st.selectbox(
                "Tipo de grafado",
                options=tipos_grafado,
                format_func=lambda tg: tg.nombre,
                key="tipo_grafado_select",
                index=index_grafado
            )

            if tipo_grafado_seleccionado:
                current_selected_id = tipo_grafado_seleccionado.id
                datos['tipo_grafado_id'] = current_selected_id

                # Actualizar session_state solo si cambia
                if st.session_state.get("grafado_seleccionado_id") != current_selected_id:
                    st.session_state["grafado_seleccionado_id"] = current_selected_id
                    # Limpiar altura si el grafado no lo requiere
                    if current_selected_id not in [3, 4]:
                         st.session_state["altura_grafado"] = 0.0
                    st.rerun() # Rerun para actualizar UI de altura_grafado
            else:
                 datos['tipo_grafado_id'] = None


            # --- Altura Grafado (Condicional) ---
            # Usar el ID almacenado en session_state para decidir si mostrar
            grafado_id_for_altura = st.session_state.get("grafado_seleccionado_id")
            if grafado_id_for_altura in [3, 4]:
                 datos['altura_grafado'] = st.number_input(
                    "Altura de grafado (mm)",
                    min_value=0.0,
                    format="%.2f",
                    help="Requerido para Grafado Horizontal Total o H.Total+Vertical",
                    key="altura_grafado",
                    value=st.session_state.get("altura_grafado", 0.0)
                 )
            else:
                 datos['altura_grafado'] = None # No aplica
                 # No es necesario mostrar nada si no aplica


        else:
            # --- Acabado (Solo No-Manga) ---
            # acabados ya viene como argumento
            # Incluir opción "Sin acabado" representada por None
            opciones_acabado = [(None, "Sin acabado")] + [(ac.id, ac.nombre) for ac in acabados]

            selected_acabado_id = st.session_state.get("acabado_id", None)

            # Encontrar índice
            try:
                index_acabado = next(i for i, (id, _) in enumerate(opciones_acabado) if id == selected_acabado_id)
            except StopIteration:
                index_acabado = 0 # Default a "Sin acabado"

            selected_option = st.selectbox(
                "Acabado",
                options=opciones_acabado,
                format_func=lambda opt: opt[1], # Mostrar el nombre
                key="acabado_select",
                index=index_acabado
            )

            datos['acabado_id'] = selected_option[0] # Guardar el ID (o None)
            st.session_state["acabado_id"] = selected_option[0] # Guardar en session state


    with col2:
        # --- Número de Paquetes/Rollos ---
        if es_manga:
            # Fijo para manga
            st.markdown('<label style="font-size: 0.875rem; color: #555;">Número de paquetes/rollos</label>', unsafe_allow_html=True)
            st.markdown('<div style="padding: 0.5rem 0; color: #333; font-weight: bold;">100</div>', unsafe_allow_html=True)
            datos['num_paquetes'] = 100
            st.session_state['num_paquetes_manga'] = 100
        else:
            # Input para no-manga
            datos['num_paquetes'] = st.number_input(
                "Número de paquetes/rollos",
                min_value=1,
                step=1,
                key="num_paquetes_otro",
                value=st.session_state.get("num_paquetes_otro", 1)
            )


def _mostrar_opciones_adicionales(datos: Dict[str, Any], es_manga: bool):
    """Muestra checkboxes para opciones adicionales (troquel, planchas separadas)."""
    # Mostrar el subheader solo si hay alguna opción visible
    mostrar_subheader = (not es_manga) or (st.session_state.get('usuario_rol') == 'administrador')
    if mostrar_subheader:
        st.subheader("Opciones Adicionales")

    col1, col2 = st.columns(2)
    with col1:
        if not es_manga: # Condición para mostrar el checkbox
            datos['tiene_troquel'] = st.checkbox(
                "¿Existe troquel?",
                key="tiene_troquel",
                value=st.session_state.get("tiene_troquel", False)
                )
        else:
            datos['tiene_troquel'] = False # Valor por defecto si es manga
        # st.session_state["tiene_troquel"] = datos['tiene_troquel'] # REMOVED: Widget handles state via key

    with col2:
        # Planchas separadas solo visible para administradores
        if st.session_state.get('usuario_rol') == 'administrador':
            datos['planchas_separadas'] = st.checkbox(
                "¿Planchas por separado?",
                key="planchas_separadas",
                value=st.session_state.get("planchas_separadas", False)
                )
            # st.session_state["planchas_separadas"] = datos['planchas_separadas'] # REMOVED: Widget handles state via key
        else:
            datos['planchas_separadas'] = False # Default para no admin


# --- Helper Function for Payment Method ---

def _mostrar_formas_pago(datos: Dict[str, Any], formas_pago: List[Any]):
    """
    Muestra el selector de forma de pago.

    Args:
        datos: Diccionario para almacenar los datos del formulario.
        formas_pago: Lista completa de objetos de forma de pago.
    """
    st.subheader("Forma de Pago")

    if not formas_pago:
        st.warning("No hay formas de pago disponibles para seleccionar.")
        datos['forma_pago_id'] = None
        return

    # Guardar el ID seleccionado previamente para mantener la selección
    selected_forma_pago_id = st.session_state.get("forma_pago_id", None)

    # Encontrar el índice de la forma de pago seleccionada previamente
    try:
        # Default al primero si no se encuentra o es la primera vez
        index = next(i for i, fp in enumerate(formas_pago) if fp.id == selected_forma_pago_id)
    except (StopIteration, AttributeError): # Manejar casos donde no se encuentra o la lista está vacía/mal formada
        index = 0

    forma_pago_seleccionada = st.selectbox(
        "Seleccione la Forma de Pago",
        options=formas_pago,
        format_func=lambda fp: fp.descripcion, # Use 'descripcion' instead of 'nombre'
        key="forma_pago_select",
        index=index
    )

    if forma_pago_seleccionada:
        datos['forma_pago_id'] = forma_pago_seleccionada.id
        st.session_state["forma_pago_id"] = forma_pago_seleccionada.id # Guardar para persistencia
    else:
        # Esto puede ocurrir si la lista de formas_pago está vacía inicialmente
        datos['forma_pago_id'] = None
        st.session_state["forma_pago_id"] = None
        st.warning("Por favor seleccione una forma de pago.")


# --- Main Function ---

def mostrar_formulario_producto(cliente: Optional[Cliente] = None) -> Dict[str, Any]:
    """
    Muestra los campos del formulario para ingresar los datos del producto,
    organizados por secciones lógicas.

    ASUME:
    - El tipo de producto ya fue seleccionado y está en st.session_state['tipo_producto_seleccionado'].
    - El rol del usuario está en st.session_state['usuario_rol'].
    - Una instancia de DBManager está en st.session_state.db.

    Args:
        cliente: Cliente seleccionado (Opcional, actualmente no se usa directamente aquí).

    Returns:
        Dict con los datos del formulario recolectados.
        Retorna un diccionario vacío si faltan datos esenciales (ej. tipo producto).
    """
    datos_producto = {}

    # Verificar dependencias clave en session_state
    tipo_producto_id = st.session_state.get('tipo_producto_seleccionado')
    if tipo_producto_id is None:
        st.error("Error: Tipo de producto no seleccionado. Por favor, vuelva al paso anterior.")
        return {} # Retornar vacío si falta el tipo

    db: DBManager = st.session_state.db # Acceder una sola vez
    if not isinstance(db, DBManager):
         st.error("Error: Conexión a la base de datos. Por favor, vuelva a cargar la página.")
         return {}

    if 'usuario_rol' not in st.session_state:
         st.warning("Rol de usuario no definido, algunas opciones pueden no funcionar correctamente.")
         # Considerar asignar un rol por defecto si es necesario

    es_manga = (tipo_producto_id == 2) # ID 2 se asume que es Manga

    # --- Obtener datos de la DB una sola vez ---
    try:
        todos_materiales = db.get_materiales()
        todos_tipos_grafado = db.get_tipos_grafado() if es_manga else []
        todos_acabados = db.get_acabados() if not es_manga else []
        todas_formas_pago = db.get_formas_pago() # <-- Nueva línea para obtener formas de pago
    except Exception as e:
        st.error(f"Error al cargar datos iniciales desde la base de datos: {e}")
        return {}


    # --- Renderizar Secciones del Formulario ---
    _mostrar_escalas(datos_producto)
    st.divider()
    _mostrar_dimensiones_y_tintas(datos_producto, es_manga)
    st.divider()
    _mostrar_material(datos_producto, es_manga, todos_materiales)
    st.divider()
    _mostrar_acabados_y_empaque(datos_producto, es_manga, todos_tipos_grafado, todos_acabados)
    st.divider()
    _mostrar_opciones_adicionales(datos_producto, es_manga) # Pasar es_manga aquí
    st.divider() # <-- Nuevo divisor
    _mostrar_formas_pago(datos_producto, todas_formas_pago) # <-- Llamada a la nueva función


    # Validar datos esenciales antes de retornar
    if not datos_producto.get('escalas'):
        st.warning("Por favor, ingrese al menos una escala válida.")
        # Podríamos invalidar el retorno o dejar que la lógica posterior lo maneje
        # return {} # Descomentar si se requiere que las escalas sean obligatorias aquí

    if datos_producto.get('material_id') is None:
         st.warning("Por favor, seleccione un material.")
         # return {} # Descomentar si se requiere material obligatorio aquí

    if datos_producto.get('forma_pago_id') is None and todas_formas_pago: # <-- Nueva validación
        st.warning("Por favor, seleccione una forma de pago.")
        # return {} # Descomentar si se requiere forma de pago obligatoria aquí

    # Añadir tipo_producto_id y es_manga al diccionario final (si es necesario fuera)
    # datos_producto['tipo_producto_id'] = tipo_producto_id
    # datos_producto['es_manga'] = es_manga
    return datos_producto
