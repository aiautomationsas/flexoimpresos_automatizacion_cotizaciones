from dataclasses import dataclass
from typing import Optional, Dict, List
import math
from calculadora_desperdicios import CalculadoraDesperdicio, OpcionDesperdicio
from calculadora_costos_escala import CalculadoraCostosEscala

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
        self._calculadora_desperdicios = None  # Inicializar como None

    @property
    def calculadora_desperdicios(self) -> CalculadoraDesperdicio:
        """Devuelve la calculadora de desperdicios actual"""
        if self._calculadora_desperdicios is None:
            self._calculadora_desperdicios = CalculadoraDesperdicio(
                ancho_maquina=self.ancho_maximo,
                gap_mm=2.6  # Este gap solo se usa para etiquetas
            )
        return self._calculadora_desperdicios

    def _get_calculadora_desperdicios(self, es_manga: bool = False) -> CalculadoraDesperdicio:
        """
        Obtiene una instancia de CalculadoraDesperdicio configurada según el tipo
        """
        return CalculadoraDesperdicio(
            ancho_maquina=self.ancho_maximo,
            gap_mm=2.6,  # Este gap solo se usa para etiquetas
            es_manga=es_manga
        )

    def calcular_ancho_total(self, num_tintas: int, pistas: int, ancho_usuario: float) -> float:
        """
        Calcula el ancho total según la fórmula:
        F3 = REDONDEAR.MAS(SI(B2=0;((E3*D3-C3)+10);((E3*D3-C3)+20));-1)
        
        Donde:
        - B2 = número de tintas
        - E3 = número de pistas
        - D3 = B3 + C3 (ancho_usuario + 3)
        - C3 = 3 (constante para gap)
        """
        # Constantes
        C3 = 3  # Gap constante
        
        # 1. Calcular D3 = ancho_usuario + C3
        D3 = ancho_usuario + C3
        
        # 2. Calcular base = E3 * D3 - C3
        base = (pistas * D3) - C3
        
        # 3. Agregar incremento según tintas
        incremento = 10 if num_tintas == 0 else 20
        ancho_total = base + incremento
        
        # 4. Redondear hacia arriba al siguiente múltiplo de 10
        ancho_total = math.ceil(ancho_total / 10) * 10
        
        return ancho_total

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
        Obtiene la mejor opción de desperdicio según el tipo de impresión
        
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
        Calcula el precio de la plancha según la fórmula:
        precio = (valor_mm * (ancho_total + gap_fijo) * (mm_unidad_montaje + avance_fijo) * num_tintas) / constante
        
        Para mangas:
        S3 = R3 + Q3
        Q3 = D3 * E3 + C3
        C3 = 0 (para mangas)
        D3 = B3 + C3 (donde B3 es el ancho)
        E3 = número de pistas
        
        Donde:
        - valor_mm = $1.5/mm
        - gap_fijo = 50 mm para mangas, 40 mm para etiquetas
        - avance_fijo = 30 mm
        - constante = número muy grande si planchas por separado (resultando en precio = 0), 1 si no
        """
        # Constantes
        VALOR_MM = 1.5  # Nuevo valor: $1.5/mm
        GAP_FIJO = 50 if es_manga else 40  # GAP fijo en mm según tipo (R3)
        AVANCE_FIJO = 30  # R4: Avance fijo en mm
        
        try:
            if es_manga:
                # Cálculo especial de S3 para mangas
                C3 = 0  # GAP para mangas es 0
                B3 = datos.ancho  # B3 es el ancho, no el número de tintas
                D3 = B3 + C3  # D3 = ancho + GAP_MANGA
                E3 = datos.pistas
                Q3 = D3 * E3 + C3  # Q3 = (ancho + GAP_MANGA) * pistas + GAP_MANGA
                s3 = GAP_FIJO + Q3  # R3 + Q3
            else:
                # Calcular ancho total (F3) para etiquetas
                ancho_total = self.calcular_ancho_total(num_tintas, datos.pistas, datos.ancho)
                s3 = GAP_FIJO + ancho_total
            
            # Obtener mm de la unidad de montaje (Q4)
            mejor_opcion = self.obtener_mejor_opcion_desperdicio(datos, es_manga)
            if not mejor_opcion:
                raise ValueError("No se pudo determinar la unidad de montaje")
            mm_unidad_montaje = mejor_opcion.medida_mm
            
            # Calcular S4 = Q4 + R4 (mm_unidad_montaje + avance_fijo)
            s4 = mm_unidad_montaje + AVANCE_FIJO
            
            # Calcular precio sin constante (precio real)
            precio_sin_constante = VALOR_MM * s3 * s4 * num_tintas
            
            # Determinar constante según si las planchas son por separado
            constante = 1000000 if datos.incluye_planchas else 1
            
            # Calcular precio final
            precio = precio_sin_constante / constante
            
            # Imprimir información detallada en la consola
            print("\n=== CÁLCULO DE PLANCHA ===")
            print(f"VALOR_MM: ${VALOR_MM}/mm")
            if es_manga:
                print(f"B3 (Ancho): {B3} mm")
                print(f"C3 (GAP mangas): {C3} mm")
                print(f"D3 (ancho + C3): {D3} mm")
                print(f"E3 (pistas): {E3}")
                print(f"Q3 (D3*E3+C3): {Q3} mm")
            else:
                print(f"Ancho total: {ancho_total} mm")
            print(f"Gap fijo (R3): {GAP_FIJO} mm")
            print(f"S3 (Total): {s3} mm")
            print(f"Unidad montaje: {mm_unidad_montaje} mm")
            print(f"Avance fijo: {AVANCE_FIJO} mm")
            print(f"S4 (Unidad + Avance): {s4} mm")
            print(f"Número de tintas: {num_tintas}")
            print(f"Planchas por separado: {datos.incluye_planchas}")
            print(f"Constante: {constante}")
            print(f"Precio sin constante: ${precio_sin_constante:.2f}")
            print(f"Precio final: ${precio:.2f}")
            
            detalles = {
                'valor_mm': VALOR_MM,
                'gap_fijo': GAP_FIJO,
                'avance_fijo': AVANCE_FIJO,
                'mm_unidad_montaje': mm_unidad_montaje,
                's3': s3,
                's4': s4,
                'num_tintas': num_tintas,
                'es_manga': es_manga,
                'incluye_planchas': datos.incluye_planchas,
                'constante': constante,
                'precio_sin_constante': precio_sin_constante
            }
            
            if es_manga:
                detalles.update({
                    'b3': B3,
                    'c3': C3,
                    'd3': D3,
                    'e3': E3,
                    'q3': Q3
                })
            else:
                detalles['ancho_total'] = ancho_total
            
            return {
                'precio': precio,
                'detalles': detalles
            }
        except Exception as e:
            print(f"Error en cálculo de plancha: {str(e)}")
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
        - factor = 2 si el troquel YA EXISTE
        - factor = 1 si hay que FABRICAR el troquel
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            repeticiones: Número de repeticiones
            valor_mm: Valor por mm del troquel (default: 100)
            troquel_existe: True si ya tienen el troquel, False si hay que hacer uno nuevo
            
        Returns:
            Dict con el valor calculado y los valores intermedios
        """
        try:
            # Constantes
            FACTOR_EXISTENTE = 2  # Si ya tienen el troquel (divide por 2)
            FACTOR_NUEVO = 1      # Si hay que hacer un troquel nuevo (divide por 1, osea no divide)
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
                              medida_montaje: float, repeticiones: int, es_manga: bool = False) -> Dict:
        """
        Calcula el área de la etiqueta según la fórmula:
        Si num_tintas = 0:
            area = (Q3/E3) * (Q4/E4)
        Si no:
            area = (S3/E3) * (Q4/E4)
            
        Para mangas:
        S3 = R3 + Q3
        Q3 = D3 * E3 + C3
        C3 = 0 (para mangas)
        D3 = B3 + C3 (donde B3 es el ancho)
        E3 = número de pistas
        
        Para etiquetas:
        Q3 = D3*E3 + C3
        D3 = ancho + gap (3mm)
        E3 = número de pistas
        C3 = gap (3mm)
        Q4 = medida de montaje
        E4 = repeticiones (del cálculo de desperdicio)
        S3 = R3 + F3
        F3 = ancho total
        R3 = gap fijo (40mm para etiquetas, 50mm para mangas)
        
        Args:
            datos: Objeto DatosLitografia con los datos necesarios
            num_tintas: Número de tintas
            medida_montaje: Medida de montaje en mm
            repeticiones: Número de repeticiones
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Dict con el área calculada y los valores intermedios
        """
        try:
            # Q4 es la medida de montaje y E4 las repeticiones (común para ambos)
            q4 = medida_montaje
            e4 = repeticiones
            
            if es_manga:
                # Cálculo especial de S3 para mangas
                C3 = 0  # GAP para mangas es 0
                B3 = datos.ancho  # B3 es el ancho
                D3 = B3 + C3  # D3 = ancho + GAP_MANGA
                E3 = datos.pistas
                Q3 = D3 * E3 + C3  # Q3 = (ancho + GAP_MANGA) * pistas + GAP_MANGA
                GAP_FIJO = 50  # R3 para mangas
                s3 = GAP_FIJO + Q3  # R3 + Q3
            else:
                # Constantes para etiquetas
                GAP = 3  # mm para D3 y C3
                GAP_FIJO = 40  # R3 para etiquetas
                
                # Cálculos para Q3
                d3 = datos.ancho + GAP
                e3 = datos.pistas
                c3 = GAP
                q3 = (d3 * e3) + c3
                
                # Cálculos para S3
                f3 = self.calcular_ancho_total(num_tintas, datos.pistas, datos.ancho)
                s3 = GAP_FIJO + f3
            
            # Variables comunes para el cálculo final
            e3 = datos.pistas  # E3 es el número de pistas en ambos casos
            q3 = Q3 if es_manga else q3  # Usar Q3 de manga o etiqueta según corresponda
            
            # Calcular área según fórmula
            if num_tintas == 0:
                area_ancho = q3/e3
                area_largo = q4/e4
                area = area_ancho * area_largo
            else:
                area_ancho = s3/e3
                area_largo = q4/e4
                area = area_ancho * area_largo
            
            # Preparar detalles según tipo
            detalles = {
                'q4': q4,
                'e4': e4,
                'e3': e3,
                's3': s3,
                'formula_usada': 'Q3/E3 * Q4/E4' if num_tintas == 0 else 'S3/E3 * Q4/E4',
                'area_ancho': area_ancho,
                'area_largo': area_largo,
                'calculo_detallado': f"({q3 if num_tintas == 0 else s3}/{e3}) * ({q4}/{e4})"
            }
            
            if es_manga:
                detalles.update({
                    'b3': B3,
                    'c3': C3,
                    'd3': D3,
                    'q3': Q3,
                    'gap_fijo': GAP_FIJO
                })
            else:
                detalles.update({
                    'q3': q3,
                    'd3': d3,
                    'c3': c3,
                    'f3': f3,
                    'gap_fijo': GAP_FIJO
                })
            
            return {
                'area': area,
                'detalles': detalles
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
            
    def generar_reporte_completo(self, datos: DatosLitografia, num_tintas: int, es_manga: bool = False) -> Dict:
        """Genera un reporte completo con todos los cálculos"""
        try:
            # Calcular ancho total primero (una sola vez)
            ancho_total = self.calcular_ancho_total(num_tintas, datos.pistas, datos.ancho)
            
            # Inicializar el resultado
            resultado = {
                'ancho_total': ancho_total,
                'desperdicio': self.calcular_desperdicio(datos, es_manga)
            }
            
            # Obtener mejor opción primero ya que la necesitamos para varios cálculos
            mejor_opcion = self.obtener_mejor_opcion_desperdicio(datos, es_manga)
            
            # Calcular precio de plancha siempre (independientemente de si se incluye o no)
            resultado['precio_plancha'] = self.calcular_precio_plancha(datos, num_tintas, es_manga)
            
            # Agregar cálculos de troquel si corresponde y tenemos mejor opción
            if datos.incluye_troquel and mejor_opcion:
                calculo_troquel = self.calcular_valor_troquel(
                    datos=datos,
                    repeticiones=mejor_opcion.repeticiones,  # Usar repeticiones de la mejor opción
                    troquel_existe=datos.troquel_existe
                )
                resultado['valor_troquel'] = calculo_troquel['valor']
            
            # Cálculo de área de etiqueta
            if mejor_opcion:
                resultado['area_etiqueta'] = self.calcular_area_etiqueta(
                    datos, 
                    num_tintas, 
                    mejor_opcion.medida_mm, 
                    mejor_opcion.repeticiones,
                    es_manga
                )['area']
                resultado['unidad_montaje_sugerida'] = mejor_opcion.dientes
                
            # Calcular valor de tinta
            if num_tintas > 0:
                resultado['valor_tinta'] = self.calcular_valor_tinta_etiqueta(
                    resultado['area_etiqueta'],
                    num_tintas
                )['valor']
            
            return resultado
        except Exception as e:
            return {'error': str(e)}

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
                "incluye_planchas": datos.incluye_planchas,
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
                    troquel_existe=datos.troquel_existe
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
                
                # 5. Calcular papel/lam usando CalculadoraCostosEscala
                calc_costos = CalculadoraCostosEscala()
                mejor_opcion = self.obtener_mejor_opcion_desperdicio(datos, es_manga)
                calculo_area = self.calcular_area_etiqueta(
                    datos, 
                    num_tintas, 
                    mejor_opcion.medida_mm, 
                    mejor_opcion.repeticiones,
                    es_manga
                )
                area_etiqueta = calculo_area['area']
                papel_lam = calc_costos.calcular_papel_lam(escala, area_etiqueta, valor_material_mm2, 0)
                
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
        print(f"Gap fijo: {self.G4} mm")
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
