from datetime import datetime, timezone
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.ports.storage_port import IDenunciaStoragePort
from app.domain.models import DenunciaCiudadana

class MotorMongoAdapter(IDenunciaStoragePort):
    def __init__(self, uri: str = "mongodb://127.0.0.1:27017", db_name: str = "bomberos_ciudadano"):
        self.client = AsyncIOMotorClient(uri)
        self.db: AsyncIOMotorDatabase = self.client[db_name]
        self.collection = self.db["denuncias"]

    async def guardar_denuncia(self, denuncia: DenunciaCiudadana) -> str:
        doc = {
            "_id": denuncia.ticket_id,
            "ticket_id": denuncia.ticket_id,
            "descripcion": denuncia.descripcion,
            "latitud": denuncia.latitud,
            "longitud": denuncia.longitud,
            "telefono": denuncia.telefono,
            "imagen_url": denuncia.imagen_url,
            "score_fuego_ia": denuncia.score_fuego_ia,
            "categoria_nlp": denuncia.categoria_nlp,
            "estado": denuncia.estado,
            "instrucciones_seguridad": denuncia.instrucciones_seguridad,
            "es_prioridad_alta": denuncia.es_prioridad_alta(),
            "fecha_creacion": denuncia.fecha_creacion
        }
        if denuncia.idempotency_key:
            doc["idempotency_key"] = denuncia.idempotency_key
        await self.collection.replace_one({"_id": denuncia.ticket_id}, doc, upsert=True)
        return denuncia.ticket_id

    async def obtener_por_ticket(self, ticket_id: str) -> Optional[DenunciaCiudadana]:
        doc = await self.collection.find_one({"_id": ticket_id})
        if not doc:
            return None
        return self._documento_a_entidad(doc)

    async def obtener_por_idempotency_key(self, idempotency_key: str) -> Optional[DenunciaCiudadana]:
        if not idempotency_key:
            return None
        doc = await self.collection.find_one({"idempotency_key": idempotency_key})
        if not doc:
            return None
        return self._documento_a_entidad(doc)

    async def listar_recientes(self, limite: int = 20) -> List[DenunciaCiudadana]:
        cursor = self.collection.find().sort("fecha_creacion", -1).limit(limite)
        docs = await cursor.to_list(length=limite)
        return [self._documento_a_entidad(d) for d in docs]

    def _documento_a_entidad(self, doc: dict) -> DenunciaCiudadana:
        fecha = doc.get("fecha_creacion")
        if isinstance(fecha, str):
            try:
                fecha = datetime.fromisoformat(fecha)
            except Exception:
                fecha = datetime.now(timezone.utc)

        return DenunciaCiudadana(
            ticket_id=doc["ticket_id"],
            descripcion=doc["descripcion"],
            latitud=float(doc["latitud"]),
            longitud=float(doc["longitud"]),
            telefono=doc.get("telefono"),
            imagen_url=doc.get("imagen_url"),
            score_fuego_ia=float(doc.get("score_fuego_ia", 0.0)),
            categoria_nlp=doc.get("categoria_nlp", "PENDIENTE_TRIAJE"),
            estado=doc.get("estado", "RECIBIDO_EN_TRIAJE"),
            idempotency_key=doc.get("idempotency_key"),
            instrucciones_seguridad=doc.get("instrucciones_seguridad"),
            fecha_creacion=fecha
        )
