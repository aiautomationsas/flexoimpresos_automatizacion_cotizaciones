import streamlit as st
from typing import Dict, Any, List, Optional
from src.logic.calculators.calculadora_desperdicios import CalculadoraDesperdicio
from src.data.models import Cliente  # Corrected import: Directly from src.data.models module
from src.data.database import DBManager  # Asumiendo que DBManager está definido aquí
import time

# --- Helper Functions for Input Sections ---

def _mostrar_escalas(default_escalas: str):
    """Muestra y procesa el input de escalas, usando el valor inicial provisto."""
    st.subheader("Cantidades a Cotizar")
    
    # Usar el valor inicial pasado como argumento
    escalas_texto = st.text_input(
        "Escalas a cotizar (separadas por coma) *", 
        value=default_escalas, # <-- USAR EL VALOR PASADO
        key="escalas_texto_input",
        help="Ej: 1000, 2000, 5000, 10000. Mínimo 100 unidades."
    )

    try:
        # Procesar el valor actual del input para validación y guardado en estado
        escalas_usuario = [int(e.strip()) for e in escalas_texto.split(",") if e.strip()]
        escalas_usuario = sorted(list(set(escalas_usuario))) 

        if not escalas_usuario:
             st.warning("Ingrese al menos una escala.")
             # Limpiar estado si el input está vacío
             if 'escalas' in st.session_state: del st.session_state['escalas']
        elif any(e < 100 for e in escalas_usuario):
            raise ValueError("Las escalas deben ser mayores o iguales a 100.")
        else:
            # Guardar la lista procesada en el estado
            st.session_state['escalas'] = escalas_usuario

    except ValueError as e:
        st.error(f"Error en las escalas: {e}")
        if 'escalas' in st.session_state: del st.session_state['escalas'] # Limpiar en error
    except Exception:
        st.error("Por favor ingrese las escalas como números enteros separados por comas.")
        if 'escalas' in st.session_state: del st.session_state['escalas'] # Limpiar en error

def _mostrar_dimensiones_y_tintas(es_manga: bool, datos_cargados: Optional[Dict] = None):
    """Muestra los inputs de dimensiones (ancho, avance, pistas) y número de tintas."""
    st.subheader("Dimensiones y Tintas")
    col1, col2 = st.columns(2)
    
    # Obtener valores por defecto desde datos cargados o session state o hardcoded
    default_ancho = datos_cargados.get('ancho', st.session_state.get('ancho', 50.0)) if datos_cargados else st.session_state.get('ancho', 50.0)
    default_avance = datos_cargados.get('avance', st.session_state.get('avance', 50.0)) if datos_cargados else st.session_state.get('avance', 50.0)
    
    # CORREGIDO: Usar 'numero_pistas' que es la clave correcta de la base de datos
    default_pistas = datos_cargados.get('numero_pistas', st.session_state.get('numero_pistas', 1)) if datos_cargados else st.session_state.get('numero_pistas', 1)
    
    # CORREGIDO: Clave correcta de base de datos
    default_tintas = datos_cargados.get('num_tintas', st.session_state.get('num_tintas', 0)) if datos_cargados else st.session_state.get('num_tintas', 0)
    

    
    with col1:
        # El valor se guarda en st.session_state.ancho via key
        st.number_input("Ancho (mm)", min_value=1.00, max_value=310.00, step=5.0, format="%.2f", key="ancho", value=float(default_ancho),
                        help="Incrementos de 5mm. Use los botones + y - para ajustar fácilmente.")
        # El valor se guarda en st.session_state.avance via key
        st.number_input("Avance (mm)", min_value=1.00, max_value=523.87, step=5.0, format="%.2f", key="avance", value=float(default_avance),
                        help="Incrementos de 5mm. Valor máximo: 523.87mm (correspondiente a la unidad de montaje de 165 dientes)")
    with col2:
        # --- Pistas ---
        usuario_rol = st.session_state.get('usuario_rol', '')
        if es_manga:
            if usuario_rol == 'comercial':
                # Mostrar como texto no editable para comercial en manga
                st.markdown('<label style="font-size: 0.875rem; color: #555;">Número de pistas</label>', unsafe_allow_html=True)
                st.markdown('<div style="padding: 0.5rem 0; color: #333; font-weight: bold;">1</div>', unsafe_allow_html=True)
                # Guardar explícitamente en session state si es diferente
                if st.session_state.get('num_pistas_manga') != 1:
                    st.session_state.num_pistas_manga = 1
            else:
                # Input numérico para admin/otros en manga
                # El valor se guarda en st.session_state.num_pistas_manga via key
                st.number_input(
                    "Número de pistas", 
                    min_value=1, 
                    step=1, 
                    key="num_pistas_manga",
                    value=int(default_pistas)
                )
        else:
            # Input numérico para no-manga (todos los roles)
            # El valor se guarda en st.session_state.num_pistas_otro via key
            st.number_input(
                "Número de pistas", 
                min_value=1, 
                step=1, 
                key="num_pistas_otro",
                 value=int(default_pistas)
            )

        # --- Tintas ---
        # El valor se guarda en st.session_state.num_tintas via key
        st.number_input("Número de tintas", min_value=0, max_value=7, step=1, key="num_tintas", value=int(default_tintas))

