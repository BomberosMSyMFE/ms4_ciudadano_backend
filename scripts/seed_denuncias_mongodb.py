#!/usr/bin/env python3
"""
scripts/seed_denuncias_mongodb.py
Seeder de Datos Realistas para el Portal Ciudadano y Denuncias de Emergencia (MS-04).
Genera 60 incidentes georreferenciados en Santa Cruz de la Sierra con scores de IA y estados operativos.
"""

import os
import sys
import random
import asyncio
from datetime import datetime, timedelta, timezone

# Agregar directorio raiz al sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motor.motor_asyncio import AsyncIOMotorClient

# Ubicaciones clave en Santa Cruz de la Sierra
UBICACIONES_SCZ = [
    {"zona": "Parque Industrial Manzana 12", "lat": -17.7680, "lon": -63.1420},
    {"zona": "Centro Histórico - Calle Junín", "lat": -17.7833, "lon": -63.1821},
    {"zona": "Plan 3000 - Plaza El Mechero", "lat": -17.8280, "lon": -63.1425},
    {"zona": "Equipetrol - Av. San Martín Calle 7", "lat": -17.7620, "lon": -63.1950},
    {"zona": "Villa 1ro de Mayo - Av. Cumavi", "lat": -17.7950, "lon": -63.1380},
    {"zona": "Pampa de la Isla - Av. Montecristo", "lat": -17.7710, "lon": -63.1190},
    {"zona": "Doble Vía a La Guardia - Km 6", "lat": -17.8310, "lon": -63.2200},
    {"zona": "Av. Cristo Redentor - Km 8 al Norte", "lat": -17.7250, "lon": -63.1680},
    {"zona": "Radial 10 y 5to Anillo", "lat": -17.8090, "lon": -63.1490},
    {"zona": "Mercado Antiguo Los Pozos", "lat": -17.7780, "lon": -63.1750},
    {"zona": "La Ramada - Av. Grigotá y 1er Anillo", "lat": -17.7920, "lon": -63.1880},
    {"zona": "Urubó - Próximo al Río Piraí", "lat": -17.7550, "lon": -63.2080},
    {"zona": "Barrio Guaracachi - Estación Ferroviaria", "lat": -17.7780, "lon": -63.1480},
    {"zona": "Av. Santos Dumont y 4to Anillo", "lat": -17.8150, "lon": -63.1890},
    {"zona": "Av. Virgen de Cotoca y 3er Anillo", "lat": -17.7810, "lon": -63.1550}
]

TIPOS_INCIDENTES = [
    {
        "categoria": "CRITICO_ESTRUCTURAL",
        "descripciones": [
            "Incendio violento en tinglado industrial de plásticos, llamas altas y peligro de colapso.",
            "Fuego descontrolado en depósito comercial de colchones, humo denso y explosiones menores.",
            "Incendio estructural en vivienda de dos plantas, chispas en tendido eléctrico contiguo.",
            "Taller mecánico en llamas, presencia de solventes inflamables y aceites en combustión.",
            "Fuego en depósito de neumáticos con columnas de humo negro visibles a varios kilómetros."
        ],
        "score_ia_range": (0.85, 0.98),
        "prioridad": True
    },
    {
        "categoria": "CRITICO_GAS",
        "descripciones": [
            "Fuga masiva de gas licuado en cocina de restaurante, fuerte olor y clientes evacuados.",
            "Garrafa industrial con válvula rota silbando en mercado de comidas, alto riesgo de deflagración.",
            "Fuga de amoníaco anhidro en frigorífico cárnico, trabajadores presentando asfixia y ardor.",
            "Tubería de gas natural domiciliario perforada por maquinaria en obras de alcantarillado."
        ],
        "score_ia_range": (0.75, 0.95),
        "prioridad": True
    },
    {
        "categoria": "ALTO_FORESTAL",
        "descripciones": [
            "Quema de pastizales y cordón ecológico propagándose velozmente hacia viviendas por viento sur.",
            "Incendio de maleza seca en lote baldío extenso, llamas superando los 3 metros de altura.",
            "Chaqueo clandestino fuera de control cerca de urbanización cerrada en zona norte.",
            "Foco de calor en borde de carretera con escasa visibilidad por humo denso."
        ],
        "score_ia_range": (0.82, 0.96),
        "prioridad": True
    },
    {
        "categoria": "ALTO_VEHICULAR",
        "descripciones": [
            "Colisión múltiple entre micro de transporte público y camión, pasajeros atrapados en fierros.",
            "Vuelco de vehículo cisterna de combustible con derrame activo sobre la calzada.",
            "Choque frontal de dos camionetas con principio de incendio en el compartimiento del motor."
        ],
        "score_ia_range": (0.65, 0.88),
        "prioridad": False
    },
    {
        "categoria": "BAJO_AUXILIO",
        "descripciones": [
            "Árbol añoso caído sobre el cableado de alta tensión obstaculizando la vía pública.",
            "Rescate de animal doméstico atrapado en boca de tormenta pluvial.",
            "Derame menor de pintura y solventes en acera peatonal sin heridos."
        ],
        "score_ia_range": (0.10, 0.40),
        "prioridad": False
    },
    {
        "categoria": "PENDIENTE_TRIAJE",
        "descripciones": [
            "Olor extraño en la cuadra, vecinos sospechan de quema de basura a puertas cerradas.",
            "Alarma contra incendios sonando continuamente en edificio residencial desocupado.",
            "Humo ligero saliendo de chimenea de panadería artesanal."
        ],
        "score_ia_range": (0.05, 0.35),
        "prioridad": False
    }
]

