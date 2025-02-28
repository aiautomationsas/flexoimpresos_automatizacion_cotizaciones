from dataclasses import dataclass, field
from typing import List, Dict, Optional
from decimal import Decimal
from uuid import UUID
from datetime import datetime

@dataclass
class EtiquetaConfig:
    """Configuración de la etiqueta o manga a cotizar"""
    ancho: float
    avance: float
    pistas: int
    num_tintas: int
    area_etiqueta: float = 0.0
    desperdicio: float = 0.0
    es_manga: bool = False
    
    @property
    def gap(self) -> float:
        """Gap según tipo de producto"""
        return 0.0 if self.es_manga else 3.0
    
    @property
    def gap_avance(self) -> float:
        """Gap de avance según tipo de producto"""
        return 0.0 if self.es_manga else 2.6

@dataclass
class MaterialConfig:
    """Configuración de materiales y acabados"""
    material_id: int
    material_nombre: str
    material_valor: float
    acabado_id: int = 0
    acabado_nombre: str = "Sin acabado"
    acabado_valor: float = 0.0
    
    @property
    def tiene_acabado(self) -> bool:
        """Indica si tiene acabado configurado"""
        return self.acabado_id > 0 and self.acabado_valor > 0

@dataclass
class ConfiguracionProduccion:
    """Configuración completa de producción"""
    etiqueta: EtiquetaConfig
    material: MaterialConfig
    escalas: List[int] = field(default_factory=lambda: [1000, 2000, 3000, 5000])
    incluye_planchas: bool = False
    troquel_existe: bool = False
    num_rollos: int = 1000
    
    @property
    def porcentaje_desperdicio(self) -> float:
        """Porcentaje de desperdicio según tipo"""
        return 0.30 if self.etiqueta.es_manga else 0.10
    
    @property
    def rentabilidad(self) -> float:
        """Porcentaje de rentabilidad según tipo"""
        return 45.0 if self.etiqueta.es_manga else 40.0

@dataclass
class ResultadoEscala:
    """Resultado del cálculo para una escala específica"""
    escala: int
    valor_unidad: float
    valor_mm: float
    metros: float
    tiempo_horas: float
    montaje: float
    mo_y_maq: float
    tintas: float
    papel_lam: float
    desperdicio: float
    desperdicio_tintas: float
    desperdicio_porcentaje: float
    
    def formato_desperdicio(self) -> str:
        """Formatea el desperdicio para mostrar en la tabla"""
        return f"${self.desperdicio_tintas:,.2f} + ${self.desperdicio_porcentaje:,.2f} = ${self.desperdicio:,.2f}"
    
    def formato_valor_unidad(self) -> str:
        """Formatea el valor por unidad"""
        return f"${self.valor_unidad:.2f}"
    
    def formato_valor_mm(self) -> str:
        """Formatea el valor en millones"""
        return f"${self.valor_mm:.3f}"

@dataclass
class ResultadoCotizacion:
    """Resultado completo de la cotización"""
    config: ConfiguracionProduccion
    resultados_escalas: List[ResultadoEscala] = field(default_factory=list)
    valor_plancha: float = 0.0
    valor_plancha_separado: Optional[float] = None
    valor_troquel: float = 0.0
    identificador: str = ""
    
    @property
    def mejor_resultado(self) -> Optional[ResultadoEscala]:
        """Devuelve el resultado de la primera escala si existe"""
        return self.resultados_escalas[0] if self.resultados_escalas else None

@dataclass
class Cotizacion:
    id: Optional[int] = None
    nombre_cliente: str = ''
    descripcion: str = ''
    tintas: str = ''
    material_id: Optional[int] = None
    acabado_id: Optional[int] = None
    comercial_id: Optional[int] = None
    updated_at: Optional[datetime] = None
    planchas_x_separado: bool = False
    existe_troquel: bool = False
    avance_mm: float = 0.0
    descripcion_tecnica: Optional[str] = None
    numero_pistas: int = 0
    referencia_cliente_id: Optional[int] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    numero_cotizacion: Optional[str] = None
    colores_tinta: Optional[int] = None
    unidades_por_rollo: Optional[int] = None
    estado: str = 'Pendiente'
    avance: float = 0.0
    tipo_impresion_id: Optional[int] = None
    escalas: List['Escala'] = field(default_factory=list)

@dataclass
class Material:
    id: Optional[int] = None
    nombre: str = ''
    valor: float = 0.0
    updated_at: Optional[datetime] = None
    code: str = ''

@dataclass
class Acabado:
    id: Optional[int] = None
    nombre: str = ''
    valor: float = 0.0
    updated_at: Optional[datetime] = None
    code: str = ''

@dataclass
class Cliente:
    id: Optional[int] = None
    nombre: str = ''
    codigo: Optional[str] = None
    persona_contacto: Optional[str] = None
    correo_electronico: Optional[str] = None
    telefono: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

@dataclass
class Comercial:
    id: Optional[UUID] = None
    nombre: str = ''
    updated_at: Optional[datetime] = None

@dataclass
class Escala:
    id: Optional[int] = None
    cotizacion_id: Optional[int] = None
    cantidad_maxima: int = 0
    precio: float = 0.0
    updated_at: Optional[datetime] = None

@dataclass
class ReferenciaCliente:
    cliente_id: int
    codigo_referencia: str
    id: Optional[int] = None
    descripcion: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    tipo_impresion_id: Optional[int] = None

@dataclass
class TipoImpresion:
    id: Optional[int] = None
    nombre: str = ''
    descripcion: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None 