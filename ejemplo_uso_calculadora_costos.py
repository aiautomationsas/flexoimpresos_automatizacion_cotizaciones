from calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from calculadora_litografia import CalculadoraLitografia, DatosLitografia
from calculadora_desperdicios import CalculadoraDesperdicio

def obtener_input_numerico(mensaje: str, minimo: float = 0) -> float:
    """Solicita un valor numérico al usuario con validación"""
    while True:
        try:
            valor = float(input(mensaje))
            if valor < minimo:
                print(f"El valor debe ser igual o mayor a {minimo}")
                continue
            return valor
        except ValueError:
            print("Por favor ingrese un número válido")

def obtener_input_si_no(mensaje: str) -> bool:
    """Solicita una respuesta Sí/No al usuario"""
    while True:
        respuesta = input(mensaje + " (s/n): ").lower()
        if respuesta in ['s', 'si', 'sí']:
            return True
        if respuesta in ['n', 'no']:
            return False
        print("Por favor responda 's' o 'n'")

def obtener_escalas() -> list:
    """Obtiene la lista de escalas del usuario"""
    escalas = []
    while True:
        try:
            n = int(obtener_input_numerico("¿Cuántas escalas desea calcular?: ", minimo=0))
            for i in range(n):
                escala = int(obtener_input_numerico(f"Ingrese la escala {i+1}: ", minimo=0))
                escalas.append(escala)
            return sorted(escalas)
        except ValueError:
            print("Por favor ingrese números enteros válidos")

