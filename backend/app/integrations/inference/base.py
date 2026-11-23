from typing import Protocol
from .schemas import ModelResult

class ModelAdapter(Protocol):
    async def analyze(self, image_path: str, symptoms: str) -> ModelResult: ...
