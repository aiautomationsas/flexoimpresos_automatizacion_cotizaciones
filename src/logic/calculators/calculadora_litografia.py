from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
import math
from src.logic.calculators.calculadora_desperdicios import CalculadoraDesperdicio, OpcionDesperdicio
from src.logic.calculators.calculadora_base import CalculadoraBase
from src.config.constants import (
    GAP_PISTAS_ETIQUETAS, GAP_AVANCE_ETIQUETAS, ANCHO_MAXIMO_LITOGRAFIA,
    VALOR_MM_PLANCHA, INCREMENTO_ANCHO_SIN_TINTAS, INCREMENTO_ANCHO_TINTAS
)

class DatosLitografia:
    """
    Clase para almacenar los datos necesarios para los cálculos de litografía.
    
    Esta clase encapsula todos los parámetros requeridos para realizar cálculos
    relacionados con litografía, como dimensiones, configuración de pistas,
    y opciones de inclusión de planchas y troqueles.
    """
    def __init__(self, ancho: float, avance: float, pistas: int = 1,
                 planchas_por_separado: bool = True, incluye_troquel: bool = True,
                 troquel_existe: bool = False, gap: float = GAP_PISTAS_ETIQUETAS, 
                 gap_avance: float = GAP_AVANCE_ETIQUETAS, ancho_maximo: float = ANCHO_MAXIMO_LITOGRAFIA,
                 tipo_grafado: Optional[str] = None):
        """
        Inicializa un objeto DatosLitografia con los parámetros especificados.
        
        Args:
            ancho: Ancho en mm
            avance: Avance/Largo en mm
            pistas: Número de pistas
            planchas_por_separado: Si las planchas se cobran por separado (True) o se incluyen en el cálculo (False)
            incluye_troquel: Si se debe incluir troquel en el cálculo
            troquel_existe: Si ya tienen el troquel (True) o hay que hacer uno nuevo (False)
            gap: Valor fijo de gap para ancho (0 para mangas o etiquetas con 1 pista, 3.0 para etiquetas con más de 1 pista)
            gap_avance: Valor fijo de gap para avance (0 para mangas, 2.6 para etiquetas)
            ancho_maximo: Ancho máximo permitido
            tipo_grafado: Tipo de grafado para mangas (None, "Sin grafado", "Vertical Total", 
                         "Horizontal Total", "Horizontal Total + Vertical")
        """
        self.ancho = ancho
        self.avance = avance
        self.pistas = pistas
        self.planchas_por_separado = planchas_por_separado
        self.incluye_troquel = incluye_troquel
        self.troquel_existe = troquel_existe
        self.gap = gap
        self.gap_avance = gap_avance
        self.ancho_maximo = ancho_maximo
        self.tipo_grafado = tipo_grafado
        # Calcular constante de troquel basada en el tipo de grafado
        self.constante_troquel = 1 if tipo_grafado == "Horizontal Total + Vertical" else 2

