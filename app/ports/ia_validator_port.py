from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class IIAValidatorPort(ABC):
    @abstractmethod
    async def validar_imagen_fuego(self, imagen_url: Optional[str]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def clasificar_urgencia_texto(self, texto: str) -> Dict[str, Any]:
        pass
