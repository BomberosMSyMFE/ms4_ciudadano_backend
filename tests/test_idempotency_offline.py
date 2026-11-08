import io
import pytest
from httpx import AsyncClient, ASGITransport
from app.api.main import app
from app.api.dependencies import get_storage, get_evidence_storage, get_ia_validator, get_notifier
from app.adapters.memory_adapter import InMemoryDenunciaAdapter
from app.ports.evidence_storage_port import IEvidenceStoragePort
from app.ports.ia_validator_port import IIAValidatorPort
from app.ports.notification_port import INotificationPort

class MockTestEvidenceStorage(IEvidenceStoragePort):
    async def subir_evidencia(self, archivo_bytes: bytes, nombre_archivo: str, content_type: str = "image/jpeg") -> str:
        return f"https://s3.amazonaws.com/bomberos-scz-evidencias/{nombre_archivo}"

class MockTestIAValidator(IIAValidatorPort):
    async def validar_imagen_fuego(self, imagen_url):
        return {"verificado_por_ia": True, "nivel_confianza": 0.92, "detecciones": ["fire"]}

    async def validar_imagen_bytes(self, archivo_bytes, nombre_archivo="evidencia.jpg", content_type="image/jpeg"):
        return {
            "verificado_automaticamente": True,
            "nivel_confianza": 0.94,
            "total_detecciones": 1,
            "detalles": [{"clase": "fire", "confianza": 0.94}],
            "motor": "YOLOv8 Deep Learning"
        }

    async def clasificar_urgencia_texto(self, texto):
        return {"categoria_predicha": "CRITICO_ESTRUCTURAL", "confianza": 0.90}

class MockTestNotifier(INotificationPort):
    def __init__(self):
        self.notificaciones = []

    async def notificar_nueva_alerta(self, denuncia) -> bool:
        self.notificaciones.append(denuncia.ticket_id)
        return True

@pytest.fixture
def setup_idempotency_env():
    mem_storage = InMemoryDenunciaAdapter()
    mock_s3 = MockTestEvidenceStorage()
    mock_ia = MockTestIAValidator()
    mock_notifier = MockTestNotifier()

    app.dependency_overrides[get_storage] = lambda: mem_storage
    app.dependency_overrides[get_evidence_storage] = lambda: mock_s3
    app.dependency_overrides[get_ia_validator] = lambda: mock_ia
    app.dependency_overrides[get_notifier] = lambda: mock_notifier

    yield {
        "storage": mem_storage,
        "notifier": mock_notifier
    }

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_idempotencia_en_reintentos_red_no_duplica(setup_idempotency_env):
    """
    Prueba que simula la pérdida de conexión del ciudadano:
    El ciudadano pulsa 'Enviar' varias veces con la misma clave Idempotency-Key.
    El backend debe procesar la primera vez y responder el mismo ticket en las subsiguientes
    sin duplicar el registro en la base de datos ni emitir alertas duplicadas a Comandos.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Idempotency-Key": "OFFLINE-RETRY-UUID-777"}

        fake_image = io.BytesIO(b"fake image bytes")
        files = {"foto": ("humo.jpg", fake_image, "image/jpeg")}
        data = {
            "descripcion": "Fuego violento en taller mecánico",
            "latitud": "-17.7833",
            "longitud": "-63.1821",
            "telefono_contacto": "+59170011223"
        }

        # 1. Primer envío (cuando hay señal)
        res1 = await client.post("/api/v1/denuncias/con-foto", files=files, data=data, headers=headers)
        assert res1.status_code == 201
        data1 = res1.json()
        ticket_original = data1["ticket_id"]
        assert data1["reintento_idempotente"] is False

        # 2. Segundo envío con la MISMA Idempotency-Key (simula reintento automático)
        fake_image2 = io.BytesIO(b"fake image bytes")
        files2 = {"foto": ("humo.jpg", fake_image2, "image/jpeg")}
        res2 = await client.post("/api/v1/denuncias/con-foto", files=files2, data=data, headers=headers)
        assert res2.status_code == 201
        data2 = res2.json()

        # Debe retornar EXACTAMENTE el mismo ticket sin crear otro
        assert data2["ticket_id"] == ticket_original
        assert data2["reintento_idempotente"] is True
        assert "ya registrado previamente" in data2["mensaje"]

        # Verificar que solo hay 1 registro en la base de datos
        recientes = await setup_idempotency_env["storage"].listar_recientes(10)
        assert len(recientes) == 1

        # Verificar que solo se notificó 1 vez a la sala de crisis
        assert len(setup_idempotency_env["notifier"].notificaciones) == 1
