from app.ports.notification_port import INotificationPort
from app.domain.models import DenunciaCiudadana

class ConsoleNotificationAdapter(INotificationPort):
    async def notificar_nueva_alerta(self, denuncia: DenunciaCiudadana) -> bool:
        prioridad = "CRITICA" if denuncia.es_prioridad_alta() else "NORMAL"
        print(f"[EVENTO SALA CRISIS] Denuncia: {denuncia.ticket_id} | Prioridad: {prioridad} | Cat: {denuncia.categoria_nlp}")
        return True
