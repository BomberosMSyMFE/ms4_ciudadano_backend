import io
import pytest
from httpx import AsyncClient, ASGITransport
from app.api.main import app
from app.api.dependencies import get_storage, get_evidence_storage, get_ia_validator, get_notifier
from app.adapters.memory_adapter import InMemoryDenunciaAdapter
from app.adapters.s3_storage_adapter import S3StorageAdapter
from app.ports.evidence_storage_port import IEvidenceStoragePort
from app.ports.ia_validator_port import IIAValidatorPort
from app.ports.notification_port import INotificationPort
from app.domain.models import DenunciaCiudadana

class MockTestEvidenceStorage(IEvidenceStoragePort):
    def __init__(self):
        self.subidas = []

    async def subir_evidencia(self, archivo_bytes: bytes, nombre_archivo: str, content_type: str = "image/jpeg") -> str:
        url = f"https://s3.amazonaws.com/bomberos-scz-evidencias/evidencias/mock_{nombre_archivo}"
        self.subidas.append({"bytes_len": len(archivo_bytes), "filename": nombre_archivo, "url": url})
        return url

class MockTestIAValidator(IIAValidatorPort):
    async def validar_imagen_fuego(self, imagen_url):
        return {"verificado_por_ia": True, "nivel_confianza": 0.90, "detecciones": ["fire"]}

    async def validar_imagen_bytes(self, archivo_bytes, nombre_archivo="evidencia.jpg", content_type="image/jpeg"):
        return {
            "verificado_automaticamente": True,
            "nivel_confianza": 0.96,
            "total_detecciones": 2,
            "detalles": [
                {"clase": "fire", "confianza": 0.96, "bbox": [10.0, 20.0, 150.0, 200.0]},
                {"clase": "dense_smoke", "confianza": 0.88, "bbox": [5.0, 5.0, 250.0, 300.0]}
            ],
            "motor": "YOLOv8 Deep Learning & Thermal Pixel Ratio"
        }

    async def clasificar_urgencia_texto(self, texto):
        return {"categoria_predicha": "CRITICO_ESTRUCTURAL", "confianza": 0.95}

class MockTestNotifier(INotificationPort):
    def __init__(self):
        self.alertas = []

    async def notificar_nueva_alerta(self, denuncia: DenunciaCiudadana) -> bool:
        self.alertas.append(denuncia.ticket_id)
        return True

@pytest.fixture
def setup_overrides():
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
        "s3": mock_s3,
        "ia": mock_ia,
        "notifier": mock_notifier
    }

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_s3_storage_adapter_fallback_local(tmp_path):
    # Sin credenciales de AWS debe usar fallback local sin lanzar excepciones
    adapter = S3StorageAdapter(
        aws_access_key="",
        aws_secret_key="",
        storage_dir=str(tmp_path)
    )
    assert not adapter.is_s3_active

    contenido = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" # Cabecera JPEG simulada
    url_generada = await adapter.subir_evidencia(contenido, "foto_siniestro.jpg", "image/jpeg")

    assert "http://localhost:8083/evidencias/" in url_generada
    assert "foto_siniestro.jpg" in url_generada

    # Verificar que el archivo se guardó físicamente en la carpeta temporal
    archivos = list(tmp_path.iterdir())
    assert len(archivos) == 1
    assert archivos[0].read_bytes() == contenido

@pytest.mark.asyncio
async def test_post_denuncia_con_foto_endpoint(setup_overrides):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Archivo simulado
        fake_image = io.BytesIO(b"fake image raw binary content for yolov8")
        files = {
            "foto": ("incendio_deposito.jpg", fake_image, "image/jpeg")
        }
        data = {
            "descripcion": "Incendio de proporciones en depósito de llantas en el Parque Industrial",
            "latitud": "-17.7689",
            "longitud": "-63.1456",
            "telefono_contacto": "+59178012345"
        }

        res = await client.post("/api/v1/denuncias/con-foto", files=files, data=data)
        assert res.status_code == 201
        res_data = res.json()

        assert "ticket_id" in res_data
        assert res_data["ticket_id"].startswith("RAD-")
        assert res_data["estado"] == "RECIBIDO_EN_TRIAJE"
        assert res_data["confianza_verificacion_ia"] == 0.96
        assert res_data["categoria_predicha"] == "CRITICO_ESTRUCTURAL"
        assert res_data["es_prioridad_alta"] is True
        assert "s3.amazonaws.com" in res_data["imagen_url"]
        assert len(res_data["detecciones_vision"]) == 2
        assert "YOLOv8" in res_data["motor_vision"]
        assert "ALERTA MÁXIMA" in res_data["instrucciones_seguridad"]

        # Verificar que se notificó a la sala de crisis
        assert len(setup_overrides["notifier"].alertas) == 1
        assert setup_overrides["notifier"].alertas[0] == res_data["ticket_id"]

        # Consultar por ticket ID para verificar consistencia
        res_get = await client.get(f"/api/v1/denuncias/{res_data['ticket_id']}")
        assert res_get.status_code == 200
        get_data = res_get.json()
        assert get_data["ticket_id"] == res_data["ticket_id"]
        assert get_data["imagen_url"] == res_data["imagen_url"]

@pytest.mark.asyncio
async def test_post_denuncia_con_foto_formato_invalido_retorna_415():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fake_pdf = io.BytesIO(b"%PDF-1.4...")
        files = {
            "foto": ("documento.pdf", fake_pdf, "application/pdf")
        }
        data = {
            "descripcion": "Documento con reporte",
            "latitud": "-17.78",
            "longitud": "-63.18"
        }
        res = await client.post("/api/v1/denuncias/con-foto", files=files, data=data)
        assert res.status_code == 415