ESTADOS_OPERATIVOS = [
    "RECIBIDO_EN_TRIAJE",
    "UNIDAD_EN_CAMINO",
    "EN_ESCENA",
    "CONTROLADO",
    "FALSA_ALARMA"
]

EVIDENCIAS_MOCK = [
    "https://bomberos-scz-evidencias.s3.us-east-1.amazonaws.com/evidencias/incendio_tinglado_scz_01.jpg",
    "https://bomberos-scz-evidencias.s3.us-east-1.amazonaws.com/evidencias/fuego_pastizal_norte_02.jpg",
    "https://bomberos-scz-evidencias.s3.us-east-1.amazonaws.com/evidencias/humo_negro_parque_industrial_03.jpg",
    "https://bomberos-scz-evidencias.s3.us-east-1.amazonaws.com/evidencias/fuga_garrafa_mercado_04.jpg",
    "https://bomberos-scz-evidencias.s3.us-east-1.amazonaws.com/evidencias/accidente_camion_cisterna_05.jpg",
    "http://localhost:8083/evidencias/fallback_evidencia_local_01.jpg",
    None
]

async def seed_mongodb(total_registros: int = 60, limpiar_anterior: bool = True):
    mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    mongo_db_name = os.getenv("MONGO_DB", "bomberos_ciudadano")
    
    print(f"============================================================")
    print(f"🚀 Iniciando Seeder de Denuncias Ciudadanas (MS-04)")
    print(f"📦 Destino: {mongo_uri} | BD: {mongo_db_name}")
    print(f"📊 Total de registros a generar: {total_registros}")
    print(f"============================================================")

    client = AsyncIOMotorClient(mongo_uri)
    db = client[mongo_db_name]
    collection = db["denuncias"]

    if limpiar_anterior:
        borrados = await collection.delete_many({})
        print(f"🧹 Registros anteriores eliminados: {borrados.deleted_count}")

    documentos = []
    ahora = datetime.now(timezone.utc)

    for i in range(total_registros):
        # 1. Seleccionar tipo de incidente y ubicación
        tipo_meta = random.choice(TIPOS_INCIDENTES)
        ubicacion = random.choice(UBICACIONES_SCZ)
        
        # Jitter aleatorio en coordenadas (+- 500 metros)
        lat = round(ubicacion["lat"] + random.uniform(-0.005, 0.005), 6)
        lon = round(ubicacion["lon"] + random.uniform(-0.005, 0.005), 6)
        
        # 2. Generar ticket y detalles
        ticket_hex = f"{random.randint(0x100000, 0xFFFFFF):06X}"
        ticket_id = f"RAD-{ticket_hex}"
        descripcion = f"[{ubicacion['zona']}] {random.choice(tipo_meta['descripciones'])}"
        telefono = f"+591{random.choice(['7', '6'])}{random.randint(1000000, 9999999)}"
        
        # 3. Scores de IA y prioridad
        score_min, score_max = tipo_meta["score_ia_range"]
        score_ia = round(random.uniform(score_min, score_max), 3)
        es_alta = score_ia >= 0.85 or tipo_meta["categoria"].startswith("CRITICO")

        # 4. Instrucciones tácticas
        if es_alta:
            instrucciones = (
                "ALERTA MÁXIMA: Evacue a favor del viento y corte suministros de gas y electricidad. "
                "Unidades despachadas con prioridad."
            )
        else:
            instrucciones = (
                "Mantenga la calma, aléjese de fuentes de calor y despeje el área para el ingreso de unidades."
            )

        # 5. Estado operativo ponderado
        estado = random.choices(
            ESTADOS_OPERATIVOS,
            weights=[30, 25, 20, 20, 5],
            k=1
        )[0]

        # 6. Fecha distribuida en los últimos 3 días
        minutos_atras = random.randint(5, 72 * 60)
        fecha_creacion = ahora - timedelta(minutes=minutos_atras)

        # 7. Evidencia fotográfica
        evidencia_url = random.choice(EVIDENCIAS_MOCK)

        doc = {
            "_id": ticket_id,
            "ticket_id": ticket_id,
            "descripcion": descripcion,
            "latitud": lat,
            "longitud": lon,
            "telefono": telefono,
            "imagen_url": evidencia_url,
            "score_fuego_ia": score_ia,
            "categoria_nlp": tipo_meta["categoria"],
            "estado": estado,
            "instrucciones_seguridad": instrucciones,
            "es_prioridad_alta": es_alta,
            "fecha_creacion": fecha_creacion
        }
        documentos.append(doc)

    # Inserción por lotes
    await collection.insert_many(documentos)
    print(f"✅ Se insertaron exitosamente {len(documentos)} denuncias en MongoDB.")

    # Resumen de estadísticas
    conteo_altas = sum(1 for d in documentos if d["es_prioridad_alta"])
    print(f"📈 Resumen Operativo:")
    print(f"   - Total Incidentes: {len(documentos)}")
    print(f"   - Prioridad ALTA (Despacho Crítico): {conteo_altas}")
    print(f"   - Prioridad NORMAL: {len(documentos) - conteo_altas}")
    print(f"   - Con Evidencia Fotográfica: {sum(1 for d in documentos if d['imagen_url'])}")
    print(f"============================================================")

    client.close()

if __name__ == "__main__":
    limpiar = "--no-clear" not in sys.argv
    total = 60
    for arg in sys.argv[1:]:
        if arg.isdigit():
            total = int(arg)
    asyncio.run(seed_mongodb(total_registros=total, limpiar_anterior=limpiar))
