# Guía Técnica Integral — MS-04 Portal Ciudadano y Denuncias de Emergencia
**Plataforma Distribuida Cuerpo de Bomberos Santa Cruz — INF512 (Ingeniería de Software II)**  
**Semestre:** 2/2026 — UAGRM  
**Responsable del Módulo:** Jael Mamani  
**Stack Principal:** Python 3.11+ / FastAPI / MongoDB 7.0 (Motor) / AWS S3 (Boto3) / YOLOv8 & PyTorch (MS-05 D-Fire) / n8n / Baileys WhatsApp Gateway  
**Puerto de Red Asignado:** `8083`  
**Swagger UI:** `http://localhost:8083/docs`  
**Health Check:** `http://localhost:8083/health`  

---

## 1. Resumen Ejecutivo y Rol del Microservicio

El microservicio **MS-04: Portal Ciudadano** es el canal civil de entrada de emergencias para toda el área metropolitana de Santa Cruz de la Sierra. Su propósito es capturar de forma inmediata reportes vecinales y siniestros provenientes del portal web, aplicaciones móviles (Flutter) o mensajería automatizada de WhatsApp (vía n8n), someterlos a validación cognitiva por inteligencia artificial y enrutar las alertas confirmadas a la Sala de Crisis de Bomberos (MS-01).

```text
==================================== ARQUITECTURA DE FLUJO INTEGRAL ====================================

  [ CIUDADANO (Flutter / Web) ]           [ MENSAJERÍA VECINAL (WhatsApp) ]
             |                                             |
             | 1. POST /denuncias/con-foto                 | 1. Mensaje entrante con foto/texto
             |    + Cabecera Idempotency-Key               v
             v                                    [ N8N AUTOMATION (Puerto 5678) ]
  +--------------------------------------------------------+---------------------------------------+
  |                          MS-04 PORTAL CIUDADANO (Puerto 8083)                                  |
  |                                                                                                |
  |   A. FILTRO DE IDEMPOTENCIA        B. ALMACENAMIENTO EVIDENCIA       C. VALIDACIÓN DEEP LEARNING|
  |   -------------------------        ---------------------------       --------------------------|
  |   Verifica 'idempotency_key' en    Sube foto/video binario           Envía bytes a MS-05 IA    |
  |   MongoDB. Si ya existe, retorna   a AWS S3 (us-east-1).             YOLOv8 Nano (D-Fire Model)|
  |   el ticket sin duplicar.          Fallback local: 'storage/'        Retorna: score 0.0 a 0.98 |
  |                                                                                                |
  |   D. TRIAJE NLP SEMÁNTICO          E. PERSISTENCIA DOCUMENTAL        F. ENLACE A SALA DE CRISIS|
  |   -----------------------          --------------------------        --------------------------|
  |   Clasifica texto descriptivo      MongoDB 7.0 (Motor Async)         Si prioridad es ALTA,     |
  |   (CRITICO_ESTRUCTURAL,            Genera Ticket RAD-XXXXXX          sincroniza con MS-01      |
  |   ALTO_FORESTAL, etc.)             Colección 'denuncias'             Comandos (Nataly / DuckDNS)|
  +--------------------------------------------------------+---------------------------------------+
                                                           |
                                                           v
  +------------------------------------------------------------------------------------------------+
  |                          SALA DE SITUACIÓN & DESPACHO TÁCTICO                                  |
  |                                                                                                |
  |   1. Operador evalúa la alerta en consola de Comandos (MS-01) y asigna unidades.               |
  |   2. Daemon de MS-04 detecta el despacho y envía WhatsApp oficial al celular del ciudadano:    |
  |      "🚨 ¡LA AYUDA ESTÁ EN CAMINO! Unidad despachada para el ticket #RAD-XXXXXX"               |
  +------------------------------------------------------------------------------------------------+
```

---

## 2. Arquitectura de Software Hexagonal (Ports & Adapters)

MS-04 sigue rigurosamente los lineamientos del **Punto 10 (Arquitecturas de Código Limpio)** mediante Arquitectura Hexagonal. El núcleo de negocio está totalmente aislado del framework FastAPI, de las librerías de AWS y de la base de datos MongoDB.

