# src/data/models/base_model.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class BaseModel:
    id: int
    created_at: Optional[str] = None