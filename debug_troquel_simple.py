import sys
sys.path.append('.')

# Mock para DBManager
class MockDBManager:
    def get_material(self, material_id):
        return type('Material', (), {'nombre': 'Material Prueba'})
    
    def get_acabado(self, acabado_id):
        return type('Acabado', (), {'codigo': 'AC', 'nombre': 'Acabado Prueba'})
    
    def get_adhesivos(self):
        return []

# Configurar session_state para simular rol de administrador
import streamlit as st
st.session_state = {'usuario_rol': 'administrador', 'db': MockDBManager()}

from src.logic.report_generator import generar_informe_tecnico_markdown

# Simular los datos que se pasarían al informe técnico
print("\n=== SIMULACIÓN DE DATOS PARA INFORME TÉCNICO ===")

# Caso 1: Troquel NO existe
cotizacion_data1 = {
    'ancho': 30,
    'avance': 108,
    'numero_pistas': 1,
    'num_tintas': 3,
    'es_manga': False,
    'cliente_nombre': 'Cliente Prueba',
    'referencia_descripcion': 'Referencia Prueba',
    'comercial_nombre': 'Comercial Prueba',
    'identificador': 'TEST-30X108MM',
    'material_id': 1,
    'acabado_id': 1
}

calculos_guardados1 = {
    'valor_material': 1800,
    'valor_acabado': 500,
    'valor_troquel': 825000.0,  # Valor para troquel nuevo
    'valor_plancha': 134244.0,
    'unidad_z_dientes': 108,
    'existe_troquel': False,  # Explícitamente False
    'repeticiones': 3
}

# Caso 2: Troquel SÍ existe
cotizacion_data2 = cotizacion_data1.copy()
calculos_guardados2 = calculos_guardados1.copy()
calculos_guardados2['existe_troquel'] = True
calculos_guardados2['valor_troquel'] = 412500.0  # Valor para troquel existente

# Probar ambos casos
print("\n=== CASO 1: TROQUEL NO EXISTE ===")
print(f"existe_troquel: {calculos_guardados1['existe_troquel']}")
print(f"valor_troquel: {calculos_guardados1['valor_troquel']}")

# Extraer la parte del informe que muestra el valor del troquel
informe1 = generar_informe_tecnico_markdown(cotizacion_data1, calculos_guardados1)
troquel_line1 = None
for line in informe1.split('\n'):
    if "Valor Troquel" in line:
        troquel_line1 = line
        break

print(f"Línea del troquel en el informe: {troquel_line1}")
if troquel_line1 is None:
    print("⚠️ ERROR: No se encontró la línea del troquel en el informe")
elif "Ya existe" in troquel_line1:
    print("⚠️ ERROR: Se muestra 'Ya existe' cuando troquel_existe=False")
else:
    print("✅ CORRECTO: No se muestra 'Ya existe' cuando troquel_existe=False")

print("\n=== CASO 2: TROQUEL SÍ EXISTE ===")
print(f"existe_troquel: {calculos_guardados2['existe_troquel']}")
print(f"valor_troquel: {calculos_guardados2['valor_troquel']}")

# Extraer la parte del informe que muestra el valor del troquel
informe2 = generar_informe_tecnico_markdown(cotizacion_data2, calculos_guardados2)
troquel_line2 = None
for line in informe2.split('\n'):
    if "Valor Troquel" in line:
        troquel_line2 = line
        break

print(f"Línea del troquel en el informe: {troquel_line2}")
if troquel_line2 is None:
    print("⚠️ ERROR: No se encontró la línea del troquel en el informe")
elif "Ya existe" in troquel_line2:
    print("✅ CORRECTO: Se muestra 'Ya existe' cuando troquel_existe=True")
else:
    print("⚠️ ERROR: No se muestra 'Ya existe' cuando troquel_existe=True")

print("\n=== REVISIÓN DEL CÓDIGO EN REPORT_GENERATOR.PY ===")
print("La lógica para mostrar 'Ya existe' es:")
print("texto_troquel = \"Valor Troquel (Total)\"")
print("if existe_troquel:")
print("    texto_troquel += \" (Ya existe)\"")
print("costos_base = f\"...\"")
print("- **{texto_troquel}**: {format_currency(valor_troquel)}")