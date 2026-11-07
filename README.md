# MS-04: Portal de Denuncias Ciudadanas y Despacho Rápido
**Plataforma Distribuida Cuerpo de Bomberos — INF512 (Ingeniería de Software II)**  
**Semestre:** 2/2026 — UAGRM  
**Responsable:** Jael Mamani  
**Stack Tecnológico:** Python 3.11+ | FastAPI 0.111+ | Motor 3.5+ (Async MongoDB) | Boto3 1.34+ (AWS S3) | Pydantic v2 2.7+ | Uvicorn 0.30+ | Pytest 8.2+ | MongoDB 7.0  
**Patrón Arquitectónico:** Arquitectura Hexagonal (Ports & Adapters)  
**Mecanismo de Exposición:** REST API (OpenAPI 3.1 / JSON / Multipart) y Webhooks Asíncronos en puerto `8083`  
**Guía Técnica Completa de Arquitectura y AWS:** Consulta [GUIA_MS4_CIUDADANO_TECNICA.md](GUIA_MS4_CIUDADANO_TECNICA.md)

---

## 1. Encabezado Técnico

* **Microservicio:** `MS-04: Portal de Denuncias Ciudadanas y Despacho Rápido`
* **Ecosistema:** Plataforma Distribuida Integral de Gestión de Emergencias y Bomberos
* **Semestre Académico:** Semestre 2/2026 — UAGRM
* **Versiones Detectadas en Código:**
  * Python: `3.11+`
  * FastAPI: `^0.111.0`
  * Motor (Async Driver NoSQL): `^3.5.0`
  * Boto3 (AWS S3 Storage SDK): `^1.34.0`
  * Pydantic: `^2.7.0` (Settings `^2.2.0`)
  * Uvicorn: `^0.30.0`
  * HTTPX: `^0.27.0`
  * Pytest / Pytest-Asyncio: `^8.2.0` / `^0.23.0`
  * MongoDB Engine: `mongo:7.0` (puerto `27017:27017`)
* **Patrón de Arquitectura:** Arquitectura Hexagonal (Puertos y Adaptadores), desacoplando completamente la lógica central de negocio de los mecanismos de almacenamiento (MongoDB / AWS S3) y comunicación externa (MS-05 IA Core / MS-01 Comandos).
* **Mecanismo de Comunicación:** REST API HTTP/JSON/Multipart con especificación OpenAPI 3.1, cabecera de idempotencia (`Idempotency-Key`), endpoint multipart para fotos (`POST /api/v1/denuncias/con-foto`) y webhook para ingesta omnicanal (n8n / WhatsApp Bot).

---

## 2. Arquitectura de Código Hexagonal

Estructura hexagonal implementada en `app/`:

```text
+---------------------------------------------------------------------------------------------------------+
|                                    DRIVING ADAPTERS (ENTRADA PRIMARIA)                                  |
|  - FastAPI Router (app/api/routers/denuncias_router.py)                                                 |
|    * POST /api/v1/denuncias/con-foto (Subida multipart de imagen directa a S3 + YOLOv8)                 |
|    * POST /api/v1/denuncias (Recepción JSON estándar)                                                   |
|    * POST /api/v1/webhook/n8n-whatsapp (Webhook de automatización n8n)                                  |
|    * GET /api/v1/denuncias/{ticketId} (Tracking de estado para el ciudadano)                            |
|    * GET /evidencias/{archivo} (Servicio estático de fotos locales en fallback)                         |
|  - Dependency Injection Container (app/api/dependencies.py)                                             |
|  +---------------------------------------------------------------------------------------------------+  |
|  |                              APPLICATION LAYER (CASOS DE USO DEL SISTEMA)                         |  |
|  |  - DenunciasApplicationService (app/services/denuncias_service.py)                                |  |
|  |  +---------------------------------------------------------------------------------------------+  |  |
|  |  |                             DOMINIO CORE (NÚCLEO PURO INMUTABLE)                            |  |  |
|  |  |  [Entities & Business Logic]                                                                |  |  |
|  |  |   - DenunciaCiudadana (app/domain/models.py)                                                |  |  |
|  |  |     * Validador coordenadas geográficas (-90..90, -180..180)                                |  |  |
|  |  |     * Regla de prioridad: score_ia >= 0.85 o categoría CRITICO                              |  |  |
|  |  |     * Generación de instrucciones reactivas de seguridad ciudadana                          |  |  |
|  |  |  [Exceptions]                                                                               |  |  |
|  |  |   - DominioCiudadanoException, CoordenadasInvalidasException                                |  |  |
|  |  |   - DescripcionVaciaException, TicketNoEncontradoException                                  |  |  |
|  |  +---------------------------------------------------------------------------------------------+  |  |
|  |  [Secondary Ports / Interfaces]                                                                   |  |
|  |   - IDenunciaStoragePort (app/ports/storage_port.py)                                              |  |
|  |   - IEvidenceStoragePort (app/ports/evidence_storage_port.py)                                     |  |
|  |   - IIAValidatorPort (app/ports/ia_validator_port.py)                                             |  |
|  |   - INotificationPort (app/ports/notification_port.py)                                            |  |
|  +---------------------------------------------------------------------------------------------------+  |
|                                  DRIVEN ADAPTERS (SALIDA SECUNDARIA)                                    |
|  - MotorMongoAdapter (app/adapters/mongo_adapter.py -> Persistencia MongoDB 7.0)                         |
|  - S3StorageAdapter (app/adapters/s3_storage_adapter.py -> AWS S3 con Fallback a 'storage/evidencias/') |
|  - HttpIAAdapter (app/adapters/http_ia_adapter.py -> YOLOv8 y Triaje NLP en MS-05 IA Core)               |
|  - HttpComandosAdapter (app/adapters/http_comandos_adapter.py -> Despacho a Sala de Crisis MS-01)        |
|  - InMemoryDenunciaAdapter (app/adapters/memory_adapter.py -> Mocking unitario)                          |
+---------------------------------------------------------------------------------------------------------+
```

