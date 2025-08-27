#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script de depuración para verificar el cálculo de repeticiones en la aplicación real
"""

import sys
import os
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Union, Optional

# Añadir el directorio src al path para poder importar los módulos
sys.path.append(os.path.abspath('.'))

try:
    from src.logic.calculators.calculadora_desperdicios import CalculadoraDesperdicio, OpcionDesperdicio
    print("Módulos importados correctamente")
except ImportError as e:
    print(f"Error importando módulos: {e}")
    sys.exit(1)

def debug_repeticiones():
    """Función para depurar el cálculo de repeticiones en la aplicación real"""
    print("\nDEPURACIÓN DE CÁLCULO DE REPETICIONES EN LA APLICACIÓN REAL")
    print("========================================================")
    
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
    
    # Crear instancia de la calculadora
    try:
        calculadora = CalculadoraDesperdicio(es_manga=es_manga)
        print("\nCalculadora inicializada correctamente")
        
        # Verificar métodos disponibles
        print("\nMétodos disponibles en la calculadora:")
        for method in dir(calculadora):
            if not method.startswith('_'):
                print(f"  - {method}")
        
        # Verificar si existe el método obtener_mejor_opcion_para_unidad
        if 'obtener_mejor_opcion_para_unidad' not in dir(calculadora):
            print("\n¡PROBLEMA DETECTADO! El método 'obtener_mejor_opcion_para_unidad' no existe en la calculadora.")
            print("Es posible que los cambios no se hayan aplicado correctamente.")
        
        # Probar el método calcular_todas_opciones
        print("\nProbando método calcular_todas_opciones:")
        opciones = calculadora.calcular_todas_opciones(avance)
        print(f"  Se encontraron {len(opciones)} opciones válidas")
        
        # Filtrar opciones para la unidad específica
        opciones_unidad = [op for op in opciones if op.dientes == unidad]
        print(f"\nOpciones para unidad {unidad} dientes:")
        if opciones_unidad:
            for op in opciones_unidad:
                print(f"  Repeticiones: {op.repeticiones}, Desperdicio: {op.desperdicio:.4f}, Ancho total: {op.ancho_total:.2f}")
        else:
            print("  No se encontraron opciones para esta unidad")
        
        # Probar el método obtener_mejor_opcion
        print("\nProbando método obtener_mejor_opcion:")
        mejor_opcion = calculadora.obtener_mejor_opcion(avance)
        if mejor_opcion:
            print(f"  Mejor opción global: Unidad {mejor_opcion.dientes} dientes, Repeticiones: {mejor_opcion.repeticiones}")
        else:
            print("  No se encontró una mejor opción global")
        
        # Probar el método obtener_mejor_opcion_para_unidad
        try:
            print("\nProbando método obtener_mejor_opcion_para_unidad:")
            mejor_opcion_unidad = calculadora.obtener_mejor_opcion_para_unidad(avance, unidad)
            if mejor_opcion_unidad:
                print(f"  Mejor opción para unidad {unidad}: Repeticiones: {mejor_opcion_unidad.repeticiones}")
            else:
                print(f"  No se encontró una mejor opción para la unidad {unidad}")
        except AttributeError:
            print("  ¡ERROR! El método obtener_mejor_opcion_para_unidad no existe en la calculadora")
            print("  Esto confirma que los cambios no se aplicaron correctamente")
        
        # Ya no hay repeticiones fijas, todas se calculan dinámicamente
        print("\nNota: Ya no se utilizan repeticiones fijas, todas se calculan dinámicamente")
        
        # Calcular manualmente el desperdicio para 1 y 2 repeticiones
        print("\nCálculo manual del desperdicio:")
        try:
            medida_mm = 0
            for _, row in calculadora.df.iterrows():
                if row['Dientes'] == unidad:
                    medida_mm = row['mm']
                    break
            
            avance_efectivo = avance if es_manga else avance + calculadora.GAP_AVANCE
            
            # Para 1 repetición
            desp_1 = abs(medida_mm - avance_efectivo * 1) / 1
            ancho_1 = calculadora._calcular_ancho_total(avance, 1)
            
            # Para 2 repeticiones
            desp_2 = abs(medida_mm - avance_efectivo * 2) / 2
            ancho_2 = calculadora._calcular_ancho_total(avance, 2)
            
            print(f"  Medida para unidad {unidad}: {medida_mm} mm")
            print(f"  Avance efectivo: {avance_efectivo} mm")
            print(f"  Para 1 repetición:")
            print(f"    Desperdicio: {desp_1:.4f} mm")
            print(f"    Ancho total: {ancho_1:.2f} mm")
            print(f"  Para 2 repeticiones:")
            print(f"    Desperdicio: {desp_2:.4f} mm")
            print(f"    Ancho total: {ancho_2:.2f} mm")
            
            # Verificar cuál tiene menor desperdicio
            if desp_1 < desp_2:
                print("\n  RESULTADO: 1 repetición tiene menor desperdicio")
            else:
                print("\n  RESULTADO: 2 repeticiones tienen menor desperdicio")
                
            # Verificar si el ancho total está dentro del límite
            if ancho_2 > calculadora.ANCHO_MAQUINA:
                print(f"  ADVERTENCIA: 2 repeticiones exceden el ancho máximo de la máquina ({calculadora.ANCHO_MAQUINA} mm)")
        except Exception as e:
            print(f"  Error en el cálculo manual: {e}")
        
    except Exception as e:
        print(f"Error inicializando la calculadora: {e}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    debug_repeticiones()
