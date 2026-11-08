from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class IIAValidatorPort(ABC):
    @abstractmethod
    async def validar_imagen_fuego(self, imagen_url: Optional[str]) -> Dict[str, Any]:
        """Valida una imagen por su URL publica mediante el inspector de vision IA."""
        pass

    @abstractmethod
    async def validar_imagen_bytes(
        self,
        archivo_bytes: bytes,
        nombre_archivo: str = "evidencia.jpg",
        content_type: str = "image/jpeg"
    ) -> Dict[str, Any]:
        """
        Envia los bytes binarios de la imagen a MS-05 IA Core para inferencia
        profunda con YOLOv8 y analisis termico de pixeles.
        """
        pass

    @abstractmethod
    async def clasificar_urgencia_texto(self, texto: str) -> Dict[str, Any]:
        """Clasifica la severidad semantica de la denuncia usando NLP supervisado."""
        pass
