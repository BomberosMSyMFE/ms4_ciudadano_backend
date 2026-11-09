from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Header, File, UploadFile, Form
from pydantic import BaseModel, Field
from app.services.denuncias_service import DenunciasApplicationService
from app.domain.exceptions import DominioCiudadanoException, TicketNoEncontradoException
from app.api.dependencies import get_denuncias_service

router = APIRouter(prefix="/api/v1", tags=["Portal Ciudadano y Denuncias"])

FORMATOS_PERMITIDOS = [
    "image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff",
    "video/mp4", "video/quicktime", "video/webm", "video/3gpp", "video/x-matroska",
    "audio/mpeg", "audio/wav", "audio/mp4", "audio/aac", "audio/ogg", "audio/webm"
]
MAX_PHOTO_BYTES = 25 * 1024 * 1024  # 25 MB

class DenunciaInputDTO(BaseModel):
    descripcion: str = Field(..., description="Descripcion del incidente")
    latitud: float = Field(..., ge=-90.0, le=90.0, description="Latitud GPS")
    longitud: float = Field(..., ge=-180.0, le=180.0, description="Longitud GPS")
    telefono_contacto: Optional[str] = Field(None, description="Telefono de contacto")
    imagen_url: Optional[str] = Field(None, description="URL de imagen opcional")

class DenunciaResponseDTO(BaseModel):
    ticket_id: str
    estado: str
    confianza_verificacion_ia: float
    reintento_idempotente: bool = False
    mensaje: str

class DenunciaConFotoResponseDTO(BaseModel):
    ticket_id: str
    estado: str
    confianza_verificacion_ia: float
    categoria_predicha: str
    es_prioridad_alta: bool
    imagen_url: Optional[str] = None
    instrucciones_seguridad: str
    detecciones_vision: list = []
    motor_vision: str = "YOLOv8 Deep Learning"
    reintento_idempotente: bool = False
    mensaje: str

class EstadoIncidenteCiudadanoDTO(BaseModel):
    ticket_id: str
    estado: str
    instrucciones_seguridad: str
    imagen_url: Optional[str] = None
    es_prioridad_alta: Optional[bool] = None

class ActualizarEstadoDTO(BaseModel):
    nuevo_estado: str = Field(..., description="Nuevo estado: RECIBIDO_EN_TRIAJE, UNIDAD_EN_CAMINO, EN_ESCENA, CONTROLADO")

class N8nWebhookDTO(BaseModel):
    telefono: Optional[str] = None
    texto: Optional[str] = None
    media_url: Optional[str] = None
    score_fuego_ia: Optional[float] = None

@router.post("/denuncias", response_model=DenunciaResponseDTO, status_code=status.HTTP_201_CREATED)
async def registrar_denuncia(
    payload: DenunciaInputDTO,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    service: DenunciasApplicationService = Depends(get_denuncias_service)
):
    try:
        resultado = await service.registrar_denuncia(
            descripcion=payload.descripcion,
            latitud=payload.latitud,
            longitud=payload.longitud,
            telefono=payload.telefono_contacto,
            imagen_url=payload.imagen_url,
            idempotency_key=idempotency_key
        )
        return DenunciaResponseDTO(
            ticket_id=resultado["ticket_id"],
            estado=resultado["estado"],
            confianza_verificacion_ia=resultado["confianza_verificacion_ia"],
            reintento_idempotente=resultado.get("reintento_idempotente", False),
            mensaje=resultado["mensaje"]
        )
    except DominioCiudadanoException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/denuncias/con-foto", response_model=DenunciaConFotoResponseDTO, status_code=status.HTTP_201_CREATED)