def _mostrar_material(es_manga: bool, materiales: List[Any], datos_cargados: Optional[Dict] = None):
    """
    Muestra el selector de material, filtrando si es manga y preseleccionando si hay datos cargados.
    Detecta cambios, actualiza estado, limpia adhesivo, limpia caché y llama a rerun.

    Args:
        es_manga: Boolean indicando si el producto es manga.
        materiales: Lista completa de objetos de material.
    """
    st.subheader("Material")

    if es_manga:
        materiales_filtrados = [m for m in materiales if m.id in [13, 14]]  # Solo PVC y PETG para mangas
    else:
        materiales_filtrados = [m for m in materiales if m.id not in [13, 14]]  # Excluir PVC y PETG para etiquetas

    previous_material_id = st.session_state.get("material_id", None)
    selected_material_id = previous_material_id 
    print(f"--> _mostrar_material: Valor PREVIO de material_id en estado: {previous_material_id}") # DEBUG

    if datos_cargados and previous_material_id is None and 'material_adhesivo_id' in datos_cargados:
        db = st.session_state.db
        material_id_from_ma = db.get_material_id_from_material_adhesivo(datos_cargados['material_adhesivo_id'])
        if material_id_from_ma:
            selected_material_id = material_id_from_ma
        else:
             st.warning(f"No se pudo determinar el material base desde material_adhesivo_id {datos_cargados['material_adhesivo_id']} para preselección.")

    try:
        index = next(i for i, m in enumerate(materiales_filtrados) if m.id == selected_material_id) 
    except StopIteration:
        index = 0 

    help_text = ""
    if not es_manga:
        help_text = "Seleccione un material compatible con adhesivos para etiquetas. El sistema mostrará los adhesivos disponibles para el material seleccionado."

    material_seleccionado = st.selectbox(
        "Seleccione el Material",
        options=materiales_filtrados,
        format_func=lambda m: m.nombre,
        key="material_select", 
        index=index,
        help=help_text
    )

    current_material_id = material_seleccionado.id if material_seleccionado else None
    print(f"--> _mostrar_material: Valor ACTUAL seleccionado en widget: {current_material_id}") # DEBUG
    print(f"--> _mostrar_material: Comparando: {previous_material_id} != {current_material_id} -> {previous_material_id != current_material_id}") # DEBUG

    if previous_material_id != current_material_id:
        st.session_state["material_id"] = current_material_id
        st.session_state["adhesivo_id"] = None
        print(f"    DETECCION: Material cambiado a {current_material_id}, limpiando adhesivo y caché, forzando rerun.") # DEBUG con indentación
        # Limpiar explícitamente el caché de la función específica
        try:
            st.session_state.db.get_adhesivos_for_material.clear()
            print("    DETECCION: Caché de get_adhesivos_for_material limpiado.") # DEBUG con indentación
        except Exception as e:
            print(f"    DETECCION: Error al intentar limpiar caché: {e}") # DEBUG con indentación
        
        # Mostrar advertencia ANTES del rerun
        st.warning("Refrescando opciones de adhesivo...") 
        time.sleep(1) # Pausa breve para que se vea el warning
        
        st.rerun() # Forzar rerun al detectar cambio
    # else: # Opcional: Log si no hay cambio
    #     print("--> _mostrar_material: No se detectó cambio de material.")
            
    if not material_seleccionado:
        st.warning("Por favor seleccione un material.")

    # Ya no necesitamos retornar el material

