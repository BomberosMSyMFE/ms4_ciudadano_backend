# MS-04: Portal de Denuncias Ciudadanas y Despacho Rápido
**Plataforma Distribuida Cuerpo de Bomberos — INF512 (Ingeniería de Software II)**  
**Semestre:** 2/2026 — UAGRM  
**Responsable:** Jael Sandoval  
**Stack Tecnológico:** Python 3.11+ | FastAPI 0.111+ | Motor 3.5+ (Async MongoDB) | Pydantic v2 2.7+ | Uvicorn 0.30+ | Pytest 8.2+ | MongoDB 7.0  
**Patrón Arquitectónico:** Arquitectura Hexagonal (Ports & Adapters)  
**Mecanismo de Exposición:** REST API (OpenAPI 3.1 / JSON) y Webhooks Asíncronos en puerto 8083  

---

## 1. Encabezado Técnico

* **Microservicio:** `MS-04: Portal de Denuncias Ciudadanas y Despacho Rápido`
* **Ecosistema:** Plataforma Distribuida Integral de Gestión de Emergencias y Bomberos
* **Semestre Académico:** Semestre 2/2026 — UAGRM
* **Versiones Detectadas en Código:**
  * Python: `3.11+`
  * FastAPI: `^0.111.0`
  * Motor (Async Driver NoSQL): `^3.5.0`
  * Pydantic: `^2.7.0` (Settings `^2.2.0`)
  * Uvicorn: `^0.30.0`
  * HTTPX: `^0.27.0`
  * Pytest / Pytest-Asyncio: `^8.2.0` / `^0.23.0`
  * MongoDB Engine: `mongo:7.0` (puerto `27017:27017`)
* **Patrón de Arquitectura:** Arquitectura Hexagonal (Puertos y Adaptadores), desacoplando completamente la lógica central de negocio de los mecanismos de almacenamiento y comunicación externa.
* **Mecanismo de Comunicación:** REST API HTTP/JSON con especificación OpenAPI 3.1, soporte de cabecera de idempotencia (`Idempotency-Key`) y webhook para ingesta omnicanal (n8n / WhatsApp Bot). Se comunica asíncronamente vía HTTP con MS-05 para inferencia cognitiva.

---

## 2. Arquitectura de Código

Estructura hexagonal implementada en `app/`:

```text
+---------------------------------------------------------------------------------------+
|                         DRIVING ADAPTERS (ENTRADA PRIMARIA)                           |
|  - FastAPI Router (app/api/routers/denuncias_router.py)                               |
|  - Ingesta Webhook n8n (app/api/routers/denuncias_router.py:webhook_n8n_whatsapp)     |
|  - Dependency Injection Container (app/api/dependencies.py)                           |
|  +---------------------------------------------------------------------------------+  |
|  |                   APPLICATION LAYER (CASOS DE USO DEL SISTEMA)                  |  |
|  |  - DenunciasApplicationService (app/services/denuncias_service.py)              |  |
|  |  +---------------------------------------------------------------------------+  |  |
|  |  |                          DOMAIN CORE (NÚCLEO PURO)                        |  |  |
|  |  |  [Entities & Business Logic]                                              |  |  |
|  |  |   - DenunciaCiudadana (app/domain/models.py)                              |  |  |
|  |  |     * Validador coordenadas geográficas (-90..90, -180..180)              |  |  |
|  |  |     * Regla de prioridad: score_ia >= 0.85 o categoría CRITICO            |  |  |
|  |  |     * Generación de instrucciones reactivas de seguridad ciudadana        |  |  |
|  |  |  [Exceptions]                                                             |  |  |
|  |  |   - DominioCiudadanoException, CoordenadasInvalidasException              |  |  |
|  |  |   - DescripcionVaciaException, TicketNoEncontradoException                |  |  |
|  |  +---------------------------------------------------------------------------+  |  |
|  |  [Secondary Ports / Interfaces]                                                 |  |
|  |   - IDenunciaStoragePort (app/ports/storage_port.py)                            |  |
|  |   - IIAValidatorPort (app/ports/ia_validator_port.py)                           |  |
|  |   - INotificationPort (app/ports/notification_port.py)                          |  |
|  +---------------------------------------------------------------------------------+  |
|                       DRIVEN ADAPTERS (SALIDA SECUNDARIA)                             |
|  - MotorMongoAdapter (app/adapters/mongo_adapter.py -> Persistencia MongoDB)          |
|  - HttpIAAdapter (app/adapters/http_ia_adapter.py -> Invocación a MS-05 IA Core)      |
|  - ConsoleNotificationAdapter (app/adapters/console_notification_adapter.py)          |
|  - InMemoryDenunciaAdapter (app/adapters/memory_adapter.py -> Mocking unitario)       |
+---------------------------------------------------------------------------------------+
```

