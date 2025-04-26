from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union, TYPE_CHECKING
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
    planchas_por_separado: bool = False
    troquel_existe: bool = False
    num_rollos: int = 100
    
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
class TipoGrafado:
    """Representa un tipo de grafado en el sistema."""
    id: int
    nombre: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'TipoGrafado':
        """Crea una instancia de TipoGrafado desde un diccionario."""
        return TipoGrafado(
            id=data['id'],
            nombre=data['nombre']
        )

@dataclass
class Material:
    id: Optional[int] = None
    nombre: str = ''
    valor: float = 0.0
    updated_at: Optional[datetime] = None
    code: str = ''
    id_adhesivos: Optional[int] = None
    adhesivo_tipo: Optional[str] = None

@dataclass
class Adhesivo:
    id: Optional[int] = None
    tipo: str = ''
    descripcion: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

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
    id: UUID
    nombre: str = ''
    created_at: Optional[datetime] = None
    email: Optional[str] = None
    celular: Optional[int] = None

@dataclass
class TipoProducto:
    id: Optional[int] = None
    nombre: str = ''
    descripcion: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

@dataclass
class PrecioEscala:
    """Representa un precio específico para una escala"""
    id: Optional[int] = None
    escala_id: Optional[int] = None
    precio: float = 0.0
    tipo_precio: str = 'normal'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Escala:
    """Representa una escala de cotización con sus cálculos y precios asociados"""
    id: Optional[int] = None
    cotizacion_id: Optional[int] = None
    escala: int = 0
    valor_unidad: float = 0.0
    metros: float = 0.0
    tiempo_horas: float = 0.0
    montaje: float = 0.0
    mo_y_maq: float = 0.0
    tintas: float = 0.0
    papel_lam: float = 0.0
    desperdicio_total: float = 0.0
    updated_at: Optional[datetime] = None
    precios: List[PrecioEscala] = field(default_factory=list)

    def agregar_precio(self, precio: float, tipo: str = 'normal') -> None:
        """Agrega un nuevo precio a la escala"""
        nuevo_precio = PrecioEscala(
            escala_id=self.id,
            precio=precio,
            tipo_precio=tipo
        )
        self.precios.append(nuevo_precio)

    def obtener_precio(self, tipo: str = 'normal') -> Optional[float]:
        """Obtiene el precio más reciente de un tipo específico"""
        precios_tipo = [p for p in self.precios if p.tipo_precio == tipo]
        if not precios_tipo:
            return None
        return max(precios_tipo, key=lambda x: x.created_at or datetime.min).precio

    @property
    def precio_normal(self) -> float:
        """Obtiene el precio normal más reciente"""
        return self.obtener_precio('normal') or self.valor_unidad

    def to_dict(self) -> Dict[str, Any]:
        """Convierte la escala a un diccionario"""
        return {
            'id': self.id,
            'cotizacion_id': self.cotizacion_id,
            'escala': self.escala,
            'valor_unidad': self.valor_unidad,
            'metros': self.metros,
            'tiempo_horas': self.tiempo_horas,
            'montaje': self.montaje,
            'mo_y_maq': self.mo_y_maq,
            'tintas': self.tintas,
            'papel_lam': self.papel_lam,
            'desperdicio_total': self.desperdicio_total,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Escala':
        """Crea una escala desde un diccionario"""
        return Escala(
            id=data.get('id'),
            cotizacion_id=data.get('cotizacion_id'),
            escala=data.get('escala'),
            valor_unidad=data.get('valor_unidad'),
            metros=data.get('metros'),
            tiempo_horas=data.get('tiempo_horas'),
            montaje=data.get('montaje'),
            mo_y_maq=data.get('mo_y_maq'),
            tintas=data.get('tintas'),
            papel_lam=data.get('papel_lam'),
            desperdicio_total=data.get('desperdicio_total'),
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None
        )

@dataclass
class ReferenciaCliente:
    """Modelo de referencia de cliente que incluye relaciones con cliente y comercial"""
    cliente_id: int
    id: Optional[int] = None
    id_usuario: Optional[UUID] = None
    descripcion: Optional[str] = None
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    tiene_cotizacion: Optional[bool] = False
    # Relaciones
    cliente: Optional[Cliente] = None
    perfil: Optional[Dict] = None

@dataclass
class MotivoRechazo:
    """Representa un motivo de rechazo de cotización"""
    id: int
    motivo: str

@dataclass
class EstadoCotizacion:
    """Representa un estado de cotización"""
    id: int
    estado: str
    motivo_rechazo_id: Optional[int] = None

@dataclass
class FormaPago:
    """Representa una forma de pago"""
    id: int
    descripcion: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'FormaPago':
        """Crea una instancia de FormaPago desde un diccionario."""
        return FormaPago(
            id=data['id'],
            descripcion=data['descripcion']
        )

@dataclass
class Cotizacion:
    """Modelo de cotización que obtiene datos de cliente y comercial a través de la tabla referencias_cliente"""
    id: Optional[int] = None
    referencia_cliente_id: Optional[int] = None  # Relación principal con referencias_cliente
    material_id: Optional[int] = None
    acabado_id: Optional[int] = None
    num_tintas: Optional[int] = None
    num_paquetes_rollos: Optional[int] = None
    numero_cotizacion: Optional[int] = None
    es_manga: bool = False
    tipo_grafado_id: Optional[int] = None
    tipo_grafado: Optional[TipoGrafado] = None
    valor_troquel: Optional[Decimal] = None
    valor_plancha_separado: Optional[Decimal] = None
    actualizado_en: Optional[datetime] = None
    planchas_x_separado: bool = False
    numero_pistas: int = 0
    tipo_producto_id: Optional[int] = None
    es_recotizacion: bool = False
    modificado_por: Optional[str] = None
    existe_troquel: bool = False
    ancho: float = 0.0
    avance: float = 0.0
    escala_id: Optional[int] = None
    fecha_creacion: Optional[datetime] = None
    ultima_modificacion_inputs: Optional[datetime] = None
    identificador: Optional[str] = None
    estado_id: int = 1
    id_motivo_rechazo: Optional[int] = None
    colores_tinta: Optional[str] = None
    forma_pago_id: Optional[int] = None
    altura_grafado: Optional[float] = None
    escalas: List[Escala] = field(default_factory=list)
    # Relaciones
    referencia_cliente: Optional[ReferenciaCliente] = None
    material: Optional[Material] = None
    acabado: Optional[Acabado] = None
    tipo_producto: Optional[TipoProducto] = None
    forma_pago: Optional[FormaPago] = None
    # --- NUEVO: Campo para perfil --- 
    perfil_comercial_info: Optional[Dict] = None # Guardará {'id': UUID, 'nombre': str, ...}
    # --- FIN NUEVO ---

    @property
    def cliente(self) -> Optional[Cliente]:
        """Obtiene el cliente a través de la referencia"""
        if self.referencia_cliente and hasattr(self.referencia_cliente, 'cliente'):
            return self.referencia_cliente.cliente
        return None

    @property
    def perfil(self) -> Optional[Dict]:
        """Obtiene el perfil a través de la referencia"""
        if self.referencia_cliente and hasattr(self.referencia_cliente, 'perfil'):
            return self.referencia_cliente.perfil
        return None

    def __init__(
        self,
        id=None,
        referencia_cliente_id=None,
        material_id=None,
        acabado_id=None,
        num_tintas=None,
        num_paquetes_rollos=None,
        numero_cotizacion=None,
        es_manga=False,
        tipo_grafado_id=None,
        valor_troquel=None,
        valor_plancha_separado=None,
        estado_id=1,
        id_motivo_rechazo=None,
        planchas_x_separado=False,
        existe_troquel=False,
        numero_pistas=None,
        tipo_producto_id=None,
        es_recotizacion=False,
        ancho=None,
        avance=None,
        fecha_creacion=None,
        escalas=None,
        identificador=None,
        modificado_por=None,
        ultima_modificacion_inputs=None,
        colores_tinta=None,
        forma_pago_id=None,
        # Relaciones
        referencia_cliente=None,
        material=None,
        acabado=None,
        tipo_producto=None,
        forma_pago=None,
        # --- NUEVO: Añadir campo para perfil --- 
        perfil_comercial_info=None,
        # --- FIN NUEVO ---
        # --- NUEVO: Añadir altura_grafado ---
        altura_grafado=None
        # --- FIN NUEVO ---
    ):
        self.id = id
        self.referencia_cliente_id = referencia_cliente_id
        self.material_id = material_id
        self.acabado_id = acabado_id
        self.num_tintas = num_tintas
        self.num_paquetes_rollos = num_paquetes_rollos
        self.numero_cotizacion = numero_cotizacion
        self.es_manga = es_manga
        self.tipo_grafado_id = tipo_grafado_id
        self.valor_troquel = Decimal(str(valor_troquel)) if valor_troquel is not None else None
        self.valor_plancha_separado = Decimal(str(valor_plancha_separado)) if valor_plancha_separado is not None else None
        self.estado_id = estado_id
        self.id_motivo_rechazo = id_motivo_rechazo
        self.planchas_x_separado = planchas_x_separado
        self.existe_troquel = existe_troquel
        self.numero_pistas = numero_pistas
        self.tipo_producto_id = tipo_producto_id
        self.es_recotizacion = es_recotizacion
        self.ancho = ancho
        self.avance = avance
        self.fecha_creacion = fecha_creacion
        self.escalas = escalas if escalas is not None else []
        self.identificador = identificador
        self.modificado_por = modificado_por
        self.ultima_modificacion_inputs = ultima_modificacion_inputs
        self.colores_tinta = colores_tinta
        self.forma_pago_id = forma_pago_id
        # Relaciones
        self.referencia_cliente = referencia_cliente
        self.material = material
        self.acabado = acabado
        self.tipo_producto = tipo_producto
        self.forma_pago = forma_pago
        # --- NUEVO: Guardar perfil --- 
        self.perfil_comercial_info = perfil_comercial_info
        # --- FIN NUEVO ---
        # --- NUEVO: Guardar altura_grafado ---
        self.altura_grafado = float(altura_grafado) if altura_grafado is not None else None
        # --- FIN NUEVO ---

    @property
    def perfil_comercial_nombre(self) -> str:
        """Devuelve el nombre del perfil del comercial asociado"""
        perfil = self.perfil_comercial_info
        return perfil.get('nombre', "Desconocido") if perfil else "Desconocido"
       