---

## 3. Modelo de Persistencia (MongoDB)

El microservicio utiliza MongoDB 7.0 para persistir incidentes de forma desacoplada y flexible en la base de datos `bomberos_ciudadano`:

| Colección | Campo Clave | Tipo | Restricciones / Reglas | Propósito en el Negocio |
| :--- | :--- | :--- | :--- | :--- |
| `denuncias` | `_id` / `ticket_id` | String | Clave única Primaria (`RAD-XXXXXX`) | Identificador universal del ticket entregado al ciudadano para tracking del incidente. |
| `denuncias` | `descripcion` | String | No vacío | Relato ciudadano de la emergencia. Base para el triaje NLP supervisado. |
| `denuncias` | `latitud` | Double | Rango [-90.0, 90.0] | Coordenada GPS para georreferenciación y despacho de unidades de bomberos. |
| `denuncias` | `longitud` | Double | Rango [-180.0, 180.0] | Coordenada GPS para georreferenciación. |
| `denuncias` | `telefono` | String | Opcional | Número de contacto de la persona que reporta para confirmaciones o canal WhatsApp. |
| `denuncias` | `imagen_url` | String | URL S3 / Local | Enlace a la evidencia en AWS S3 (`https://...amazonaws.com/...`) o local (`http://localhost:8083/evidencias/...`). |
| `denuncias` | `score_fuego_ia` | Double | Rango [0.0, 1.0] | Nivel de confianza emitido por la red convolucional YOLOv8 / análisis térmico. |
| `denuncias` | `categoria_nlp` | String | Taxonomía estandarizada | Clasificación semántica (`CRITICO_ESTRUCTURAL`, `ALTO_FORESTAL`, `CRITICO_GAS`, etc.). |
| `denuncias` | `estado` | String | Máquina de estados | Estado operativo (`RECIBIDO_EN_TRIAJE`, `UNIDAD_EN_CAMINO`, `EN_ESCENA`, `CONTROLADO`, `FALSA_ALARMA`). |
| `denuncias` | `es_prioridad_alta`| Boolean| Flag computado | `True` si el score de IA $\ge 0.85$ o la categoría inicia con `CRITICO`. Activa alarma en sala de crisis. |
| `denuncias` | `instrucciones_seguridad` | String | Texto reactivo | Guía para preservar la vida según la severidad evaluada (ej. evacuar, cortar suministros). |
| `denuncias` | `fecha_creacion` | Date | Timestamp UTC | Fecha y hora para orden cronológico en tableros de control. |

---

## 4. Almacenamiento en AWS S3 & Fallback Híbrido

El sistema implementa **resiliencia total de almacenamiento**:
* **Con credenciales AWS:** Guarda directamente en el Bucket S3 asignado.
* **Sin credenciales o si AWS no responde:** Almacena de forma desatendida en la carpeta local `storage/evidencias/` y la sirve mediante el endpoint `http://localhost:8083/evidencias/{archivo}`.
* Cuando se reciban las credenciales definitivas de AWS, solo basta colocarlas en `.env`:
  ```env
  AWS_ACCESS_KEY_ID=tu_access_key
  AWS_SECRET_ACCESS_KEY=tu_secret_key
  AWS_REGION=us-east-1
  AWS_S3_BUCKET_NAME=bomberos-scz-evidencias
  ```

---

## 5. Seeder de Datos Masivos (60 Incidentes en Santa Cruz)

Para demostración inmediata y pruebas de sala de crisis:
```bash
python scripts/seed_denuncias_mongodb.py 60
```
Genera 60 denuncias realistas georreferenciadas en el Parque Industrial, Plan 3000, Equipetrol, Centro Histórico, Urubó, etc., con scores de IA calculados y evidencias fotográficas.

---

## 6. Comandos de Inicialización y Ejecución

### Paso 1: Instalar Dependencias
```bash
pip install -r requirements.txt
```

### Paso 2: Iniciar Servidor FastAPI
```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8083 --reload
```

### Paso 3: Ejecutar Tests Automatizados
```bash
pytest tests/ -v
```
**Resultado:** 13 pruebas unitarias y de integración pasando al 100%.

---

## 7. Enlaces y Recursos

* **Swagger UI Interactivo:** `http://localhost:8083/docs`
* **Guía Técnica de Arquitectura y AWS S3:** [GUIA_MS4_CIUDADANO_TECNICA.md](GUIA_MS4_CIUDADANO_TECNICA.md)
* **Contrato OpenAPI YAML Compartido:** [ms4_contrato.yaml](file:///C:/Users/Usuario/Documents/U/Semestre%20II-2026/SW2/SegundoParcial/shared_contracts_specs/ms4_contrato.yaml)
* **Seeder de MongoDB:** [seed_denuncias_mongodb.py](file:///C:/Users/Usuario/Documents/U/Semestre%20II-2026/SW2/SegundoParcial/ms4_ciudadano_backend/scripts/seed_denuncias_mongodb.py)