```text
ms4_ciudadano_backend/
├── app/
│   ├── domain/                         # DOMINIO PURO (Reglas Invariables de Negocio)
│   │   ├── models.py                   # Entidad DenunciaCiudadana (idempotencia, prioridad, estados)
│   │   └── exceptions.py               # Excepciones de Dominio (CoordenadasInvalidas, DescripcionVacia)
│   │
│   ├── ports/                          # PUERTOS (Interfaces Abstractas ABC)
│   │   ├── storage_port.py             # IDenunciaStoragePort (Persistencia de tickets)
│   │   ├── evidence_storage_port.py    # IEvidenceStoragePort (Subida a S3 / Fallback)
│   │   ├── ia_validator_port.py        # IIAValidatorPort (Inferencia YOLOv8 y Triaje NLP)
│   │   └── notification_port.py        # INotificationPort (Despacho a Comandos y WhatsApp)
│   │
│   ├── adapters/                       # ADAPTADORES (Infraestructura Concreta)
│   │   ├── mongo_adapter.py            # MotorMongoAdapter (MongoDB Driver asíncrono Motor)
│   │   ├── memory_adapter.py           # InMemoryDenunciaAdapter (Pruebas unitarias ultra rápidas)
│   │   ├── s3_storage_adapter.py       # S3StorageAdapter (AWS S3 SDK boto3 + Fallback local)
│   │   ├── http_ia_adapter.py          # HttpIAAdapter (Cliente HTTP hacia MS-05 IA Core)
│   │   ├── http_comandos_adapter.py    # HttpComandosAdapter (Cliente HTTP Comandos + WhatsApp Gateway)
│   │   └── console_notification_adapter.py
│   │
│   ├── services/                       # CASOS DE USO / SERVICIOS DE APLICACIÓN
│   │   └── denuncias_service.py        # DenunciasApplicationService (Orquestación del flujo)
│   │
│   └── api/                            # ADAPTADOR PRIMARIO / DRIVING (FastAPI & HTTP)
│       ├── main.py                     # Configuración FastAPI, CORS, Lifespan y StaticFiles
│       ├── dependencies.py             # Inyección de dependencias modular
│       └── routers/
│           └── denuncias_router.py     # Endpoints REST, multipart y webhooks
│
├── storage/evidencias/                 # Almacenamiento local automático de evidencia (Fallback)
├── scripts/
│   └── seed_denuncias_mongodb.py       # Seeder masivo con 60 incidentes de Santa Cruz
├── tests/
│   ├── test_api_integration.py        # Pruebas de integración HTTP y esquemas
│   ├── test_domain_hexagonal.py       # Pruebas de invariantes de negocio
│   ├── test_evidence_s3_and_vision.py # Pruebas del adaptador S3 y YOLOv8
│   ├── test_idempotency_offline.py    # Pruebas de prevención de duplicados
│   └── test_mongo_persistence_live.py # Pruebas directas contra MongoDB
│
├── Dockerfile                          # Contenedor optimizado de producción
├── docker-compose.yml                  # Orquestación con MongoDB 7.0 y volumen persistente
├── .dockerignore                       # Exclusiones de construcción Docker
├── requirements.txt                    # Dependencias Python congeladas
└── .env.example                        # Plantilla de variables de entorno
```

---

## 3. Almacenamiento en AWS S3 Bucket con Fallback Híbrido

### 3.1. Filosofía de Misión Crítica (Zero-Crash)
En una plataforma de bomberos, un fallo de conexión a AWS o la falta temporal de credenciales **nunca debe impedir registrar una denuncia ciudadana**.
Por ello, `S3StorageAdapter` implementa un patrón híbrido:

1. **Si las credenciales de AWS están presentes en `.env`:**
   - Sube el archivo binario directamente al Bucket de S3 vía `boto3`.
   - Asigna cabeceras `ContentType` adecuadas (ej. `image/jpeg`, `video/mp4`).
   - Retorna la URL pública de AWS:  
     `https://bomberos-scz-evidencias.s3.us-east-1.amazonaws.com/evidencias/{uuid}_{nombre}.jpg`
2. **Si las credenciales no existen o si AWS no responde en 3 segundos:**
   - Captura la excepción o timeout de forma transparente.
   - Guarda físicamente el archivo en el directorio local del servidor `storage/evidencias/`.
   - Genera una URL servida por el propio microservicio:  
     `http://localhost:8083/evidencias/{uuid}_{nombre}.jpg`
   - El ciudadano recibe su ticket sin bloqueos ni errores en pantalla.

### 3.2. Configuración en `.env`
```env
AWS_ACCESS_KEY_ID=AKIA2SKQ4VWPLGJQFQES
AWS_SECRET_ACCESS_KEY=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
AWS_REGION=us-east-1
AWS_S3_BUCKET_NAME=bomberos-scz-evidencias
AWS_S3_PUBLIC_BASE_URL=
LOCAL_STORAGE_BASE_URL=http://localhost:8083
```

---

## 4. Deep Learning con YOLOv8 (Dataset Oficial D-Fire)

