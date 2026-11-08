from abc import ABC, abstractmethod

class IEvidenceStoragePort(ABC):
    @abstractmethod
    async def subir_evidencia(
        self,
        archivo_bytes: bytes,
        nombre_archivo: str,
        content_type: str = "image/jpeg"
    ) -> str:
        """
        Sube la evidencia fotografica o video a almacenamiento seguro en la nube (AWS S3)
        o al almacenamiento local de respaldo (fallback).
        Retorna la URL publica o local accesible del recurso.
        """
        pass
