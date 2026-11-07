import uuid
from typing import Optional, Dict, Any
from app.domain.models import DenunciaCiudadana
from app.domain.exceptions import TicketNoEncontradoException
from app.ports.storage_port import IDenunciaStoragePort
from app.ports.ia_validator_port import IIAValidatorPort
from app.ports.notification_port import INotificationPort
from app.ports.evidence_storage_port import IEvidenceStoragePort

class DenunciasApplicationService:
    def __init__(
        self,
        storage: IDenunciaStoragePort,
        ia_validator: IIAValidatorPort,
        notifier: INotificationPort,
        evidence_storage: Optional[IEvidenceStoragePort] = None
    ):
        self.storage = storage
        self.ia_validator = ia_validator
        self.notifier = notifier
        self.evidence_storage = evidence_storage

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
            "imagen_url": denuncia.imagen_url,
            "mensaje": "Reporte registrado y encolado para atencion inmediata."
        }

    async def registrar_denuncia_con_foto(
        self,
        archivo_bytes: bytes,
        nombre_archivo: str,
        content_type: str,
        descripcion: str,
        latitud: float,
        longitud: float,
        telefono: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Flujo completo de recepcion con evidencia directa:
        1. Almacena la foto en AWS S3 (o fallback local).
        2. Ejecuta inferencia Deep Learning con YOLOv8 en MS-05 sobre los bytes reales.
        3. Clasifica el texto con NLP supervisado.
        4. Persiste en MongoDB.
        5. Notifica en vivo a MS-01 Comandos si la prioridad es ALTA.
        """
        # 1. Almacenar evidencia
        imagen_url = None
        if self.evidence_storage:
            imagen_url = await self.evidence_storage.subir_evidencia(
                archivo_bytes=archivo_bytes,
                nombre_archivo=nombre_archivo,
                content_type=content_type
            )

        # 2. Inferencia Deep Learning (YOLOv8) con bytes
        res_vision = await self.ia_validator.validar_imagen_bytes(
            archivo_bytes=archivo_bytes,
            nombre_archivo=nombre_archivo,
            content_type=content_type
        )
        score_fuego = float(res_vision.get("nivel_confianza", 0.0))

        # 3. Clasificacion NLP
        res_nlp = await self.ia_validator.clasificar_urgencia_texto(descripcion)
        categoria_nlp = res_nlp.get("categoria_predicha", "PENDIENTE_TRIAJE")

        # 4. Creacion de la entidad de Dominio
        ticket_id = f"RAD-{uuid.uuid4().hex[:6].upper()}"
        denuncia = DenunciaCiudadana(
            ticket_id=ticket_id,
            descripcion=descripcion,
            latitud=latitud,
            longitud=longitud,
            telefono=telefono,
            imagen_url=imagen_url
        )
        denuncia.asignar_evaluacion_ia(score_fuego=score_fuego, categoria=categoria_nlp)

        # 5. Persistencia y notificacion a Sala de Crisis
        await self.storage.guardar_denuncia(denuncia)
        await self.notifier.notificar_nueva_alerta(denuncia)

        return {
            "ticket_id": denuncia.ticket_id,
            "estado": denuncia.estado,
            "confianza_verificacion_ia": denuncia.score_fuego_ia,
            "categoria_predicha": denuncia.categoria_nlp,
            "es_prioridad_alta": denuncia.es_prioridad_alta(),
            "imagen_url": denuncia.imagen_url,
            "instrucciones_seguridad": denuncia.instrucciones_seguridad,
            "detecciones_vision": res_vision.get("detalles", []),
            "motor_vision": res_vision.get("motor", "YOLOv8 Deep Learning"),
            "mensaje": "Evidencia visual analizada con Deep Learning y reporte encolado exitosamente."
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
            "score_fuego_ia": denuncia.score_fuego_ia,
            "imagen_url": denuncia.imagen_url,
            "es_prioridad_alta": denuncia.es_prioridad_alta(),
            "instrucciones_seguridad": denuncia.instrucciones_seguridad,
            "fecha_creacion": denuncia.fecha_creacion.isoformat()
        }
