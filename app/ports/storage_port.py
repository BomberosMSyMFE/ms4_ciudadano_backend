from abc import ABC, abstractmethod
from typing import Optional, List
from app.domain.models import DenunciaCiudadana

class IDenunciaStoragePort(ABC):
    @abstractmethod
    async def guardar_denuncia(self, denuncia: DenunciaCiudadana) -> str:
        pass

    @abstractmethod
    async def obtener_por_ticket(self, ticket_id: str) -> Optional[DenunciaCiudadana]:
        pass

    @abstractmethod
    async def listar_recientes(self, limite: int = 20) -> List[DenunciaCiudadana]:
        pass
