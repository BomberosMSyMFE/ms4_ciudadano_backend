import pytest
from app.adapters.mongo_adapter import MotorMongoAdapter
from app.domain.models import DenunciaCiudadana

@pytest.mark.asyncio
async def test_mongo_live_guardar_y_recuperar():
    adapter = MotorMongoAdapter(uri="mongodb://127.0.0.1:27017", db_name="bomberos_ciudadano_test")
    
    # Ping
    await adapter.db.command("ping")

    ticket = "RAD-LIVE-999"
    denuncia = DenunciaCiudadana(
        ticket_id=ticket,
        descripcion="Prueba de persistencia real en contenedor MongoDB Docker",
        latitud=-17.7833,
        longitud=-63.1821,
        telefono="+59170011223"
    )
    denuncia.asignar_evaluacion_ia(score_fuego=0.91, categoria="CRITICO_ESTRUCTURAL")

    # Guardar
    saved_id = await adapter.guardar_denuncia(denuncia)
    assert saved_id == ticket

    # Recuperar
    recuperada = await adapter.obtener_por_ticket(ticket)
    assert recuperada is not None
    assert recuperada.ticket_id == ticket
    assert recuperada.descripcion == "Prueba de persistencia real en contenedor MongoDB Docker"
    assert recuperada.score_fuego_ia == 0.91
    assert recuperada.categoria_nlp == "CRITICO_ESTRUCTURAL"
    assert recuperada.es_prioridad_alta() is True
