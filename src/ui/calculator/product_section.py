import streamlit as st
from typing import Optional, Dict, Any
from src.data.models.cliente import Cliente
from src.data.database import DBManager

def mostrar_formulario_producto(cliente: Cliente) -> Dict[str, Any]:
    """
    Muestra el formulario para ingresar los datos del producto.
    
    Args:
        cliente: Cliente seleccionado
        
    Returns:
        Dict con los datos del formulario
    """
    datos = {}
    
    # Primero, selección del tipo de producto
    tipos_producto = st.session_state.db.get_tipos_producto()
    tipo_producto = st.selectbox(
        "Tipo de Producto",
        options=tipos_producto,
        format_func=lambda x: x.nombre,
        help="Seleccione si es manga o etiqueta"
    )
    
    if tipo_producto:
        datos['tipo_producto_id'] = tipo_producto.id
        datos['es_manga'] = "MANGA" in tipo_producto.nombre.upper()
        
        # Sección de escalas
        st.subheader("Escalas a Cotizar")
        
        # Escalas predefinidas usando checkboxes
        st.write("Seleccione las escalas que desea cotizar:")
        escalas_seleccionadas = []
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            if st.checkbox("1,000", value=True):
                escalas_seleccionadas.append(1000)
        with col2:
            if st.checkbox("2,000", value=True):
                escalas_seleccionadas.append(2000)
        with col3:
            if st.checkbox("3,000", value=True):
                escalas_seleccionadas.append(3000)
        with col4:
            if st.checkbox("5,000", value=True):
                escalas_seleccionadas.append(5000)
        with col5:
            if st.checkbox("10,000"):
                escalas_seleccionadas.append(10000)
        
        # Escala personalizada
        escala_personalizada = st.number_input(
            "Escala personalizada (opcional)",
            min_value=100,
            step=100,
            help="Ingrese una cantidad personalizada para cotizar"
        )
        if escala_personalizada > 0 and escala_personalizada not in escalas_seleccionadas:
            escalas_seleccionadas.append(escala_personalizada)
        
        # Ordenar escalas
        escalas_seleccionadas.sort()
        datos['escalas'] = escalas_seleccionadas
        
        # Mostrar escalas seleccionadas
        st.write(f"Escalas a cotizar: {', '.join(f'{e:,}' for e in escalas_seleccionadas)}")
        
        # Resto de los campos del formulario
        col1, col2 = st.columns(2)
        
        with col1:
            datos['ancho'] = st.number_input("Ancho (mm)", min_value=1.0, format="%.2f")
            datos['avance'] = st.number_input("Avance (mm)", min_value=1.0, format="%.2f")
            datos['pistas'] = st.number_input("Número de pistas", min_value=1)
            datos['num_tintas'] = st.number_input("Número de tintas", min_value=1)
            
        with col2:
            datos['num_paquetes'] = st.number_input("Número de paquetes/rollos", min_value=1)
            
            # Campos específicos según el tipo de producto
            if datos['es_manga']:
                datos['altura_grafado'] = st.number_input(
                    "Altura de grafado (mm)", 
                    min_value=0.0, 
                    format="%.2f",
                    help="Solo para mangas"
                )
            else:
                # Campos específicos para etiquetas
                datos['acabado_id'] = st.selectbox(
                    "Acabado",
                    options=[None] + st.session_state.db.get_acabados(),
                    format_func=lambda x: "Sin acabado" if x is None else x.nombre
                )
            
            datos['planchas_separadas'] = st.checkbox("¿Planchas por separado?")
            datos['tiene_troquel'] = st.checkbox("¿Existe troquel?")
        
        # Selección de material
        materiales = st.session_state.db.get_materiales()
        material = st.selectbox(
            "Material",
            options=materiales,
            format_func=lambda x: x.nombre
        )
        if material:
            datos['material_id'] = material.id
    
    return datos