def _mostrar_adhesivo(adhesivos_filtrados: List[Any], material_obj_actual: Optional[Any], datos_cargados: Optional[Dict] = None):
    """
    Muestra el selector de adhesivo, preseleccionando si hay datos cargados.
    Recibe la lista de adhesivos ya filtrada y el objeto material actual.

    Args:
        adhesivos_filtrados: Lista de objetos Adhesivo ya filtrados.
        material_obj_actual: El objeto Material actualmente seleccionado.
        datos_cargados: Datos precargados para edición.
    """
    # Log al entrar a la función
    print(f"--> Entrando a _mostrar_adhesivo:")
    print(f"    Material Recibido: {material_obj_actual.nombre if material_obj_actual else 'None'}")
    print(f"    Adhesivos Filtrados Recibidos: {len(adhesivos_filtrados) if adhesivos_filtrados is not None else 'None'} items")
    print(f"    Datos Cargados: {'Sí' if datos_cargados else 'No'}")
    
    st.subheader("Adhesivo")

    # Usar el objeto material pasado directamente
    material_nombre = material_obj_actual.nombre if material_obj_actual else "desconocido"
    
    if not adhesivos_filtrados:
        st.info(f"No hay adhesivos disponibles para el material seleccionado: {material_nombre}")
        st.warning("Debe seleccionar un material que sea compatible con adhesivos para etiquetas.")
        # Asegurarse de que el ID esté limpio si no hay opciones
        if st.session_state.get("adhesivo_id") is not None:
             st.session_state["adhesivo_id"] = None
        return

    st.success(f"Mostrando adhesivos compatibles con: {material_nombre}")

    opciones_adhesivo = [(ad.id, ad.tipo) for ad in adhesivos_filtrados]
    include_select_option = len(opciones_adhesivo) > 1
    display_options = [(None, "Seleccione...")] + opciones_adhesivo if include_select_option else opciones_adhesivo
    
    selected_adhesivo_id = st.session_state.get("adhesivo_id", None) # Usar el estado actual
    
    # Preselección si vienen datos cargados (solo si el estado actual es None)
    if selected_adhesivo_id is None and datos_cargados and 'material_adhesivo_id' in datos_cargados:
         combined_id = datos_cargados['material_adhesivo_id']
         if combined_id:
            try:
                db = st.session_state.db
                id_desde_db = db.get_adhesivo_id_from_material_adhesivo(combined_id)
                if id_desde_db:
                     selected_adhesivo_id = id_desde_db
                     st.session_state["adhesivo_id"] = id_desde_db # Actualizar estado si cargamos
                else:
                     st.warning(f"No se pudo obtener el adhesivo_id para la entrada material_adhesivo ID {combined_id}")
            except Exception as e_fetch:
                 st.error(f"Error obteniendo ID de adhesivo desde DB: {e_fetch}")
        
    # Verificar que el adhesivo seleccionado esté en la lista actual de opciones
    adhesivo_ids_disponibles = [ad.id for ad in adhesivos_filtrados]
    if selected_adhesivo_id not in adhesivo_ids_disponibles:
        selected_adhesivo_id = None
        st.session_state["adhesivo_id"] = None # Limpiar si el ID guardado no es válido
        
    default_index = 0
    is_disabled = False
    if len(opciones_adhesivo) == 1:
        selected_adhesivo_id = opciones_adhesivo[0][0]
        default_index = 0
        is_disabled = True
        # Asegurarse que el estado refleje la única opción
        if st.session_state.get("adhesivo_id") != selected_adhesivo_id:
             st.session_state["adhesivo_id"] = selected_adhesivo_id
    elif include_select_option:
        try:
            default_index = next(i for i, (id, _) in enumerate(display_options) if id == selected_adhesivo_id)
        except StopIteration:
            default_index = 0 

    selected_option = st.selectbox(
        "Seleccione el Adhesivo",
        options=display_options,
        format_func=lambda opt: opt[1],
        key="adhesivo_select",  # Volver a una clave simple
        index=default_index,
        help="Seleccione el adhesivo compatible con el material para el producto tipo etiqueta.",
        disabled=is_disabled
    )

    # Actualizar el estado basado en la selección del widget
    actual_selected_id_widget = selected_option[0] if not is_disabled else selected_adhesivo_id
    if st.session_state.get("adhesivo_id") != actual_selected_id_widget:
        st.session_state["adhesivo_id"] = actual_selected_id_widget

    # Mostrar información sobre el adhesivo seleccionado (basado en estado)
    current_state_adhesivo_id = st.session_state.get("adhesivo_id")
    if current_state_adhesivo_id is not None:
        try:
            adhesivo_info = next((ad for ad in adhesivos_filtrados if ad.id == current_state_adhesivo_id), None)
            if adhesivo_info:
                st.success(f"Adhesivo seleccionado: {adhesivo_info.tipo}")
        except Exception:
            pass

    if current_state_adhesivo_id is None and include_select_option:
        st.warning("Debe seleccionar un adhesivo de la lista.")

