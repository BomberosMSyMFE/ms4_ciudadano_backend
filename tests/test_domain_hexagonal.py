import pytest
from app.domain.models import DenunciaCiudadana
from app.domain.exceptions import CoordenadasInvalidasException, DescripcionVaciaException
from app.adapters.memory_adapter import InMemoryDenunciaAdapter
from app.services.denuncias_service import DenunciasApplicationService
from app.ports.ia_validator_port import IIAValidatorPort
from app.ports.notification_port import INotificationPort

class MockIAAdapter(IIAValidatorPort):
    async def validar_imagen_fuego(self, imagen_url):
        if imagen_url and "fuego" in imagen_url:
            return {"verificado_por_ia": True, "nivel_confianza": 0.95, "detecciones": ["fuego"]}
        return {"verificado_por_ia": False, "nivel_confianza": 0.10, "detecciones": []}

    async def validar_imagen_bytes(self, archivo_bytes, nombre_archivo="evidencia.jpg", content_type="image/jpeg"):
        return {
            "verificado_automaticamente": True,
            "nivel_confianza": 0.95,
            "total_detecciones": 1,
            "detalles": [{"clase": "fire", "confianza": 0.95}],
            "motor": "YOLOv8 Deep Learning"
        }

    async def clasificar_urgencia_texto(self, texto):
        if "tinglado" in texto or "humo" in texto:
            return {"categoria_predicha": "CRITICO_ESTRUCTURAL", "confianza": 0.92}
        return {"categoria_predicha": "BAJO_AUXILIO", "confianza": 0.80}

class MockNotifier(INotificationPort):
    def __init__(self):
        self.notificaciones = []

    async def notificar_nueva_alerta(self, denuncia):
        self.notificaciones.append(denuncia.ticket_id)
        return True

def test_dominio_invariantes_coordenadas_validas():
    # Coordenadas de Santa Cruz de la Sierra válidas
    denuncia = DenunciaCiudadana(
        ticket_id="RAD-TEST-01",
        descripcion="Incendio en depósito",
        latitud=-17.7833,
        longitud=-63.1821
    )
    assert denuncia.ticket_id == "RAD-TEST-01"
    assert denuncia.latitud == -17.7833
    assert not denuncia.es_prioridad_alta()

def test_dominio_rechaza_coordenadas_fuera_de_rango():
    with pytest.raises(CoordenadasInvalidasException):
        DenunciaCiudadana(
            ticket_id="RAD-TEST-02",
            descripcion="Incendio",
            latitud=150.0, # Inválido
            longitud=-63.0
        )

def test_dominio_rechaza_descripcion_vacia():
    with pytest.raises(DescripcionVaciaException):
        DenunciaCiudadana(
            ticket_id="RAD-TEST-03",
            descripcion="   ",
            latitud=-17.78,
            longitud=-63.18
        )

def test_dominio_regla_prioridad_alta_con_ia():
    denuncia = DenunciaCiudadana(
        ticket_id="RAD-TEST-04",
        descripcion="Fuego forestal",
        latitud=-17.78,
        longitud=-63.18
    )
    assert not denuncia.es_prioridad_alta()

    # Asigna score IA alto
    denuncia.asignar_evaluacion_ia(score_fuego=0.92, categoria="ALTO_FORESTAL")
    assert denuncia.es_prioridad_alta()
    assert "ALERTA MÁXIMA" in denuncia.instrucciones_seguridad

@pytest.mark.asyncio
async def test_servicio_aplicacion_orquestacion_completa():
    storage = InMemoryDenunciaAdapter()
    ia = MockIAAdapter()
    notifier = MockNotifier()

    service = DenunciasApplicationService(storage, ia, notifier)

    resultado = await service.registrar_denuncia(
        descripcion="Humo negro y llamas en tinglado",
        latitud=-17.7833,
        longitud=-63.1821,
        telefono="+59170012345",
        imagen_url="http://evidencias/fuego_tinglado.jpg"
    )

    assert resultado["ticket_id"].startswith("RAD-")
    assert resultado["estado"] == "RECIBIDO_EN_TRIAJE"
    assert resultado["confianza_verificacion_ia"] == 0.95
    assert resultado["categoria_predicha"] == "CRITICO_ESTRUCTURAL"
    assert resultado["es_prioridad_alta"] is True
    assert len(notifier.notificaciones) == 1

    # Verificar persistencia en el puerto de almacenamiento
    guardado = await storage.obtener_por_ticket(resultado["ticket_id"])
    assert guardado is not None
    assert guardado.telefono == "+59170012345"
