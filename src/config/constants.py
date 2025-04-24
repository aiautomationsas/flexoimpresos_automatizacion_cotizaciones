"""
Archivo de constantes para toda la aplicación.
Este archivo centraliza todas las constantes utilizadas en los diferentes módulos,
organizadas por categorías para facilitar su mantenimiento y actualización.
"""

# Constantes generales y de producto
RENTABILIDAD_MANGAS = 45.0  # Porcentaje de rentabilidad para mangas
RENTABILIDAD_ETIQUETAS = 40.0  # Porcentaje de rentabilidad para etiquetas
DESPERDICIO_MANGAS = 30.0  # Porcentaje de desperdicio para mangas
DESPERDICIO_ETIQUETAS = 10.0  # Porcentaje de desperdicio para etiquetas

# Constantes de máquina y velocidad
VELOCIDAD_MAQUINA_NORMAL = 20.0  # Velocidad normal de la máquina en m/min
VELOCIDAD_MAQUINA_MANGAS_7_TINTAS = 7.0  # Velocidad especial para mangas con 7 tintas
ANCHO_MAXIMO_MAQUINA = 325.0  # Ancho máximo para cálculos de escala en mm
ANCHO_MAXIMO_LITOGRAFIA = 335.0  # Ancho máximo para litografía en mm

# Constantes para GAPs y dimensiones
GAP_AVANCE_ETIQUETAS = 2.6  # GAP al avance para etiquetas en mm
GAP_AVANCE_MANGAS = 0  # GAP al avance para mangas en mm
GAP_PISTAS_ETIQUETAS = 3.0  # GAP entre pistas para etiquetas en mm
GAP_PISTAS_MANGAS = 0  # GAP entre pistas para mangas en mm
GAP_FIJO = 50  # R3 es 50 tanto para mangas como etiquetas
AVANCE_FIJO = 30  # Avance fijo para cálculos

# Constantes para factor y ajustes de ancho
FACTOR_ANCHO_MANGAS = 2  # Factor de multiplicación para el ancho en mangas
INCREMENTO_ANCHO_MANGAS = 20  # Incremento en mm para el ancho en mangas
INCREMENTO_ANCHO_TINTAS = 20  # Incremento de ancho para productos con tintas
INCREMENTO_ANCHO_SIN_TINTAS = 10  # Incremento de ancho para productos sin tintas

# Constantes para cálculos de costos
VALOR_MM_PLANCHA = 1.5  # Valor por mm de plancha
MM_COLOR = 30000  # MM de color para cálculo de desperdicio
FACTOR_TINTA_AREA = 0.00000800  # Factor para calcular costo de tinta por área
CANTIDAD_TINTA_ESTANDAR = 100  # Cantidad estándar de tinta para cálculos

# Constantes para mano de obra
MO_MONTAJE = 5000.0  # Valor fijo de mano de obra para montaje
MO_IMPRESION = 50000.0  # Valor fijo de mano de obra para impresión
MO_TROQUELADO = 50000.0  # Valor fijo de mano de obra para troquelado
MO_SELLADO = 50000.0  # Valor fijo de mano de obra para sellado
MO_CORTE = 50000.0  # Valor fijo de mano de obra para corte

# Constantes para cálculos de material
VALOR_GR_TINTA = 30.0  # Valor fijo para gramo de tinta 