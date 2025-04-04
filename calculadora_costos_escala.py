from dataclasses import dataclass
from typing import List, Dict, Tuple
import math
import pandas as pd
from calculadora_base import CalculadoraBase
from constants import (
    VELOCIDAD_MAQUINA_NORMAL, MO_MONTAJE, MO_IMPRESION, MO_TROQUELADO,
    VALOR_GR_TINTA, RENTABILIDAD_ETIQUETAS, DESPERDICIO_ETIQUETAS,
    ANCHO_MAXIMO_MAQUINA, GAP_PISTAS_ETIQUETAS, MM_COLOR, GAP_FIJO,
    INCREMENTO_ANCHO_SIN_TINTAS, INCREMENTO_ANCHO_TINTAS, 
    GAP_AVANCE_ETIQUETAS, GAP_AVANCE_MANGAS, MO_SELLADO, MO_CORTE,
    FACTOR_TINTA_AREA, CANTIDAD_TINTA_ESTANDAR, INCREMENTO_ANCHO_MANGAS
)

@dataclass
class DatosEscala:
    """
    Clase para almacenar los datos necesarios para los cálculos por escala.
    
    Esta clase encapsula todos los parámetros requeridos para realizar cálculos
    de costos por escala, incluyendo dimensiones, configuración de producción,
    y valores fijos para cálculos.
    """
    escalas: List[int]
    pistas: int
    ancho: float  # Ancho base para calcular ancho_total
    avance: float  # Avance en mm
    avance_total: float  # Avance total incluyendo gaps
    desperdicio: float
    velocidad_maquina: float = VELOCIDAD_MAQUINA_NORMAL  # Valor fijo desde constants.py
    mo_montaje: float = MO_MONTAJE  # Valor fijo desde constants.py
    mo_impresion: float = MO_IMPRESION  # Valor fijo desde constants.py
    mo_troquelado: float = MO_TROQUELADO  # Valor fijo desde constants.py
    valor_gr_tinta: float = VALOR_GR_TINTA  # Valor fijo desde constants.py
    rentabilidad: float = RENTABILIDAD_ETIQUETAS  # Valor por defecto para etiquetas desde constants.py
    area_etiqueta: float = 0.0  # Se calcula o se recibe
    porcentaje_desperdicio: float = DESPERDICIO_ETIQUETAS  # Porcentaje de desperdicio por defecto desde constants.py
    valor_metro: float = 0.0  # Valor del metro de material

    def set_area_etiqueta(self, area: float):
        """Set the area of the label."""
        self.area_etiqueta = area