def _mostrar_grafado_altura(es_manga: bool, tipos_grafado: List[Any], datos_cargados: Optional[Dict] = None):
    """
    Muestra el selector de tipo de grafado y el campo de altura cuando corresponde (fuera del formulario).
    
    Args:
        es_manga: Boolean indicando si el producto es manga.
        tipos_grafado: Lista de objetos de tipo grafado.
        datos_cargados: Datos precargados para edición.
    """
    # Solo mostrar para mangas
    if not es_manga:
        # No mostrar los selectores y limpiar valores
        st.session_state["grafado_seleccionado_id"] = None
        st.session_state["altura_grafado"] = None
        return
        
    st.subheader("Grafado")
    
    # Valores por defecto
    default_grafado_id = datos_cargados.get('tipo_grafado_id', st.session_state.get("grafado_seleccionado_id", 1)) if datos_cargados else st.session_state.get("grafado_seleccionado_id", 1)
    default_altura_grafado = datos_cargados.get('altura_grafado', st.session_state.get("altura_grafado", 0.0)) if datos_cargados else st.session_state.get("altura_grafado", 0.0)
    
    # --- Tipo de Grafado ---
    # Inicializar variables
    selected_grafado_id = default_grafado_id
    try:
        index_grafado = next(i for i, tg in enumerate(tipos_grafado) if tg.id == selected_grafado_id)
    except StopIteration:
        index_grafado = 0

    # Regla de Fundas Transparentes (0 tintas): deshabilitar grafado si ancho efectivo > 325mm
    try:
        es_funda_transparente = es_manga and int(st.session_state.get('num_tintas', 0)) == 0
        ancho_cerrado_ft = float(st.session_state.get('ancho', 0) or 0)
        ancho_efectivo_ft = (ancho_cerrado_ft * 2) + 6 if es_funda_transparente else 0
        disable_grafado = es_funda_transparente and ancho_efectivo_ft > 325
        if disable_grafado:
            # Si está deshabilitado, apuntar el índice por defecto a 'Sin grafado' (id=1)
            try:
                index_grafado = next(i for i, tg in enumerate(tipos_grafado) if tg.id == 1)
            except StopIteration:
                index_grafado = 0
    except Exception:
        disable_grafado = False

    tipo_grafado_seleccionado = st.selectbox(
        "Tipo de grafado",
        options=tipos_grafado,
        format_func=lambda tg: tg.nombre,
        key="tipo_grafado_select",
        index=index_grafado,
        disabled=disable_grafado
    )
    
    # Obtener y guardar el ID seleccionado
    if tipo_grafado_seleccionado:
        current_selected_id = tipo_grafado_seleccionado.id
        previous_id = st.session_state.get("grafado_seleccionado_id")
        
        # Guardar ID y detectar cambios que requieran rerun
        st.session_state["grafado_seleccionado_id"] = current_selected_id
        
        # Si cambió entre un tipo que requiere altura y uno que no, hacer rerun
        if previous_id != current_selected_id and (
            (previous_id in [3, 4] and current_selected_id not in [3, 4]) or
            (previous_id not in [3, 4] and current_selected_id in [3, 4])
        ):
            st.rerun()
    else:
        st.session_state["grafado_seleccionado_id"] = None
    
    # --- Altura de Grafado (condicional) ---
    current_id = st.session_state.get("grafado_seleccionado_id")
    
    # Solo mostrar campo de altura si es tipo 3 o 4
    if current_id in [3, 4]:
        valor_mostrar = 0.0
        
        # Determinar valor a mostrar
        if datos_cargados and 'altura_grafado' in datos_cargados and datos_cargados['altura_grafado'] is not None:
            valor_mostrar = float(datos_cargados['altura_grafado'])
        elif st.session_state.get("altura_grafado") is not None:
            valor_mostrar = float(st.session_state.get("altura_grafado"))
            
        # Mostrar campo de altura
        st.number_input(
            "Altura de grafado (mm)",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="altura_grafado",
            value=valor_mostrar,
            help="Incrementos de 1mm. Use los botones + y - para ajustar fácilmente."
        )
    else:
        # Si no requiere altura, establecer None
        st.session_state["altura_grafado"] = None

    # Restricciones para Fundas Transparentes (0 Tintas):
    # - Ancho efectivo = ancho cerrado * 2 + 6
    # - Si ancho efectivo > 325mm, no permitir grafado (forzar 'Sin grafado')
    try:
        if es_manga and int(st.session_state.get('num_tintas', 0)) == 0:
            ancho_cerrado = float(st.session_state.get('ancho', 0) or 0)
            ancho_efectivo = (ancho_cerrado * 2) + 6
            if ancho_efectivo > 325:
                # Forzar grafado 'Sin grafado' si el seleccionado no es 1
                if st.session_state.get("grafado_seleccionado_id") not in (None, 1):
                    st.session_state["grafado_seleccionado_id"] = 1
                    st.session_state["tipo_grafado_select"] = next((i for i, tg in enumerate(tipos_grafado) if tg.id == 1), 0)
                    st.warning("Para fundas transparentes de ancho efectivo > 325mm, se fuerza 'Sin grafado'.")
                    st.rerun()
    except Exception:
        pass

