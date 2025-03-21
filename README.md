# Sistema de Cotización - Flexo Impresos

Una herramienta especializada para el cálculo y generación de cotizaciones en la industria flexográfica. Este sistema permite:
- Calcular costos precisos para etiquetas y mangas
- Validar parámetros técnicos de producción
- Generar documentos de cotización profesionales
- Mantener un registro estructurado de referencias

## Requisitos del sistema

- Python 3.8+
- Bibliotecas: Streamlit, Pandas, NumPy
- Conexión a base de datos SQL

## Instalación

1. Clonar el repositorio
2. Instalar dependencias: `pip install -r requirements.txt`
3. Configurar conexión a base de datos
4. Ejecutar: `streamlit run app_calculadora_costos.py`

## Constantes del Sistema

### Constantes Generales
```python
# Constantes de Rentabilidad y Desperdicio
RENTABILIDAD_MANGAS = 45.0     # Porcentaje de rentabilidad para mangas
RENTABILIDAD_ETIQUETAS = 40.0  # Porcentaje de rentabilidad para etiquetas
DESPERDICIO_MANGAS = 30.0      # Porcentaje de desperdicio para mangas
DESPERDICIO_ETIQUETAS = 10.0   # Porcentaje de desperdicio para etiquetas

# Constantes de Medidas
GAP = 3.0          # Gap entre pistas (mm)
GAP_FIJO = 20.0    # Gap fijo para cálculos de área (mm)
GAP_AVANCE = 2.6   # Gap al avance para etiquetas (mm)
AVANCE_FIJO = 3.0  # Avance fijo para cálculos (mm)
MM_COLOR = 10.0    # Milímetros adicionales por color (mm)

# Constantes de Mangas
FACTOR_ANCHO_MANGAS = 2        # Factor de multiplicación para el ancho en mangas
INCREMENTO_ANCHO_MANGAS = 20   # Incremento en mm para el ancho en mangas
```

### Velocidades de Máquina
- Velocidad estándar: 20.0 m/min
- Velocidad para mangas con 7 tintas: 7.0 m/min

## Validaciones de Ancho

El sistema implementa las siguientes validaciones para el ancho de los productos:

### Ancho Total Mínimo (60mm)
- El ancho total calculado no puede ser menor a 60mm para ningún producto
- Este ancho total incluye:
  - El ancho base del producto
  - Los gaps entre pistas (3mm por cada pista adicional)
  - El incremento por tintas (20mm si hay tintas, 10mm si no hay tintas)

### Fórmulas de Cálculo del Ancho Total

1. Para Etiquetas:
```
ancho_total = pistas * (ancho + gap_pistas) - gap_pistas + incremento_tintas
donde:
- gap_pistas = 3.0mm si hay más de 1 pista, 0mm si es 1 pista
- incremento_tintas = 20mm si hay tintas, 10mm si no hay tintas
```

2. Para Mangas:
```
ancho_total = pistas * ((ancho * 2 + 20) + gap_pistas) - gap_pistas + incremento_tintas
donde:
- gap_pistas = 3.0mm si hay más de 1 pista, 0mm si es 1 pista
- incremento_tintas = 20mm si hay tintas, 10mm si no hay tintas
```

### Ancho Máximo (335mm)
- El ancho total calculado no puede exceder los 335mm para ningún producto

### Anchos Mínimos por Tipo
1. Etiquetas:
   - Ancho mínimo por pista: 20mm
   - El ancho total debe ser ≥ 60mm

2. Mangas:
   - Ancho mínimo por pista: 10mm
   - Ancho efectivo mínimo (ancho*2 + 20): 40mm
   - El ancho total debe ser ≥ 60mm

## Consideraciones Especiales para Mangas

### Tipos de Grafado
1. Sin grafado
2. Vertical Total
3. Horizontal Total
4. Horizontal Total + Vertical