async def registrar_denuncia_con_foto(
    foto: UploadFile = File(..., description="Fotografia o video del siniestro"),
    descripcion: str = Form(..., description="Descripcion detallada de la emergencia"),
    latitud: float = Form(..., ge=-90.0, le=90.0, description="Latitud GPS"),
    longitud: float = Form(..., ge=-180.0, le=180.0, description="Longitud GPS"),
    telefono_contacto: Optional[str] = Form(None, description="Numero de telefono del denunciante"),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    service: DenunciasApplicationService = Depends(get_denuncias_service)
):
    """
    Endpoint principal para la recepcion de denuncias con evidencia fotografica.
    - Soporta cabecera Idempotency-Key para evitar duplicados si la red reintenta.
    - Sube la imagen a AWS S3 (o fallback local 'storage/evidencias/').
    - Valida mediante Deep Learning (YOLOv8 y ratio termico) en MS-05.
    - Clasifica la urgencia mediante NLP supervisado en MS-05.
    - Guarda en MongoDB y notifica a MS-01 Sala de Crisis y al WhatsApp del ciudadano.
    """
    if foto.content_type not in FORMATOS_PERMITIDOS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Formato de archivo '{foto.content_type}' no soportado. Formatos validos: {FORMATOS_PERMITIDOS}"
        )

    try:
        contenido = await foto.read()
        if len(contenido) > MAX_PHOTO_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"El archivo supera el limite maximo permitido de {MAX_PHOTO_BYTES // (1024*1024)} MB."
            )

        resultado = await service.registrar_denuncia_con_foto(
            archivo_bytes=contenido,
            nombre_archivo=foto.filename or "evidencia.jpg",
            content_type=foto.content_type,
            descripcion=descripcion,
            latitud=latitud,
            longitud=longitud,
            telefono=telefono_contacto,
            idempotency_key=idempotency_key
        )

        return DenunciaConFotoResponseDTO(
            ticket_id=resultado["ticket_id"],
            estado=resultado["estado"],
            confianza_verificacion_ia=resultado["confianza_verificacion_ia"],
            categoria_predicha=resultado["categoria_predicha"],
            es_prioridad_alta=resultado["es_prioridad_alta"],
            imagen_url=resultado.get("imagen_url"),
            instrucciones_seguridad=resultado["instrucciones_seguridad"],
            detecciones_vision=resultado.get("detecciones_vision", []),
            motor_vision=resultado.get("motor_vision", "YOLOv8 Deep Learning"),
            reintento_idempotente=resultado.get("reintento_idempotente", False),
            mensaje=resultado["mensaje"]
        )
    except DominioCiudadanoException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/denuncias/{ticketId}", response_model=EstadoIncidenteCiudadanoDTO)
async def consultar_estado_denuncia(
    ticketId: str,
    service: DenunciasApplicationService = Depends(get_denuncias_service)
):
    try:
        denuncia = await service.consultar_por_ticket(ticketId)
        return EstadoIncidenteCiudadanoDTO(
            ticket_id=denuncia["ticket_id"],
            estado=denuncia["estado"],
            instrucciones_seguridad=denuncia["instrucciones_seguridad"],
            imagen_url=denuncia.get("imagen_url"),
            es_prioridad_alta=denuncia.get("es_prioridad_alta")
        )
    except TicketNoEncontradoException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.patch("/denuncias/{ticketId}/estado")
async def actualizar_estado_denuncia(
    ticketId: str,
    payload: ActualizarEstadoDTO,
    service: DenunciasApplicationService = Depends(get_denuncias_service)
):
    """
    Actualiza el estado operativo de una denuncia en la linea de tiempo.
    Permite avanzar entre:
    - RECIBIDO_EN_TRIAJE
    - UNIDAD_EN_CAMINO
    - EN_ESCENA
    - CONTROLADO
    """
    denuncia = await service.storage.obtener_por_ticket(ticketId)
    if not denuncia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontro el ticket '{ticketId}'"
        )

    estado_limpio = payload.nuevo_estado.strip().upper()
    denuncia.estado = estado_limpio
    await service.storage.guardar_denuncia(denuncia)

    if estado_limpio in ["UNIDAD_EN_CAMINO", "DESPACHADO"]:
        if denuncia.telefono:
            try:
                await service.notifier.notificar_despacho_whatsapp(
                    telefono=denuncia.telefono,
                    ticket_id=ticketId,
                    codigo_radial=ticketId,
                    estado=estado_limpio,
                    unidades=1
                )
            except Exception as e:
                print(f"[NOTIFICACION ERROR] {e}")

    return {
        "ticket_id": ticketId,
        "nuevo_estado": denuncia.estado,
        "mensaje": f"Estado actualizado exitosamente a {denuncia.estado}"
    }

@router.post("/webhook/n8n-whatsapp", status_code=status.HTTP_200_OK)
async def webhook_n8n_whatsapp(
    payload: N8nWebhookDTO,
    service: DenunciasApplicationService = Depends(get_denuncias_service)
):
    try:
        texto = payload.texto or "Emergencia reportada por WhatsApp"
        resultado = await service.registrar_denuncia(
            descripcion=texto,
            latitud=-17.7833,
            longitud=-63.1821,
            telefono=payload.telefono,
            imagen_url=payload.media_url,
            score_ia_manual=payload.score_fuego_ia
        )
        return {
            "status": "PROCESADO_Y_ENCOLADO",
            "ticket_id": resultado["ticket_id"],
            "es_prioridad_alta": resultado["es_prioridad_alta"]
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/denuncias")
async def listar_denuncias_recientes(
    limite: int = 50,
    service: DenunciasApplicationService = Depends(get_denuncias_service)
):
    denuncias = await service.storage.listar_recientes(limite)
    return [d.to_dict() for d in denuncias]