def _mostrar_acabados_y_empaque(es_manga: bool, acabados: List[Any], datos_cargados: Optional[Dict] = None):
    """
    Muestra los inputs relacionados con acabados y empaque.

    Args:
        es_manga: Boolean indicando si el producto es manga.
        acabados: Lista de objetos de acabado.
        datos_cargados: Datos precargados para edición.
    """
    st.subheader("Acabados y Empaque")
    col1, col2 = st.columns(2)

    # Valores por defecto
    default_acabado_id = datos_cargados.get('acabado_id', st.session_state.get("acabado_seleccionado_id")) if datos_cargados else st.session_state.get("acabado_seleccionado_id")
    default_num_paquetes = datos_cargados.get('num_paquetes_rollos', st.session_state.get("num_paquetes", 1000)) if datos_cargados else st.session_state.get("num_paquetes", 1000)
    default_tipo_foil_id = datos_cargados.get('tipo_foil_id', st.session_state.get("tipo_foil_id")) if datos_cargados else st.session_state.get("tipo_foil_id")

    with col1:
        if not es_manga:
            # --- Acabado (No Manga) ---
            selected_acabado_id = default_acabado_id
            try:
                index_acabado = next(i for i, ac in enumerate(acabados) if ac.id == selected_acabado_id)
            except StopIteration:
                index_acabado = 0
                
            acabado_seleccionado = st.selectbox(
                "Acabado",
                options=acabados,
                format_func=lambda ac: ac.nombre,
                key="acabado_select",
                index=index_acabado
            )

            # Obtener el ID del acabado seleccionado
            acabado_id = acabado_seleccionado.id if acabado_seleccionado else None
            
            # Si el acabado seleccionado es 5 o 6, mostrar selector de tipo de foil
            if acabado_id in [5, 6]:
                # Obtener tipos de foil de la base de datos
                db = st.session_state.db
                tipos_foil = db.get_tipos_foil()
                
                try:
                    index_foil = next(i for i, tf in enumerate(tipos_foil) if tf.id == default_tipo_foil_id)
                except StopIteration:
                    index_foil = 0

                tipo_foil_seleccionado = st.selectbox(
                    "Tipo de Foil",
                    options=tipos_foil,
                    format_func=lambda tf: tf.nombre,
                    key="tipo_foil_select",
                    index=index_foil
                )
                
                if tipo_foil_seleccionado:
                    st.session_state["tipo_foil_id"] = tipo_foil_seleccionado.id
                else:
                    st.session_state["tipo_foil_id"] = None
            else:
                # Limpiar el tipo de foil si no es acabado 5 o 6
                st.session_state["tipo_foil_id"] = None
        else:
            # Para mangas, no mostrar acabado, usar espacio para equilibrio
            st.write("Sin acabado (manga)")
            st.session_state["tipo_foil_id"] = None

    with col2:
        # --- Empaque --- 
        if es_manga:
            # Para mangas, mostrar valor fijo de 100 unidades por paquete y no permitir edición
            st.markdown('<label style="font-size: 0.875rem; color: #555;">Unidades por paquete</label>', unsafe_allow_html=True)
            st.markdown('<div style="padding: 0.5rem 0; color: #333; font-weight: bold;">100</div>', unsafe_allow_html=True)
            # Asegurar que el valor en session_state sea 100
            st.session_state.num_paquetes = 100
        else:
            # Para etiquetas, mantener campo editable
            empaque_label = "Etiquetas por rollo"
            st.number_input(empaque_label, min_value=1, step=1, key="num_paquetes", value=int(default_num_paquetes))


