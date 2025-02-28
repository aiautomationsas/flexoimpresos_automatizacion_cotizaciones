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
        
    def calcular_metros(self, escala: int, datos: DatosEscala, es_manga: bool = False) -> float:
        """
        Calcula los metros según la fórmula: =(A8/$E$3)*(($D$4+$C$5)/1000)
        donde:
        - A8 = escala
        - $E$3 = pistas
        - $D$4 = avance + gap (gap es 0 para mangas, 2.6 para etiquetas)
        - $C$5 = desperdicio de la unidad de montaje
        """
        GAP_FIJO = 0 if es_manga else 2.6  # Gap es 0 para mangas, 2.6 para etiquetas
        d4 = datos.avance_total + GAP_FIJO  # Avance + gap fijo
        return (escala / datos.pistas) * ((d4 + datos.desperdicio) / 1000)
        
    def calcular_tiempo_horas(self, metros: float, datos: DatosEscala) -> float:
        """Calcula el tiempo en horas según la fórmula: metros / velocidad_maquina / 60"""
        return metros / datos.velocidad_maquina / 60
        
    def calcular_montaje(self, num_tintas: int, datos: DatosEscala) -> float:
        """Calcula el montaje según la fórmula: Tintas * MO Montaje"""
        return num_tintas * datos.mo_montaje
        
    def calcular_mo_y_maq(self, tiempo_horas: float, num_tintas: int, datos: DatosEscala, es_manga: bool = False) -> float:
        """
        Calcula MO y Maq según la fórmula:
        Para etiquetas:
            SI(tintas>0;SI(F8<1;MO Impresión;MO Impresión*(F8)));SI(F8<1;MO Troquelado;MO Troquelado*(F8)))
        Para mangas:
            Se suma además MO Sellado (50000) y MO Corte (50000)
        """
        # Constantes para mangas
        MO_SELLADO = 50000
        MO_CORTE = 50000
        
        # Cálculo base (igual que antes)
        if num_tintas > 0:
            if tiempo_horas < 1:
                base = datos.mo_impresion
            else:
                base = datos.mo_impresion * tiempo_horas
        else:
            if tiempo_horas < 1:
                base = datos.mo_troquelado
            else:
                base = datos.mo_troquelado * tiempo_horas
        
        # Para mangas, sumar MO Sellado y MO Corte
        if es_manga:
            return base + MO_SELLADO + MO_CORTE
        
        return base
            
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
        
    def calcular_desperdicio(self, num_tintas: int, ancho: float, papel_lam: float, valor_material: float, datos: DatosEscala, porcentaje_desperdicio: float = 0.10) -> float:
        """
        Calcula el costo del desperdicio combinando:
        1. Desperdicio por tintas: MM_Totales * valor_material * (ancho_total + GAP_PLANCHAS)
        2. Porcentaje del costo del papel/laminado
        """
        # Constantes
        MM_COLOR = 30000  # mm por color
        GAP_PLANCHAS = 40  # gap constante de planchas

        print("\n=== DETALLE COMPLETO DE CÁLCULO DE DESPERDICIO ===")
        print(f"Parámetros de entrada:")
        print(f"- Número de tintas: {num_tintas}")
        print(f"- Ancho: {ancho} mm")
        print(f"- Papel/lam: ${papel_lam:.2f}")
        print(f"- Valor material: ${valor_material:.6f}/mm²")
        print(f"- Porcentaje desperdicio: {porcentaje_desperdicio * 100:.1f}%")
        print(f"- MM por color: {MM_COLOR}")
        print(f"- Gap planchas: {GAP_PLANCHAS}")

        # Cálculo de desperdicio por tintas
        if num_tintas > 0:
            mm_totales = MM_COLOR * num_tintas
            # El método devuelve una tupla, tomamos solo el primer valor
            ancho_total = self.calcular_ancho_total(num_tintas, datos.pistas, ancho)
            if isinstance(ancho_total, tuple):
                ancho_total = ancho_total[0]
            desperdicio_tintas = (mm_totales * valor_material * (ancho_total + GAP_PLANCHAS)) / 1000000
            
            print(f"\n--- Verificación del Cálculo ---")
            print(f"MM Totales: {mm_totales}")
            print(f"Valor Material: {valor_material}")
            print(f"Ancho Total: {ancho_total}")
            print(f"GAP Planchas: {GAP_PLANCHAS}")
            print(f"Operación: ({mm_totales} × {valor_material} × ({ancho_total} + {GAP_PLANCHAS})) ÷ 1,000,000")
            print(f"Resultado: {desperdicio_tintas}")
        else:
            desperdicio_tintas = 0
            print("\n--- Sin tintas, desperdicio por tintas = $0 ---")

        # Parte 2: Porcentaje del costo del papel/laminado
        desperdicio_porcentaje = papel_lam * porcentaje_desperdicio
        
        print("\n--- Cálculo Desperdicio por Porcentaje ---")
        print(f"Papel/lam: ${papel_lam:.2f}")
        print(f"Porcentaje desperdicio: {porcentaje_desperdicio * 100:.1f}%")
        print(f"Desperdicio por porcentaje: ${desperdicio_porcentaje:.2f}")
        
        # Desperdicio total
        desperdicio_total = desperdicio_tintas + desperdicio_porcentaje
        
        print("\n=== RESUMEN DESPERDICIO ===")
        print(f"Desperdicio por tintas: ${desperdicio_tintas:.2f}")
        print(f"Desperdicio por porcentaje: ${desperdicio_porcentaje:.2f}")
        print(f"Desperdicio total: ${desperdicio_total:.2f}")
        
        return desperdicio_total
        
    def calcular_valor_unidad_full(self, suma_costos: float, datos: DatosEscala, 
                                 escala: int, valor_plancha: float, valor_troquel: float) -> float:
        """
        Calcula el valor por unidad según la fórmula:
        valor_unidad = (suma_costos / ((100 - rentabilidad) / 100) + valor_planchas + valor_troquel) / escala
        """
        try:
            # Asegurarnos de que los valores son números
            valor_plancha = float(valor_plancha) if valor_plancha else 0
            valor_troquel = float(valor_troquel) if valor_troquel else 0
            suma_costos = float(suma_costos) if suma_costos else 0
            
            print("\n=== DEPURACIÓN VALOR UNIDAD ===")
            print(f"suma_costos: {suma_costos}")
            print(f"rentabilidad: {datos.rentabilidad}")
            print(f"valor_plancha: {valor_plancha}")
            print(f"valor_troquel: {valor_troquel}")
            print(f"escala: {escala}")
            
            # Asegurar que escala no sea cero
            if escala <= 0:
                print("Escala es cero o negativa, retornando 0")
                return 0
            
            # Cálculo paso a paso
            factor_rentabilidad = (100 - datos.rentabilidad) / 100
            print(f"factor_rentabilidad: {factor_rentabilidad}")
            
            # Corregir el cálculo de costos indirectos
            costos_indirectos = suma_costos / factor_rentabilidad
            print(f"costos_indirectos: {costos_indirectos}")
            
            costos_fijos = valor_plancha + valor_troquel
            print(f"costos_fijos: {costos_fijos}")
            
            costos_totales = costos_indirectos + costos_fijos
            print(f"costos_totales: {costos_totales}")
            
            # Calcular valor por unidad
            valor_unidad = costos_totales / escala
            print(f"valor_unidad: {valor_unidad}")
            print(f"tipo valor_unidad: {type(valor_unidad)}")
            
            # Verificar que el resultado sea un número válido
            if not isinstance(valor_unidad, (int, float)) or valor_unidad < 0:
                print("Valor unidad inválido, retornando 0")
                return 0
            
            return valor_unidad
        
        except Exception as e:
            print(f"Error en cálculo de valor unidad: {str(e)}")
            return 0
        
    def calcular_mm(self, valor_unidad: float, escala: int) -> float:
        """
        Calcula el valor en millones según la fórmula:
        valor_mm = valor_unidad * escala / 1000000
        """
        try:
            # Asegurarnos de que los valores son números
            valor_unidad = float(valor_unidad) if valor_unidad else 0
            escala = int(escala) if escala else 0
            
            # Calcular valor en millones
            valor_mm = valor_unidad * escala / 1000000
            print(f"valor_mm: {valor_mm}")
            print(f"tipo valor_mm: {type(valor_mm)}")
            
            # Verificar que el resultado sea un número válido
            if not isinstance(valor_mm, (int, float)) or valor_mm < 0:
                print("Valor MM inválido, retornando 0")
                return 0
            
            return valor_mm
        
        except Exception as e:
            print(f"Error en cálculo de valor MM: {str(e)}")
            return 0
        
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
        Calcula los costos para cada escala de producción
        
        Args:
            datos: Objeto con los datos base para el cálculo
            num_tintas: Número de tintas utilizadas
            valor_etiqueta: Valor por etiqueta
            valor_plancha: Valor de la plancha
            valor_troquel: Valor del troquel
            valor_material: Valor del material por mm²
            valor_acabado: Valor del acabado por mm²
            es_manga: True si es manga, False si es etiqueta
            
        Returns:
            List[Dict]: Lista de resultados para cada escala
        """
        print("\n=== VALORES INICIALES PARA CÁLCULO ===")
        print(f"Ancho: {datos.ancho}")
        print(f"Avance: {datos.avance}")
        print(f"Área etiqueta: {datos.area_etiqueta}")
        print(f"Valor material: ${valor_material}")
        print(f"Valor acabado: ${valor_acabado}")
        print(f"Es manga: {es_manga}")
        
        resultados = []
        
        try:
            # Convertir todos los valores a float para asegurar compatibilidad
            valor_etiqueta = float(valor_etiqueta)
            valor_plancha = float(valor_plancha)
            valor_troquel = float(valor_troquel)
            valor_material = float(valor_material)
            valor_acabado = float(valor_acabado)
            
            # Ajustar porcentaje de desperdicio y rentabilidad según el tipo
            porcentaje_desperdicio = 0.30 if es_manga else 0.10  # 30% para mangas, 10% para etiquetas
            datos.rentabilidad = 45.0 if es_manga else 40.0  # 45% para mangas, 40% para etiquetas
            
            for escala in datos.escalas:
                # Calcular metros lineales considerando si es manga o no
                metros = self.calcular_metros(escala, datos, es_manga)
                
                # Calcular tiempo en horas
                tiempo_horas = self.calcular_tiempo_horas(metros, datos)
                
                # Calcular costos
                montaje = self.calcular_montaje(num_tintas, datos)
                mo_y_maq = self.calcular_mo_y_maq(tiempo_horas, num_tintas, datos, es_manga)
                tintas = self.calcular_tintas(escala, num_tintas, valor_etiqueta, datos)
                papel_lam = self.calcular_papel_lam(escala, datos.area_etiqueta, valor_material, valor_acabado)
                
                # Calcular componentes del desperdicio
                MM_COLOR = 30000  # mm por color
                GAP_PLANCHAS = 40  # gap constante de planchas

                if num_tintas > 0:
                    mm_totales = MM_COLOR * num_tintas  # S7
                    
                    if es_manga:
                        # Cálculo específico para mangas
                        C3 = 0  # GAP para mangas es 0
                        B3 = datos.ancho  # B3 es el ancho
                        D3 = B3 + C3  # D3 = ancho + GAP_MANGA
                        E3 = datos.pistas
                        Q3 = D3 * E3 + C3  # Q3 = (ancho + GAP_MANGA) * pistas + GAP_MANGA
                        GAP_FIJO = 50  # R3 para mangas
                        s3 = GAP_FIJO + Q3  # R3 + Q3
                        
                        # Desperdicio para mangas = S7 × S3 × O7
                        desperdicio_tintas = mm_totales * s3 * (valor_material / 1000000)
                    else:
                        # Cálculo para etiquetas (código existente)
                        ancho_total = self.calcular_ancho_total(num_tintas, datos.pistas, datos.ancho)
                        if isinstance(ancho_total, tuple):
                            ancho_total = ancho_total[0]
                        desperdicio_tintas = (mm_totales * valor_material * (ancho_total + GAP_PLANCHAS)) / 1000000
                else:
                    desperdicio_tintas = 0
                
                desperdicio_porcentaje = papel_lam * porcentaje_desperdicio
                desperdicio = desperdicio_tintas + desperdicio_porcentaje
                
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
                    'desperdicio': desperdicio,
                    'desperdicio_tintas': desperdicio_tintas,
                    'desperdicio_porcentaje': desperdicio_porcentaje,
                    'num_tintas': num_tintas,
                    'ancho': datos.ancho,
                    'porcentaje_desperdicio': porcentaje_desperdicio
                })
            
            return resultados
        
        except Exception as e:
            raise ValueError(f"Error en cálculo de costos: {str(e)}")
