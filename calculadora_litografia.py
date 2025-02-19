from dataclasses import dataclass
from typing import Optional, Dict, List
import math
from calculadora_desperdicios import CalculadoraDesperdicio, OpcionDesperdicio
import streamlit as st

class DatosLitografia:
    """Clase para almacenar los datos necesarios para los cálculos de litografía"""
    def __init__(self, ancho: float, avance: float, pistas: int = 1,
                 incluye_planchas: bool = True, incluye_troquel: bool = True,
                 troquel_existe: bool = False, gap: float = 3.0, 
                 gap_avance: float = 2.6, ancho_maximo: float = 335.0):
        """
        Args:
            ancho: Ancho en mm
            avance: Avance/Largo en mm
            pistas: Número de pistas
            incluye_planchas: Si se deben incluir planchas en el cálculo
            incluye_troquel: Si se debe incluir troquel en el cálculo
            troquel_existe: Si ya tienen el troquel (True) o hay que hacer uno nuevo (False)
            gap: Valor fijo de gap para ancho
            gap_avance: Valor fijo de gap para avance
            ancho_maximo: Ancho máximo permitido
        """
        self.ancho = ancho
        self.avance = avance
        self.pistas = pistas
        self.incluye_planchas = incluye_planchas
        self.incluye_troquel = incluye_troquel
        self.troquel_existe = troquel_existe
        self.gap = gap
        self.gap_avance = gap_avance
        self.ancho_maximo = ancho_maximo

