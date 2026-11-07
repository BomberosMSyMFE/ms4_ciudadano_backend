from typing import Optional, List, Dict
from app.ports.storage_port import IDenunciaStoragePort
from app.domain.models import DenunciaCiudadana

class InMemoryDenunciaAdapter(IDenunciaStoragePort):
    """
    Adaptador en memoria para pruebas unitarias sin dependencias externas.
    """

    def __init__(self):
        self._storage: Dict[str, DenunciaCiudadana] = {}

    async def guardar_denuncia(self, denuncia: DenunciaCiudadana) -> str:
        self._storage[denuncia.ticket_id] = denuncia
        return denuncia.ticket_id

    async def obtener_por_ticket(self, ticket_id: str) -> Optional[DenunciaCiudadana]:
        return self._storage.get(ticket_id)

    async def obtener_por_idempotency_key(self, idempotency_key: str) -> Optional[DenunciaCiudadana]:
        if not idempotency_key:
            return None
        for d in self._storage.values():
            if d.idempotency_key == idempotency_key:
                return d
        return None

    async def listar_recientes(self, limite: int = 20) -> List[DenunciaCiudadana]:
        todos = list(self._storage.values())
        todos.sort(key=lambda x: x.fecha_creacion, reverse=True)
        return todos[:limite]
