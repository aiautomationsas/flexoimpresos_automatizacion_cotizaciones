from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from decimal import Decimal

@dataclass
class Material:
    id: int
    nombre: str
    valor: Decimal
    code: str
    updated_at: Optional[datetime] = None

@dataclass
class Acabado:
    id: int
    nombre: str
    valor: Decimal
    code: str
    updated_at: Optional[datetime] = None

@dataclass
class Cliente:
    id: int
    nombre: str
    codigo: Optional[str] = None
    persona_contacto: Optional[str] = None
    correo_electronico: Optional[str] = None
    telefono: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

@dataclass
class Comercial:
    id: str  # UUID
    nombre: str
    updated_at: Optional[datetime] = None

@dataclass
class Escala:
    cantidad_maxima: int
    precio: Decimal
    cotizacion_id: Optional[int] = None
    id: Optional[int] = None
    updated_at: Optional[datetime] = None

@dataclass
class Cotizacion:
    nombre_cliente: str
    descripcion: str
    tintas: str
    material_id: int
    acabado_id: int
    comercial_id: int
    avance_mm: Decimal
    numero_pistas: int
    avance: Decimal
    planchas_x_separado: bool = False
    existe_troquel: bool = False
    descripcion_tecnica: Optional[str] = None
    referencia_cliente_id: Optional[int] = None
    numero_cotizacion: Optional[str] = None
    colores_tinta: Optional[int] = None
    unidades_por_rollo: Optional[int] = None
    estado: str = 'Pendiente'
    tipo_impresion_id: Optional[int] = None
    id: Optional[int] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    escalas: List[Escala] = None

    def __post_init__(self):
        if self.escalas is None:
            self.escalas = []

@dataclass
class TipoImpresion:
    id: int
    nombre: str
    descripcion: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

@dataclass
class ReferenciaCliente:
    cliente_id: int
    codigo_referencia: str
    id: Optional[int] = None
    descripcion: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    tipo_impresion_id: Optional[int] = None