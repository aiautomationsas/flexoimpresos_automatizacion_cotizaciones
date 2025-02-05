import streamlit as st
import pandas as pd
from calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from calculadora_litografia import CalculadoraLitografia, DatosLitografia

# Configuración de página
st.set_page_config(
    page_title="Calculadora de Costos",
    layout="wide"
)

def main():
    st.title("Calculadora de Costos por Escala")
    
    # Sección de datos de litografía
    st.header("Datos de Litografía")
    
    col1, col2 = st.columns(2)
    
    with col1:
        ancho = st.number_input("Ancho (mm)", min_value=0.1, max_value=335.0, value=100.0, step=0.1,
                               help="El ancho no puede exceder 335mm")
        avance = st.number_input("Avance/Largo (mm)", min_value=0.1, value=100.0, step=0.1)
        pistas = st.number_input("Número de pistas", min_value=1, value=1, step=1)
        
    with col2:
        num_tintas = st.number_input("Número de tintas", min_value=0, value=4, step=1)
        incluye_planchas = st.checkbox("Incluye planchas", value=True)
        troquel_existe = st.checkbox("¿Existe troquel?", value=False)
    
    # Sección de escalas
    st.header("Escalas de Producción")
    escalas_text = st.text_input(
        "Ingrese las escalas separadas por comas",
        value="1000, 2000, 3000, 5000",
        help="Ejemplo: 1000, 2000, 3000, 5000"
    )
    
    try:
        escalas = [int(x.strip()) for x in escalas_text.split(",")]
    except ValueError:
        st.error("Por favor ingrese números válidos separados por comas")
        return
    
    # Botón para calcular
    if st.button("Calcular", type="primary"):
        try:
            # Crear datos de litografía
            datos_lito = DatosLitografia(
                ancho=ancho,
                avance=avance,
                pistas=pistas,
                incluye_planchas=incluye_planchas,
                incluye_troquel=True,  # Siempre se incluye troquel
                troquel_existe=troquel_existe
            )
            
            # Generar reporte de litografía
            calculadora_lito = CalculadoraLitografia()
            reporte_lito = calculadora_lito.generar_reporte_completo(datos_lito, num_tintas)
            
            # Verificar si tenemos la mejor opción de desperdicio
            if not reporte_lito['desperdicio'] or not reporte_lito['desperdicio']['mejor_opcion']:
                st.error("No se pudo calcular el desperdicio. Por favor revise los valores de ancho y avance.")
                return
            
            mejor_opcion = reporte_lito['desperdicio']['mejor_opcion']
            
            # Crear datos para calculadora de costos
            datos = DatosEscala(
                escalas=escalas,
                pistas=datos_lito.pistas,
                ancho=datos_lito.ancho,
                avance_total=datos_lito.avance,
                desperdicio=mejor_opcion['desperdicio'],
                area_etiqueta=reporte_lito['area_etiqueta'] if reporte_lito['area_etiqueta'] else 0
            )
            
            # Obtener valores de litografía
            valor_etiqueta = reporte_lito['valor_tinta'] if reporte_lito['valor_tinta'] else 0
            valor_plancha = round(reporte_lito['precio_plancha'] / 1000) * 1000 if reporte_lito['precio_plancha'] else 0
            
            # Obtener valor del troquel
            valor_troquel = 0
            if reporte_lito['valor_troquel'] is not None:
                valor_troquel = reporte_lito['valor_troquel']
            else:
                calculo_troquel = calculadora_lito.calcular_valor_troquel(
                    datos=datos_lito,
                    repeticiones=mejor_opcion['repeticiones'],
                    valor_mm=100,
                    troquel_existe=troquel_existe
                )
                if calculo_troquel['valor'] is not None:
                    valor_troquel = calculo_troquel['valor']
                    
                    # Mostrar detalles del troquel
                    st.subheader("Detalles del Troquel")
                    detalles = calculo_troquel['detalles']
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"- Perímetro: {detalles['perimetro']}mm")
                        st.write(f"- Valor base: ${detalles['valor_base']:,.2f}")
                        st.write(f"- Valor mínimo: ${detalles['valor_minimo']:,.2f}")
                    with col2:
                        st.write(f"- Valor calculado: ${detalles['valor_calculado']:,.2f}")
                        st.write(f"- Factor base: ${detalles['factor_base']:,.2f}")
                        st.write(f"- Factor división: {detalles['factor_division']}")
            
            # Calcular costos
            calculadora = CalculadoraCostosEscala()
            resultados = calculadora.calcular_costos_por_escala(
                datos=datos,
                num_tintas=num_tintas,
                valor_etiqueta=valor_etiqueta,
                valor_plancha=valor_plancha if incluye_planchas else 0,
                valor_troquel=valor_troquel
            )
            
            # Mostrar resultados
            st.header("Resultados")
            
            # Mostrar valores de entrada
            st.subheader("Valores de Entrada")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"- Unidad de montaje: {reporte_lito['unidad_montaje_sugerida']:.1f} dientes")
                st.write(f"- Área etiqueta: {datos.area_etiqueta:.2f} mm²")
                st.write(f"- Valor etiqueta: ${valor_etiqueta:,.6f}")
                st.write(f"- Valor plancha: ${valor_plancha:,.0f}")
            with col2:
                st.write(f"- Valor troquel: ${valor_troquel:,.2f}")
                st.write(f"- Desperdicio: {datos.desperdicio:.2f} mm")
                st.write(f"- Rentabilidad: {datos.rentabilidad}%")
                st.write(f"- Velocidad máquina: {datos.velocidad_maquina} m/min")
            
            # Mostrar tabla de resultados
            st.subheader("Costos por Escala")
            df = pd.DataFrame([
                {
                    'Escala': f"{r['escala']:,}",
                    '$/U Full': f"${r['valor_unidad']:.2f}",
                    '$MM': f"${r['valor_mm']:.3f}",
                    'mts': f"{r['metros']:.2f}",
                    't (h)': f"{r['tiempo_horas']:.2f}",
                    'Montaje': f"${r['montaje']:,.2f}",
                    'MO y Maq': f"${r['mo_y_maq']:,.2f}",
                    'Tintas': f"${r['tintas']:,.2f}",
                    'Papel/lam': f"${r['papel_lam']:,.2f}",
                    'Desperdicio': f"${r['desperdicio']:,.2f}"
                }
                for r in resultados
            ])
            st.dataframe(df, hide_index=True)
            
            # Si no se incluyen planchas, mostrar valor adicional con planchas
            if not incluye_planchas and valor_plancha > 0:
                st.subheader("Valor Adicional con Planchas")
                valor_plancha_ajustado = round((valor_plancha / 0.75) / 1000) * 1000
                st.write(f"Valor plancha ajustado: ${valor_plancha_ajustado:,.0f}")
                
                resultados_con_planchas = calculadora.calcular_costos_por_escala(
                    datos=datos,
                    num_tintas=num_tintas,
                    valor_etiqueta=valor_etiqueta,
                    valor_plancha=valor_plancha_ajustado,
                    valor_troquel=valor_troquel
                )
                
                df_planchas = pd.DataFrame([
                    {
                        'Escala': f"{r['escala']:,}",
                        '$/U Full': f"${r['valor_unidad']:.2f}",
                        '$MM': f"${r['valor_mm']:.3f}"
                    }
                    for r in resultados_con_planchas
                ])
                st.dataframe(df_planchas, hide_index=True)
                
        except ValueError as e:
            st.error(f"Error: {str(e)}")
            st.info("Por favor revise los valores ingresados e intente nuevamente.")
        except Exception as e:
            st.error(f"Error inesperado: {str(e)}")
            st.info("Por favor contacte al soporte técnico.")

if __name__ == "__main__":
    main()
