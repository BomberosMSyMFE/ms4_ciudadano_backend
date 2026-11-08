import os
import re
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import httpx

# Cargar variables de entorno desde .env del microservicio o raiz
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.exists():
    load_dotenv(dotenv_path=_env_file)
else:
    load_dotenv()

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routers import denuncias_router
from app.api.dependencies import get_storage, get_notifier

storage_dir = Path("storage/evidencias")
storage_dir.mkdir(parents=True, exist_ok=True)

async def _poller_despacho_comandos():
    """
    Monitor en tiempo real de Sala de Crisis (MS-01):
    Detecta cuándo el operador valida un reporte ciudadano y despacha unidades,
    para emitir en ese instante exacto la notificación a WhatsApp por n8n/gateway.
    """
    await asyncio.sleep(2)
    print("[COMANDOS MONITOR] Servicio de monitoreo de despachos activo y escuchando eventos...", flush=True)
    storage = get_storage()
    notifier = get_notifier()
    notificados = set()

    while True:
        try:
            await asyncio.sleep(4)
            token = await notifier._obtener_token_comandos()
            if not token:
                continue

            async with httpx.AsyncClient(timeout=6.0, verify=False) as client:
                res = await client.get(
                    f"{notifier.base_url}/api/v1/incidentes/activos",
                    headers={"Authorization": f"Bearer {token}"}
                )
                if res.status_code == 200:
                    data = res.json()
                    incidentes = data if isinstance(data, list) else data.get("value", [])
                    for inc in incidentes:
                        desc = inc.get("descripcion", "")
                        match = re.search(r"RAD-[A-Z0-9]{6}", desc)
                        if match:
                            ticket_id = match.group(0)
                            unidades = inc.get("unidadesAsignadas", 0)
                            estado = inc.get("estado", "")
                            codigo = inc.get("codigoRadial", ticket_id)

                            # Sincronizar estado táctico en la base de datos local
                            d = await storage.obtener_por_ticket(ticket_id)
                            if d:
                                nuevo_estado_ciudadano = d.estado
                                if estado in ["DESPACHADO"]:
                                    nuevo_estado_ciudadano = "UNIDAD_EN_CAMINO"
                                elif estado in ["EN_COMBATE"]:
                                    nuevo_estado_ciudadano = "EN_ESCENA"
                                elif estado in ["CONTROLADO", "CERRADO", "LIQUIDADO"]:
                                    nuevo_estado_ciudadano = "CONTROLADO"

                                if d.estado != nuevo_estado_ciudadano:
                                    d.estado = nuevo_estado_ciudadano
                                    await storage.guardar_denuncia(d)
                                    print(f"[COMANDOS SYNC] Ticket {ticket_id} sincronizado a '{nuevo_estado_ciudadano}' según Sala de Crisis ({estado})", flush=True)

                            if (unidades > 0 or estado in ["DESPACHADO", "EN_COMBATE", "CONTROLADO"]) and ticket_id not in notificados:
                                telefono = None
                                denunciante = inc.get("denunciante")
                                if isinstance(denunciante, dict):
                                    telefono = denunciante.get("telefono")

                                if not telefono and d and d.telefono:
                                    telefono = d.telefono

                                if telefono:
                                    print(f"[COMANDOS DESPACHO] Operador validó ticket {ticket_id} ({codigo}) en estado '{estado}' con {unidades} unidad(es). Enviando WhatsApp oficial...", flush=True)
                                    await notifier.notificar_despacho_whatsapp(
                                        telefono=telefono,
                                        ticket_id=ticket_id,
                                        codigo_radial=codigo,
                                        estado=estado,
                                        unidades=max(1, unidades)
                                    )
                                    notificados.add(ticket_id)
        except Exception as e:
            print(f"[COMANDOS MONITOR ERROR] {e}", flush=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_poller_despacho_comandos())
    try:
        storage = get_storage()
        await storage.db.command("ping")
        await storage.collection.create_index("idempotency_key", unique=True, sparse=True)
    except Exception:
        pass
    yield
    task.cancel()

app = FastAPI(
    title="MS-04 Portal Ciudadano y Denuncias de Emergencia",
    version="1.0.0",
    description="API REST para recepcion de denuncias ciudadanas, evidencia fotografica (AWS S3) y webhooks de n8n.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Montar directorio estatico para servir evidencias locales en modo fallback
app.mount("/evidencias", StaticFiles(directory=str(storage_dir)), name="evidencias")

@app.get("/", tags=["Info"])
async def root():
    return {
        "microservicio": "MS-04 Portal Ciudadano y Denuncias de Emergencia",
        "estado": "ACTIVO",
        "version": "1.0.0",
        "documentacion_swagger": "/docs",
        "health": "/health",
        "endpoints": {
            "registrar_denuncia_json": "POST /api/v1/denuncias",
            "registrar_denuncia_con_foto": "POST /api/v1/denuncias/con-foto",
            "consultar_ticket": "GET /api/v1/denuncias/{ticketId}",
            "actualizar_estado": "PATCH /api/v1/denuncias/{ticketId}/estado",
            "webhook_n8n": "POST /api/v1/webhook/n8n-whatsapp"
        }
    }

@app.get("/health", tags=["Salud"])
async def health():
    return {
        "status": "HEALTHY",
        "service": "ms4_ciudadano_backend",
        "version": "1.0.0"
    }

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

app.include_router(denuncias_router.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8083, reload=True)