---

## 3. Modelo de Persistencia

El microservicio utiliza MongoDB 7.0 para persistir incidentes de forma desacoplada y flexible en la base de datos `bomberos_ciudadano`:

| Colección | Campo Clave | Tipo | Índices y Restricciones | Propósito Operativo en el Negocio |
| :--- | :--- | :--- | :--- | :--- |
| `denuncias` | `_id` / `ticket_id` | String | Clave única Primaria (`RAD-XXXXXX`) | Identificador universal del ticket entregado al ciudadano para tracking del incidente. |
| `denuncias` | `descripcion` | String | No vacío | Relato ciudadano de la emergencia. Base para el triaje NLP supervisado. |
| `denuncias` | `latitud` | Double | Rango validado [-90.0, 90.0] | Coordenada GPS para georreferenciación y despacho de unidades de bomberos. |
| `denuncias` | `longitud` | Double | Rango validado [-180.0, 180.0] | Coordenada GPS para georreferenciación. |
| `denuncias` | `telefono` | String | Opcional | Número de contacto de la persona que reporta para confirmaciones o canal WhatsApp. |
| `denuncias` | `imagen_url` | String | Opcional (URI) | URL de la imagen o video adjunto, enviado a MS-05 para visión computacional. |
| `denuncias` | `score_fuego_ia` | Double | Rango [0.0, 1.0] | Nivel de confianza emitido por la red convolucional YOLOv8 / análisis térmico. |
| `denuncias` | `categoria_nlp` | String | Taxonomía estandarizada | Clasificación semántica (`CRITICO_ESTRUCTURAL`, `ALTO_FORESTAL`, `CRITICO_GAS`, etc.). |
| `denuncias` | `estado` | String | Máquina de estados | Estado operativo (`RECIBIDO_EN_TRIAJE`, `UNIDAD_EN_CAMINO`, `EN_ESCENA`, `CONTROLADO`, `FALSA_ALARMA`). |
| `denuncias` | `es_prioridad_alta`| Boolean| Flag computado | `True` si el score de IA $\ge 0.85$ o la categoría inicia con `CRITICO`. Activa alarma en sala de crisis. |
| `denuncias` | `instrucciones_seguridad` | String | Texto reactivo | Guía para preservar la vida según la severidad evaluada (ej. evacuar, cortar suministros). |
| `denuncias` | `fecha_creacion` | Date | Índice descendente `-1` | Timestamp UTC para orden cronológico en tableros de control. |

---

## 4. Integración Distribuida y Flujos de Negocio

### Diagrama de Flujo del Ecosistema (ASCII)

```text
  Ciudadano / Web           Bot WhatsApp (n8n)
        |                           |
        |--- POST /denuncias ------>|
        |                           |--- POST /webhook/n8n-whatsapp ---> MS-04 Ciudadano
        |                                                                     |
        |                                                                     |-- 1. Valida Coordenadas
        |                                                                     |      y Reglas Dominio
        |                                                                     |
        |                                  MS-05 IA Core                      |-- 2. Invocación HTTP Asíncrona
        |                                        |                            |
        |                                        |<-- POST /vision/validar ---| (Si hay evidencia URL)
        |                                        |--- Score Confianza ------->|
        |                                        |                            |
        |                                        |<-- POST /nlp/clasificar ---| (Texto descripción)
        |                                        |--- Categoría y Nivel ----->|
        |                                                                     |
        |                                                                     |-- 3. Computa Prioridad Alta
        |                                                                     |      e Instrucciones
        |                                                                     |
        |                                  MongoDB 7.0                        |-- 4. Persiste Ticket
        |                                        |                            |      Colección 'denuncias'
        |                                        |<-- upsert(RAD-XXXXXX) -----|
        |                                                                     |
        |                                  MS-01 Comandos / Sala de Crisis    |-- 5. Evento Notificación
        |                                        |                            |
        |<-- Retorna Ticket y Recomendación -----|<-- Nueva Alerta Crítica ---|
```