class CalculadoraLitografia(CalculadoraBase):
    """
    Calculadora para litografía que maneja los cálculos específicos de este proceso.
    """
    
    # Constantes específicas de litografía
    VALOR_MM_PLANCHA = VALOR_MM_PLANCHA  # Valor por mm de plancha
    ANCHO_MAXIMO = ANCHO_MAXIMO_LITOGRAFIA  # Ancho máximo permitido en mm
    
    def __init__(self):
        """Inicializa la calculadora de litografía."""
        super().__init__()
        self._calculadora_desperdicios = None
        self._calculadora_desperdicios_manga = None

    @property
    def calculadora_desperdicios(self) -> CalculadoraDesperdicio:
        """Devuelve la calculadora de desperdicios actual"""
        if self._calculadora_desperdicios is None:
            self._calculadora_desperdicios = CalculadoraDesperdicio(
                ancho_maquina=self.ANCHO_MAXIMO,
                gap_mm=GAP_AVANCE_ETIQUETAS  # Este gap solo se usa para etiquetas
            )
        return self._calculadora_desperdicios

    def _get_calculadora_desperdicios(self, es_manga: bool = False) -> CalculadoraDesperdicio:
        """
        Obtiene una instancia de CalculadoraDesperdicio configurada según el tipo
        """
        return CalculadoraDesperdicio(
            ancho_maquina=self.ANCHO_MAXIMO,
            gap_mm=GAP_AVANCE_ETIQUETAS,  # Este gap solo se usa para etiquetas
            es_manga=es_manga
        )

    def calcular_ancho_total(self, num_tintas: int, pistas: int, ancho: float) -> Tuple[float, Optional[str]]:
        """
        Calcula el ancho total según la fórmula:
        ROUNDUP(IF(B2=0, ((E3*D3-C3)+10), ((E3*D3-C3)+20)), -1)
        donde:
        - B2 = número de tintas
        - E3 = pistas
        - C3 = valor fijo de 3
        - D3 = ancho + C3
        
        Returns:
            Tuple[float, Optional[str]]: (ancho_total, mensaje_recomendacion)
            El mensaje_recomendacion será None si no hay problemas
        """
        # Usar el GAP de la clase base
        C3 = 0 if pistas <= 1 else self.GAP
        
        # Calcular D3 = ancho + C3
        d3 = ancho + C3
        
        # Calcular base = pistas * D3 - C3
        base = pistas * d3 - C3
        
        # Incremento según número de tintas
        incremento = INCREMENTO_ANCHO_SIN_TINTAS if num_tintas == 0 else INCREMENTO_ANCHO_TINTAS
        
        # Calcular resultado
        resultado = base + incremento
        
        # Redondear hacia arriba al siguiente múltiplo de 10
        ancho_redondeado = math.ceil(resultado / 10) * 10
        
        mensaje = None
        if ancho_redondeado > self.ANCHO_MAXIMO:
            # Calcular pistas recomendadas
            ancho_con_gap = ancho + C3
            pistas_recomendadas = math.floor((self.ANCHO_MAXIMO - incremento + C3) / ancho_con_gap)
            
            if ancho > self.ANCHO_MAXIMO:
                mensaje = f"ERROR: El ancho base ({ancho}mm) excede el máximo permitido ({self.ANCHO_MAXIMO}mm)"
            else:
                mensaje = f"ADVERTENCIA: El ancho total calculado ({ancho_redondeado}mm) excede el máximo permitido ({self.ANCHO_MAXIMO}mm). Se recomienda usar {pistas_recomendadas} pistas o menos."
        
        return ancho_redondeado, mensaje

    def calcular_desperdicio(self, datos: DatosLitografia, es_manga: bool = False) -> Dict:
        """
        Calcula el desperdicio y las opciones de impresión usando la calculadora de desperdicios
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Dict: Reporte completo con todas las opciones de desperdicio y la mejor opción
        """
        calculadora = self._get_calculadora_desperdicios(es_manga)
        return calculadora.generar_reporte(datos.avance)

    def obtener_mejor_opcion_desperdicio(self, datos: DatosLitografia, es_manga: bool = False) -> Optional[OpcionDesperdicio]:
        """
        Obtiene la mejor opción de desperdicio según el tipo de producto
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Optional[OpcionDesperdicio]: La mejor opción de desperdicio si existe
        """
        calculadora = self._get_calculadora_desperdicios(es_manga)
        opciones = calculadora.calcular_todas_opciones(datos.avance)
        if not opciones:
            raise ValueError("No se encontraron opciones válidas para el avance especificado")
        
        return opciones[0]  # Ya está ordenado por desperdicio absoluto y dientes

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
        Calcula el precio de la plancha basado en dimensiones y número de tintas.
        
        El cálculo se basa en la fórmula:
        precio = (VALOR_MM_PLANCHA * S3 * S4 * num_tintas) / constante
        
        Donde:
        - S3 = GAP_FIJO + Q3 (ancho total ajustado con gap fijo)
        - S4 = mm_unidad_montaje + AVANCE_FIJO (largo total ajustado)
        - Q3 = resultado de _calcular_q3 (ancho total con gaps entre pistas)
        - constante = 10000000 si planchas por separado (planchas_por_separado=True), 1 si no (planchas_por_separado=False)
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            num_tintas: Número de tintas (colores)
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Dict con el precio calculado y detalles del cálculo
            
        Raises:
            ValueError: Si no se puede determinar la unidad de montaje
        """
        try:
            print("\n=== INICIO CÁLCULO DE PLANCHA ===")
            print(f"Datos de entrada:")
            print(f"- Ancho: {datos.ancho} mm")
            print(f"- Pistas: {datos.pistas}")
            print(f"- Número de tintas: {num_tintas}")
            print(f"- Es manga: {es_manga}")
            print(f"- Incluye planchas: {datos.planchas_por_separado}")
            
            # 1. Calcular Q3 (ancho total ajustado) usando el método auxiliar
            q3_result = self._calcular_q3(num_tintas, datos.ancho, datos.pistas, es_manga)
            q3 = q3_result['q3']
            c3 = q3_result['c3']
            d3 = q3_result['d3']
            
            # 2. Calcular S3 = GAP_FIJO + Q3 (ancho total con gap fijo)
            s3 = self.GAP_FIJO + q3
            
            # 3. Obtener mm de la unidad de montaje (para S4)
            mejor_opcion = self.obtener_mejor_opcion_desperdicio(datos, es_manga)
            if not mejor_opcion:
                raise ValueError("No se pudo determinar la unidad de montaje")
            mm_unidad_montaje = mejor_opcion.medida_mm
            
            # 4. Calcular S4 = mm_unidad_montaje + AVANCE_FIJO (largo total)
            s4 = mm_unidad_montaje + self.AVANCE_FIJO
            
            # 5. Calcular precio sin aplicar constante
            precio_sin_constante = self.VALOR_MM_PLANCHA * s3 * s4 * num_tintas
            
            # 6. Determinar constante según si las planchas se cobran por separado
            # NOTA: En la interfaz, "Planchas por separado" = "Sí" se traduce a planchas_por_separado=True
            # Si planchas_por_separado es True, significa que las planchas se cobran por separado y la constante debe ser 10000000
            # Si planchas_por_separado es False, significa que las planchas se incluyen en el cálculo y la constante debe ser 1
            constante = 10000000 if datos.planchas_por_separado else 1
            
            # 7. Calcular precio final
            precio = precio_sin_constante / constante
            
            # Imprimir información detallada para depuración
            print("\n=== CÁLCULO DE PLANCHA ===")
            print(f"VALOR_MM: ${self.VALOR_MM_PLANCHA}/mm")
            print(f"B3 (Ancho): {datos.ancho} mm")
            print(f"C3 (GAP): {c3} mm")
            print(f"D3 (ancho + C3): {d3} mm")
            print(f"E3 (pistas): {datos.pistas}")
            print(f"Q3 (D3*E3+C3): {q3} mm")
            print(f"Gap fijo (R3): {self.GAP_FIJO} mm")
            print(f"S3 (Total): {s3} mm")
            print(f"Unidad montaje: {mm_unidad_montaje} mm")
            print(f"Avance fijo: {self.AVANCE_FIJO} mm")
            print(f"S4 (Unidad + Avance): {s4} mm")
            print(f"Número de tintas: {num_tintas}")
            print(f"Planchas por separado: {datos.planchas_por_separado}")
            print(f"Constante: {constante}")
            print(f"Precio sin constante: ${precio_sin_constante:.2f}")
            print(f"Precio final: ${precio:.2f}")
            
            # Verificar si el precio es razonable (validación)
            if precio_sin_constante > 0 and num_tintas > 0:
                precio_por_tinta = precio_sin_constante / num_tintas
                print(f"Precio por tinta: ${precio_por_tinta:.2f}")
                
                if precio_por_tinta < 10000 or precio_por_tinta > 1000000:
                    print(f"ADVERTENCIA: El precio por tinta parece inusual: ${precio_por_tinta:.2f}")
            
            # Preparar detalles para el retorno
            detalles = {
                'valor_mm': self.VALOR_MM_PLANCHA,
                'gap_fijo': self.GAP_FIJO,
                'avance_fijo': self.AVANCE_FIJO,
                'mm_unidad_montaje': mm_unidad_montaje,
                's3': s3,
                's4': s4,
                'q3': q3,
                'c3': c3,
                'd3': d3,
                'num_tintas': num_tintas,
                'es_manga': es_manga,
                'planchas_por_separado': datos.planchas_por_separado,
                'constante': constante,
                'precio_sin_constante': precio_sin_constante
            }
            
            return {
                'precio': precio,
                'detalles': detalles
            }
            
        except Exception as e:
            print(f"Error en cálculo de precio de plancha: {str(e)}")
            return {
                'precio': 0,
                'error': str(e),
                'detalles': None
            }

    def calcular_valor_troquel(self, datos: DatosLitografia, repeticiones: int, 
                            valor_mm: float = 100, troquel_existe: bool = False, 
                            tipo_grafado_id: Optional[int] = None, 
                            es_manga: bool = False) -> Dict:
        """
        Calcula el valor del troquel según el tipo de producto y grafado ID.
        Para mangas:
        - Si tipo_grafado_id es 4 (Horizontal Total + Vertical), factor_division = 1
        - Para otros tipos de grafado, factor_division = 2
        Para etiquetas:
        - Si troquel_existe = True, factor_division = 2
        - Si troquel_existe = False, factor_division = 1
        """
        try:
            # Constantes
            FACTOR_BASE = 25 * 5000  # 125,000
            VALOR_MINIMO = 700000
            
            # Debug inicial
            print("\n=== INICIO CÁLCULO TROQUEL ===")
            print(f"Tipo grafado ID recibido: {tipo_grafado_id}")
            print(f"Es manga: {es_manga}")
            print(f"Ancho: {datos.ancho}, Avance: {datos.avance}, Pistas: {datos.pistas}")
            print(f"Repeticiones: {repeticiones}, Valor_mm: {valor_mm}")
            
            # Calcular valor base
            perimetro = (datos.ancho + datos.avance) * 2
            valor_base = perimetro * datos.pistas * repeticiones * valor_mm
            valor_calculado = max(VALOR_MINIMO, valor_base)
            
            # Determinar si es manga y el factor de división
            if es_manga:
                # Lógica específica para mangas usando ID
                # Si tipo_grafado_id es 4 (Horizontal Total + Vertical), factor_division = 1
                # Para otros tipos de grafado, factor_division = 2
                factor_division = 1 if tipo_grafado_id == 4 else 2
                print(f"ES MANGA - Tipo grafado ID: {tipo_grafado_id}")
                print(f"Factor división seleccionado: {factor_division}")
            else:
                # Lógica para etiquetas
                factor_division = 2 if troquel_existe else 1
                print("ES ETIQUETA")
                print(f"Troquel existe: {troquel_existe}")
                print(f"Factor división seleccionado: {factor_division}")
            
            # Calcular valor final
            valor_final = (FACTOR_BASE + valor_calculado) / factor_division
            
            # Asegurar que el valor final nunca sea cero
            if valor_final <= 0:
                print("ADVERTENCIA: Valor final <= 0, usando valor mínimo")
                valor_final = VALOR_MINIMO
            
            print(f"Perimetro: {perimetro:,.2f} mm")
            print(f"Valor base: ${valor_base:,.2f}")
            print(f"Valor calculado (max con mínimo): ${valor_calculado:,.2f}")
            print(f"FACTOR_BASE: ${FACTOR_BASE:,.2f}")
            print(f"Suma antes de división: ${(FACTOR_BASE + valor_calculado):,.2f}")
            print(f"Factor de división aplicado: {factor_division}")
            print(f"Valor final después de división: ${valor_final:,.2f}")
            
            return {
                'valor': valor_final,
                'detalles': {
                    'perimetro': perimetro,
                    'valor_base': valor_base,
                    'valor_minimo': VALOR_MINIMO,
                    'valor_calculado': valor_calculado,
                    'factor_base': FACTOR_BASE,
                    'factor_division': factor_division,
                    'es_manga': es_manga,
                    'tipo_grafado_id': tipo_grafado_id if es_manga else None,
                    'suma_antes_division': FACTOR_BASE + valor_calculado,
                    'valor_final': valor_final
                }
            }
        except Exception as e:
            print(f"ERROR en cálculo troquel: {str(e)}")
            # En caso de error, retornar el valor mínimo en lugar de None
            return {
                'error': str(e),
                'valor': VALOR_MINIMO,
                'detalles': {
                    'error': str(e),
                    'valor_minimo_usado': VALOR_MINIMO
                }
            }

    def calcular_area_etiqueta(self, datos: DatosLitografia, num_tintas: int, 
                              medida_montaje: float, repeticiones: int, es_manga: bool = False) -> Dict:
        """
        Calcula el área de la etiqueta basada en dimensiones y configuración.
        
        El cálculo del área depende del número de tintas:
        - Si num_tintas = 0: area = (Q3/E3) * (Q4/E4)
        - Si num_tintas > 0: area = (S3/E3) * (Q4/E4)
        
        Donde:
        - Q3 = Ancho total ajustado (calculado por _calcular_q3)
        - S3 = GAP_FIJO + Q3 (ancho total con gap fijo)
        - E3 = Número de pistas
        - Q4 = Medida de montaje en mm
        - E4 = Número de repeticiones
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            num_tintas: Número de tintas (colores)
            medida_montaje: Medida de montaje en mm (Q4)
            repeticiones: Número de repeticiones (E4)
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Dict con el área calculada y los valores intermedios utilizados
        """
        try:
            # 1. Definir parámetros comunes
            q4 = medida_montaje  # Medida de montaje
            e4 = repeticiones    # Número de repeticiones
            e3 = datos.pistas    # Número de pistas
            
            # 2. Calcular Q3 usando el método auxiliar
            q3_result = self._calcular_q3(num_tintas, datos.ancho, e3, es_manga)
            q3 = q3_result['q3']
            c3 = q3_result['c3']
            d3 = q3_result['d3']
            
            # 3. Calcular S3 = GAP_FIJO + Q3
            s3 = self.GAP_FIJO + q3
            
            # 4. Calcular ancho total para etiquetas (solo para información adicional)
            f3 = None
            f3_detalles = None
            if not es_manga:
                f3 = self.calcular_ancho_total(num_tintas, e3, datos.ancho)
                
                # Calcular detalles de f3 para depuración
                C3_f3 = 0 if e3 <= 1 else self.GAP
                D3_f3 = datos.ancho + C3_f3
                base_f3 = (e3 * D3_f3) - C3_f3
                incremento_f3 = 10 if num_tintas == 0 else 20
                f3_sin_redondeo = base_f3 + incremento_f3
                f3_redondeado = math.ceil(f3_sin_redondeo / 10) * 10
                
                f3_detalles = {
                    'c3_f3': C3_f3,
                    'd3_f3': D3_f3,
                    'base_f3': base_f3,
                    'incremento_f3': incremento_f3,
                    'f3_sin_redondeo': f3_sin_redondeo,
                    'f3_redondeado': f3_redondeado
                }
            
            # 5. Calcular área según fórmula basada en número de tintas
            if num_tintas == 0:
                area_ancho = q3/e3
                formula_usada = 'Q3/E3 * Q4/E4'
                calculo_detallado = f"({q3}/{e3}) * ({q4}/{e4})"
            else:
                area_ancho = s3/e3
                formula_usada = 'S3/E3 * Q4/E4'
                calculo_detallado = f"({s3}/{e3}) * ({q4}/{e4})"
                
                area_largo = q4/e4
                area = area_ancho * area_largo
            
            # 6. Preparar detalles del cálculo
            detalles = {
                'q3': q3,
                'c3': c3,
                'd3': d3,
                's3': s3,
                'q4': q4,
                'e3': e3,
                'e4': e4,
                'gap_fijo': self.GAP_FIJO,
                'formula_usada': formula_usada,
                'area_ancho': area_ancho,
                'area_largo': area_largo,
                'calculo_detallado': calculo_detallado,
                'es_manga': es_manga
            }
            
            # Agregar detalles específicos para etiquetas
            if not es_manga and f3 is not None:
                detalles.update({
                    'f3': f3,
                    'f3_detalles': f3_detalles
                })
            
            return {
                'area': area,
                'detalles': detalles
            }
        except Exception as e:
            print(f"Error en cálculo de área de etiqueta: {str(e)}")
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
            # Calcular valor por etiqueta
            valor_etiqueta = num_tintas * self.VALOR_MM2_TINTA * area_etiqueta
            
            return {
                'valor': valor_etiqueta,
                'detalles': {
                    'gramos_m2': self.GRAMOS_M2_TINTA,
                    'valor_mm2': self.VALOR_MM2_TINTA,
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
            
    def generar_reporte_completo(self, datos: DatosLitografia, num_tintas: int, es_manga: bool = False) -> Dict:
        """Genera un reporte completo con todos los cálculos"""
        try:
            # Inicializar resultado con valores por defecto
            resultado = {
                'ancho_total': self.calcular_ancho_total(num_tintas, datos.pistas, datos.ancho),
                'valor_tinta': 0  # Inicializar valor_tinta a 0 por defecto
            }
            
            # Cálculo de desperdicio
            resultado['desperdicio'] = self.calcular_desperdicio(datos, es_manga)
            
            # Obtener mejor opción de desperdicio
            mejor_opcion = self.obtener_mejor_opcion_desperdicio(datos, es_manga)
            
            if not mejor_opcion:
                return {
                    'error': 'No se encontró una opción válida de desperdicio',
                    'detalles': 'Revise los valores de ancho y avance'
                }
            
            # Cálculo de precio de plancha
            resultado['precio_plancha'] = self.calcular_precio_plancha(datos, num_tintas, es_manga)
            
            # Cálculo de valor de troquel
            if datos.incluye_troquel:
                resultado['valor_troquel'] = self.calcular_valor_troquel(
                    datos,
                    mejor_opcion.repeticiones,
                    troquel_existe=datos.troquel_existe,
                    es_manga=es_manga
                )
            
            # Cálculo de área de etiqueta
            calculo_area = self.calcular_area_etiqueta(
                datos, 
                num_tintas, 
                mejor_opcion.medida_mm, 
                mejor_opcion.repeticiones,
                es_manga
            )
            resultado['area_etiqueta'] = calculo_area
            resultado['unidad_montaje_sugerida'] = mejor_opcion.dientes
                
            # Calcular valor de tinta solo si hay tintas y el área se calculó correctamente
            if num_tintas > 0 and isinstance(calculo_area, dict) and 'area' in calculo_area and calculo_area['area'] is not None:
                try:
                    calculo_tinta = self.calcular_valor_tinta_etiqueta(
                        calculo_area['area'],
                        num_tintas
                    )
                    if isinstance(calculo_tinta, dict) and 'valor' in calculo_tinta and calculo_tinta['valor'] is not None:
                        resultado['valor_tinta'] = calculo_tinta['valor']
                    else:
                        print("Advertencia: El cálculo de tinta no devolvió un valor válido")
                except Exception as e:
                    print(f"Error al calcular valor de tinta: {str(e)}")
            else:
                print(f"No se calculó valor de tinta: num_tintas={num_tintas}, area_calculada={'Si' if isinstance(calculo_area, dict) and 'area' in calculo_area else 'No'}")
            
            return resultado
        except Exception as e:
            return {
                'error': str(e),
                'detalles': 'Error al generar el reporte completo',
                'valor_tinta': 0  # Asegurar que valor_tinta esté presente incluso en caso de error
            }

    def generar_debug_info(self, datos: DatosLitografia, num_tintas: int = 0, es_manga: bool = False) -> Dict:
        """
        Genera información detallada de depuración para comparar con Excel
        
        Args:
            datos: Objeto DatosLitografia con los datos de entrada
            num_tintas: Número de tintas
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Dict: Diccionario con todos los valores intermedios y finales para depuración
        """
        debug_info = {
            "entradas": {
                "ancho": datos.ancho,
                "avance": datos.avance,
                "pistas": datos.pistas,
                "num_tintas": num_tintas,
                "es_manga": es_manga,
                "gap": datos.gap,
                "gap_avance": datos.gap_avance,
                "planchas_por_separado": datos.planchas_por_separado,
                "incluye_troquel": datos.incluye_troquel,
                "troquel_existe": datos.troquel_existe
            },
            "calculos_intermedios": {},
            "resultados": {}
        }
        
        try:
            # 1. Ancho total
            ancho_total = self.calcular_ancho_total(num_tintas, datos.pistas, datos.ancho)
            debug_info["calculos_intermedios"]["ancho_total"] = ancho_total
            
            # 2. Desperdicio
            reporte_desperdicio = self.calcular_desperdicio(datos, es_manga)
            debug_info["calculos_intermedios"]["reporte_desperdicio"] = reporte_desperdicio
            
            # Extraer datos de la mejor opción de desperdicio
            if reporte_desperdicio.get("mejor_opcion"):
                mejor_opcion = reporte_desperdicio["mejor_opcion"]
                debug_info["calculos_intermedios"]["mejor_opcion"] = {
                    "dientes": mejor_opcion.get("dientes"),
                    "repeticiones": mejor_opcion.get("repeticiones"),
                    "medida_mm": mejor_opcion.get("medida_mm"),
                    "desperdicio": mejor_opcion.get("desperdicio")
                }
            
            # 3. Precio de plancha (con detalles extendidos)
            calculo_plancha = self.calcular_precio_plancha(datos, num_tintas, es_manga)
            debug_info["calculos_intermedios"]["calculo_plancha"] = calculo_plancha
            
            # Agregar detalles adicionales del cálculo de la plancha
            if calculo_plancha.get("detalles"):
                detalles = calculo_plancha["detalles"]
                debug_info["calculos_intermedios"]["plancha_desglose"] = {
                    "valor_mm": detalles.get("valor_mm"),
                    "gap_fijo": detalles.get("gap_fijo"),
                    "avance_fijo": detalles.get("avance_fijo"),
                    "ancho_total": detalles.get("ancho_total"),
                    "mm_unidad_montaje": detalles.get("mm_unidad_montaje"),
                    "s3": detalles.get("s3"),
                    "s4": detalles.get("s4"),
                    "formula": f"{detalles.get('valor_mm')} * {detalles.get('s3')} * {detalles.get('s4')} * {detalles.get('num_tintas')}",
                    "resultado": calculo_plancha.get("precio")
                }
            
            # 4. Área de etiqueta (factor crucial)
            area_etiqueta = None
            if reporte_desperdicio.get("mejor_opcion"):
                mejor_opcion = reporte_desperdicio["mejor_opcion"]
                calculo_area = self.calcular_area_etiqueta(
                    datos=datos, 
                    num_tintas=num_tintas,
                    medida_montaje=mejor_opcion.get("medida_mm"),
                    repeticiones=mejor_opcion.get("repeticiones"),
                    es_manga=es_manga
                )
                area_etiqueta = calculo_area.get("area")
                debug_info["calculos_intermedios"]["area_etiqueta"] = {
                    "valor": area_etiqueta,
                    "detalles": calculo_area.get("detalles")
                }
            
            # 5. Valor de tinta por etiqueta
            if area_etiqueta:
                calculo_tinta = self.calcular_valor_tinta_etiqueta(
                    area_etiqueta=area_etiqueta,
                    num_tintas=num_tintas
                )
                debug_info["calculos_intermedios"]["valor_tinta"] = {
                    "valor": calculo_tinta.get("valor"),
                    "detalles": calculo_tinta.get("detalles")
                }
            
            # 6. Valor de troquel
            if datos.incluye_troquel and reporte_desperdicio.get("mejor_opcion"):
                mejor_opcion = reporte_desperdicio["mejor_opcion"]
                calculo_troquel = self.calcular_valor_troquel(
                    datos=datos,
                    repeticiones=mejor_opcion.get("repeticiones"),
                    troquel_existe=datos.troquel_existe,
                    es_manga=es_manga
                )
                debug_info["calculos_intermedios"]["valor_troquel"] = {
                    "valor": calculo_troquel.get("valor"),
                    "detalles": calculo_troquel.get("detalles")
                }
            
            # 7. Comparación directa con valores del Excel
            debug_info["comparacion_excel"] = {
                "ancho": datos.ancho,
                "avance": datos.avance,
                "pistas": datos.pistas,
                "tintas": num_tintas,
                "area_etiqueta": area_etiqueta,
                "valor_plancha": calculo_plancha.get("precio"),
                "valor_plancha_por_tinta": calculo_plancha.get("precio") / num_tintas if num_tintas > 0 else 0,
                "desperdicio_mm": mejor_opcion.get("desperdicio") if reporte_desperdicio.get("mejor_opcion") else None,
                "dientes": mejor_opcion.get("dientes") if reporte_desperdicio.get("mejor_opcion") else None
            }
            
            return debug_info
            
        except Exception as e:
            debug_info["error"] = str(e)
            return debug_info

    def calcular_desperdicio_por_escala(self, datos: DatosLitografia, num_tintas: int, valor_material_mm2: float, escala: int, es_manga: bool = False) -> Dict:
        """
        Calcula el desperdicio por escala según la fórmula:
        
        Para mangas:
            desperdicio = S7 * S3 * O7
            donde:
            - S7 = mm por color (30000 * num_tintas)
            - S3 = R3 + Q3 (donde R3=50mm y Q3=D3*E3+C3)
            - O7 = precio por mm² del material
        
        Para etiquetas:
            desperdicio = (s3 * s7 * o7) + (10% * Papel/lam)
            donde:
            - s3 = mismo valor calculado en planchas (gap_fijo + ancho_total)
            - s7 = mm por color (30000 * num_tintas)
            - o7 = precio por mm² del material
            - Papel/lam = área_etiqueta * valor_material_mm2 * escala
        """
        try:
            # 1. Obtener S3 del cálculo de planchas
            calculo_plancha = self.calcular_precio_plancha(datos, num_tintas, es_manga)
            
            # Verificar si calculo_plancha tiene la estructura esperada
            if isinstance(calculo_plancha, dict) and ('error' in calculo_plancha or 'detalles' not in calculo_plancha):
                return {
                    'error': 'No se pudo calcular el precio de plancha correctamente',
                    'valor': 0,
                    'detalles': {
                        's3': 0,
                        's7': 0,
                        'o7': 0,
                        'desperdicio_total': 0,
                        'es_manga': es_manga
                    }
                }
            
            s3 = calculo_plancha['detalles']['s3']
            
            # 2. Calcular S7 (mm por color)
            s7 = 30000 * num_tintas if num_tintas > 0 else 0
            
            # 3. O7 es el precio por mm² del material
            o7 = valor_material_mm2 / 1000000  # Convertir a millones
            
            if es_manga:
                # Para mangas, el desperdicio es simplemente S7 * S3 * O7
                desperdicio_total = s7 * s3 * o7
            else:
                # 4. Primera parte: (s3 * s7 * o7)
                primera_parte = s3 * s7 * o7
                
                # 5. Calcular papel/lam directamente sin usar CalculadoraCostosEscala
                mejor_opcion = self.obtener_mejor_opcion_desperdicio(datos, es_manga)
                calculo_area = self.calcular_area_etiqueta(
                    datos, 
                    num_tintas, 
                    mejor_opcion.medida_mm, 
                    mejor_opcion.repeticiones,
                    es_manga
                )
                area_etiqueta = calculo_area['area']
                papel_lam = area_etiqueta * valor_material_mm2 * escala
                
                # 6. Segunda parte: 10% del papel/lam
                segunda_parte = 0.1 * papel_lam
                
                # 7. Desperdicio total para etiquetas
                desperdicio_total = primera_parte + segunda_parte
            
            # Debug info consolidado
            print(f"\n=== CÁLCULO DE DESPERDICIO ({('MANGA' if es_manga else 'ETIQUETA')}, Escala {escala}) ===")
            print(f"1. Fórmula: {'S7 * S3 * O7' if es_manga else '(s3 * s7 * o7) + (10% * Papel/lam)'}")
            print(f"2. Valores:")
            print(f"   - s3 (Gap + {'Q3' if es_manga else 'Ancho Total'}): {s3} mm")
            print(f"   - s7 (mm por color): {s7} mm")
            print(f"   - o7 (precio material): ${o7:.8f}/mm²")
            if es_manga:
                print(f"   - Desperdicio total (S7 * S3 * O7): ${desperdicio_total:.2f}")
            else:
                print(f"   - Primera parte (s3 * s7 * o7): ${primera_parte:.2f}")
                print(f"   - Papel/lam: ${papel_lam:.2f}")
                print(f"   - Segunda parte (10% * Papel/lam): ${segunda_parte:.2f}")
                print(f"   - Desperdicio total: ${desperdicio_total:.2f}")
            
            detalles = {
                's3': s3,
                's7': s7,
                'o7': o7,
                'desperdicio_total': desperdicio_total,
                'es_manga': es_manga
            }
            
            if not es_manga:
                detalles.update({
                    'primera_parte': primera_parte,
                    'papel_lam': papel_lam,
                    'segunda_parte': segunda_parte,
                    'area_etiqueta': area_etiqueta
                })
            
            return {
                'valor': desperdicio_total,
                'detalles': detalles
            }
        except Exception as e:
            print(f"Error al calcular desperdicio: {str(e)}")
            return {
                'error': str(e),
                'valor': 0,
                'detalles': {
                    's3': 0,
                    's7': 0,
                    'o7': 0,
                    'desperdicio_total': 0,
                    'es_manga': es_manga
                }
            }

    def calcular_desperdicio_escala_completo(self, datos: DatosLitografia, num_tintas: int, valor_material_mm2: float = 1800.0, es_manga: bool = False) -> Dict:
        """
        Calcula el desperdicio para diferentes escalas de producción
        
        Args:
            datos: Objeto DatosLitografia
            num_tintas: Número de tintas
            valor_material_mm2: Precio por mm² del material (default: 1800.0)
            es_manga: True si es manga, False si es etiqueta
        
        Returns:
            Dict con los valores de desperdicio para diferentes escalas
        """
        escalas = [1000, 2000, 3000, 5000]
        resultados_desperdicio = {}
        
        # Obtener S3 una sola vez para todas las escalas
        calculo_plancha = self.calcular_precio_plancha(datos, num_tintas, es_manga)
        
        # Verificar si calculo_plancha tiene la estructura esperada
        if isinstance(calculo_plancha, dict) and ('error' in calculo_plancha or 'detalles' not in calculo_plancha):
            return {'error': 'No se pudo calcular el precio de plancha correctamente'}
        
        s3 = calculo_plancha['detalles']['s3']
        
        print("\n=== RESUMEN DE DESPERDICIOS POR ESCALA ===")
        print(f"Tipo: {'MANGA' if es_manga else 'ETIQUETA'}")
        print(f"S3 (Gap + {'Q3' if es_manga else 'Ancho Total'}): {s3} mm")
        print(f"Número de tintas: {num_tintas}")
        print(f"Valor material: ${valor_material_mm2}/mm²\n")
        
        for escala in escalas:
            resultado = self.calcular_desperdicio_por_escala(datos, num_tintas, valor_material_mm2, escala, es_manga)
            resultados_desperdicio[escala] = resultado
        
        return resultados_desperdicio

    def obtener_input_numerico(self, mensaje: str, minimo: float = 0.1) -> float:
        """Obtiene un input numérico con validación"""
        while True:
            try:
                valor = float(input(mensaje))
                if valor < minimo:
                    print(f"El valor debe ser mayor a {minimo}")
                    continue
                return valor
            except ValueError:
                print("Por favor ingrese un número válido")

    def _print_info_global(self, num_tintas: int, ancho_total: float, valor_material: float):
        print("\n=== INFORMACIÓN GLOBAL ===")
        print(f"Número de tintas: {num_tintas}")
        print(f"Ancho total: {ancho_total:.2f} mm")  # Usar el ancho_total pasado como parámetro
        print(f"Gap fijo: {self.GAP_FIJO} mm")
        print(f"Valor material: ${valor_material:f}/mm²")

    def calcular_precio_troquel(self, datos: DatosLitografia) -> Dict:
        """
        Calcula el precio del troquel según la fórmula:
        Precio troquel = (ancho + avance) * 1800
        """
        try:
            precio_troquel = (datos.ancho + datos.avance) * 1800
            
            return {
                'valor': precio_troquel,
                'detalles': {
                    'ancho': datos.ancho,
                    'avance': datos.avance
                }
            }
        except Exception as e:
            return {'error': str(e)}

    def _calcular_q3(self, num_tintas: int, ancho: float, pistas: int, es_manga: bool = False) -> Dict:
        """
        Método auxiliar para calcular Q3, C3 y D3 para cálculos de área y precio.
        Este método es un wrapper del método de la clase base para mantener compatibilidad.
        """
        return self.calcular_q3(ancho, pistas, es_manga)
