"""
Clase base para cálculos comunes entre CalculadoraLitografia y CalculadoraCostosEscala.
"""
from typing import Dict

class CalculadoraBase:
    """
    Clase base que contiene los cálculos comunes para Q3, S3 y variables relacionadas.
    """
    
    # Constantes compartidas
    GAP = 3  # GAP entre pistas
    GAP_FIJO = 50  # R3 es 50 tanto para mangas como etiquetas
    AVANCE_FIJO = 30  # Avance fijo para cálculos
    MM_COLOR = 30000  # MM de color para cálculo de desperdicio
    
    def calcular_q3(self, ancho: float, pistas: int, es_manga: bool = False) -> Dict:
        """
        Calcula Q3, C3 y D3 para cálculos de área y precio.
        
        Este método centraliza el cálculo de Q3 (ancho total ajustado) que se utiliza
        en múltiples cálculos. Implementa la fórmula: Q3 = D3 * pistas + C3
        
        Args:
            ancho: Ancho en mm
            pistas: Número de pistas
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Dict con los valores calculados:
                - c3: Valor de C3 (gap)
                - d3: Valor de D3 (ancho + gap)
                - e3: Número de pistas
                - q3: Valor de Q3 (ancho total ajustado)
        """
        # Determinar C3 según tipo y pistas
        c3 = 0 if es_manga or pistas <= 1 else self.GAP
        
        # Calcular D3 = ancho + C3
        d3 = ancho + c3
        
        # Calcular Q3 = D3 * pistas + C3
        q3 = (d3 * pistas) + c3
        
        return {
            'c3': c3,
            'd3': d3,
            'e3': pistas,
            'q3': q3
        }
    
    def calcular_s3(self, ancho: float, pistas: int, es_manga: bool = False) -> Dict:
        """
        Calcula S3 basado en Q3 y el GAP_FIJO.
        
        Args:
            ancho: Ancho en mm
            pistas: Número de pistas
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            Dict con los valores calculados incluyendo s3 y los valores intermedios
        """
        # Calcular Q3 y valores relacionados
        resultado_q3 = self.calcular_q3(ancho, pistas, es_manga)
        
        # Calcular S3 = GAP_FIJO + Q3
        s3 = self.GAP_FIJO + resultado_q3['q3']
        
        # Agregar S3 al resultado
        resultado_q3['s3'] = s3
        resultado_q3['gap_fijo'] = self.GAP_FIJO
        
        return resultado_q3 