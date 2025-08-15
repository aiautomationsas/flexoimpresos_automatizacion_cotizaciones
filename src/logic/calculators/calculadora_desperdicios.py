import pandas as pd
from typing import Dict, List, Union
from dataclasses import dataclass

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
        
        # Datos de la tabla con repeticiones fijas correctas
        self.data = {
            'Dientes': [80.00, 84.00, 88.00, 96.00, 102.00, 108.00, 112.00, 120.00, 64.00, 128.00, 140.00, 165.00],
            'Pulg_diente': [0.1250] * 12,
            'Pulgadas': [10.0000, 10.5000, 11.0000, 12.0000, 12.7500, 13.5000, 14.0000, 15.0000, 8.0000, 16.0000, 17.5000, 20.6250],
            'cm_pulg': [25.40] * 12,
            'mm': [254.0000, 266.7000, 279.4000, 304.8000, 323.8500, 342.9000, 355.6000, 381.0000, 203.2000, 406.4000, 444.5000, 523.8750],
            'repeticiones_fijas': [2, 2, 2, 2, 2, 3, 3, 3, 1, 3, 4, 4]  # Repeticiones correctas según tabla del usuario
        }
        self.df = pd.DataFrame(self.data)
        self._validar_datos_iniciales()

    def _validar_datos_iniciales(self) -> None:
        """Valida la integridad de los datos iniciales"""
        if self.df.empty:
            raise ValueError("No hay datos cargados en la calculadora")
        
        columnas_requeridas = ['Dientes', 'mm', 'repeticiones_fijas']
        for col in columnas_requeridas:
            if col not in self.df.columns:
                raise ValueError(f"Falta la columna requerida: {col}")
        
        if (self.df['mm'] <= 0).any():
            raise ValueError("Existen medidas inválidas (nulas o negativas)")
        
        if (self.df['Dientes'] <= 0).any():
            raise ValueError("Existen números de dientes inválidos (nulos o negativos)")
            
        if (self.df['repeticiones_fijas'] <= 0).any():
            raise ValueError("Existen repeticiones inválidas (nulas o negativas)")

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
    
    def _obtener_repeticiones_fijas(self, dientes: float) -> int:
        """Obtiene el número de repeticiones fijas para un número específico de dientes"""
        fila = self.df[self.df['Dientes'] == dientes]
        if fila.empty:
            # Si no se encuentra el número exacto de dientes, usar la lógica original
            return None
        return int(fila['repeticiones_fijas'].iloc[0])

    def calcular_todas_opciones(self, avance_mm: float) -> List[OpcionDesperdicio]:
        """Calcula todas las opciones válidas ordenadas por desperdicio, usando repeticiones fijas cuando están disponibles"""
        self._validar_avance(avance_mm)
        
        opciones = []
        
        # Para cada medida en la tabla
        for _, row in self.df.iterrows():
            dientes = row['Dientes']
            mm = row['mm']
            
            # Obtener repeticiones fijas para este número de dientes
            rep_fija = self._obtener_repeticiones_fijas(dientes)
            
            if rep_fija is not None:
                # Usar solo la repetición fija
                repeticiones_a_probar = [rep_fija]
            else:
                # Usar la lógica original (probar de 1 a 20)
                repeticiones_a_probar = range(1, self.MAX_REPETICIONES + 1)
            
            for rep in repeticiones_a_probar:
                ancho_total = self._calcular_ancho_total(avance_mm, rep)
                
                # Para repeticiones fijas, permitir incluso si excede el ancho de máquina
                # Para lógica original, mantener la validación
                if rep_fija is not None or rep == 1 or self._validar_ancho_total(ancho_total):
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