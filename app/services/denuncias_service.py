import uuid
from typing import Optional, Dict, Any
from app.domain.models import DenunciaCiudadana
from app.domain.exceptions import TicketNoEncontradoException
from app.ports.storage_port import IDenunciaStoragePort
from app.ports.ia_validator_port import IIAValidatorPort
from app.ports.notification_port import INotificationPort

class DenunciasApplicationService:
    def __init__(
        self,
        storage: IDenunciaStoragePort,
        ia_validator: IIAValidatorPort,
        notifier: INotificationPort
    ):
        self.storage = storage
        self.ia_validator = ia_validator
        self.notifier = notifier

    async def registrar_denuncia(
        self,
        descripcion: str,
        latitud: float,
        longitud: float,
        telefono: Optional[str] = None,
        imagen_url: Optional[str] = None,
        score_ia_manual: Optional[float] = None
    ) -> Dict[str, Any]:
        ticket_id = f"RAD-{uuid.uuid4().hex[:6].upper()}"

        denuncia = DenunciaCiudadana(
            ticket_id=ticket_id,
            descripcion=descripcion,
            latitud=latitud,
            longitud=longitud,
            telefono=telefono,
            imagen_url=imagen_url
        )

        if score_ia_manual is not None:
            score_fuego = score_ia_manual
        else:
            res_vision = await self.ia_validator.validar_imagen_fuego(imagen_url)
            score_fuego = float(res_vision.get("nivel_confianza", 0.0))

        res_nlp = await self.ia_validator.clasificar_urgencia_texto(descripcion)
        categoria_nlp = res_nlp.get("categoria_predicha", "PENDIENTE_TRIAJE")

        denuncia.asignar_evaluacion_ia(score_fuego=score_fuego, categoria=categoria_nlp)
        await self.storage.guardar_denuncia(denuncia)
        await self.notifier.notificar_nueva_alerta(denuncia)

        return {
            "ticket_id": denuncia.ticket_id,
            "estado": denuncia.estado,
            "confianza_verificacion_ia": denuncia.score_fuego_ia,
            "categoria_predicha": denuncia.categoria_nlp,
            "es_prioridad_alta": denuncia.es_prioridad_alta(),
            "instrucciones_seguridad": denuncia.instrucciones_seguridad,
            "mensaje": "Reporte registrado y encolado para atencion inmediata."
        }

    async def consultar_por_ticket(self, ticket_id: str) -> Dict[str, Any]:
        denuncia = await self.storage.obtener_por_ticket(ticket_id)
        if not denuncia:
            raise TicketNoEncontradoException(ticket_id)

        return {
            "ticket_id": denuncia.ticket_id,
            "estado": denuncia.estado,
            "descripcion": denuncia.descripcion,
            "categoria": denuncia.categoria_nlp,
            "instrucciones_seguridad": denuncia.instrucciones_seguridad,
            "fecha_creacion": denuncia.fecha_creacion.isoformat()
        }
