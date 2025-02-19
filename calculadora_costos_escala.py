from dataclasses import dataclass
from typing import List, Dict, Tuple
import math

@dataclass
class DatosEscala:
    """Clase para almacenar los datos necesarios para los cálculos por escala"""
    escalas: List[int]
    pistas: int
    ancho: float  # Ancho base para calcular ancho_total
    avance: float  # Nuevo atributo para avance
    avance_total: float  # Mantener avance_total
    desperdicio: float
    velocidad_maquina: float = 20.0  # Valor fijo
    mo_montaje: float = 5000.0  # Valor fijo
    mo_impresion: float = 50000.0  # Valor fijo
    mo_troquelado: float = 50000.0  # Valor fijo
    valor_gr_tinta: float = 30.0  # Valor fijo
    rentabilidad: float = 40.0  # Valor por defecto para etiquetas
    area_etiqueta: float = 0.0  # Se calcula o se recibe

class CalculadoraCostosEscala:
    """Clase para calcular los costos por escala"""
    
    def __init__(self):
        self.C3 = 3  # Valor fijo para el cálculo de ancho_total
        self.ANCHO_MAXIMO = 335  # Ancho máximo permitido en mm
        
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
        incremento = 10 if num_tintas == 0 else 20
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
        
    def calcular_metros(self, escala: int, datos: DatosEscala) -> float:
        """
        Calcula los metros según la fórmula: =(A8/$E$3)*(($D$4+$C$5)/1000)
        donde:
        - A8 = escala
        - $E$3 = pistas
        - $D$4 = avance + 2.6 (gap fijo)
        - $C$5 = desperdicio de la unidad de montaje
        """
        GAP_FIJO = 2.6  # Gap fijo para el avance
        d4 = datos.avance_total + GAP_FIJO  # Avance + gap fijo
        return (escala / datos.pistas) * ((d4 + datos.desperdicio) / 1000)
        
    def calcular_tiempo_horas(self, metros: float, datos: DatosEscala) -> float:
        """Calcula el tiempo en horas según la fórmula: metros / velocidad_maquina / 60"""
        return metros / datos.velocidad_maquina / 60
        
    def calcular_montaje(self, num_tintas: int, datos: DatosEscala) -> float:
        """Calcula el montaje según la fórmula: Tintas * MO Montaje"""
        return num_tintas * datos.mo_montaje
        
    def calcular_mo_y_maq(self, tiempo_horas: float, num_tintas: int, datos: DatosEscala) -> float:
        """
        Calcula MO y Maq según la fórmula:
        SI(tintas>0;SI(F8<1;MO Impresión;MO Impresión*(F8)));SI(F8<1;MO Troquelado;MO Troquelado*(F8)))
        """
        if num_tintas > 0:
            if tiempo_horas < 1:
                return datos.mo_impresion
            return datos.mo_impresion * tiempo_horas
        else:
            if tiempo_horas < 1:
                return datos.mo_troquelado
            return datos.mo_troquelado * tiempo_horas
            
    def calcular_tintas(self, escala: int, num_tintas: int, valor_etiqueta: float, datos: DatosEscala) -> float:
        """
        Calcula el valor de tintas según la fórmula:
        $/etiqueta*A8+(100*tintas*$/gr)
        """
        return valor_etiqueta * escala + (100 * num_tintas * datos.valor_gr_tinta)
        
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
        # Cálculo detallado
        costo_material = (area_etiqueta * valor_material) / 1000000
        costo_acabado = (area_etiqueta * valor_acabado) / 1000000
        
        # Imprimir detalles para depuración
        print(f"\n=== CÁLCULO PAPEL/LAM ===")
        print(f"Área etiqueta: {area_etiqueta:.4f} mm²")
        print(f"Valor material: ${valor_material:.6f}/mm²")
        print(f"Valor acabado: ${valor_acabado:.6f}/mm²")
        print(f"Costo material: ${costo_material:.4f}")
        print(f"Costo acabado: ${costo_acabado:.4f}")
        print(f"Escala: {escala}")
        
        # Cálculo final
        papel_lam = escala * (costo_material + costo_acabado)
        print(f"Papel/lam total: ${papel_lam:.2f}")
        
        return papel_lam
        
    def calcular_desperdicio(self, num_tintas: int, ancho_total: float, papel_lam: float, valor_material: float) -> float:
        """
        Calcula el desperdicio según la fórmula:
        Si tintas > 0:
            primera_parte = 30000 * num_tintas * (gap_fijo + ancho_total) * precio_material / 1000000
        Si tintas = 0:
            primera_parte = 0
        
        desperdicio = primera_parte + (10% * papel_lam)
        """
        # Constantes
        MM_COLOR = 30000  # mm por color (constante)
        GAP_FIJO = 40  # Gap fijo de planchas en mm
        
        # Primera parte - Desperdicio por tintas
        if num_tintas > 0:
            mm_totales = MM_COLOR * num_tintas  # 30000 mm/color * número de tintas
            area_total = mm_totales * (GAP_FIJO + ancho_total)
            primera_parte = area_total * valor_material / 1000000
            print(f"\nDEBUG - Cálculo primera parte:")
            print(f"1. mm_totales = {MM_COLOR} * {num_tintas} = {mm_totales}")
            print(f"2. area_total = {mm_totales} * ({GAP_FIJO} + {ancho_total}) = {area_total}")
            print(f"3. primera_parte = {area_total} * {valor_material} / 1000000 = {primera_parte}")
        else:
            primera_parte = 0
            mm_totales = 0
            area_total = 0
            print("\nDEBUG - Tintas es 0, primera_parte = 0")
        
        # Segunda parte - 10% del papel/lam
        segunda_parte = 0.10 * papel_lam
        
        # Desperdicio total
        desperdicio = primera_parte + segunda_parte
        
        # Imprimir detalles para depuración
        print(f"\n=== CÁLCULO DESPERDICIO ===")
        print(f"Número de tintas: {num_tintas} (tipo: {type(num_tintas)})")
        print(f"mm por color: {MM_COLOR}")
        print(f"mm totales (30000 * tintas): {mm_totales}")
        print(f"Ancho total: {ancho_total:.2f} mm")
        print(f"Gap fijo: {GAP_FIJO} mm")
        print(f"Área total: {area_total:.2f} mm²")
        print(f"Precio material: ${valor_material:.6f}/mm²")
        print(f"Primera parte (tintas): ${primera_parte:.2f}")
        print(f"Segunda parte (10% papel/lam): ${segunda_parte:.2f}")
        print(f"Desperdicio total: ${desperdicio:.2f}")
        
        print(f"\n=== INFORMACIÓN DE DIENTES ===")
        print(f"Ancho total: {ancho_total} mm")
        print(f"Número de tintas: {num_tintas}")
        print(f"Área total de dientes: {area_total} mm²")
        
        return desperdicio
        
    def calcular_valor_unidad_full(self, suma_costos: float, datos: DatosEscala, 
                                 escala: int, valor_plancha: float, valor_troquel: float) -> float:
        """
        Calcula el valor por unidad según la fórmula:
        valor_unidad = (suma_costos / ((100 - rentabilidad) / 100) + valor_planchas + valor_troquel) / escala
        
        Donde:
        - suma_costos = Montaje + MO y Maq + Tintas + Papel/lam + Desperdicio
        - rentabilidad = 40%
        """
        # Detalles de impresión
        print(f"\n=== CÁLCULO VALOR UNIDAD ===")
        print(f"Suma costos directos: ${suma_costos:.2f}")
        print(f"Rentabilidad: {datos.rentabilidad}%")
        
        # Cálculo paso a paso
        factor_rentabilidad = (100 - datos.rentabilidad) / 100
        print(f"Factor rentabilidad: {factor_rentabilidad:.4f}")
        
        costos_indirectos = suma_costos / factor_rentabilidad
        print(f"Costos indirectos (suma_costos / factor_rentabilidad): ${costos_indirectos:.2f}")
        
        costos_fijos = valor_plancha + valor_troquel
        print(f"Costos fijos (planchas + troquel): ${costos_fijos:.2f}")
        
        costos_totales = costos_indirectos + costos_fijos
        print(f"Costos totales: ${costos_totales:.2f}")
        
        valor_unidad = costos_totales / escala
        print(f"Valor unidad (costos_totales / {escala}): ${valor_unidad:.2f}")
        
        return valor_unidad
        
    def calcular_mm(self, valor_unidad: float, escala: int) -> float:
        """Calcula el valor en millones según la fórmula: B8*A8/1000000"""
        return valor_unidad * escala / 1000000
        
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
        Calcula los costos para cada escala
        """
        resultados = []
        
        # Ajustar porcentaje de desperdicio y rentabilidad según el tipo
        porcentaje_desperdicio = 0.30 if es_manga else 0.10  # 30% para mangas, 10% para etiquetas
        datos.rentabilidad = 45.0 if es_manga else 40.0  # 45% para mangas, 40% para etiquetas
        
        for escala in datos.escalas:
            # Calcular metros lineales
            metros = self.calcular_metros(escala, datos)
            
            # Agregar desperdicio según el tipo
            metros_con_desperdicio = metros * (1 + porcentaje_desperdicio)
            
            # Calcular tiempo en horas
            tiempo_horas = self.calcular_tiempo_horas(metros_con_desperdicio, datos)
            
            # Calcular costos
            montaje = self.calcular_montaje(num_tintas, datos)
            mo_y_maq = self.calcular_mo_y_maq(tiempo_horas, num_tintas, datos)
            tintas = self.calcular_tintas(escala, num_tintas, valor_etiqueta, datos)
            papel_lam = self.calcular_papel_lam(escala, datos.area_etiqueta, valor_material, valor_acabado)
            desperdicio = self.calcular_desperdicio(num_tintas, datos.ancho, papel_lam, valor_material)
            
            # Suma de costos para valor unidad
            suma_costos = montaje + mo_y_maq + tintas + papel_lam + desperdicio
            
            # Cálculo final
            valor_unidad = self.calcular_valor_unidad_full(
                suma_costos, datos, escala, valor_plancha, valor_troquel
            )
            valor_mm = self.calcular_mm(valor_unidad, escala)
            
            resultados.append({
                'escala': escala,
                'valor_unidad': valor_unidad,
                'valor_mm': valor_mm,
                'metros': metros_con_desperdicio,  # Usar metros con desperdicio
                'tiempo_horas': tiempo_horas,
                'montaje': montaje,
                'mo_y_maq': mo_y_maq,
                'tintas': tintas,
                'papel_lam': papel_lam,
                'desperdicio': desperdicio
            })
            
        return resultados