### Operaciones Críticas de API

#### 1. Registrar Denuncia Ciudadana (`POST /api/v1/denuncias`)
* **Headers:** `Idempotency-Key` (opcional para prevenir registros duplicados por reintentos de red).
* **Payload:** `descripcion` (string), `latitud` (float), `longitud` (float), `telefono_contacto` (string opcional), `imagen_url` (string opcional).
* **Flujo:** Evalúa el contenido mediante MS-05 (YOLOv8 + NLP), calcula la prioridad, persiste en MongoDB y notifica a sala de crisis.
* **Respuesta:** HTTP 201 (`ticket_id`, `estado`, `confianza_verificacion_ia`, `mensaje`).

#### 2. Consultar Estado de Incidente (`GET /api/v1/denuncias/{ticketId}`)
* **Parámetros:** `ticketId` (identificador único del ticket, ej. `RAD-E49818`).
* **Respuesta:** HTTP 200 (`ticket_id`, `estado`, `instrucciones_seguridad`).

#### 3. Webhook Omnicanal n8n / WhatsApp (`POST /api/v1/webhook/n8n-whatsapp`)
* **Payload:** `telefono`, `texto`, `media_url`, `score_fuego_ia`.
* **Flujo:** Ingesta directa de alertas ciudadanas provenientes del bot conversacional automatizado con n8n.
* **Respuesta:** HTTP 200 (`status: PROCESADO_Y_ENCOLADO`, `ticket_id`, `es_prioridad_alta`).

#### 4. Listar Denuncias Recientes (`GET /api/v1/denuncias`)
* **Query Params:** `limite` (entero, default: 20).
* **Respuesta:** Lista de incidentes ordenada cronológicamente para paneles de control de despacho.

---

## 5. Comandos de Inicialización y Ejecución

### Paso 1: Levantar MongoDB con Docker
```bash
# Iniciar contenedor MongoDB 7.0
docker run -d --name bomberos-mongo-ciudadano \
  -p 27017:27017 \
  mongo:7.0
```

### Paso 2: Instalar Dependencias
```bash
# Crear y activar entorno virtual (opcional pero recomendado)
python -m venv venv
# En Windows:
.\venv\Scripts\activate
# En Linux/macOS:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Paso 3: Configurar Variables de Entorno
```bash
cp .env.example .env
```
Contenido de `.env`:
```dotenv
APP_NAME="MS-04 Portal Ciudadano"
APP_ENV=development
PORT=8083
MONGO_URI=mongodb://127.0.0.1:27017
MONGO_DB=bomberos_ciudadano
IA_CORE_URL=http://127.0.0.1:8005
```

### Paso 4: Iniciar el Servidor de Desarrollo
```bash
# Iniciar con Uvicorn en localhost (Puerto 8083)
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8083 --reload
```
> Al ingresar a `http://localhost:8083/` o `http://127.0.0.1:8083/` en cualquier navegador, el microservicio redirige automáticamente a la interfaz 

### Paso 5: Ejecución de Tests Automatizados
```bash
# Ejecutar suite completa de tests de dominio hexagonal e integración
pytest tests/test_domain_hexagonal.py tests/test_api_integration.py
```

---

## 6. Enlaces y Documentación de Pruebas

* **Swagger UI Interactivo:** `http://localhost:8083/docs`
* **Especificación ReDoc:** `http://localhost:8083/redoc`
* **Contrato OpenAPI YAML Compartido:** [ms4_contrato.yaml](file:///C:/Users/Usuario/Documents/U/Semestre%20II-2026/SW2/SegundoParcial/shared_contracts_specs/ms4_contrato.yaml)
* **Suite de Pruebas Hexagonales:** [test_domain_hexagonal.py](file:///C:/Users/Usuario/Documents/U/Semestre%20II-2026/SW2/SegundoParcial/ms4_ciudadano_backend/tests/test_domain_hexagonal.py)
* **Suite de Pruebas de Integración API:** [test_api_integration.py](file:///C:/Users/Usuario/Documents/U/Semestre%20II-2026/SW2/SegundoParcial/ms4_ciudadano_backend/tests/test_api_integration.py)