def _mostrar_opciones_adicionales(es_manga: bool, datos_cargados: Optional[Dict] = None):
    """Muestra las opciones adicionales (troquel, planchas)."""
    st.subheader("Opciones Adicionales")
    
    # Valores por defecto
    # Usar nombres de campo consistentes con datos_cargados
    print(f"\n=== DEBUG DATOS_CARGADOS ===")
    print(f"datos_cargados: {datos_cargados}")
    if datos_cargados:
        print(f"existe_troquel en datos_cargados: {datos_cargados.get('existe_troquel')} (tipo: {type(datos_cargados.get('existe_troquel'))})")
    print(f"tiene_troquel en session_state: {st.session_state.get('tiene_troquel')} (tipo: {type(st.session_state.get('tiene_troquel'))})")
    
    # SOLUCIÓN: Si no hay un valor explícito en session_state, usar False como valor por defecto
    # Esto evita que datos_cargados de cotizaciones anteriores afecten nuevas cotizaciones
    if "tiene_troquel" not in st.session_state:
        # Si es una nueva cotización, usar False como valor por defecto
        default_tiene_troquel = False
        print("Nueva cotización detectada - usando False como valor por defecto")
    else:
        # Si ya hay un valor en session_state, usarlo
        default_tiene_troquel = st.session_state.get("tiene_troquel", False)
        print("Usando valor existente en session_state")
    
    print(f"default_tiene_troquel calculado: {default_tiene_troquel} (tipo: {type(default_tiene_troquel)})")
    
    default_planchas_sep = datos_cargados.get('planchas_x_separado', st.session_state.get("planchas_separadas", False)) if datos_cargados else st.session_state.get("planchas_separadas", False)

    if not es_manga:
        # El valor bool se guarda en st.session_state.tiene_troquel
        index_seleccionado = 0 if bool(default_tiene_troquel) else 1
        print(f"Índice seleccionado para selectbox: {index_seleccionado} (basado en default_tiene_troquel: {default_tiene_troquel})")
        
        tiene_troquel = st.selectbox(
            "¿Existe troquel?",
            options=["Sí", "No"],
            key="tiene_troquel",
            index=index_seleccionado
        )
        
        # Debug para verificar el valor seleccionado
        print(f"\n=== DEBUG SELECCIÓN DE TROQUEL ===")
        print(f"Valor seleccionado en UI: {tiene_troquel}")
        print(f"Valor en session_state: {st.session_state.get('tiene_troquel')}")
        print(f"Convertido a booleano: {st.session_state.get('tiene_troquel') == 'Sí'}")

        # Si el usuario indica que sí existe troquel, permitir elegir la unidad de montaje
        if st.session_state.get("tiene_troquel") == "Sí":
            avance_actual = st.session_state.get("avance")
            try:
                avance_float = float(avance_actual) if avance_actual is not None else 0.0
            except Exception:
                avance_float = 0.0
            if avance_float <= 0:
                st.info("Ingrese primero el avance para listar las unidades disponibles.")
            else:
                try:
                    calc = CalculadoraDesperdicio(es_manga=es_manga)
                    
                    # En lugar de filtrar por avance, obtenemos todas las unidades de montaje disponibles
                    # Creamos registros para todas las unidades de la tabla en calc.df
                    mejores_por_diente = {}
                    for _, row in calc.df.iterrows():
                        dientes = row['Dientes']
                        medida_mm = row['mm']
                        
                        # Creamos un registro para cada unidad de montaje
                        # Ya no usamos repeticiones_fijas aquí, se calcularán dinámicamente
                        registro = {
                            'dientes': dientes,
                            'medida_mm': medida_mm,
                            'desperdicio': 0,  # No relevante para mostrar todas las opciones
                            'ancho_total': 0,  # No relevante para mostrar todas las opciones
                        }
                        mejores_por_diente[dientes] = registro

                    if not mejores_por_diente:
                        st.warning("No hay unidades de montaje disponibles.")
                    else:
                        lista_opciones = sorted(mejores_por_diente.values(), key=lambda x: x['dientes'])
                        etiquetas = [f"{int(x['dientes'])} dientes ({x['medida_mm']:.3f} mm)" for x in lista_opciones]
                        valores = [x['dientes'] for x in lista_opciones]

                        # Selección persistente
                        valor_por_defecto = st.session_state.get('unidad_montaje_dientes')
                        try:
                            index_default = valores.index(valor_por_defecto) if valor_por_defecto in valores else 0
                        except Exception:
                            index_default = 0

                        seleccion = st.selectbox(
                            "Unidad de montaje",
                            options=list(range(len(valores))),
                            format_func=lambda i: etiquetas[i],
                            index=index_default,
                            key="unidad_montaje_select_index",
                            help="Seleccione la unidad de montaje (cilindro) a utilizar en los cálculos."
                        )

                        # Guardar solo el valor de dientes seleccionado en session_state
                        st.session_state['unidad_montaje_dientes'] = valores[seleccion]
                except Exception as e:
                    st.error(f"Error listando unidades de montaje: {e}")
    else:
        # Asegurar que el estado es False si es manga
        if st.session_state.get("tiene_troquel") is not False:
             st.session_state.tiene_troquel = False

    # --- Planchas Separadas (Solo Admin) ---
    if st.session_state.get('usuario_rol') == 'administrador':
        # El valor bool se guarda en st.session_state.planchas_separadas
        st.checkbox(
            "¿Planchas por separado?", 
            key="planchas_separadas", 
            value=bool(default_planchas_sep),
            help="Si se marca, el costo de las planchas se mostrará como un ítem separado en la cotización."
        )
    else:
        # Si no es admin, asegurar que el estado sea False
        if st.session_state.get("planchas_separadas") is not False:
             st.session_state.planchas_separadas = False





