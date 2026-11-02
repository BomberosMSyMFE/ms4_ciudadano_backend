from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, Field
from app.services.denuncias_service import DenunciasApplicationService
from app.domain.exceptions import DominioCiudadanoException, TicketNoEncontradoException
from app.api.dependencies import get_denuncias_service

router = APIRouter(prefix="/api/v1", tags=["Portal Ciudadano y Denuncias"])

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
    mensaje: str

class EstadoIncidenteCiudadanoDTO(BaseModel):
    ticket_id: str
    estado: str
    instrucciones_seguridad: str

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
            imagen_url=payload.imagen_url
        )
        return DenunciaResponseDTO(
            ticket_id=resultado["ticket_id"],
            estado=resultado["estado"],
            confianza_verificacion_ia=resultado["confianza_verificacion_ia"],
            mensaje=resultado["mensaje"]
        )
    except DominioCiudadanoException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
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
            instrucciones_seguridad=denuncia["instrucciones_seguridad"]
        )
    except TicketNoEncontradoException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

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
    limite: int = 20,
    service: DenunciasApplicationService = Depends(get_denuncias_service)
):
    denuncias = await service.storage.listar_recientes(limite)
    return [d.to_dict() for d in denuncias]