### 4.1. Arquitectura de Inferencia y Cero Falsos Positivos
Cuando un ciudadano envía una foto mediante `POST /api/v1/denuncias/con-foto`:
1. `DenunciasApplicationService` toma los bytes en memoria de la imagen.
2. Invoca el método `validar_imagen_bytes()` del puerto `IIAValidatorPort`.
3. El adaptador `HttpIAAdapter` envía la imagen por HTTP multipart a **MS-05 IA Core**:
   - `POST http://127.0.0.1:8005/api/v1/vision/validar-evidencia`
4. En **MS-05**, el motor carga la red neuronal convolucional entrenada sobre el **Dataset D-Fire** (`yolov8_fire_smoke.pt`):
   - **Clases detectadas:** `0: smoke` (humo de combustión) y `1: fire` (fuego directo).
   - **Resolución de inferencia:** 640x640 px optimizada.
   - **Tiempo de inferencia:** ~250 milisegundos en CPU.
   - **Filtrado estricto:** Imágenes de casas, edificios, calles y paisajes soleados sin fuego devuelven **`verificado_por_ia: false, nivel_confianza: 0.0`** con cero detecciones.

```json
{
  "verificado_por_ia": true,
  "nivel_confianza": 0.87,
  "total_objetos_detectados": 1,
  "detecciones": [
    {
      "clase": "humo_combustion",
      "confianza": 0.868,
      "bounding_box": [1.6, 3.2, 299.2, 300.0]
    }
  ],
  "motor": "YOLOv8 Deep Learning (D-Fire Neural Network)"
}
```

---

## 5. Idempotencia y Prevención de Duplicados

### 5.1. El Problema del Doble Clic en Situaciones de Emergencia
Bajo pánico o estrés, un ciudadano tiende a presionar el botón "Enviar" múltiples veces. Si la red celular tiene latencia o retransmite paquetes, una API sin protección crearía múltiples tickets y saturaría la Sala de Crisis con incidentes duplicados.

### 5.2. Mecanismo de Protección en Tres Niveles
1. **Nivel 1 — Frontend (Flutter):**
   - El botón se bloquea de inmediato al primer toque (`_isLoading ? null : _submitReport`).
   - Mantiene la misma clave UUID v4 (`_activeIdempotencyKey`) mientras la pantalla esté activa.
2. **Nivel 2 — Backend (FastAPI Application Service):**
   - Extrae la cabecera `Idempotency-Key: <UUID>`.
   - Consulta en MongoDB si ya existe un ticket generado con esa misma clave.
   - Si existe, **retorna inmediatamente el ticket original** con la bandera `"reintento_idempotente": true`, sin volver a procesar la imagen con IA ni crear otro registro.
3. **Nivel 3 — Base de Datos (MongoDB Index):**
   - Índice único disperso (`sparse unique index`) sobre el campo `idempotency_key` en la colección `denuncias`.

---

## 6. Integración con n8n y WhatsApp Gateway

### 6.1. Canal de Entrada (Recepción Vecinal)
* **Webhook n8n:** `POST http://localhost:5678/webhook/denuncia-whatsapp`
* **Workflow:** `Pipeline_Bomberos_WhatsApp_Triaje_Jael` (`wohPVkJJlEIsRSPW`).
* El flujo recibe el mensaje, valida la foto con MS-05, registra en MS-04 y responde al vecino con su número de ticket.

### 6.2. Canal de Salida (Notificación Oficial de Despacho)
* **Daemon de Monitoreo:** En segundo plano, `ms4_ciudadano_backend` consulta periódicamente los incidentes activos de la Sala de Crisis de Nataly (`https://bomberos-uagrm-scz.duckdns.org`).
* Cuando el operador de comandos valida y despacha unidades (`EN_COMBATE` o `DESPACHADO`), MS-04 detecta el cambio y emite un mensaje al WhatsApp del denunciante a través del Gateway Baileys (puerto 8088):
  > *"🚒 [CUERPO DE BOMBEROS SANTA CRUZ] — ¡LA AYUDA ESTÁ EN CAMINO! Central de Crisis ha confirmado el despacho de unidades hacia tu ubicación para el ticket #RAD-XXXXXX."*
* **Teléfono dinámico:** Funciona para **cualquier número telefónico** ingresado por el ciudadano, normalizando automáticamente prefijos de Bolivia (`591`).

---

## 7. Catálogo Completo de Endpoints

