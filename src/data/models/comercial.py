from dataclasses import dataclass
from typing import Optional
from .base_model import BaseModel

@dataclass
class Comercial(BaseModel):
    nombre: str
    email: str
    celular: Optional[str] = None
    rol_nombre: str = 'comercial'
