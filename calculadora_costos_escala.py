from dataclasses import dataclass
from typing import List, Dict, Tuple
import math
import pandas as pd
from calculadora_desperdicios import CalculadoraDesperdicio
from calculadora_base import CalculadoraBase

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
    velocidad_maquina: float = 20.0  # Valor fijo
    mo_montaje: float = 5000.0  # Valor fijo
    mo_impresion: float = 50000.0  # Valor fijo
    mo_troquelado: float = 50000.0  # Valor fijo
    valor_gr_tinta: float = 30.0  # Valor fijo
    rentabilidad: float = 40.0  # Valor por defecto para etiquetas
    area_etiqueta: float = 0.0  # Se calcula o se recibe
    porcentaje_desperdicio: float = 10.0  # Porcentaje de desperdicio por defecto
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
    
    def __init__(self, ancho_maximo: float = 325):
        """
        Inicializa la calculadora de costos por escala.
        
        Args:
            ancho_maximo: Ancho máximo de la máquina en mm
        """
        super().__init__()
        self.ANCHO_MAXIMO = ancho_maximo
        self.GAP = 3  # GAP entre pistas
        
        # Constantes para cálculos
        self.C3 = self.GAP  # GAP fijo para cálculos
        self.MM_COLOR = 30000  # MM de color para cálculo de desperdicio
        self.GAP_FIJO = 50  # R3 es 50 tanto para mangas como etiquetas
        
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
        
    def calcular_metros(self, escala: int, datos: DatosEscala, es_manga: bool = False) -> float:
        """
        Calcula los metros según la fórmula: (Escala / Pistas) * ((Avance_total + Desperdicio_unidad) / 1000)
        donde:
        - Avance_total = Avance + GAP (2.6 para etiquetas, 0 para mangas)
        - Desperdicio_unidad = desperdicio por los dientes del troquel
        """
        # GAP solo para etiquetas
        gap = 2.6 if not es_manga else 0
        
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
        MO_SELLADO = 50000
        MO_CORTE = 50000
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
        # Calcular R11
        R11 = 0.00000800 * num_tintas * area_etiqueta
        
        # Costo que varía con la escala
        costo_variable = R11 * escala
        
        # Costo fijo por número de tintas
        costo_fijo = 100 * num_tintas * datos.valor_gr_tinta
        
        print(f"\n--- Verificación del Cálculo de Tintas ---")
        print(f"R11 (costo por etiqueta): ${R11:.8f}")
        print(f"Escala: {escala}")
        print(f"Costo variable (R11 * escala): ${costo_variable:.2f}")
        print(f"Costo fijo (100 * num_tintas * valor_gr_tinta): ${costo_fijo:.2f}")
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
        
    def calcular_desperdicio_tintas(self, datos: DatosEscala, num_tintas: int, valor_material: float, es_manga: bool = False) -> float:
        """
        Calcula el desperdicio de tintas según la fórmula:
        S7 × S3 × O7
        donde:
        - S7 = MM_COLOR * num_tintas
        - S3 = GAP_FIJO + Q3
        - O7 = valor_material / 1000000
        """
        if num_tintas <= 0:
            return 0
            
        # Calcular mm totales
        mm_totales = self.MM_COLOR * num_tintas
        
        # Calcular Q3 usando el método auxiliar
        resultado_q3 = self._calcular_q3(
            num_tintas=num_tintas,
            ancho=datos.ancho,
            pistas=datos.pistas,
            es_manga=es_manga
        )
        
        # Extraer Q3 del resultado
        q3 = resultado_q3['q3']
        c3 = resultado_q3['c3']
        d3 = resultado_q3['d3']
        
        # Calcular S3 = GAP_FIJO + Q3
        s3 = self.GAP_FIJO + q3
        
        # Calcular desperdicio
        desperdicio_tintas = mm_totales * s3 * (valor_material / 1000000)
        
        print(f"\n--- Verificación del Cálculo de Desperdicio Tintas ---")
        print(f"MM Totales (S7): {mm_totales}")
        print(f"Valor Material (O7): {valor_material}")
        print(f"C3 (GAP): {c3}")
        print(f"D3 (ancho + GAP): {d3}")
        print(f"E3 (pistas): {datos.pistas}")
        print(f"Q3: {q3}")
        print(f"R3 (GAP_FIJO): {self.GAP_FIJO}")
        print(f"S3 (GAP_FIJO + Q3): {s3}")
        print(f"Desperdicio tintas: ${desperdicio_tintas:.2f}")
        
        return desperdicio_tintas
        
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
                
                tintas = self.calcular_tintas(escala, num_tintas, datos.area_etiqueta, datos)
                print(f"Tintas: ${tintas:.2f}")
                
                papel_lam = self.calcular_papel_lam(escala, datos.area_etiqueta, valor_material, valor_acabado)
                print(f"Papel/lam: ${papel_lam:.2f}")
                
                # 3.4 Calcular desperdicios
                desperdicio_porcentaje = papel_lam * porcentaje_desperdicio
                print(f"Desperdicio porcentaje: ${desperdicio_porcentaje:.2f}")

                if num_tintas > 0:
                    desperdicio_tintas = self.calcular_desperdicio_tintas(
                        datos=datos,
                        num_tintas=num_tintas,
                        valor_material=valor_material,
                        es_manga=es_manga
                    )
                else:
                    desperdicio_tintas = 0
                    print(f"Desperdicio tintas: ${desperdicio_tintas:.2f} (no hay tintas)")
                
                # Desperdicio total
                desperdicio = desperdicio_porcentaje + desperdicio_tintas
                print(f"Desperdicio total: ${desperdicio:.2f}")
                
                # 3.5 Calcular suma de costos variables
                suma_costos = montaje + mo_y_maq + tintas + papel_lam + desperdicio
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
                    'desperdicio': datos.desperdicio,  # Agregar el desperdicio original (por dientes)
                    'desperdicio_tintas': desperdicio_tintas,
                    'desperdicio_porcentaje': desperdicio_porcentaje,
                    'num_tintas': num_tintas,
                    'ancho': datos.ancho,
                    'avance': datos.avance,  # Agregar el avance a los resultados
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