### Cálculos Especiales para Mangas
1. **Ancho Efectivo**:
   - Se calcula como: `ancho * 2 + 20`
   - Este valor se usa como base para todos los cálculos posteriores
   - El factor de multiplicación (2) representa las dos caras de la manga
   - El incremento fijo (20mm) contempla los márgenes de seguridad para el corte

2. **Tratamiento del Troquel**:
   - Para grafado "Horizontal Total + Vertical":
     - Si el desperdicio > 2mm: Se fuerza `troquel_existe = False`
     - Esto afecta el cálculo del valor del troquel, dividiendo el costo a la mitad
     - Esta regla especial se implementa por limitaciones técnicas de producción

3. **Velocidad de Máquina**:
   - Normal: 20.0 m/min
   - Con 7 tintas: 7.0 m/min (reducción automática)
   - La reducción de velocidad se debe a la complejidad técnica y tiempo de secado

4. **Materiales Permitidos**:
   - Solo PVC y PETG
   - Filtrado automático en la selección de materiales
   - Esta restricción responde a los requisitos técnicos de resistencia y flexibilidad

## Cálculo de Desperdicios

### Para Etiquetas
1. **Desperdicio Base**:
   - Se calcula usando la fórmula: `mejor_opcion['desperdicio']`
   - Considera: Ancho, pistas, relación con dientes disponibles
   - Típicamente entre 0.1mm y 5mm dependiendo de la configuración
   - Optimizado automáticamente para minimizar el material desperdiciado

2. **GAP al Avance**:
   - Valor fijo de 2.6mm adicionales
   - Necesario para separación entre etiquetas consecutivas
   - No aplicable a mangas

3. **Desperdicio Total**:
   - Suma de desperdicio base + GAP al avance
   - Impacta directamente en el costo final del producto

### Para Mangas
1. **Desperdicio Base**:
   - Calculado considerando las dimensiones de la manga y limitaciones de maquinaria
   - Especialmente crítico para grafados especiales
   - Optimizado para reducir costos de producción

2. **Sin GAP al Avance**:
   - No se suma el GAP_AVANCE debido a la naturaleza continua de las mangas
   - Representa una ventaja en eficiencia de material frente a etiquetas

3. **Consideraciones de Grafado**:
   - El tipo de grafado influye directamente en el desperdicio calculado
   - Para grafados complejos (Horizontal + Vertical) se aplican reglas especiales
   - Puede modificar el tratamiento del troquel si el desperdicio supera 2mm

## Manejo de Excepciones

### Validaciones Críticas
1. **Ancho Total**:
   - < 60mm: Error, detiene el cálculo
   - > 335mm: Error, detiene el cálculo
   - Estos límites responden a restricciones físicas de la maquinaria

2. **Número de Tintas**:
   - Máximo: 7 tintas (límite físico de estaciones de impresión)
   - Mínimo: 0 tintas (solo troquelado)
   - La velocidad de máquina se reduce a 7.0 m/min cuando se usan 7 tintas

3. **Materiales**:
   - Mangas: Solo PVC/PETG
   - Etiquetas: Todos los materiales disponibles en catálogo
   - Restricciones basadas en propiedades físicas requeridas

### Advertencias No Críticas
- Mensajes de advertencia que permiten continuar con el proceso
- Se muestran en la interfaz pero no detienen el cálculo
- Típicamente informan sobre configuraciones subóptimas pero viables

## Cálculos de Costos

### Componentes del Costo
1. **Valor de Plancha**:
   - Normal: Incluido en el cálculo del costo total
   - Por separado: Se calcula aparte y se muestra como ítem independiente
   - Calculado considerando área, complejidad y cantidad de tintas

2. **Valor de Troquel**:
   - Etiquetas: Según existencia previa (nuevo o existente)
   - Mangas: Depende del grafado y desperdicio
   - Factor de ajuste especial para grafados complejos con desperdicio > 2mm