| Método | Endpoint | Content-Type | Descripción |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/denuncias/con-foto` | `multipart/form-data` | **Endpoint Principal:** Sube foto a S3, evalúa con YOLOv8 en MS-05, persiste en Mongo con Idempotencia y notifica a Comandos. |
| `POST` | `/api/v1/denuncias` | `application/json` | Registro de denuncia por JSON (usado por n8n e integraciones B2B). |
| `GET` | `/api/v1/denuncias/{ticketId}` | `application/json` | Consulta de evolución de estado y recomendaciones de seguridad. |
| `PATCH` | `/api/v1/denuncias/{ticketId}/estado` | `application/json` | Actualización de estado operativo (UNIDAD_EN_CAMINO, EN_ESCENA, CONTROLADO). |
| `GET` | `/api/v1/denuncias/publicas/muro` | `application/json` | **Muro Público de Alertas:** Consulta ciudadana de incidentes activos para evacuación. |
| `POST` | `/api/v1/webhook/n8n-whatsapp` | `application/json` | Webhook de entrada para automatizaciones de n8n. |
| `GET` | `/evidencias/{archivo}` | `image/jpeg` / etc. | Acceso estático a las fotografías almacenadas en modo fallback local. |
| `GET` | `/health` | `application/json` | Chequeo de salud del servicio (Liveness probe). |

---

## 8. Guía Paso a Paso para Levantar Localmente

### Paso 1: Levantar MongoDB con Docker
```bash
docker run -d --name bomberos-mongo-ciudadano -p 27017:27017 mongo:7.0
```

### Paso 2: Configurar el Entorno Python
```bash
cd ms4_ciudadano_backend

# Crear entorno virtual (si no existe)
python -m venv venv

# Activar entorno virtual
# En Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# En Linux/macOS:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### Paso 3: Configurar Variables de Entorno (`.env`)
Crear el archivo `.env` en la raíz de `ms4_ciudadano_backend/` con el siguiente contenido:
```env
APP_NAME="MS-04 Portal Ciudadano"
APP_ENV=development
PORT=8083
MONGO_URI=mongodb://127.0.0.1:27017
MONGO_DB=bomberos_ciudadano
IA_CORE_URL=http://127.0.0.1:8005
COMANDOS_MS1_URL=https://bomberos-uagrm-scz.duckdns.org

# AWS S3 Storage
AWS_ACCESS_KEY_ID=AKIA2SKQ4VWPLGJQFQES
AWS_SECRET_ACCESS_KEY=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
AWS_REGION=us-east-1
AWS_S3_BUCKET_NAME=bomberos-scz-evidencias
LOCAL_STORAGE_BASE_URL=http://localhost:8083
```

### Paso 4: Iniciar el Microservicio
```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8083 --reload
```
Verificar en el navegador:
* **Documentación interactiva Swagger:** `http://localhost:8083/docs`
* **Health Check:** `http://localhost:8083/health`

### Paso 5: Ejecutar la Batería de Pruebas Automatizadas
```bash
pytest tests/ -v
```

---

## 9. Guía de Despliegue en Producción (DevOps — PUNTO 13)

Cumpliendo con la directriz del docente y las especificaciones del **Punto 13 (Guía Maestra de Despliegue DevOps Integral)**:

### 9.1. Despliegue con Docker Compose (Recomendado)
Estando en la carpeta `ms4_ciudadano_backend/`:
```bash
# Construir imagen y levantar MongoDB + Backend
docker compose up -d --build

# Verificar estado de los contenedores
docker compose ps

# Ver logs en tiempo real
docker compose logs -f ms4-ciudadano-backend
```

### 9.2. Despliegue con Docker CLI Independiente
```bash
# 1. Construir la imagen Docker
docker build -t bomberos-ms4-ciudadano:latest .

# 2. Ejecutar el contenedor conectado a la red de bomberos
docker run -d \
  --name bomberos-ms4-ciudadano \
  --restart unless-stopped \
  -p 8083:8083 \
  --env-file .env \
  -v $(pwd)/storage/evidencias:/app/storage/evidencias \
  bomberos-ms4-ciudadano:latest
```

### 9.3. Configuración en Reverse Proxy Nginx (PUNTO 13)
Para exponer el microservicio bajo un dominio público seguro con certificado SSL (HTTPS):

```nginx
# Fragmento para /etc/nginx/sites-available/bomberos
location /api/v1/ciudadano/ {
    proxy_pass http://127.0.0.1:8083/api/v1/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 25M;
}
```

---

## 10. Ejemplos de Invocación con cURL

### A. Registro con Foto e Idempotencia
```bash
curl -X POST "http://localhost:8083/api/v1/denuncias/con-foto" \
  -H "Idempotency-Key: IDEM-SCZ-001" \
  -F "foto=@incendio.jpg;type=image/jpeg" \
  -F "descripcion=Incendio estructural en vivienda con llamas altas" \
  -F "latitud=-17.7833" \
  -F "longitud=-63.1821" \
  -F "telefono_contacto=70012345"
```

### B. Consulta de Estado por Ticket
```bash
curl -X GET "http://localhost:8083/api/v1/denuncias/RAD-B51FE2"
```

### C. Muro Público de Alertas Ciudadanas
```bash
curl -X GET "http://localhost:8083/api/v1/denuncias/publicas/muro"
```
