from dataclasses import dataclass
from typing import List, Dict, Tuple
import math

@dataclass
class DatosEscala:
    """Clase para almacenar los datos necesarios para los cálculos por escala"""
    escalas: List[int]
    pistas: int
    ancho: float  # Ancho base para calcular ancho_total
    avance_total: float
    desperdicio: float
    velocidad_maquina: float = 20.0  # Valor fijo
    mo_montaje: float = 5000.0  # Valor fijo
    mo_impresion: float = 50000.0  # Valor fijo
    mo_troquelado: float = 50000.0  # Valor fijo
    valor_gr_tinta: float = 30.0  # Valor fijo
    rentabilidad: float = 40.0  # Valor fijo
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
        SI(tintas>0;SI(F8<1;MO Impresión;MO Impresión*(F8));SI(F8<1;MO Troquelado;MO Troquelado*(F8)))
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
        
    def calcular_papel_lam(self, escala: int, area_etiqueta: float) -> float:
        """
        Calcula Papel/lam según la fórmula:
        A8*(material + acabado)
        donde:
        material = 0.0023 * area_etiqueta
        acabado = 0.0005 * area_etiqueta
        """
        material = 0.0023 * area_etiqueta
        acabado = 0.0005 * area_etiqueta
        return escala * (material + acabado)
        
    def calcular_desperdicio(self, num_tintas: int, ancho_total: float, papel_lam: float) -> float:
        """
        Calcula el desperdicio según la fórmula:
        Desperdicio = T7 + (K6 * J8)
        donde:
        - T7 = S7 * S3 * O7
        - S7 = if(B2=0, 0, R7*B2) donde R7=30000 y B2=número de tintas
        - S3 = ancho_total + 40 (gap fijo)
        - O7 = 0.0023 ($/mm²)
        - K6 = 10%
        - J8 = papel por lámina
        """
        # Constantes
        R7 = 30000  # mm/color
        GAP_FIJO = 40
        O7 = 0.0023  # $/mm²
        K6 = 0.10  # 10%

        # Cálculo de S7
        s7 = 0 if num_tintas == 0 else R7 * num_tintas
        
        # Cálculo de S3
        s3 = ancho_total + GAP_FIJO
        
        # Cálculo de T7
        t7 = s7 * s3 * O7
        
        # Cálculo final del desperdicio
        return t7 + (K6 * papel_lam)
        
    def calcular_valor_unidad_full(self, suma_costos: float, datos: DatosEscala, 
                                 escala: int, valor_plancha: float, valor_troquel: float) -> float:
        """
        Calcula el valor por unidad full según la fórmula:
        (((SUMA(G8:K8))/((100-rentabilidad)/100))+(valor planca+valor troquel))/A8
        """
        factor_rentabilidad = (100 - datos.rentabilidad) / 100
        return (((suma_costos) / factor_rentabilidad) + (valor_plancha + valor_troquel)) / escala
        
    def calcular_mm(self, valor_unidad: float, escala: int) -> float:
        """Calcula el valor en millones según la fórmula: B8*A8/1000000"""
        return valor_unidad * escala / 1000000
        
    def calcular_costos_por_escala(self, datos: DatosEscala, num_tintas: int, 
                                 valor_etiqueta: float, valor_plancha: float = 0, 
                                 valor_troquel: float = 0) -> List[Dict]:
        """
        Calcula todos los costos para cada escala proporcionada
        
        Returns:
            List[Dict]: Lista de diccionarios con los valores calculados para cada escala
        """
        resultados = []
        
        for escala in datos.escalas:
            # Cálculos base
            metros = self.calcular_metros(escala, datos)
            tiempo_horas = self.calcular_tiempo_horas(metros, datos)
            
            # Cálculos de costos
            montaje = self.calcular_montaje(num_tintas, datos)
            mo_y_maq = self.calcular_mo_y_maq(tiempo_horas, num_tintas, datos)
            tintas = self.calcular_tintas(escala, num_tintas, valor_etiqueta, datos)
            papel_lam = self.calcular_papel_lam(escala, datos.area_etiqueta)
            # Calcular ancho total
            ancho_total, mensaje = self.calcular_ancho_total(num_tintas, datos.pistas, datos.ancho)
            if mensaje:
                raise ValueError(mensaje)
                
            desperdicio = self.calcular_desperdicio(num_tintas, ancho_total, papel_lam)
            
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
                'metros': metros,
                'tiempo_horas': tiempo_horas,
                'montaje': montaje,
                'mo_y_maq': mo_y_maq,
                'tintas': tintas,
                'papel_lam': papel_lam,
                'desperdicio': desperdicio
            })
            
        return resultados
