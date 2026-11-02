import pytest
from httpx import AsyncClient, ASGITransport
from app.api.main import app
from app.api.dependencies import get_storage
from app.adapters.memory_adapter import InMemoryDenunciaAdapter

@pytest.fixture(autouse=True)
def override_storage():
    """Usa un adaptador en memoria para pruebas de API independientes."""
    mem_storage = InMemoryDenunciaAdapter()
    app.dependency_overrides[get_storage] = lambda: mem_storage
    yield
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_health_check_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "HEALTHY"
        assert data["service"] == "ms4_ciudadano_backend"

@pytest.mark.asyncio
async def test_post_denuncia_flujo_exitoso():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "descripcion": "Hay humo negro saliendo de un galpón y peligro de propagación",
            "latitud": -17.7833,
            "longitud": -63.1821,
            "telefono_contacto": "+59170099887",
            "imagen_url": "https://storage.bomberos.gob.bo/foto_1.jpg"
        }
        res = await client.post("/api/v1/denuncias", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert "ticket_id" in data
        assert data["ticket_id"].startswith("RAD-")
        assert data["estado"] == "RECIBIDO_EN_TRIAJE"
        assert "confianza_verificacion_ia" in data

        ticket_id = data["ticket_id"]

        # Consultar el estado del ticket recién creado
        res_get = await client.get(f"/api/v1/denuncias/{ticket_id}")
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert data_get["ticket_id"] == ticket_id
        assert "instrucciones_seguridad" in data_get

@pytest.mark.asyncio
async def test_post_denuncia_coordenadas_invalidas_retorna_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "descripcion": "Incendio",
            "latitud": 95.0, # Fuera de rango
            "longitud": -63.1821
        }
        res = await client.post("/api/v1/denuncias", json=payload)
        # Pydantic o el dominio deben rechazar
        assert res.status_code in [400, 422]

@pytest.mark.asyncio
async def test_webhook_n8n_whatsapp_ingesta():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "telefono": "+59176543210",
            "texto": "Fuego en un lote baldío en 4to anillo",
            "media_url": "https://storage.whatsapp.com/img123.jpg",
            "score_fuego_ia": 0.89
        }
        res = await client.post("/api/v1/webhook/n8n-whatsapp", json=payload)
        if res.status_code != 200:
            print("ERROR RESPONSE:", res.text)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "PROCESADO_Y_ENCOLADO"
        assert "ticket_id" in data
        assert data["es_prioridad_alta"] is True