def main():
    print("=== Calculadora de Costos por Escala ===")
    print("\nPrimero ingresaremos los datos de litografía:")
    
    try:
        # Obtener datos de litografía
        ancho = obtener_input_numerico("Ancho (mm): ")
        if ancho > 335:
            print(f"\nERROR: El ancho base ({ancho}mm) excede el máximo permitido (335mm)")
            print("Por favor ingrese un ancho menor.")
            return
            
        avance = obtener_input_numerico("Avance/Largo (mm): ")
        pistas = int(obtener_input_numerico("Número de pistas: ", minimo=1))
        num_tintas = int(obtener_input_numerico("Número de tintas: ", minimo=0))
        incluye_planchas = obtener_input_si_no("¿Incluye planchas?")
        troquel_existe = obtener_input_si_no("¿Existe troquel?")
        
        # Crear datos de litografía y obtener cálculos
        datos_lito = DatosLitografia(
            ancho=ancho,
            avance=avance,
            pistas=pistas,
            incluye_planchas=incluye_planchas,
            incluye_troquel=True,  # Siempre se incluye troquel
            troquel_existe=troquel_existe
        )
        
        calculadora_lito = CalculadoraLitografia()
        reporte_lito = calculadora_lito.generar_reporte_completo(datos_lito, num_tintas)
        
        # Verificar si tenemos la mejor opción de desperdicio
        if not reporte_lito['desperdicio'] or not reporte_lito['desperdicio']['mejor_opcion']:
            print("\nERROR: No se pudo calcular el desperdicio")
            print("Por favor revise los valores de ancho y avance.")
            return
        
        mejor_opcion = reporte_lito['desperdicio']['mejor_opcion']
        
        print("\nAhora ingresaremos las escalas para el cálculo de costos:")
        escalas = obtener_escalas()
        
        # Crear datos para calculadora de costos
        datos = DatosEscala(
            escalas=escalas,
            pistas=datos_lito.pistas,
            ancho=datos_lito.ancho,  # Ancho base para calcular ancho_total
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
            # Si no está en el reporte, calcularlo directamente
            calculo_troquel = calculadora_lito.calcular_valor_troquel(
                datos=datos_lito,
                repeticiones=mejor_opcion['repeticiones'],
                valor_mm=100,  # Valor fijo por mm del troquel
                troquel_existe=troquel_existe
            )
            if calculo_troquel['valor'] is not None:
                valor_troquel = calculo_troquel['valor']
                print("\nDetalles del cálculo del troquel:")
                detalles = calculo_troquel['detalles']
                print(f"- Perímetro: {detalles['perimetro']}mm")
                print(f"- Valor base: ${detalles['valor_base']:,.2f}")
                print(f"- Valor mínimo: ${detalles['valor_minimo']:,.2f}")
                print(f"- Valor calculado: ${detalles['valor_calculado']:,.2f}")
                print(f"- Factor base: ${detalles['factor_base']:,.2f}")
                print(f"- Factor división: {detalles['factor_division']}")
                print(f"- Valor por mm: ${detalles['valor_mm']:,.2f}")
        
        # Calcular costos
        calculadora = CalculadoraCostosEscala()
        try:
            resultados = calculadora.calcular_costos_por_escala(
                datos=datos,
                num_tintas=num_tintas,
                valor_etiqueta=valor_etiqueta,
                valor_plancha=valor_plancha if incluye_planchas else 0,
                valor_troquel=valor_troquel
            )
            
            # Si no se incluyen planchas, calcular valor adicional con planchas
            if not incluye_planchas and valor_plancha > 0:
                print("\nValor adicional con planchas:")
                valor_plancha_ajustado = round((valor_plancha / 0.75) / 1000) * 1000
                print(f"Valor plancha ajustado: ${valor_plancha_ajustado:,.0f}")
                resultados_con_planchas = calculadora.calcular_costos_por_escala(
                    datos=datos,
                    num_tintas=num_tintas,
                    valor_etiqueta=valor_etiqueta,
                    valor_plancha=valor_plancha_ajustado,
                    valor_troquel=valor_troquel
                )
                print("\nCostos por escala (incluyendo planchas):")
                print(f"{'Escala':>10} | {'$/U Full':>10} | {'$MM':>10}")
                print("-" * 45)
                for r in resultados_con_planchas:
                    print(f"{r['escala']:10d} | {r['valor_unidad']:10.2f} | {r['valor_mm']:10.3f}")
        except ValueError as e:
            print(f"\nERROR: {str(e)}")
            print("Por favor revise los valores ingresados e intente nuevamente.")
            return
        except Exception as e:
            print(f"\nERROR INESPERADO: {str(e)}")
            print("Por favor contacte al soporte técnico.")
            return
        
        # Mostrar resultados
        print("\n=== Resultados ===")
        
        # Mostrar cálculo de desperdicio para la primera escala
        print("\nDetalle del cálculo de desperdicio (primera escala):")
        papel_lam_primera_escala = calculadora.calcular_papel_lam(escalas[0], datos.area_etiqueta)
        
        # Calcular y mostrar ancho total
        ancho_total, mensaje_ancho = calculadora.calcular_ancho_total(num_tintas, datos.pistas, datos.ancho)
        print(f"- Cálculo de ancho total:")
        print(f"  * Número de tintas (B2): {num_tintas}")
        print(f"  * Pistas (E3): {datos.pistas}")
        print(f"  * Ancho base: {datos.ancho}")
        print(f"  * D3 (ancho + C3): {datos.ancho + calculadora.C3}")
        print(f"  * Base (E3*D3-C3): {datos.pistas * (datos.ancho + calculadora.C3) - calculadora.C3}")
        print(f"  * Incremento: {10 if num_tintas == 0 else 20}")
        print(f"  * Ancho total final: {ancho_total}")
        if mensaje_ancho:
            print(f"  * {mensaje_ancho}")
        
        # Calcular desperdicio con el nuevo ancho total
        desperdicio_primera_escala = calculadora.calcular_desperdicio(
            num_tintas=num_tintas,
            ancho_total=ancho_total,
            papel_lam=papel_lam_primera_escala
        )
        print(f"\n- Cálculo de desperdicio:")
        print(f"  * S3 (ancho_total + 40): {ancho_total + 40}")
        print(f"  * Papel/lam (J8): ${papel_lam_primera_escala:,.2f}")
        print(f"  * Desperdicio calculado: ${desperdicio_primera_escala:,.2f}")
        
        print(f"\nValores de entrada:")
        print(f"- Unidad de montaje: {reporte_lito['unidad_montaje_sugerida']:.1f} dientes")
        print(f"- Área etiqueta: {datos.area_etiqueta:.2f} mm²")
        print(f"- Valor etiqueta: ${valor_etiqueta:,.6f}")
        print(f"- Valor plancha: ${valor_plancha:,.0f}")
        print(f"- Valor troquel: ${valor_troquel:,.2f}")
        print(f"- Desperdicio: {datos.desperdicio:.2f} mm")
        print(f"- Rentabilidad: {datos.rentabilidad}%")
        print(f"- Velocidad máquina: {datos.velocidad_maquina} m/min")
        
        print("\nCostos por escala:")
        print(f"{'Escala':>10} | {'$/U Full':>10} | {'$MM':>10} | {'mts':>10} | {'t (h)':>10} | {'Montaje':>10} | {'MO y Maq':>10} | {'Tintas':>10} | {'Papel/lam':>10} | {'Desperdicio':>10}")
        print("-" * 120)
        
        for r in resultados:
            print(f"{r['escala']:10d} | {r['valor_unidad']:10.2f} | {r['valor_mm']:10.3f} | {r['metros']:10.2f} | {r['tiempo_horas']:10.2f} | {r['montaje']:10.2f} | {r['mo_y_maq']:10.2f} | {r['tintas']:10.2f} | {r['papel_lam']:10.2f} | {r['desperdicio']:10.2f}")
        
        print("\n¿Desea realizar otro cálculo?")
        if obtener_input_si_no(""):
            print("\n" + "="*40 + "\n")
            main()
            
    except Exception as e:
        print(f"\nERROR INESPERADO: {str(e)}")
        print("Por favor contacte al soporte técnico.")
        return

if __name__ == "__main__":
    main()
