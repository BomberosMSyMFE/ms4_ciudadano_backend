# Guía de Integración Técnica de Microservicios — Módulos Jael Sandoval
**Plataforma Distribuida Cuerpo de Bomberos — INF512 (Ingeniería de Software II)**  
**Semestre:** 2/2026 — UAGRM  
**Responsable:** Jael Sandoval  

Esta guía está diseñada para los compañeros del equipo de desarrollo (Nataly en MS-01 Comandos/Despacho, encargados de MS-02 Flotas, Microfrontends y Automatizaciones n8n). Aquí se detalla todo lo implementado, cómo interactuar con cada servicio, puertos de ejecución, contratos y ejemplos concretos de integración.

---

## 1. Resumen Ejecutivo del Trabajo Implementado

| Microservicio | Responsabilidad Principal | Stack / Versiones | Patrón Arquitectónico | Mecanismo y Puerto |
| :--- | :--- | :--- | :--- | :--- |
| **MS-03: Inventario y Recursos** | Gestión de kits de respiración EPP, espumógeno/retardante, participante en transacción distribuida SAGA. | PHP 8.2+ / Laravel 11 / PostgreSQL 16 / Lighthouse | Domain-Driven Design (DDD) Táctico | GraphQL API (`POST /graphql`) en **Puerto 8003** |
| **MS-04: Portal Ciudadano** | Recepción de denuncias de emergencias, cálculo de prioridad, webhooks omnicanal y georreferenciación. | Python 3.11+ / FastAPI / MongoDB 7.0 / Motor | Arquitectura Hexagonal (Ports & Adapters) | REST API (OpenAPI 3.1) en **Puerto 8083** |
| **MS-05: IA Core (Visión y NLP)** | Inferencia cognitiva offline de evidencias visuales (YOLOv8 Nano) y triaje semántico de emergencias (NLP TF-IDF). | Python 3.11+ / PyTorch / YOLOv8 / Scikit-Learn | Service-Based In-Memory Ingestion | REST API en **Puerto 8005** |

---

## 2. Guía de Integración con MS-03 (Inventario Backend)

### ¿Cómo integrarse desde MS-01 (Nataly / Orquestador SAGA de Despacho)?
Durante el flujo de despacho de una emergencia, MS-01 debe interactuar con MS-03 mediante el endpoint GraphQL:
* **URL:** `http://localhost:8003/graphql`
* **Método:** `POST`
* **Header:** `Content-Type: application/json`

#### A. Paso 2 de la SAGA: Reservar Recursos para un Camión
Cuando se determina despachar un camión (ej. `B-04-SCZ`) con requerimiento de espumógeno para un incidente:

```graphql
mutation {
  reservarKitParaDespacho(
    incidenteId: "INC-101"
    camionId: "B-04-SCZ"
    litrosEspumogeno: 250.0
  ) {
    exito
    transaccionId
    materialesReservados
    mensaje
    codigoError
  }
}
```
* **Comportamiento interno:** 
  1. Verifica que exista un Kit EPP con tubo de oxígeno a presión segura ($\ge 250$ bares).
  2. Verifica que haya al menos 250 litros de espumógeno vigentes (no vencidos).
  3. Descuenta atómicamente el stock en PostgreSQL y pasa el Kit a estado `ASIGNADO_CAMION`.
  4. Genera y retorna un identificador de transacción único (ej. `TX-SAGA-INV-A1B2C3`).

#### B. Compensación de la SAGA (Rollback en caso de fallo en Flotas)
Si posteriormente la asignación del camión en MS-02 falla (ej. sin chofer o vehículo en pana), Nataly debe disparar la mutación compensatoria para garantizar consistencia eventual:

```graphql
mutation {
  liberarReservaCompensatoria(
    transaccionId: "TX-SAGA-INV-A1B2C3"
  ) {
    exito
    mensaje
  }
}
```
* **Comportamiento interno:** Repone de inmediato los 250 litros de espumógeno y restaura el Kit EPP al estado `DISPONIBLE`.

#### C. Integración desde Microfrontends (Consultas sin Over-fetching)
Para tableros administrativos donde solo se requiere el balance rápido de stock sin sobrecargar la red:
```graphql
query {
  auditoriaStockGeneral(estacionId: "EST-01") {
    codigo
    nombre
    litrosDisponibles
  }
}
```

---

## 3. Guía de Integración con MS-04 (Portal Ciudadano Backend)

