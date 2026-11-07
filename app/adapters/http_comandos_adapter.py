import os
from typing import Optional
import httpx
from app.ports.notification_port import INotificationPort
from app.domain.models import DenunciaCiudadana

class HttpComandosAdapter(INotificationPort):
    """
    Adaptador de integracion de notificaciones hacia MS-01 Comandos & Sala de Crisis.
    Cuando un ciudadano reporta una emergencia clasificada como ALTA PRIORIDAD,
    este adaptador emite un evento/POST al centro de comando de bomberos.
    """

    def __init__(self, comandos_base_url: Optional[str] = None):
        self.base_url = (comandos_base_url or os.getenv("COMANDOS_MS1_URL", "http://127.0.0.1:3000")).rstrip("/")

    def _mapear_tipo_incidente(self, categoria_nlp: str) -> str:
        cat = categoria_nlp.upper()
        if "ESTRUCTURAL" in cat:
            return "INCENDIO_ESTRUCTURAL"
        if "FORESTAL" in cat:
            return "INCENDIO_FORESTAL"
        if "GAS" in cat:
            return "FUGA_DE_GAS"
        if "VEHICULAR" in cat:
            return "ACCIDENTE_VEHICULAR"
        if "RESCATE" in cat:
            return "RESCATE_PERSONAS"
        return "INCENDIO_ESTRUCTURAL"

    async def notificar_nueva_alerta(self, denuncia: DenunciaCiudadana) -> bool:
        prioridad = "CRITICA" if denuncia.es_prioridad_alta() else "NORMAL"
        print(f"[EVENTO SALA CRISIS] Denuncia: {denuncia.ticket_id} | Prioridad: {prioridad} | Cat: {denuncia.categoria_nlp}")

        # Solo despachamos activamente a Sala de Crisis si la alerta es de alta prioridad
        if not denuncia.es_prioridad_alta():
            return True

        tipo_incidente = self._mapear_tipo_incidente(denuncia.categoria_nlp)
        payload = {
            "tipoIncidente": tipo_incidente,
            "severidad": "CRITICA",
            "descripcion": f"[REPORTE CIUDADANO {denuncia.ticket_id}] {denuncia.descripcion}",
            "latitud": denuncia.latitud,
            "longitud": denuncia.longitud,
            "denuncianteNombre": "Portal Ciudadano SCZ",
            "denuncianteTelefono": denuncia.telefono or "+591-70000000",
            "denuncianteEmail": "denuncias@bomberos.gob.bo"
        }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/incidentes",
                    json=payload
                )
                if res.status_code in [200, 201]:
                    print(f"[COMANDOS MS-01] Notificacion de emergencia enviada exitosamente para ticket {denuncia.ticket_id}")
                    return True
                else:
                    print(f"[COMANDOS MS-01] Notificacion enviada con respuesta HTTP {res.status_code} (posible guardia JWT activa)")
        except Exception as e:
            print(f"[COMANDOS MS-01] Comandos offline o inaccesible temporalmente ({e}). Alerta preservada en base de datos.")

        return True
