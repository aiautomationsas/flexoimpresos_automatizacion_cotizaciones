import pandas as pd
from typing import List, Dict

def generar_tabla_resultados(resultados: List[Dict], es_manga: bool = False) -> pd.DataFrame:
    """Genera una tabla formateada con los resultados de la cotización"""
    columnas = [
        'Escala', 'Valor Unidad', 'Metros', 'Tiempo (h)', 
        'Montaje', 'MO y Maq', 'Tintas', 'Papel/lam', 'Desperdicio'
    ]
    
    datos = [
        {
            'Escala': f"{r['escala']:,}",
            'Valor Unidad': f"${float(r['valor_unidad']):.2f}",
            'Metros': f"{r['metros']:.2f}",
            'Tiempo (h)': f"{r['tiempo_horas']:.2f}",
            'Montaje': f"${r['montaje']:,.2f}",
            'MO y Maq': f"${r['mo_y_maq']:,.2f}",
            'Tintas': f"${r['tintas']:,.2f}",
            'Papel/lam': f"${r['papel_lam']:,.2f}",
            'Desperdicio': f"${r['desperdicio_total']:,.2f}"
        }
        for r in resultados
    ]
    
    return pd.DataFrame(datos, columns=columnas)

