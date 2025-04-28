import streamlit as st
from typing import Dict, Any, List, Optional
from src.data.models import Cliente  # Corrected import: Directly from src.data.models module
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
        # Updated IDs for manga materials (e.g., PVC, PETG)
        materiales_filtrados = [m for m in materiales if m.id in [13, 14]] 
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


def _mostrar_adhesivo(datos: Dict[str, Any], adhesivos: List[Any]):
    """
    Muestra el selector de adhesivo.

    Args:
        datos: Diccionario para almacenar los datos del formulario.
        adhesivos: Lista completa de objetos de adhesivo.
    """
    st.subheader("Adhesivo")

    if not adhesivos:
        # If the DB call returned an empty list for this material, it means NO adhesives apply (not even 'Sin Adhesivo')
        st.info("Este material no requiere/utiliza adhesivo.") # Changed warning to info
        datos['adhesivo_id'] = None # Ensure it's None if no options
        # Clear session state if it existed from a previous material
        if "adhesivo_id" in st.session_state:
            st.session_state["adhesivo_id"] = None
        return

    # Build options. Include "Seleccione..." ONLY if there's more than one actual adhesive option.
    opciones_adhesivo = [(ad.id, ad.tipo) for ad in adhesivos]
    include_select_option = len(opciones_adhesivo) > 1
    display_options = [(None, "Seleccione...")] + opciones_adhesivo if include_select_option else opciones_adhesivo
    
    # Determine default selection/index
    selected_adhesivo_id = st.session_state.get("adhesivo_id", None)
    default_index = 0
    if len(opciones_adhesivo) == 1:
        # If only one adhesive is valid, default to it
        selected_adhesivo_id = opciones_adhesivo[0][0]
        st.session_state["adhesivo_id"] = selected_adhesivo_id # Pre-set state
        default_index = 0 # Index within display_options (which only has the one option)
    elif include_select_option:
        # If multiple options, find the index of the previously selected one, default to "Seleccione..."
        try:
            default_index = next(i for i, (id, _) in enumerate(display_options) if id == selected_adhesivo_id)
        except StopIteration:
            default_index = 0 # Default to "Seleccione..."
    
    # Determine if the selectbox should be disabled (only one option)
    is_disabled = len(opciones_adhesivo) == 1

    selected_option = st.selectbox(
        "Seleccione el Adhesivo",
        options=display_options,
        format_func=lambda opt: opt[1], # Mostrar el tipo/nombre
        key="adhesivo_select",
        index=default_index,
        help="Seleccione el adhesivo compatible con el material.",
        disabled=is_disabled
    )

    # Get the actual selected ID (might be None if "Seleccione..." was chosen)
    actual_selected_id = selected_option[0] if not is_disabled else selected_adhesivo_id

    datos['adhesivo_id'] = actual_selected_id
    # Update session state only if the selection changed
    if st.session_state.get("adhesivo_id") != actual_selected_id:
        st.session_state["adhesivo_id"] = actual_selected_id
        # Rerun might be needed if adhesive choice affects other calculations dynamically
        # st.rerun() 

    # Refined Validation Warning:
    # Warn only if "Seleccione..." is the current selection AND there were multiple actual options to choose from.
    if actual_selected_id is None and include_select_option:
        st.warning("Debe seleccionar un adhesivo de la lista.")


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
    - Los adhesivos están cargados en st.session_state.initial_data['adhesivos'] (o similar)

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
    
    # --- Obtener Adhesivos Compatibles (si aplica) ---
    adhesivos_compatibles = []
    selected_material_id = datos_producto.get('material_id') # Get selected material ID
    
    if not es_manga and selected_material_id is not None:
        try:
            print(f"--- DEBUG: Fetching compatible adhesives for material ID: {selected_material_id} ---")
            adhesivos_compatibles = db.get_adhesivos_for_material(selected_material_id)
            print(f"--- DEBUG: Compatible adhesives found: {len(adhesivos_compatibles)} ---")
        except Exception as e:
            st.error(f"Error al cargar adhesivos compatibles para el material seleccionado: {e}")
            # Handle error appropriately, maybe return {} or show a persistent warning
    
    # --- Mostrar Adhesivo solo si NO es manga ---
    if not es_manga:
        st.divider() # Separador antes de adhesivo
        _mostrar_adhesivo(datos_producto, adhesivos_compatibles) # <-- Pass filtered list
    else:
        # Asegurar que adhesivo_id sea None si es manga
        datos_producto['adhesivo_id'] = None
        if "adhesivo_id" in st.session_state:
             del st.session_state["adhesivo_id"] # Limpiar estado si se cambió a manga

    st.divider() # Separador después de material/adhesivo
    _mostrar_acabados_y_empaque(datos_producto, es_manga, todos_tipos_grafado, todos_acabados)
    st.divider()

    # --- OBTENER material_adhesivo_id --- 
    # Después de obtener material_id y adhesivo_id (si aplica)
    material_id = datos_producto.get('material_id')
    adhesivo_id = datos_producto.get('adhesivo_id') # Será None si es manga
    datos_producto['material_adhesivo_id'] = None # Inicializar

    if material_id is not None and adhesivo_id is not None:
        try:
            print(f"Buscando ID de material_adhesivo para material {material_id} y adhesivo {adhesivo_id}")
            entry = db.get_material_adhesivo_entry(material_id, adhesivo_id)
            if entry and 'id' in entry:
                datos_producto['material_adhesivo_id'] = entry['id']
                print(f"Encontrado material_adhesivo_id: {entry['id']}")
            else:
                print(f"Advertencia: No se encontró entrada en material_adhesivo para la combinación {material_id} / {adhesivo_id}")
                # Mantener material_adhesivo_id como None, puede que se valide después
        except Exception as e_lookup:
            print(f"Error buscando material_adhesivo_id: {e_lookup}")
            # Mantener como None y posiblemente mostrar error
            st.warning("Error al determinar la combinación material-adhesivo.")
    elif material_id is not None and es_manga: # Caso específico para manga (sin adhesivo)
        # Asumiendo que hay una entrada para material + "sin adhesivo" ID
        ID_SIN_ADHESIVO = 4 # Reconfirmar este ID
        try:
            print(f"Buscando ID de material_adhesivo para MANGA material {material_id} (Adhesivo={ID_SIN_ADHESIVO})")
            entry = db.get_material_adhesivo_entry(material_id, ID_SIN_ADHESIVO)
            if entry and 'id' in entry:
                datos_producto['material_adhesivo_id'] = entry['id']
                print(f"Encontrado material_adhesivo_id para manga: {entry['id']}")
            else:
                print(f"Advertencia: No se encontró entrada en material_adhesivo para MANGA {material_id} / Sin Adhesivo ({ID_SIN_ADHESIVO})")
        except Exception as e_lookup_manga:
            print(f"Error buscando material_adhesivo_id para manga: {e_lookup_manga}")
            st.warning("Error al determinar la combinación material-adhesivo para manga.")
            
    # Eliminar las claves intermedias si ya no se necesitan fuera
    # datos_producto.pop('material_id', None)
    # datos_producto.pop('adhesivo_id', None)
    # ----------------------------------

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

    # --- Validar Adhesivo si es Etiqueta ---
    if not es_manga and datos_producto.get('adhesivo_id') is None:
         st.warning("Por favor, seleccione un adhesivo para la etiqueta.")
         # return {} # Descomentar si se requiere adhesivo obligatorio aquí

    if datos_producto.get('forma_pago_id') is None and todas_formas_pago: # <-- Nueva validación
        st.warning("Por favor, seleccione una forma de pago.")
        # return {} # Descomentar si se requiere forma de pago obligatoria aquí

    # Añadir tipo_producto_id y es_manga al diccionario final (si es necesario fuera)
    # datos_producto['tipo_producto_id'] = tipo_producto_id
    # datos_producto['es_manga'] = es_manga
    return datos_producto
