#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script de prueba para verificar el cálculo de repeticiones
Este script permite probar el cálculo de repeticiones para diferentes unidades y avances
"""

import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Union, Optional

@dataclass
class OpcionDesperdicio:
    dientes: float
    medida_mm: float
    desperdicio: float
    repeticiones: int
    ancho_total: float  # Nuevo campo para mostrar el ancho total incluyendo gaps

class CalculadoraDesperdicio:
    def __init__(self, ancho_maquina: float = 325, gap_mm: float = 3, es_manga: bool = False):
        # Constantes de la máquina
        self.ANCHO_MAQUINA = ancho_maquina
        self.GAP_MM = gap_mm  # Gap para ancho total
        self.GAP_AVANCE = 2.6  # Gap fijo para el avance (solo para etiquetas)
        self.DESPERDICIO_MINIMO = 2.6
        self.MAX_REPETICIONES = 20  # Máximo de repeticiones a considerar (hasta la columna Z)
        self.es_manga = es_manga  # Nuevo flag para diferenciar mangas de etiquetas
        
        # Datos de la tabla de unidades disponibles
        self.data = {
            'Dientes': [80.00, 84.00, 88.00, 96.00, 102.00, 108.00, 112.00, 120.00, 64.00, 128.00, 140.00, 165.00],
            'Pulg_diente': [0.1250] * 12,
            'Pulgadas': [10.0000, 10.5000, 11.0000, 12.0000, 12.7500, 13.5000, 14.0000, 15.0000, 8.0000, 16.0000, 17.5000, 20.6250],
            'cm_pulg': [25.40] * 12,
            'mm': [254.0000, 266.7000, 279.4000, 304.8000, 323.8500, 342.9000, 355.6000, 381.0000, 203.2000, 406.4000, 444.5000, 523.8750]
        }
        self.df = pd.DataFrame(self.data)
        self._validar_datos_iniciales()

    def _validar_datos_iniciales(self) -> None:
        """Valida la integridad de los datos iniciales"""
        if self.df.empty:
            raise ValueError("No hay datos cargados en la calculadora")
        
        columnas_requeridas = ['Dientes', 'mm']
        for col in columnas_requeridas:
            if col not in self.df.columns:
                raise ValueError(f"Falta la columna requerida: {col}")
        
        if (self.df['mm'] <= 0).any():
            raise ValueError("Existen medidas inválidas (nulas o negativas)")
        
        if (self.df['Dientes'] <= 0).any():
            raise ValueError("Existen números de dientes inválidos (nulos o negativos)")

    def _calcular_ancho_total(self, avance_mm: float, repeticiones: int) -> float:
        """
        Calcula el ancho total incluyendo gaps entre repeticiones.
        Para mangas, no se incluye el gap entre repeticiones.
        """
        if self.es_manga:
            return avance_mm * repeticiones
        return (avance_mm * repeticiones) + (self.GAP_MM * (repeticiones - 1))

    def _validar_ancho_total(self, ancho_total: float) -> bool:
        """Valida si el ancho total está dentro del límite de la máquina"""
        return ancho_total <= self.ANCHO_MAQUINA

    def _validar_avance(self, avance_mm: float) -> None:
        """Valida que el avance sea un valor válido"""
        if not isinstance(avance_mm, (int, float)):
            raise TypeError("El avance debe ser un número")
        if avance_mm <= 0:
            raise ValueError("El avance debe ser mayor que 0")

    def _calcular_desperdicio_individual(self, medida_mm: float, avance: float, repeticiones: int) -> float:
        """
        Calcula el desperdicio para una medida específica.
        Para mangas, no se agrega el GAP_AVANCE.
        Para etiquetas, se agrega el GAP_AVANCE.
        """
        # Para mangas, usar el avance directo. Para etiquetas, agregar el gap
        avance_efectivo = avance if self.es_manga else avance + self.GAP_AVANCE
        
        # Si la medida es menor que el espacio necesario, es inválido
        if medida_mm < (repeticiones * avance_efectivo):
            return 999.9999
            
        # Calcular el desperdicio
        return abs(medida_mm - avance_efectivo * repeticiones) / repeticiones

    def _filtrar_opciones_validas(self, opciones: List[OpcionDesperdicio]) -> List[OpcionDesperdicio]:
        """
        Filtra las opciones según el criterio de desperdicio mínimo.
        Solo se consideran válidas las opciones con desperdicio < 999.
        Se ordenan por el valor absoluto del desperdicio para encontrar la opción que más se acerca a 0.
        """
        # Filtrar opciones con desperdicio válido (menor a 999)
        opciones_validas = [op for op in opciones if op.desperdicio < 999]
        
        if not opciones_validas:
            return []
        
        # Ordenar por el valor absoluto del desperdicio y luego por dientes
        # Esto asegura que se seleccione la opción que minimiza el desperdicio real
        return sorted(opciones_validas, key=lambda x: (abs(x.desperdicio), x.dientes))

    def _calcular_max_repeticiones(self, avance_mm: float) -> int:
        """Calcula el máximo número de repeticiones posibles considerando el ancho de máquina y gaps"""
        max_rep = 1
        while self._calcular_ancho_total(avance_mm, max_rep + 1) <= self.ANCHO_MAQUINA:
            max_rep += 1
        return max_rep
    
    # El método _obtener_repeticiones_fijas ha sido eliminado
    # Ahora todas las repeticiones se calculan dinámicamente

    def calcular_todas_opciones(self, avance_mm: float) -> List[OpcionDesperdicio]:
        """Calcula todas las opciones válidas ordenadas por desperdicio, probando todas las repeticiones posibles"""
        self._validar_avance(avance_mm)
        
        opciones = []
        
        # Para cada medida en la tabla
        for _, row in self.df.iterrows():
            dientes = row['Dientes']
            mm = row['mm']
            
            # Probar todas las repeticiones posibles (de 1 a 20)
            # Ya no usamos repeticiones_fijas para limitar las opciones
            for rep in range(1, self.MAX_REPETICIONES + 1):
                ancho_total = self._calcular_ancho_total(avance_mm, rep)
                
                # Verificar si el ancho total es válido (para rep=1 siempre es válido)
                if rep == 1 or self._validar_ancho_total(ancho_total):
                    desperdicio = self._calcular_desperdicio_individual(mm, avance_mm, rep)
                    if desperdicio < 999:
                        opciones.append(OpcionDesperdicio(
                            dientes=dientes,
                            medida_mm=mm,
                            desperdicio=desperdicio,
                            repeticiones=rep,
                            ancho_total=ancho_total
                        ))
        
        return self._filtrar_opciones_validas(opciones)

    def obtener_mejor_opcion(self, avance_mm: float) -> Union[OpcionDesperdicio, None]:
        """Devuelve la mejor opción (menor desperdicio por encima de 2.6)"""
        opciones = self.calcular_todas_opciones(avance_mm)
        return opciones[0] if opciones else None
        
    def obtener_mejor_opcion_para_unidad(self, avance_mm: float, dientes: float) -> Union[OpcionDesperdicio, None]:
        """
        Devuelve la mejor opción (menor desperdicio) para una unidad específica (dientes)
        Calcula dinámicamente las repeticiones óptimas para esa unidad
        """
        opciones = self.calcular_todas_opciones(avance_mm)
        
        # Filtrar opciones para la unidad específica
        opciones_unidad = [op for op in opciones if op.dientes == dientes]
        
        # Si no hay opciones para esta unidad, devolver None
        if not opciones_unidad:
            return None
            
        # Devolver la opción con menor desperdicio para esta unidad
        return opciones_unidad[0]

    def generar_reporte(self, avance_mm: float) -> Dict:
        """Genera un reporte completo con todas las opciones válidas y la mejor opción"""
        try:
            opciones = self.calcular_todas_opciones(avance_mm)
            mejor_opcion = opciones[0] if opciones else None
            
            return {
                'avance_mm': avance_mm,
                'ancho_maquina': self.ANCHO_MAQUINA,
                'gap_mm': self.GAP_MM,
                'desperdicio_minimo_aceptado': self.DESPERDICIO_MINIMO,
                'mejor_opcion': mejor_opcion.__dict__ if mejor_opcion else None,
                'todas_opciones': [op.__dict__ for op in opciones],
                'total_opciones_validas': len(opciones)
            }
        except Exception as e:
            return {
                'error': str(e),
                'avance_mm': avance_mm,
                'mejor_opcion': None,
                'todas_opciones': [],
                'total_opciones_validas': 0
            }

def mostrar_opciones_por_unidad(avance: float, es_manga: bool = False):
    """
    Muestra las opciones de repeticiones para cada unidad disponible
    para un avance específico
    """
    calculadora = CalculadoraDesperdicio(es_manga=es_manga)
    
    print(f"\n{'=' * 80}")
    print(f"PRUEBA DE CÁLCULO DE REPETICIONES")
    print(f"Avance: {avance} mm | Tipo: {'MANGA' if es_manga else 'ETIQUETA'}")
    print(f"{'=' * 80}")
    
    # Obtener todas las opciones para este avance
    opciones = calculadora.calcular_todas_opciones(avance)
    
    # Agrupar opciones por unidad (dientes)
    opciones_por_unidad = {}
    for op in opciones:
        if op.dientes not in opciones_por_unidad:
            opciones_por_unidad[op.dientes] = []
        opciones_por_unidad[op.dientes].append(op)
    
    # Mostrar la mejor opción global
    mejor_opcion = calculadora.obtener_mejor_opcion(avance)
    if mejor_opcion:
        print(f"\nMEJOR OPCIÓN GLOBAL:")
        print(f"  Dientes: {mejor_opcion.dientes}")
        print(f"  Repeticiones: {mejor_opcion.repeticiones}")
        print(f"  Medida (mm): {mejor_opcion.medida_mm}")
        print(f"  Desperdicio: {mejor_opcion.desperdicio:.4f}")
        print(f"  Ancho total: {mejor_opcion.ancho_total:.2f} mm")
    else:
        print("\nNo se encontró una opción válida para este avance.")
    
    # Mostrar las mejores opciones para cada unidad
    print(f"\nMEJORES OPCIONES POR UNIDAD:")
    print(f"{'Dientes':<10} {'Repeticiones':<15} {'Medida (mm)':<15} {'Desperdicio':<15} {'Ancho Total':<15}")
    print(f"{'-' * 70}")
    
    # Ordenar las unidades para mostrarlas en orden
    unidades_ordenadas = sorted(opciones_por_unidad.keys())
    
    for dientes in unidades_ordenadas:
        # Ordenar opciones por desperdicio
        opciones_ordenadas = sorted(opciones_por_unidad[dientes], key=lambda x: abs(x.desperdicio))
        mejor_op = opciones_ordenadas[0]
        
        # Verificar si coincide con la tabla de repeticiones fijas
        rep_fija = calculadora._obtener_repeticiones_fijas(dientes)
        
        # Mostrar la mejor opción para esta unidad
        print(f"{dientes:<10} {mejor_op.repeticiones:<15} {mejor_op.medida_mm:<15.2f} {mejor_op.desperdicio:<15.4f} {mejor_op.ancho_total:<15.2f}")
        
        # Si hay una repetición fija definida, mostrarla para comparación
        if rep_fija is not None and rep_fija != mejor_op.repeticiones:
            print(f"  ↳ Repetición fija en tabla: {rep_fija} (DIFERENTE DE LA ÓPTIMA)")
    
    print(f"\nTODAS LAS OPCIONES DISPONIBLES POR UNIDAD:")
    for dientes in unidades_ordenadas:
        print(f"\nUnidad: {dientes} dientes")
        print(f"  {'Repeticiones':<15} {'Desperdicio':<15} {'Ancho Total':<15}")
        print(f"  {'-' * 45}")
        
        # Ordenar opciones por repeticiones
        opciones_ordenadas = sorted(opciones_por_unidad[dientes], key=lambda x: x.repeticiones)
        
        for op in opciones_ordenadas:
            print(f"  {op.repeticiones:<15} {op.desperdicio:<15.4f} {op.ancho_total:<15.2f}")

def main():
    """Función principal para probar el cálculo de repeticiones con valores específicos"""
    print("\nPRUEBA DE CÁLCULO DE REPETICIONES CON VALORES ESPECÍFICOS")
    print("=====================================================")
    
    # Valores específicos del caso de prueba
    avance = 70.0
    ancho = 50.0
    pistas = 3
    tintas = 3
    unidad = 64.0
    es_manga = False
    
    print(f"Valores de prueba:")
    print(f"  Ancho: {ancho} mm")
    print(f"  Avance: {avance} mm")
    print(f"  Pistas: {pistas}")
    print(f"  Tintas: {tintas}")
    print(f"  Unidad escogida: {unidad} dientes")
    print(f"  Tipo: {'MANGA' if es_manga else 'ETIQUETA'}")
    
    # Mostrar opciones para este avance
    mostrar_opciones_por_unidad(avance, es_manga)
    
    # Probar la unidad específica
    print("\nPRUEBA DE UNIDAD ESPECÍFICA")
    print("==========================")
    
    calculadora = CalculadoraDesperdicio(es_manga=es_manga)
    mejor_op_unidad = calculadora.obtener_mejor_opcion_para_unidad(avance, unidad)
    
    if mejor_op_unidad:
        print(f"\nMejor opción para unidad {unidad} dientes:")
        print(f"  Repeticiones: {mejor_op_unidad.repeticiones}")
        print(f"  Medida (mm): {mejor_op_unidad.medida_mm}")
        print(f"  Desperdicio: {mejor_op_unidad.desperdicio:.4f}")
        print(f"  Ancho total: {mejor_op_unidad.ancho_total:.2f} mm")
        
        # Ya no hay repeticiones fijas, todas se calculan dinámicamente
        print("\nNota: Ya no se utilizan repeticiones fijas, todas se calculan dinámicamente")
        
        print(f"\nRESPUESTA ESPERADA: 2")
        print(f"RESPUESTA ACTUAL: {mejor_op_unidad.repeticiones}")
        
        # Analizar por qué no coincide con lo esperado
        if mejor_op_unidad.repeticiones != 2:
            print("\nANÁLISIS DEL PROBLEMA:")
            
            # Calcular manualmente el desperdicio para 1 y 2 repeticiones
            avance_efectivo = avance if es_manga else avance + calculadora.GAP_AVANCE
            
            # Para 1 repetición
            desp_1 = abs(mejor_op_unidad.medida_mm - avance_efectivo * 1) / 1
            ancho_1 = calculadora._calcular_ancho_total(avance, 1)
            
            # Para 2 repeticiones
            desp_2 = abs(mejor_op_unidad.medida_mm - avance_efectivo * 2) / 2
            ancho_2 = calculadora._calcular_ancho_total(avance, 2)
            
            print(f"  Para 1 repetición:")
            print(f"    Desperdicio: {desp_1:.4f} mm")
            print(f"    Ancho total: {ancho_1:.2f} mm")
            print(f"  Para 2 repeticiones:")
            print(f"    Desperdicio: {desp_2:.4f} mm")
            print(f"    Ancho total: {ancho_2:.2f} mm")
            
            if ancho_2 > calculadora.ANCHO_MAQUINA:
                print(f"\n  PROBLEMA DETECTADO: 2 repeticiones exceden el ancho máximo de la máquina ({calculadora.ANCHO_MAQUINA} mm)")
            elif desp_1 < desp_2:
                print(f"\n  PROBLEMA DETECTADO: El desperdicio con 1 repetición es menor que con 2 repeticiones")
    else:
        print(f"\nNo se encontró una opción válida para la unidad {unidad} dientes.")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