3. **Costos de Material**:
   - Basado en área calculada (ancho × largo × cantidad)
   - Incluye porcentaje de desperdicio calculado
   - Precio unitario extraído de la base de datos de materiales

4. **Costos de Acabado**:
   - Solo para etiquetas (barniz, laminado, etc.)
   - Mangas siempre "Sin acabado"
   - Depende del tipo seleccionado y área a cubrir

## Interfaz de Usuario

### Campos Adaptivos
- Los campos mostrados cambian según el tipo de producto seleccionado
- Validaciones en tiempo real para prevenir errores
- Mensajes de ayuda contextuales que guían al usuario
- Valores predeterminados optimizados según el tipo de producto
- Visualización simplificada de materiales y acabados (solo nombres, sin códigos ni precios)

### Información Técnica
- Detalles de cálculos mostrados en secciones expandibles
- Resultados desglosados por componente de costo:
  - Montaje
  - MO y Maq (Mano de Obra y Maquinaria)
  - Tintas
  - Papel/laminado
  - Desperdicio
- Información detallada de desperdicios y optimización
- Identificador único destacado visualmente

### Tabla de Resultados
- Escala: Cantidad de unidades a producir
- Valor Unidad: Precio unitario del producto
- Metros: Cantidad de metros lineales requeridos
- Tiempo (h): Tiempo estimado de producción
- Desglose de costos por componente

## Generación de Documentos

### PDF de Cotización
- Incluye todos los detalles técnicos relevantes para producción
- Muestra escalas de producción con precios por volumen
- Incluye información de contacto del comercial asignado
- Formato profesional con identificadores únicos para seguimiento

### Identificador Único
- Formato específico según tipo de producto (ET para etiquetas, MT para mangas)
- Incluye información codificada: material, dimensiones, tintas, cliente
- Facilita seguimiento y referencia en sistemas de producción
- Ejemplo: `ET BOPP 40x100 4T BR R×1000 CLIENTE PRODUCTO 1984`

## Depuración y solución de problemas

### Problemas comunes

1. **"No se puede calcular el desperdicio"**
   - Causa: Valores de ancho y avance incompatibles con la configuración de dientes disponibles
   - Solución: Ajustar ancho o avance según especificaciones recomendadas

2. **"El ancho total excede el máximo permitido"**
   - Causa: Combinación de ancho, pistas y tintas genera un valor > 335mm
   - Solución: Reducir ancho por pista, número de pistas, o ambos

3. **"Error en cálculo de costos"**
   - Causa: Datos incompletos o incompatibles en la configuración
   - Solución: Verificar que todos los campos obligatorios estén correctamente completados

## Mensajes de Error
El sistema mostrará mensajes de error claros cuando:
- El ancho total sea menor a 60mm
- El ancho total exceda 335mm
- El ancho por pista sea menor al mínimo requerido
- El ancho efectivo para mangas sea menor al mínimo requerido
- El material seleccionado no sea compatible con el tipo de producto
- El número de tintas exceda el máximo permitido
- No se pueda calcular el desperdicio
- Ocurran errores en el cálculo de costos

## Glosario de términos técnicos

- **GAP**: Espacio entre pistas en milímetros
- **Pistas**: Número de productos lado a lado en el material
- **Troquel**: Herramienta de corte para definir la forma del producto
- **Grafado**: Proceso de marcado para dobleces en mangas
- **Desperdicio**: Material no aprovechable durante la producción
- **Escala**: Cantidad de unidades a producir en un lote
- **Acabado**: Tratamiento superficial aplicado a etiquetas (barniz, laminado, etc.)
- **Plancha**: Matriz de impresión flexográfica, una por cada color/tinta
- **Repeticiones**: Número de productos a lo largo del rollo de material
- **MO y Maq**: Costos asociados a mano de obra y maquinaria
- **Montaje**: Costos de preparación y configuración inicial 