# --- Función Principal Refactorizada --- 
def mostrar_secciones_internas_formulario(
    es_manga: bool, 
    initial_data: Dict, 
    datos_cargados: Optional[Dict] = None,
    default_escalas: str = "" # <-- NUEVO PARÁMETRO con valor default
) -> None:
    """Muestra todas las secciones del formulario que dependen de la selección inicial.
    Args:
        es_manga: Boolean indicando si el producto es manga.
        initial_data: Diccionario con datos iniciales cacheados (tipos_grafado, acabados, etc.).
        datos_cargados: Diccionario con datos precargados para modo edición.
        default_escalas (str): String formateado para el valor inicial del input de escalas.
    """
    # 1. Escalas (Pasar el valor inicial)
    _mostrar_escalas(default_escalas=default_escalas)
    st.divider()

    # 2. Dimensiones y Tintas
    _mostrar_dimensiones_y_tintas(es_manga, datos_cargados)
    
    # 3. Grafado (solo para mangas, inmediatamente después de dimensiones)
    if es_manga:
        tipos_grafado = initial_data.get('tipos_grafado', [])
        _mostrar_grafado_altura(es_manga, tipos_grafado, datos_cargados)
    st.divider()
    
    # 4. Acabados y Empaque
    acabados = initial_data.get('acabados', [])
    _mostrar_acabados_y_empaque(es_manga, acabados, datos_cargados)
    st.divider()
    
    # 5. Opciones Adicionales
    _mostrar_opciones_adicionales(es_manga, datos_cargados)

# --- FIN FUNCIÓN RENOMBRADA --- 
