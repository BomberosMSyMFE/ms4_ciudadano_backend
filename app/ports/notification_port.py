from abc import ABC, abstractmethod
from app.domain.models import DenunciaCiudadana

class INotificationPort(ABC):
    @abstractmethod
    async def notificar_nueva_alerta(self, denuncia: DenunciaCiudadana) -> bool:
        pass