class CalculadoraCostosEscala(CalculadoraBase):
    """
    Clase para calcular los costos por escala.
    
    Esta clase proporciona métodos para calcular costos de producción
    basados en diferentes escalas, incluyendo costos de materiales,
    mano de obra, desperdicios, y otros factores relevantes.
    """
    
    def __init__(self, ancho_maximo: float = ANCHO_MAXIMO_MAQUINA):
        """
        Inicializa la calculadora de costos por escala.
        
        Args:
            ancho_maximo: Ancho máximo de la máquina en mm
        """
        super().__init__()
        self.ANCHO_MAXIMO = ancho_maximo
        self.GAP = GAP_PISTAS_ETIQUETAS  # GAP entre pistas desde constants.py
        
        # Constantes para cálculos
        self.C3 = self.GAP  # GAP fijo para cálculos
        self.MM_COLOR = MM_COLOR  # MM de color para cálculo de desperdicio desde constants.py
        self.GAP_FIJO = GAP_FIJO  # R3 es 50 tanto para mangas como etiquetas desde constants.py
        
    def _calcular_q3(self, num_tintas: int, ancho: float, pistas: int, es_manga: bool = False) -> Dict:
        """
        Método auxiliar para calcular Q3, C3 y D3 para cálculos de área y precio.
        Este método es un wrapper del método de la clase base para mantener compatibilidad.
        """
        return self.calcular_q3(ancho, pistas, es_manga)
        
    def calcular_ancho_total(self, num_tintas: int, pistas: int, ancho: float) -> Tuple[float, str]:
        """
        Calcula el ancho total según la fórmula:
        ROUNDUP(IF(B2=0, ((E3*D3-C3)+10), ((E3*D3-C3)+20)), -1)
        donde:
        - B2 = número de tintas
        - E3 = pistas
        - C3 = valor fijo de 3
        - D3 = ancho + C3
        
        Returns:
            Tuple[float, str]: (ancho_total, mensaje_recomendacion)
            El mensaje_recomendacion será None si no hay problemas
        """
        d3 = ancho + self.C3
        base = pistas * d3 - self.C3
        incremento = INCREMENTO_ANCHO_SIN_TINTAS if num_tintas == 0 else INCREMENTO_ANCHO_TINTAS
        resultado = base + incremento
        # Redondear hacia arriba al siguiente múltiplo de 10
        ancho_redondeado = math.ceil(resultado / 10) * 10
        
        mensaje = None
        if ancho_redondeado > self.ANCHO_MAXIMO:
            # Calcular pistas recomendadas
            ancho_con_gap = ancho + self.C3
            pistas_recomendadas = math.floor((self.ANCHO_MAXIMO - incremento + self.C3) / ancho_con_gap)
            
            if ancho > self.ANCHO_MAXIMO:
                mensaje = f"ERROR: El ancho base ({ancho}mm) excede el máximo permitido ({self.ANCHO_MAXIMO}mm)"
            else:
                mensaje = f"ADVERTENCIA: El ancho total calculado ({ancho_redondeado}mm) excede el máximo permitido ({self.ANCHO_MAXIMO}mm). Se recomienda usar {pistas_recomendadas} pistas o menos."
            
        return ancho_redondeado, mensaje
        
    def calcular_metros(self, escala: int, datos: DatosEscala, es_manga: bool = False) -> float:
        """
        Calcula los metros según la fórmula: (Escala / Pistas) * ((Avance_total + Desperdicio_unidad) / 1000)
        donde:
        - Avance_total = Avance + GAP (2.6 para etiquetas, 0 para mangas)
        - Desperdicio_unidad = desperdicio por los dientes del troquel
        """
        # GAP solo para etiquetas
        gap = GAP_AVANCE_ETIQUETAS if not es_manga else GAP_AVANCE_MANGAS
        
        # Avance total incluye el GAP
        avance_total = datos.avance + gap
        
        # Desperdicio por unidad (dientes del troquel)
        desperdicio_unidad = datos.desperdicio
        
        # Cálculo paso a paso
        factor_escala = escala / datos.pistas
        factor_avance = (avance_total + desperdicio_unidad) / 1000
        metros = factor_escala * factor_avance
        
        return metros
        
    def calcular_tiempo_horas(self, metros: float, datos: DatosEscala) -> float:
        """Calcula el tiempo en horas según la fórmula: metros / velocidad_maquina / 60"""
        tiempo = metros / datos.velocidad_maquina / 60
        
        # Debug detallado
        debug_info = f"""
=== DEBUG CÁLCULO DE TIEMPO ===
Inputs:
- Metros: {metros:.2f}
- Velocidad máquina: {datos.velocidad_maquina:.2f} m/min

Cálculo:
1. Tiempo (horas) = {metros:.2f} / {datos.velocidad_maquina:.2f} / 60 = {tiempo:.2f}
"""
        print(debug_info)
        
        return tiempo
        
    def calcular_montaje(self, num_tintas: int, datos: DatosEscala) -> float:
        """Calcula el montaje según la fórmula: Tintas * MO Montaje"""
        return num_tintas * datos.mo_montaje
        
    def calcular_mo_y_maq(self, tiempo_horas: float, num_tintas: int, datos: DatosEscala, es_manga: bool = False) -> float:
        """
        Calcula MO y Maq según la fórmula:

        Para etiquetas:
        if Tintas > 0:
            if t(h) < 1:
                MO_y_Maq = MO_Impresion
            else:
                MO_y_Maq = MO_Impresion * t(h)
        else:
            if t_h < 1:
                MO_y_Maq = MO_Troquelado
            else:
                MO_y_Maq = MO_Troquelado * t(h)
        """
        if not es_manga:
            # Cálculo para etiquetas
            base_mo = datos.mo_impresion if num_tintas > 0 else datos.mo_troquelado
            return base_mo if tiempo_horas < 1 else base_mo * tiempo_horas
        
        # Cálculo para mangas (mantener lógica existente)
        base_mo = datos.mo_impresion if num_tintas > 0 else datos.mo_troquelado
        total_mo = base_mo + MO_SELLADO + MO_CORTE
        return total_mo if tiempo_horas < 1 else total_mo * tiempo_horas

    def calcular_tintas(self, escala: int, num_tintas: int, area_etiqueta: float, datos: DatosEscala) -> float:
        """
        Calcula el valor de tintas según la fórmula:
        (R11 * escala) + (100 * num_tintas * valor_gr_tinta)
        
        Donde R11 es el costo por etiqueta calculado como:
        R11 = 0.00000800 * num_tintas * area_etiqueta
        """
        # Prevenir errores con área de etiqueta no definida o cero
        if area_etiqueta is None or area_etiqueta <= 0:
            print(f"\n--- ERROR EN CÁLCULO DE TINTAS ---")
            print(f"Área de etiqueta no válida: {area_etiqueta}")
            return 0
            
        # Calcular R11
        R11 = FACTOR_TINTA_AREA * num_tintas * area_etiqueta
        
        # Costo que varía con la escala
        costo_variable = R11 * escala
        
        # Costo fijo por número de tintas
        costo_fijo = CANTIDAD_TINTA_ESTANDAR * num_tintas * datos.valor_gr_tinta
        
        print(f"\n--- Verificación del Cálculo de Tintas ---")
        print(f"Área de etiqueta: {area_etiqueta:.2f} mm²")
        print(f"Factor tinta área: {FACTOR_TINTA_AREA:.8f}")
        print(f"Número de tintas: {num_tintas}")
        print(f"R11 (costo por etiqueta): ${R11:.8f}")
        print(f"Escala: {escala}")
        print(f"Costo variable (R11 * escala): ${costo_variable:.2f}")
        print(f"Valor gr tinta: ${datos.valor_gr_tinta:.2f}")
        print(f"Costo fijo ({CANTIDAD_TINTA_ESTANDAR} * {num_tintas} * {datos.valor_gr_tinta}): ${costo_fijo:.2f}")
        print(f"Costo total: ${costo_variable + costo_fijo:.2f}")
        
        return costo_variable + costo_fijo
        
    def calcular_papel_lam(self, escala: int, area_etiqueta: float, 
                           valor_material: float, valor_acabado: float) -> float:
        """
        Calcula Papel/lam según la fórmula:
        escala * ((area_etiqueta * Valor material / 1000000) + (area_etiqueta * Valor acabado / 1000000))
        
        Args:
            escala: Cantidad de unidades
            area_etiqueta: Área de la etiqueta en mm²
            valor_material: Valor del material por mm²
            valor_acabado: Valor del acabado por mm²
        """
        # Prevenir errores con área de etiqueta no definida o cero
        if area_etiqueta is None or area_etiqueta <= 0:
            print(f"\n--- ERROR EN CÁLCULO DE PAPEL/LAM ---")
            print(f"Área de etiqueta no válida: {area_etiqueta}")
            return 0
            
        # Prevenir valores negativos o nulos en los valores de material y acabado
        if valor_material <= 0:
            print(f"\n--- ADVERTENCIA EN CÁLCULO DE PAPEL/LAM ---")
            print(f"Valor material no válido: {valor_material}")
        
        # Cálculo detallado
        costo_material = (area_etiqueta * valor_material) / 1000000
        costo_acabado = (area_etiqueta * valor_acabado) / 1000000
        
        # Imprimir detalles para depuración
        print("\n=== CÁLCULO PAPEL/LAM DETALLADO ===")
        print(f"Área etiqueta: {area_etiqueta:.4f} mm²")
        print(f"Valor material: ${valor_material:.6f}/mm²")
        print(f"Valor acabado: ${valor_acabado:.6f}/mm²")
        print(f"Costo material por unidad: ${costo_material:.6f}")
        print(f"Costo acabado por unidad: ${costo_acabado:.6f}")
        print(f"Escala: {escala}")
        
        # Cálculo final
        papel_lam = escala * (costo_material + costo_acabado)
        print(f"Papel/lam total: ${papel_lam:.2f}")
        
        return papel_lam
        
    def calcular_desperdicio(self, num_tintas: int, ancho: float, papel_lam: float, valor_material: float, datos: DatosEscala, porcentaje_desperdicio: float = 0.10, es_manga: bool = False) -> float:
        """
        Calcula el costo del desperdicio combinando:
        1. Desperdicio por tintas: MM_Totales * valor_material * (ancho_total + GAP_PLANCHAS)
        2. Porcentaje del costo del papel/laminado
        """
        # Constantes
        MM_COLOR = 30000  # mm por color
        GAP_PLANCHAS = 50  # gap constante de planchas

        print("\n=== DETALLE COMPLETO DE CÁLCULO DE DESPERDICIO ===")
        print(f"Parámetros de entrada:")
        print(f"- Número de tintas: {num_tintas}")
        print(f"- Ancho: {ancho} mm")
        print(f"- Papel/lam: ${papel_lam:.2f}")
        print(f"- Valor material: ${valor_material:.6f}/mm²")
        print(f"- Porcentaje desperdicio: {porcentaje_desperdicio * 100:.1f}%")
        print(f"- MM por color: {MM_COLOR}")
        print(f"- Gap planchas: {GAP_PLANCHAS}")
        print(f"- Es manga: {es_manga}")
        print(f"- Pistas: {datos.pistas}")

        # Cálculo de desperdicio por tintas
        if num_tintas > 0:
            mm_totales = MM_COLOR * num_tintas
            
            # Cálculo usando fórmula R3+Q3
            C3 = 0  # GAP inicial es 0 para ambos
            if not es_manga and datos.pistas > 1:  # Solo para etiquetas con más de 1 pista
                C3 = 3
            B3 = ancho  # B3 es el ancho
            D3 = B3 + C3  # D3 = ancho + GAP
            E3 = datos.pistas
            Q3 = D3 * E3 + C3  # Q3 = (ancho + GAP) * pistas + GAP
            GAP_FIJO = 50  # R3 es 50 tanto para mangas como etiquetas
            s3 = GAP_FIJO + Q3  # R3 + Q3
            
            # Desperdicio para ambos = S7 × S3 × O7
            desperdicio_tintas = mm_totales * s3 * (valor_material / 1000000)
            
            print(f"\n--- Verificación del Cálculo ---")
            print(f"MM Totales (S7): {mm_totales}")
            print(f"Valor Material (O7): {valor_material}")
            print(f"C3 (GAP): {C3}")
            print(f"B3 (ancho): {B3}")
            print(f"D3 (ancho + GAP): {D3}")
            print(f"E3 (pistas): {E3}")
            print(f"Q3 ((ancho + GAP) * pistas + GAP): {Q3}")
            print(f"R3 (GAP_FIJO): {GAP_FIJO}")
            print(f"S3 (R3 + Q3): {s3}")
            print(f"Operación: {mm_totales} × {s3} × ({valor_material}/1000000)")
            print(f"Resultado desperdicio tintas: ${desperdicio_tintas:.2f}")
        else:
            desperdicio_tintas = 0
            print("No hay tintas, desperdicio_tintas = 0")

        # Desperdicio por porcentaje del papel/laminado
        desperdicio_porcentaje = papel_lam * porcentaje_desperdicio
        print(f"Desperdicio porcentaje: ${desperdicio_porcentaje:.2f} (papel_lam * porcentaje_desperdicio)")
        
        # Desperdicio total
        desperdicio_total = desperdicio_tintas + desperdicio_porcentaje
        print(f"Desperdicio total: ${desperdicio_total:.2f} (desperdicio_tintas + desperdicio_porcentaje)")
        
        return desperdicio_total
        
    def calcular_valor_unidad_full(self, suma_costos: float, datos: DatosEscala, 
                                 escala: int, valor_plancha: float, valor_troquel: float) -> float:
        """
        Calcula el valor por unidad basado en costos, rentabilidad y escala.
        
        El cálculo se basa en la fórmula:
        valor_unidad = (costos_indirectos + costos_fijos) / escala
        
        Donde:
        - costos_indirectos = suma_costos / factor_rentabilidad
        - factor_rentabilidad = (100 - rentabilidad) / 100
        - costos_fijos = valor_plancha + valor_troquel
        
        Args:
            suma_costos: Suma de todos los costos variables (montaje, MO, tintas, papel/lam, desperdicio)
            datos: Objeto DatosEscala con información de rentabilidad
            escala: Número de unidades a producir
            valor_plancha: Valor de las planchas (costo fijo)
            valor_troquel: Valor del troquel (costo fijo)
            
        Returns:
            float: Valor por unidad calculado
        """
        try:
            # 1. Validar y convertir valores de entrada
            valor_plancha = float(valor_plancha) if valor_plancha is not None else 0
            valor_troquel = float(valor_troquel) if valor_troquel is not None else 0
            suma_costos = float(suma_costos) if suma_costos is not None else 0
            
            # Imprimir información para depuración
            print("\n=== DEPURACIÓN VALOR UNIDAD ===")
            print(f"suma_costos: {suma_costos:.2f}")
            print(f"rentabilidad: {datos.rentabilidad:.2f}%")
            print(f"valor_plancha: {valor_plancha:.2f}")
            print(f"valor_troquel: {valor_troquel:.2f}")
            print(f"escala: {escala:,}")
            
            # 2. Validar escala
            if escala <= 0:
                print("Error: Escala es cero o negativa, retornando 0")
                return 0
            
            # 3. Calcular factor de rentabilidad
            factor_rentabilidad = (100 - datos.rentabilidad) / 100
            print(f"factor_rentabilidad: (100 - {datos.rentabilidad}) / 100 = {factor_rentabilidad:.4f}")
            
            # 4. Calcular costos indirectos (ajustados por rentabilidad)
            costos_indirectos = suma_costos / factor_rentabilidad
            print(f"costos_indirectos: {suma_costos:.2f} / {factor_rentabilidad:.4f} = {costos_indirectos:.2f}")
            
            # 5. Calcular costos fijos
            costos_fijos = valor_plancha + valor_troquel
            print(f"costos_fijos: {valor_plancha:.2f} + {valor_troquel:.2f} = {costos_fijos:.2f}")
            
            # 6. Calcular costos totales
            costos_totales = costos_indirectos + costos_fijos
            print(f"costos_totales: {costos_indirectos:.2f} + {costos_fijos:.2f} = {costos_totales:.2f}")
            
            # 7. Calcular valor por unidad
            valor_unidad = costos_totales / escala
            print(f"valor_unidad: {costos_totales:.2f} / {escala:,} = {valor_unidad:.6f}")
            
            # 8. Verificar resultado
            if not isinstance(valor_unidad, (int, float)) or valor_unidad < 0:
                print("Error: Valor unidad inválido, retornando 0")
                return 0
            
            return valor_unidad
        
        except Exception as e:
            print(f"Error en cálculo de valor unidad: {str(e)}")
            import traceback
            traceback.print_exc()
            return 0
        
    def calcular_desperdicio_tintas(self, dados: DatosEscala, num_tintas: int, valor_material: float, es_manga: bool = False) -> Dict:
        # Validaciones iniciales
        if num_tintas <= 0 or valor_material <= 0:
            return {
                'desperdicio_tintas': 0,
                'detalles': {}
            }

        # Constantes
        MM_COLOR = 30000  # mm por color
        GAP_FIJO = 50  # R3 es 50 tanto para mangas como etiquetas

        print("\n========== CÁLCULO DETALLADO DE DESPERDICIO DE TINTAS ==========")
        print(f"1. Constante MM_COLOR = {MM_COLOR}")

        # Calcular mm totales
        mm_totales = MM_COLOR * num_tintas
        print(f"2. MM Totales (S7) = MM_COLOR * num_tintas = {MM_COLOR} * {num_tintas} = {mm_totales}")

        # Cálculo específico para mangas
        if es_manga:
            # Aplicar el ajuste de ancho para mangas
            B3 = (dados.ancho * 2) + INCREMENTO_ANCHO_MANGAS
            C3 = 0  # No hay gap entre pistas para mangas
            print(f"3. Cálculo de ancho para mangas:")
            print(f"   - Ancho original: {dados.ancho} mm")
            print(f"   - Incremento de ancho: {INCREMENTO_ANCHO_MANGAS} mm")
            print(f"   - B3 calculado: ({dados.ancho} * 2) + {INCREMENTO_ANCHO_MANGAS} = {B3} mm")
        else:
            # Lógica para etiquetas
            B3 = dados.ancho
            # Para etiquetas: C3 = 0 si pistas = 1, C3 = 3 si pistas > 1
            C3 = 0 if dados.pistas == 1 else self.GAP

        # Calcular D3 (ancho + GAP)
        D3 = B3 + C3
        
        # Calcular E3 (pistas)
        E3 = dados.pistas

        # Calcular Q3
        Q3 = (D3 * E3) + C3

        print(f"4. Cálculo de Q3:")
        print(f"   - C3 (GAP): {C3} mm")
        print(f"   - B3 (ancho): {B3} mm")
        print(f"   - D3 (ancho + GAP): {D3} mm")
        print(f"   - E3 (pistas): {E3}")
        print(f"   - Q3 = (D3 * pistas + C3) = ({D3} * {E3} + {C3}) = {Q3} mm")

        # Calcular S3
        S3 = GAP_FIJO + Q3
        print(f"5. GAP_FIJO (R3) = {GAP_FIJO} mm")
        print(f"6. S3 = GAP_FIJO + Q3 = {GAP_FIJO} + {Q3} = {S3} mm")

        # Calcular factor de conversión
        print(f"7. Valor material: ${valor_material} por mm²")
        factor = valor_material / 1000000
        print(f"8. Factor de conversión (O7) = valor_material / 1000000 = {valor_material} / 1000000 = {factor:.8f}")

        # Calcular desperdicio de tintas
        desperdicio_tintas = mm_totales * S3 * factor
        print(f"9. Cálculo final:")
        print(f"   Desperdicio tintas = S7 * S3 * O7")
        print(f"   Desperdicio tintas = MM_Totales * S3 * Factor")
        print(f"   Desperdicio tintas = {mm_totales} * {S3} * {factor:.8f} = ${desperdicio_tintas:.2f}")

        # Retornar diccionario con más detalles
        return {
            'desperdicio_tintas': desperdicio_tintas,
            'detalles': {
                'mm_totales': mm_totales,
                'q3': Q3,
                'c3': C3,
                'd3': D3,
                's3': S3,
                'factor': factor,
                'formula': 'desperdicio_tintas = mm_totales * s3 * factor',
                'ancho_original': dados.ancho,
                'ancho_ajustado': B3,
                'pistas': E3,
                'es_manga': es_manga
            }
        }
        
    def calcular_costos_por_escala(
        self, 
        datos: DatosEscala, 
        num_tintas: int,
        valor_etiqueta: float,
        valor_plancha: float,
        valor_troquel: float,
        valor_material: float,
        valor_acabado: float,
        es_manga: bool = False
    ) -> List[Dict]:
        """
        Calcula los costos para cada escala especificada.
        """
        try:
            resultados = []
            # Usar el porcentaje de desperdicio adecuado según el tipo de producto
            porcentaje_desperdicio = datos.porcentaje_desperdicio / 100
            
            # Debug inicial
            print("\n=== INICIO CÁLCULO DE COSTOS POR ESCALA ===")
            print(f"Datos de entrada:")
            print(f"- Número de tintas: {num_tintas}")
            print(f"- Valor etiqueta: ${valor_etiqueta:.6f}")
            print(f"- Valor plancha: ${valor_plancha:.2f}")
            print(f"- Valor troquel: ${valor_troquel:.2f}")
            print(f"- Valor material: ${valor_material:.6f}/mm²")
            print(f"- Valor acabado: ${valor_acabado:.6f}/mm²")
            print(f"- Es manga: {es_manga}")
            print(f"- Porcentaje desperdicio: {porcentaje_desperdicio * 100}%")
            print(f"- Área etiqueta: {datos.area_etiqueta:.2f} mm²")
            
            # Validar área de etiqueta
            if datos.area_etiqueta <= 0:
                print("ADVERTENCIA: El área de etiqueta es cero o negativa. Esto afectará los cálculos.")
            
            # 3. Calcular costos para cada escala
            for escala in datos.escalas:
                print(f"\n=== CÁLCULO PARA ESCALA: {escala:,} ===")
                
                # 3.1 Calcular metros lineales
                metros = self.calcular_metros(escala, datos, es_manga)
                print(f"Metros lineales: {metros:.2f}")
                
                # 3.2 Calcular tiempo en horas
                tiempo_horas = self.calcular_tiempo_horas(metros, datos)
                print(f"Tiempo en horas: {tiempo_horas:.2f}")
                
                # 3.3 Calcular componentes de costo
                montaje = self.calcular_montaje(num_tintas, datos)
                print(f"Montaje: ${montaje:.2f}")
                
                mo_y_maq = self.calcular_mo_y_maq(tiempo_horas, num_tintas, datos, es_manga)
                print(f"MO y Maq: ${mo_y_maq:.2f}")
                
                # Verificar área de etiqueta antes de calcular tintas
                print(f"Área etiqueta para cálculo de tintas: {datos.area_etiqueta:.2f} mm²")
                tintas = self.calcular_tintas(escala, num_tintas, datos.area_etiqueta, datos)
                print(f"Tintas: ${tintas:.2f}")
                
                # Verificar área de etiqueta antes de calcular papel_lam
                print(f"Área etiqueta para cálculo de papel_lam: {datos.area_etiqueta:.2f} mm²")
                papel_lam = self.calcular_papel_lam(escala, datos.area_etiqueta, valor_material, valor_acabado)
                print(f"Papel/lam: ${papel_lam:.2f}")
                
                # 3.4 Calcular desperdicios
                # Desperdicio por porcentaje del papel/laminado usando constantes
                desperdicio_porcentaje = papel_lam * porcentaje_desperdicio
                print(f"Desperdicio porcentaje ({porcentaje_desperdicio * 100}%): ${desperdicio_porcentaje:.2f}")

                # Desperdicio de tintas
                if num_tintas > 0:
                    resultado_desperdicio = self.calcular_desperdicio_tintas(
                        dados=datos,
                        num_tintas=num_tintas,
                        valor_material=valor_material,
                        es_manga=es_manga
                    )
                    # Extrae solo el valor numérico del diccionario
                    desperdicio_tintas = resultado_desperdicio['desperdicio_tintas']
                    desperdicio_tintas_detalles = resultado_desperdicio['detalles']
                else:
                    desperdicio_tintas = 0
                    desperdicio_tintas_detalles = {}

                # Ahora ambos son valores numéricos para la suma
                desperdicio_total = desperdicio_porcentaje + desperdicio_tintas
                print(f"Desperdicio total: ${desperdicio_total:.2f} = ${desperdicio_porcentaje:.2f} + ${desperdicio_tintas:.2f}")
                
                # 3.5 Calcular suma de costos variables
                suma_costos = montaje + mo_y_maq + tintas + papel_lam + desperdicio_total
                print(f"Suma de costos variables: ${suma_costos:.2f}")
                
                # 3.6 Calcular valor por unidad
                valor_unidad = self.calcular_valor_unidad_full(
                    suma_costos, datos, escala, valor_plancha, valor_troquel
                )
                print(f"Valor por unidad: ${valor_unidad:.6f}")
                
                # 3.7 Agregar resultados a la lista
                resultados.append({
                    'escala': escala,
                    'valor_unidad': valor_unidad,
                    'metros': metros,
                    'tiempo_horas': tiempo_horas,
                    'montaje': montaje,
                    'mo_y_maq': mo_y_maq,
                    'tintas': tintas,
                    'papel_lam': papel_lam,
                    'desperdicio': datos.desperdicio,  # Desperdicio original (por dientes)
                    'desperdicio_tintas': desperdicio_tintas,
                    'desperdicio_porcentaje': desperdicio_porcentaje,
                    'desperdicio_total': desperdicio_total,  # Suma total del desperdicio
                    'num_tintas': num_tintas,
                    'ancho': datos.ancho,
                    'avance': datos.avance,
                    'porcentaje_desperdicio': porcentaje_desperdicio
                })
            
            return resultados
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise ValueError(f"Error en cálculo de costos: {str(e)}")

    def generar_tabla_resultados(self, resultados: List[Dict]) -> pd.DataFrame:
        """Genera una tabla formateada con los resultados de la cotización"""
        print("\n=== DEPURACIÓN TABLA RESULTADOS ===")
        
        return pd.DataFrame([
            {
                'Escala': f"{r['escala']:,}",
                'Valor Unidad': f"${float(r['valor_unidad']):.2f}",
                'Metros': f"{r['metros']:.2f} = ({r['escala']:,}/2) × ({150}+2.6+{r.get('desperdicio', 0):.1f})/1000",
                'Tiempo (h)': f"{r['tiempo_horas']:.2f}",
                'Montaje': f"${r['montaje']:,.2f}",
                'MO y Maq': f"${r['mo_y_maq']:,.2f}",
                'Tintas': f"${r['tintas']:,.2f}",
                'Papel/lam': f"${r['papel_lam']:,.2f}",
                'Desperdicio': f"${r['desperdicio_total']:,.2f}"
            }
            for r in resultados
        ])
