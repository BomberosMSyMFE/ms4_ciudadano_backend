from datetime import datetime, timezone
from typing import Optional
from app.domain.exceptions import CoordenadasInvalidasException, DescripcionVaciaException

class DenunciaCiudadana:
    def __init__(
        self,
        ticket_id: str,
        descripcion: str,
        latitud: float,
        longitud: float,
        telefono: Optional[str] = None,
        imagen_url: Optional[str] = None,
        score_fuego_ia: float = 0.0,
        categoria_nlp: str = "PENDIENTE_TRIAJE",
        estado: str = "RECIBIDO_EN_TRIAJE",
        instrucciones_seguridad: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        fecha_creacion: Optional[datetime] = None
    ):
        self._validar(descripcion, latitud, longitud)
        self.ticket_id = ticket_id
        self.descripcion = descripcion.strip()
        self.latitud = latitud
        self.longitud = longitud
        self.telefono = telefono
        self.imagen_url = imagen_url
        self.score_fuego_ia = float(score_fuego_ia)
        self.categoria_nlp = categoria_nlp
        self.estado = estado
        self.idempotency_key = idempotency_key
        self.fecha_creacion = fecha_creacion or datetime.now(timezone.utc)
        self.instrucciones_seguridad = instrucciones_seguridad or self._instrucciones_base()

    def _validar(self, descripcion: str, latitud: float, longitud: float):
        if not descripcion or not descripcion.strip():
            raise DescripcionVaciaException()
        if not (-90.0 <= latitud <= 90.0) or not (-180.0 <= longitud <= 180.0):
            raise CoordenadasInvalidasException(latitud, longitud)

    def es_prioridad_alta(self) -> bool:
        return self.score_fuego_ia >= 0.65 or self.categoria_nlp.startswith("CRITICO") or self.categoria_nlp.startswith("ALTO")

    def asignar_evaluacion_ia(self, score_fuego: float, categoria: str):
        self.score_fuego_ia = round(float(score_fuego), 3)
        self.categoria_nlp = categoria
        if self.es_prioridad_alta():
            self.instrucciones_seguridad = (
                "ALERTA MÁXIMA: Evacue a favor del viento y corte suministros de gas y electricidad. "
                "Unidades despachadas con prioridad."
            )

    def actualizar_estado(self, nuevo_estado: str):
        validos = ["RECIBIDO_EN_TRIAJE", "UNIDAD_EN_CAMINO", "EN_ESCENA", "CONTROLADO", "FALSA_ALARMA"]
        if nuevo_estado not in validos:
            raise ValueError(f"Estado invalido: {nuevo_estado}")
        self.estado = nuevo_estado

    def _instrucciones_base(self) -> str:
        return "Mantenga la calma, alejese de fuentes de calor y despeje el area para el ingreso de unidades."

    def to_dict(self) -> dict:
        return {
            "ticket_id": self.ticket_id,
            "descripcion": self.descripcion,
            "latitud": self.latitud,
            "longitud": self.longitud,
            "telefono": self.telefono,
            "imagen_url": self.imagen_url,
            "score_fuego_ia": self.score_fuego_ia,
            "categoria_nlp": self.categoria_nlp,
            "estado": self.estado,
            "idempotency_key": self.idempotency_key,
            "instrucciones_seguridad": self.instrucciones_seguridad,
            "es_prioridad_alta": self.es_prioridad_alta(),
            "fecha_creacion": self.fecha_creacion.isoformat()
        }