### ¿Cómo integrarse desde Aplicaciones Ciudadanas o Canales Web?
* **Base URL:** `http://localhost:8083/api/v1`
* **Documentación Interactiva (Swagger):** `http://localhost:8083/docs`

#### A. Registro de una Denuncia Ciudadana (`POST /api/v1/denuncias`)
```bash
curl -X POST "http://localhost:8083/api/v1/denuncias" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: CLAVE-UNICA-12345" \
  -d '{
    "descripcion": "Incendio violento en tinglado industrial con riesgo de propagacion",
    "latitud": -17.7833,
    "longitud": -63.1821,
    "telefono_contacto": "+59170011223",
    "imagen_url": "https://storage.bomberos.gob.bo/evidencias/fuego_tinglado.jpg"
  }'
```
* **Respuesta (HTTP 201):**
```json
{
  "ticket_id": "RAD-B9F2A1",
  "estado": "RECIBIDO_EN_TRIAJE",
  "confianza_verificacion_ia": 0.94,
  "mensaje": "Reporte registrado y encolado para atencion inmediata."
}
```

#### B. Ingesta desde el Bot de WhatsApp / Agente n8n (`POST /api/v1/webhook/n8n-whatsapp`)
Si configuraron un flujo en n8n que recibe mensajes o fotos de WhatsApp:
```bash
curl -X POST "http://localhost:8083/api/v1/webhook/n8n-whatsapp" \
  -H "Content-Type: application/json" \
  -d '{
    "telefono": "+59178999888",
    "texto": "Fuga de gas en garrafa de restaurante en el centro",
    "media_url": null,
    "score_fuego_ia": null
  }'
```

#### C. Consulta del Estado de la Denuncia (`GET /api/v1/denuncias/{ticketId}`)
Permite al ciudadano o al operador saber la evolución del incidente:
```bash
curl -X GET "http://localhost:8083/api/v1/denuncias/RAD-B9F2A1"
```

---

## 4. Guía de Integración con MS-05 (IA Core Cognitivo)

* **Base URL:** `http://localhost:8005/api/v1`
* **Documentación Swagger:** `http://localhost:8005/docs`

#### A. Clasificación NLP de Urgencia (`POST /api/v1/nlp/clasificar-urgencia`)
Clasifica mensajes de texto de emergencias en categorías estandarizadas:
```bash
curl -X POST "http://localhost:8005/api/v1/nlp/clasificar-urgencia" \
  -H "Content-Type: application/json" \
  -d '{"texto": "Quema de pastizales descontrolada con viento fuerte en la ruta al norte"}'
```
* **Respuesta:**
```json
{
  "categoria_predicha": "ALTO_FORESTAL",
  "severidad": "ALTA",
  "confianza": 0.89,
  "palabras_clave": ["quema", "pastizales", "viento"]
}
```

#### B. Validación de Evidencia Visual por IA (`POST /api/v1/vision/validar-evidencia`)
Envío de imagen en binario (`multipart/form-data`) para inferencia con YOLOv8 Nano:
```bash
curl -X POST "http://localhost:8005/api/v1/vision/validar-evidencia" \
  -F "archivo=@evidencia_siniestro.jpg"
```

---

## 5. Matriz de Puertos y Servicios para Levantamiento Local

| Servicio | Puerto Predeterminado | Endpoint Principal | Swagger / Playground |
| :--- | :--- | :--- | :--- |
| **PostgreSQL (Inventario)** | `5435` (mapeado a `5432` del contenedor) | `localhost:5435` | `psql -h 127.0.0.1 -p 5435 -U jael_admin -d inventario_db` |
| **MongoDB (Ciudadano)** | `27017` | `mongodb://127.0.0.1:27017` | `mongosh mongodb://127.0.0.1:27017/bomberos_ciudadano` |
| **MS-03 Inventario** | `8003` | `http://localhost:8003/graphql` | `http://localhost:8003/graphql` |
| **MS-04 Ciudadano** | `8083` | `http://localhost:8083/api/v1` | `http://localhost:8083/docs` |
| **MS-05 IA Core** | `8005` | `http://localhost:8005/api/v1` | `http://localhost:8005/docs` |

---

## 6. Ubicación de Contratos Oficiales en `shared_contracts_specs`

1. **Contrato GraphQL MS-03:** `shared_contracts_specs/ms3_schema.graphql`
2. **Contrato OpenAPI MS-04:** `shared_contracts_specs/ms4_contrato.yaml`