class CalculadoraLitografia:
    def __init__(self):
        self.ancho_maximo = 335.0  # mm
        self.calculadora_desperdicios = CalculadoraDesperdicio(
            ancho_maquina=self.ancho_maximo,
            gap_mm=2.6  # Este gap solo se usa para etiquetas
        )

    def calcular_ancho_total(self, datos: DatosLitografia, num_tintas: int = 0, es_manga: bool = False) -> float:
        """
        Calcula el ancho total basado en el tipo de impresión
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            num_tintas: Número de tintas a utilizar
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            float: Ancho total redondeado
        """
        if es_manga:
            # Para mangas: (ancho * 2 + 20) redondeado al múltiplo de 5 superior
            ancho_manga = (datos.ancho * 2) + 20
            ancho_redondeado = math.ceil(ancho_manga / 5) * 5
        else:
            # Para etiquetas: mantener la lógica actual
            ancho_con_gap = datos.ancho + datos.gap
            base = (datos.pistas * ancho_con_gap - datos.gap)
            margen = 20 if num_tintas > 0 else 10
            ancho_total = base + margen
            ancho_redondeado = math.ceil(ancho_total / 10) * 10
        
        if ancho_redondeado > self.ancho_maximo:
            raise ValueError(f"El ancho calculado ({ancho_redondeado}mm) excede el máximo permitido ({self.ancho_maximo}mm)")
            
        return ancho_redondeado

    def calcular_desperdicio(self, datos: DatosLitografia) -> Dict:
        """
        Calcula el desperdicio y las opciones de impresión usando la calculadora de desperdicios
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            
        Returns:
            Dict: Reporte completo con todas las opciones de desperdicio y la mejor opción
        """
        return self.calculadora_desperdicios.generar_reporte(datos.avance)

    def obtener_mejor_opcion_desperdicio(self, datos: DatosLitografia, es_manga: bool = False) -> Optional[OpcionDesperdicio]:
        """
        Obtiene la mejor opción de desperdicio según el tipo de impresión
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Optional[OpcionDesperdicio]: La mejor opción de desperdicio si existe
        """
        opciones = self.calculadora_desperdicios.calcular_todas_opciones(datos.avance)
        if not opciones:
            raise ValueError("No se encontraron opciones válidas para el avance especificado")
        
        if es_manga:
            # Para mangas: buscar el desperdicio más cercano a 0
            # En caso de empate, seleccionar el de menor dientes
            mejor_opcion = min(
                opciones,
                key=lambda x: (abs(x.desperdicio), x.dientes)  # Primero por desperdicio absoluto, luego por dientes
            )
        else:
            # Para etiquetas: mantener la lógica actual (primera opción)
            mejor_opcion = opciones[0]
        
        return mejor_opcion

    def validar_medidas(self, datos: DatosLitografia) -> bool:
        """
        Valida que las medidas estén dentro de los rangos permitidos
        
        Args:
            datos: Objeto DatosLitografia con los datos a validar
            
        Returns:
            bool: True si las medidas son válidas
            
        Raises:
            ValueError: Si alguna medida está fuera de rango
        """
        if datos.ancho <= 0:
            raise ValueError("El ancho debe ser mayor a 0")
        if datos.avance <= 0:
            raise ValueError("El avance debe ser mayor a 0")
        if datos.pistas <= 0:
            raise ValueError("El número de pistas debe ser mayor a 0")
        
        return True

    def calcular_unidad_montaje_sugerida(self, datos: DatosLitografia, es_manga: bool = False) -> float:
        """
        Calcula la unidad de montaje sugerida basada en el criterio según tipo
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            float: Número de dientes sugerido para el montaje
            
        Raises:
            ValueError: Si no se encuentra una opción válida
        """
        mejor_opcion = self.obtener_mejor_opcion_desperdicio(datos, es_manga)
        return mejor_opcion.dientes

    def calcular_precio_plancha(self, datos: DatosLitografia, num_tintas: int = 0, es_manga: bool = False) -> Dict:
        """
        Calcula el precio de la plancha según la fórmula:
        precio = valor_mm * (ancho_total + gap_fijo) * (mm_unidad_montaje + avance_fijo)
        
        Donde:
        - valor_mm = 120 para mangas, 100 para etiquetas
        - gap_fijo = 50 mm para mangas, 40 mm para etiquetas
        - avance_fijo = 30 mm
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            num_tintas: Número de tintas a utilizar
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Dict: Diccionario con el precio y los valores usados en el cálculo
        """
        # Constantes
        VALOR_MM = 120 if es_manga else 100  # Valor por mm según tipo
        GAP_FIJO = 50 if es_manga else 40  # GAP fijo en mm según tipo
        AVANCE_FIJO = 30  # R4: Avance fijo en mm
        
        try:
            # Calcular ancho total (F3)
            ancho_total = self.calcular_ancho_total(datos, num_tintas, es_manga)
            
            # Obtener mm de la unidad de montaje (Q4)
            mejor_opcion = self.obtener_mejor_opcion_desperdicio(datos, es_manga)
            if not mejor_opcion:
                raise ValueError("No se pudo determinar la unidad de montaje")
            mm_unidad_montaje = mejor_opcion.medida_mm
            
            # Calcular S3 = R3 + F3 (gap_fijo + ancho_total)
            s3 = GAP_FIJO + ancho_total
            
            # Calcular S4 = Q4 + R4 (mm_unidad_montaje + avance_fijo)
            s4 = mm_unidad_montaje + AVANCE_FIJO
            
            # Calcular precio final, multiplicando directamente por número de tintas
            precio = VALOR_MM * s3 * s4 * num_tintas
            
            return {
                'precio': precio,
                'detalles': {
                    'valor_mm': VALOR_MM,
                    'gap_fijo': GAP_FIJO,
                    'avance_fijo': AVANCE_FIJO,
                    'ancho_total': ancho_total,
                    'mm_unidad_montaje': mm_unidad_montaje,
                    's3': s3,
                    's4': s4,
                    'num_tintas': num_tintas,
                    'es_manga': es_manga
                }
            }
        except Exception as e:
            return {
                'error': str(e),
                'precio': None,
                'detalles': None
            }

    def calcular_valor_troquel(self, datos: DatosLitografia, repeticiones: int, 
                             valor_mm: float = 100, troquel_existe: bool = False) -> Dict:
        """
        Calcula el valor del troquel según la fórmula:
        ((25*5000) + max(700000, ((ancho+avance)*2*pistas*repeticiones)*valor_mm)) / factor
        
        donde:
        - factor = 2 si el troquel existe, 1 si hay que hacer uno nuevo
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            repeticiones: Número de repeticiones
            valor_mm: Valor por mm del troquel (default: 100)
            troquel_existe: True si ya tienen el troquel, False si hay que hacer uno nuevo
            
        Returns:
            Dict: Diccionario con el valor del troquel y los valores usados en el cálculo
        """
        try:
            # Constantes
            FACTOR_EXISTENTE = 2  # Si ya tienen el troquel
            FACTOR_NUEVO = 1      # Si hay que hacer un troquel nuevo
            VALOR_MINIMO = 700000
            FACTOR_BASE = 25 * 5000  # 25 * 5000 = 125000
            
            # Calcular el valor base del troquel
            perimetro = (datos.ancho + datos.avance) * 2
            valor_base = perimetro * datos.pistas * repeticiones * valor_mm
            
            # Tomar el máximo entre el valor base y el mínimo
            valor_calculado = max(VALOR_MINIMO, valor_base)
            
            # Agregar el factor base y dividir por el factor según si existe o no
            factor_division = FACTOR_EXISTENTE if troquel_existe else FACTOR_NUEVO
            valor_final = (FACTOR_BASE + valor_calculado) / factor_division
            
            return {
                'valor': valor_final,
                'detalles': {
                    'perimetro': perimetro,
                    'valor_base': valor_base,
                    'valor_minimo': VALOR_MINIMO,
                    'valor_calculado': valor_calculado,
                    'factor_base': FACTOR_BASE,
                    'factor_division': factor_division,
                    'troquel_existe': troquel_existe,
                    'valor_mm': valor_mm
                }
            }
        except Exception as e:
            return {
                'error': str(e),
                'valor': None,
                'detalles': None
            }

    def calcular_area_etiqueta(self, datos: DatosLitografia, num_tintas: int, 
                              medida_montaje: float, repeticiones: int) -> Dict:
        """
        Calcula el área de la etiqueta según la fórmula:
        Si num_tintas = 0:
            area = (Q3/E3) * (Q4/E4)
        Si no:
            area = (S3/E3) * (Q4/E4)
            
        donde:
        Q3 = D3*E3 + C3
        D3 = ancho + gap (3mm)
        E3 = número de pistas
        C3 = gap (3mm)
        Q4 = medida de montaje
        E4 = repeticiones (del cálculo de desperdicio)
        S3 = R3 + F3
        F3 = ancho total
        R3 = gap fijo (40mm)
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            num_tintas: Número de tintas
            medida_montaje: Medida de montaje en mm
            repeticiones: Número de repeticiones
            
        Returns:
            Dict con el área calculada y los valores intermedios
        """
        try:
            # Constantes
            GAP = 3  # mm para D3 y C3
            GAP_R3 = 40  # mm para R3
            
            # Cálculos para Q3
            d3 = datos.ancho + GAP
            e3 = datos.pistas
            c3 = GAP
            q3 = (d3 * e3) + c3
            
            # Cálculos para S3
            f3 = self.calcular_ancho_total(datos, num_tintas)
            r3 = GAP_R3  # Ahora es 40mm
            s3 = r3 + f3
            
            # Q4 es la medida de montaje
            q4 = medida_montaje
            e4 = repeticiones
            
            # Calcular área según fórmula
            if num_tintas == 0:
                area_ancho = q3/e3
                area_largo = q4/e4
                area = area_ancho * area_largo
            else:
                area_ancho = s3/e3
                area_largo = q4/e4
                area = area_ancho * area_largo
            
            return {
                'area': area,
                'detalles': {
                    'q3': q3,
                    'd3': d3,
                    'e3': e3,
                    'c3': c3,
                    's3': s3,
                    'f3': f3,
                    'r3': r3,
                    'q4': q4,
                    'e4': e4,
                    'formula_usada': 'Q3/E3 * Q4/E4' if num_tintas == 0 else 'S3/E3 * Q4/E4',
                    'area_ancho': area_ancho,
                    'area_largo': area_largo,
                    'calculo_detallado': f"({q3 if num_tintas == 0 else s3}/{e3}) * ({q4}/{e4})"
                }
            }
        except Exception as e:
            return {
                'error': str(e),
                'area': None,
                'detalles': None
            }
    
    def calcular_valor_tinta_etiqueta(self, area_etiqueta: float, num_tintas: int) -> Dict:
        """
        Calcula el valor de la tinta por etiqueta según la fórmula:
        $/etiqueta = tintas * $/mm2 * area_etiqueta
        
        donde:
        $/mm2 = gr/m2 / 1000000 = 0.00000800
        gr/m2 = 8 (fijo)
        
        Args:
            area_etiqueta: Área de la etiqueta en mm2
            num_tintas: Número de tintas
            
        Returns:
            Dict con el valor calculado y los valores intermedios
        """
        try:
            # Constantes
            GRAMOS_M2 = 8  # gr/m2
            VALOR_MM2 = 0.00000800  # $/mm2
            
            # Calcular valor por etiqueta
            valor_etiqueta = num_tintas * VALOR_MM2 * area_etiqueta
            
            return {
                'valor': valor_etiqueta,
                'detalles': {
                    'gramos_m2': GRAMOS_M2,
                    'valor_mm2': VALOR_MM2,
                    'area_etiqueta': area_etiqueta,
                    'num_tintas': num_tintas
                }
            }
        except Exception as e:
            return {
                'error': str(e),
                'valor': None,
                'detalles': None
            }
            
    def generar_reporte_completo(self, datos: DatosLitografia, num_tintas: int = 0, es_manga: bool = False) -> Dict:
        """Genera un reporte completo con todos los cálculos relevantes"""
        try:
            # Ajustar gaps si es manga
            if es_manga:
                datos.gap = 0
                datos.gap_avance = 0

            ancho_total = self.calcular_ancho_total(datos, num_tintas, es_manga)
            reporte_desperdicio = self.calcular_desperdicio(datos)
            unidad_montaje = self.calcular_unidad_montaje_sugerida(datos, es_manga)
            calculo_plancha = self.calcular_precio_plancha(datos, num_tintas, es_manga)
            
            # Calcular área de etiqueta y valor de tinta
            area_etiqueta = None
            valor_tinta = None
            detalles_area = None
            detalles_tinta = None
            
            if reporte_desperdicio['mejor_opcion']:
                mejor_opcion = reporte_desperdicio['mejor_opcion']
                calculo_area = self.calcular_area_etiqueta(
                    datos=datos,
                    num_tintas=num_tintas,
                    medida_montaje=mejor_opcion['medida_mm'],
                    repeticiones=mejor_opcion['repeticiones']
                )
                area_etiqueta = calculo_area['area']
                detalles_area = calculo_area['detalles']
                
                if area_etiqueta is not None:
                    calculo_tinta = self.calcular_valor_tinta_etiqueta(
                        area_etiqueta=area_etiqueta,
                        num_tintas=num_tintas
                    )
                    valor_tinta = calculo_tinta['valor']
                    detalles_tinta = calculo_tinta['detalles']
            
            # Calcular valor del troquel si es necesario
            valor_troquel = None
            detalles_troquel = None
            if datos.incluye_troquel and reporte_desperdicio['mejor_opcion']:
                mejor_opcion = reporte_desperdicio['mejor_opcion']
                calculo_troquel = self.calcular_valor_troquel(
                    datos=datos,
                    repeticiones=mejor_opcion['repeticiones'],
                    troquel_existe=datos.troquel_existe
                )
                valor_troquel = calculo_troquel['valor']
                detalles_troquel = calculo_troquel['detalles']
            
            return {
                'ancho_total': ancho_total,
                'unidad_montaje_sugerida': unidad_montaje,
                'desperdicio': reporte_desperdicio,
                'precio_plancha': calculo_plancha['precio'],
                'detalles_plancha': calculo_plancha['detalles'],
                'valor_troquel': valor_troquel,
                'detalles_troquel': detalles_troquel,
                'area_etiqueta': area_etiqueta,
                'detalles_area': detalles_area,
                'valor_tinta': valor_tinta,
                'detalles_tinta': detalles_tinta,
                'datos_entrada': {
                    'ancho': datos.ancho,
                    'avance': datos.avance,
                    'pistas': datos.pistas,
                    'incluye_planchas': datos.incluye_planchas,
                    'incluye_troquel': datos.incluye_troquel,
                    'num_tintas': num_tintas,
                    'es_manga': es_manga
                }
            }
        except Exception as e:
            return {
                'error': str(e),
                'ancho_total': None,
                'unidad_montaje_sugerida': None,
                'desperdicio': None,
                'precio_plancha': None,
                'detalles_plancha': None,
                'valor_troquel': None,
                'detalles_troquel': None,
                'area_etiqueta': None,
                'detalles_area': None,
                'valor_tinta': None,
                'detalles_tinta': None,
                'datos_entrada': {
                    'ancho': datos.ancho,
                    'avance': datos.avance,
                    'pistas': datos.pistas,
                    'incluye_planchas': datos.incluye_planchas,
                    'incluye_troquel': datos.incluye_troquel,
                    'num_tintas': num_tintas,
                    'es_manga': es_manga
                }
            }
