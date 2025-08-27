"""
Script para verificar directamente el problema con el valor del troquel en el informe técnico.
"""

# Simular el código relevante de report_generator.py
def test_troquel_existe(existe_troquel, valor_troquel):
    """Simula la lógica que determina si mostrar 'Ya existe' en el informe"""
    texto_troquel = "Valor Troquel (Total)"
    if existe_troquel:
        texto_troquel += " (Ya existe)"
    
    print(f"existe_troquel: {existe_troquel}")
    print(f"valor_troquel: {valor_troquel}")
    print(f"Texto mostrado: {texto_troquel}")
    print(f"Línea completa: - **{texto_troquel}**: ${valor_troquel:,.2f}")
    print()

# Probar diferentes combinaciones
print("\n=== CASO 1: TROQUEL NO EXISTE, VALOR NORMAL ===")
test_troquel_existe(False, 825000.0)

print("=== CASO 2: TROQUEL SÍ EXISTE, VALOR MITAD ===")
test_troquel_existe(True, 412500.0)

print("=== CASO 3: TROQUEL NO EXISTE, PERO VALOR MITAD (INCORRECTO) ===")
test_troquel_existe(False, 412500.0)

print("=== CASO 4: TROQUEL SÍ EXISTE, PERO VALOR NORMAL (INCORRECTO) ===")
test_troquel_existe(True, 825000.0)

# Ahora vamos a revisar el código en app_calculadora_costos.py
print("\n=== ANÁLISIS DEL FLUJO DE DATOS ===")
print("1. En app_calculadora_costos.py, se guarda:")
print("   datos_calculo_persistir['valor_troquel'] = valor_troquel_defecto")
print("   datos_calculo_persistir['existe_troquel'] = datos_escala.troquel_existe")

print("\n2. En report_generator.py, se lee:")
print("   valor_troquel = calculos_guardados.get('valor_troquel', 0.0)")
print("   existe_troquel = calculos_guardados.get('existe_troquel', False)")

print("\n3. La lógica para mostrar el texto es:")
print("   texto_troquel = \"Valor Troquel (Total)\"")
print("   if existe_troquel:")
print("       texto_troquel += \" (Ya existe)\"")

print("\nCONCLUSIÓN:")
print("Si en la aplicación real estás viendo 'Ya existe' cuando no debería,")
print("significa que calculos_guardados['existe_troquel'] es True cuando debería ser False.")
print("Esto podría ocurrir si:")
print("1. El valor se está estableciendo incorrectamente en app_calculadora_costos.py")
print("2. El valor se está modificando en algún punto entre el cálculo y el informe")
print("3. Hay un problema en la persistencia de datos (base de datos)")

print("\nPRUEBA ADICIONAL:")
print("Verifica el valor real de existe_troquel en la base de datos para esta cotización.")
