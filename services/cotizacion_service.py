from typing import List, Dict, Optional
import pandas as pd
from model_classes.cotizacion_model import *
from calculadora_litografia import CalculadoraLitografia, DatosLitografia
from calculadora_costos_escala import CalculadoraCostosEscala, DatosEscala

class CotizacionService:
    """Servicio para gestionar el proceso de cotización"""
    
    def __init__(self):
        self.calculadora_lito = CalculadoraLitografia()
        self.calculadora_costos = CalculadoraCostosEscala()
    
    def generar_cotizacion(self, config: ConfiguracionProduccion) -> ResultadoCotizacion:
        """
        Genera una cotización completa basada en la configuración proporcionada
        
        Args:
            config: Configuración de producción
            
        Returns:
            ResultadoCotizacion: Resultado completo de la cotización
        """
        # Crear datos de litografía
        datos_lito = DatosLitografia(
            ancho=config.etiqueta.ancho,
            avance=config.etiqueta.avance,
            pistas=config.etiqueta.pistas,
            planchas_por_separado=config.planchas_por_separado,
            incluye_troquel=True,
            troquel_existe=config.troquel_existe,
            gap=config.etiqueta.gap,
            gap_avance=config.etiqueta.gap_avance
        )
        
        # Generar reporte de litografía
        reporte_lito = self.calculadora_lito.generar_reporte_completo(
            datos_lito, 
            config.etiqueta.num_tintas,
            es_manga=config.etiqueta.es_manga
        )
        
        # Verificar si tenemos la mejor opción de desperdicio
        if not reporte_lito['desperdicio'] or not reporte_lito['desperdicio']['mejor_opcion']:
            raise ValueError("No se pudo calcular el desperdicio. Revise los valores de ancho y avance.")
        
        mejor_opcion = reporte_lito['desperdicio']['mejor_opcion']
        
        # Actualizar área de etiqueta y desperdicio
        config.etiqueta.area_etiqueta = reporte_lito['area_etiqueta'] if reporte_lito['area_etiqueta'] else 0
        config.etiqueta.desperdicio = mejor_opcion['desperdicio']
        
        # Crear datos para calculadora de costos
        datos_escala = DatosEscala(
            escalas=config.escalas,
            pistas=config.etiqueta.pistas,
            ancho=config.etiqueta.ancho,
            avance=config.etiqueta.avance,
            avance_total=config.etiqueta.avance,
            desperdicio=config.etiqueta.desperdicio,
            area_etiqueta=config.etiqueta.area_etiqueta
        )
        
        # Obtener valores
        valor_etiqueta = reporte_lito.get('valor_tinta', 0)
        
        # Obtener valor de plancha del reporte
        valor_plancha_dict = reporte_lito.get('precio_plancha', {'precio': 0})
        valor_plancha = valor_plancha_dict['precio'] if isinstance(valor_plancha_dict, dict) else valor_plancha_dict
        
        # Obtener valor del troquel del reporte
        valor_troquel_dict = reporte_lito.get('valor_troquel', {'valor': 0})
        valor_troquel = valor_troquel_dict['valor'] if isinstance(valor_troquel_dict, dict) else valor_troquel_dict
        
        # Calcular valor de plancha separado si aplica
        valor_plancha_separado = None
        valor_plancha_para_calculo = valor_plancha
        
        if config.planchas_por_separado:
            valor_plancha_separado = self._calcular_valor_plancha_separado(valor_plancha_dict)
            valor_plancha_para_calculo = 0
        
        # Calcular costos por escala
        resultados_calc = self.calculadora_costos.calcular_costos_por_escala(
            datos=datos_escala,
            num_tintas=config.etiqueta.num_tintas,
            valor_etiqueta=valor_etiqueta,
            valor_plancha=valor_plancha_para_calculo,
            valor_troquel=valor_troquel,
            valor_material=config.material.material_valor,
            valor_acabado=config.material.acabado_valor,
            es_manga=config.etiqueta.es_manga
        )
        
        # Convertir resultados a objetos ResultadoEscala
        resultados_escalas = []
        for r in resultados_calc:
            resultados_escalas.append(ResultadoEscala(
                escala=r['escala'],
                valor_unidad=r['valor_unidad'],
                valor_mm=r['valor_mm'],
                metros=r['metros'],
                tiempo_horas=r['tiempo_horas'],
                montaje=r['montaje'],
                mo_y_maq=r['mo_y_maq'],
                tintas=r['tintas'],
                papel_lam=r['papel_lam'],
                desperdicio=r['desperdicio'],
                desperdicio_tintas=r['desperdicio_tintas'],
                desperdicio_porcentaje=r['desperdicio_porcentaje']
            ))
        
        # Crear resultado de cotización
        return ResultadoCotizacion(
            config=config,
            resultados_escalas=resultados_escalas,
            valor_plancha=valor_plancha,
            valor_plancha_separado=valor_plancha_separado,
            valor_troquel=valor_troquel
        )
    
    def generar_tabla_resultados(self, cotizacion: ResultadoCotizacion) -> pd.DataFrame:
        """
        Genera una tabla formateada con los resultados de la cotización
        
        Args:
            cotizacion: Resultado de cotización
            
        Returns:
            DataFrame: Tabla formateada para mostrar en la interfaz
        """
        df = pd.DataFrame([
            {
                'Escala': f"{r.escala:,}",
                'Valor Unidad': r.formato_valor_unidad(),
                'Valor MM': r.formato_valor_mm(),
                'Metros': f"{r.metros:.2f}",
                'Tiempo (h)': f"{r.tiempo_horas:.2f}",
                'Montaje': f"${r.montaje:,.2f}",
                'MO y Maq': f"${r.mo_y_maq:,.2f}",
                'Tintas': f"${r.tintas:,.2f}",
                'Papel/lam': f"${r.papel_lam:,.2f}",
                'Desperdicio': r.formato_desperdicio()
            }
            for r in cotizacion.resultados_escalas
        ])
        
        return df
    
    def _calcular_valor_plancha_separado(self, valor_plancha_dict: Dict) -> float:
        """Calcula el valor de la plancha por separado"""
        if isinstance(valor_plancha_dict, dict) and 'precio' in valor_plancha_dict:
            return valor_plancha_dict['precio'] * 1.2  # Ejemplo: 20% adicional
        return 0 