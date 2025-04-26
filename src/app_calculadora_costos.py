def obtener_valor_troquel(reporte_lito: Dict) -> float:
    """
    Obtiene el valor del troquel del reporte de litografía.
    Si no existe o es inválido, retorna el valor mínimo (700,000).
    """
    try:
        VALOR_MINIMO = 700000
        
        # Si no hay reporte, retornar valor mínimo
        if not reporte_lito:
            print("No hay reporte de litografía, usando valor mínimo para troquel")
            return VALOR_MINIMO
            
        # Obtener el valor del troquel del reporte
        valor_troquel = reporte_lito.get('valor_troquel', {'valor': VALOR_MINIMO})
        
        # Si es un diccionario, extraer el valor
        if isinstance(valor_troquel, dict):
            valor = valor_troquel.get('valor', VALOR_MINIMO)
        else:
            valor = valor_troquel
            
        # Si el valor es None o <= 0, usar valor mínimo
        if valor is None or valor <= 0:
            print(f"Valor de troquel inválido ({valor}), usando valor mínimo")
            return VALOR_MINIMO
            
        return float(valor)
        
    except Exception as e:
        print(f"Error al obtener valor del troquel: {str(e)}")
        return VALOR_MINIMO 