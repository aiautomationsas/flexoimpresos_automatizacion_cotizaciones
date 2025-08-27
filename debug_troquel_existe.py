import sys
sys.path.append('.')

from src.logic.report_generator import generar_informe_tecnico_markdown
from src.logic.calculators.calculadora_litografia import CalculadoraLitografia, DatosLitografia
from src.logic.calculators.calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala
from src.config.constants import GAP_AVANCE_ETIQUETAS

# Datos del caso específico
ancho = 30
avance = 108
pistas = 1
repeticiones = 3
tintas = 3
valor_material = 1800
valor_acabado = 500
troquel_existe = False  # Explícitamente establecido como False
unidad_montaje_dientes = 108
planchas_por_separado = False

print("\n=== PRUEBA DE INFORME TÉCNICO CON TROQUEL NO EXISTENTE ===")
print(f"Valores de prueba:")
print(f"  Ancho: {ancho} mm")
print(f"  Avance: {avance} mm")
print(f"  Pistas: {pistas}")
print(f"  Tintas: {tintas}")
print(f"  Troquel existe: {troquel_existe}")
print(f"  Unidad escogida: {unidad_montaje_dientes} dientes")

# Calcular valor del troquel con CalculadoraLitografia
print("\n=== CÁLCULO CON CALCULADORA LITOGRAFIA ===")
calc_lito = CalculadoraLitografia()
datos_lito = DatosLitografia(
    ancho=ancho, 
    avance=avance, 
    pistas=pistas, 
    troquel_existe=troquel_existe
)
resultado_lito = calc_lito.calcular_valor_troquel(
    datos=datos_lito,
    repeticiones=repeticiones,
    troquel_existe=troquel_existe
)
print(f"Valor troquel calculado con CalculadoraLitografia: {resultado_lito['valor']}")

# Calcular valor del troquel con CalculadoraCostosEscala
print("\n=== CÁLCULO CON CALCULADORA COSTOS ESCALA ===")
calc_escala = CalculadoraCostosEscala()
datos_escala = DatosEscala(
    escalas=[1000],
    pistas=pistas,
    ancho=ancho,
    avance=avance,
    avance_total=avance + GAP_AVANCE_ETIQUETAS,
    desperdicio=0,
    troquel_existe=troquel_existe,
    unidad_montaje_dientes=unidad_montaje_dientes
)
valor_troquel_escala = calc_escala.calcular_valor_troquel(
    datos=datos_escala,
    es_manga=False
)
print(f"Valor troquel calculado con CalculadoraCostosEscala: {valor_troquel_escala}")

# Simular los datos que se pasarían al informe técnico
print("\n=== SIMULACIÓN DE DATOS PARA INFORME TÉCNICO ===")
cotizacion_data = {
    'ancho': ancho,
    'avance': avance,
    'numero_pistas': pistas,
    'num_tintas': tintas,
    'es_manga': False,
    'cliente_nombre': 'Cliente Prueba',
    'referencia_descripcion': 'Referencia Prueba',
    'comercial_nombre': 'Comercial Prueba',
    'identificador': 'TEST-30X108MM'
}

# Simular que somos administradores para ver los costos base
import streamlit as st
# Crear un diccionario simulado para session_state
st.session_state = {'usuario_rol': 'administrador', 'db': None}

calculos_guardados = {
    'valor_material': valor_material,
    'valor_acabado': valor_acabado,
    'valor_troquel': resultado_lito['valor'],  # Usar el valor calculado
    'valor_plancha': 134244.0,
    'unidad_z_dientes': unidad_montaje_dientes,
    'existe_troquel': troquel_existe,  # Este es el valor clave que queremos verificar
    'repeticiones': repeticiones
}

# Generar el informe técnico
print("\n=== GENERANDO INFORME TÉCNICO ===")
informe = generar_informe_tecnico_markdown(cotizacion_data, calculos_guardados)

# Extraer la parte del informe que muestra el valor del troquel
import re
troquel_line = None
for line in informe.split('\n'):
    if "Valor Troquel" in line:
        troquel_line = line
        break

print("\n=== RESULTADO EN EL INFORME TÉCNICO ===")
print(f"Línea del troquel en el informe: {troquel_line}")
print(f"¿Debería mostrar 'Ya existe'?: {troquel_existe}")

# Imprimir el informe completo para depuración
print("\nINFORME TÉCNICO COMPLETO:")
print(informe)

# Verificar si hay una discrepancia
if troquel_line is None:
    print("\n⚠️ ERROR: No se encontró la línea del troquel en el informe")
elif troquel_existe and "Ya existe" not in troquel_line:
    print("\n⚠️ ERROR: El troquel existe pero NO se muestra 'Ya existe' en el informe")
elif not troquel_existe and "Ya existe" in troquel_line:
    print("\n⚠️ ERROR: El troquel NO existe pero se muestra 'Ya existe' en el informe")
else:
    print("\n✅ CORRECTO: La indicación de 'Ya existe' coincide con el valor de troquel_existe")

# Verificar los valores de troquel_existe en diferentes etapas
print("\n=== VERIFICACIÓN DE VALORES DE TROQUEL_EXISTE ===")
print(f"1. Valor inicial de troquel_existe: {troquel_existe}")
print(f"2. Valor en datos_escala.troquel_existe: {datos_escala.troquel_existe}")
print(f"3. Valor en calculos_guardados['existe_troquel']: {calculos_guardados['existe_troquel']}")

# Verificar el código en report_generator.py que determina si mostrar "Ya existe"
print("\n=== CÓDIGO EN REPORT_GENERATOR.PY ===")
print("texto_troquel = \"Valor Troquel (Total)\"")
print("if existe_troquel:")
print("    texto_troquel += \" (Ya existe)\"")
