from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from app.api.routers import denuncias_router
from app.api.dependencies import get_storage

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        storage = get_storage()
        await storage.db.command("ping")
    except Exception:
        pass
    yield

app = FastAPI(
    title="MS-04 Portal Ciudadano y Denuncias de Emergencia",
    version="1.0.0",
    description="API REST para recepcion de denuncias ciudadanas y webhooks de n8n.",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["Info"])
async def root():
    return {
        "microservicio": "MS-04 Portal Ciudadano y Denuncias de Emergencia",
        "estado": "ACTIVO",
        "version": "1.0.0",
        "documentacion_swagger": "/docs",
        "health": "/health",
        "endpoints": {
            "registrar_denuncia": "POST /api/v1/denuncias",
            "consultar_ticket": "GET /api/v1/denuncias/{ticketId}",
            "webhook_whatsapp_n8n": "POST /api/v1/webhook/n8n-whatsapp",
            "listar_denuncias": "GET /api/v1/denuncias"
        }
    }

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

app.include_router(denuncias_router.router)

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "HEALTHY",
        "service": "ms4_ciudadano_backend",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api.main:app", host="0.0.0.0", port=8083, reload=True)
