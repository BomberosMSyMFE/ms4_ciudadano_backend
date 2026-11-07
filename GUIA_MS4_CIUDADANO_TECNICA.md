# Guía Técnica Integral — MS-04 Portal Ciudadano y Denuncias de Emergencia
**Plataforma Distribuida Cuerpo de Bomberos Santa Cruz — INF512 (Ingeniería de Software II)**  
**Semestre:** 2/2026 — UAGRM  
**Responsable del Módulo:** Jael Mamani  
**Stack Principal:** Python 3.11+ / FastAPI / MongoDB 7.0 (Motor) / AWS S3 (Boto3) / YOLOv8 & PyTorch (MS-05)  
**Puerto de Red Asignado:** `8083`  
**Swagger UI:** `http://localhost:8083/docs`  

---

## 1. Resumen Ejecutivo y Rol del Microservicio

El microservicio **MS-04: Portal Ciudadano** es el canal civil de entrada de emergencias para toda el área metropolitana de Santa Cruz de la Sierra. Su propósito es capturar de forma inmediata reportes vecinales y siniestros provenientes del portal web, aplicaciones móviles o bots automatizados de WhatsApp (vía n8n), someterlos a validación cognitiva por inteligencia artificial y enrutar las alertas críticas a la Sala de Crisis de Bomberos (MS-01).

```text
==================================== ARQUITECTURA DE FLUJO INTEGRAL ====================================

  [ CIUDADANO (Web / App) ]               [ MENSAJERÍA VECINAL (WhatsApp) ]
             |                                             |
             | Subida de Foto + Datos                      | Mensaje + Imagen
             v                                             v
  +---------------------------------------------------------------------------------------------------+
  |                               MS-04 PORTAL CIUDADANO (Puerto 8083)                                |
  |                                                                                                   |
  |   1. Recepción Multipart          2. Subida de Evidencia              3. Inferencia Deep Learning |
  |   ----------------------          ----------------------              --------------------------- |
  |   POST /denuncias/con-foto        AWS S3 Bucket                       POST /vision/validar-evidencia
  |   POST /denuncias                 (Fallback local 'storage/')         MS-05 IA Core (YOLOv8)      |
  |                                                                                                   |
  |   4. Persistencia Documental      5. Evaluación de Reglas             6. Enlace a Sala de Crisis  |
  |   --------------------------      -----------------------             --------------------------  |
  |   MongoDB 7.0 (Motor)             score_fuego_ia >= 0.85              POST /incidentes            |
  |   Colección 'denuncias'           o CRITICO_ESTRUCTURAL               MS-01 Comandos (Nataly)     |
  +---------------------------------------------------------------------------------------------------+
                                            |
                                            v
                              [ SALA DE CRISIS MFE-01 ]
                              Sirena activa y WebSockets
```

---

## 2. Arquitectura de Software Hexagonal (Ports & Adapters)

MS-04 sigue de manera rigurosa los lineamientos del **Punto 10 (Arquitecturas de Código Limpio)** mediante Arquitectura Hexagonal. El núcleo de negocio está totalmente aislado del framework FastAPI, de las librerías de AWS y de la base de datos MongoDB.

```text
ms4_ciudadano_backend/
├── app/
│   ├── domain/                         # DOMINIO PURO (Reglas Invariables, sin dependencias externas)
│   │   ├── models.py                   # Entidad DenunciaCiudadana (lógica de prioridad, instrucciones)
│   │   └── exceptions.py               # Excepciones de Dominio (CoordenadasInvalidas, DescripcionVacia)
│   │
│   ├── ports/                          # PUERTOS (Interfaces Abstractas ABC)
│   │   ├── storage_port.py             # IDenunciaStoragePort (Persistencia de tickets)
│   │   ├── evidence_storage_port.py    # IEvidenceStoragePort (Subida de fotos/video)
│   │   ├── ia_validator_port.py        # IIAValidatorPort (Inferencia YOLOv8 y Triaje NLP)
│   │   └── notification_port.py        # INotificationPort (Despacho a Sala de Crisis)
│   │
│   ├── adapters/                       # ADAPTADORES (Implementaciones de Infraestructura)
│   │   ├── mongo_adapter.py            # MotorMongoAdapter (MongoDB Driver asíncrono)
│   │   ├── memory_adapter.py           # InMemoryDenunciaAdapter (Pruebas unitarias ultra rápidas)
│   │   ├── s3_storage_adapter.py       # S3StorageAdapter (AWS S3 + Fallback local 'storage/evidencias/')
│   │   ├── http_ia_adapter.py          # HttpIAAdapter (Cliente HTTP hacia MS-05 IA Core)
│   │   ├── http_comandos_adapter.py    # HttpComandosAdapter (Cliente HTTP hacia MS-01 Comandos)
│   │   └── console_notification_adapter.py
│   │
│   ├── services/                       # CASOS DE USO / SERVICIOS DE APLICACIÓN
│   │   └── denuncias_service.py        # DenunciasApplicationService (Orquestación del flujo)
│   │
│   └── api/                            # ADAPTADOR PRIMARIO / DRIVING (FastAPI & HTTP)
│       ├── main.py                     # Configuración de FastAPI, CORS, Lifespan y StaticFiles
│       ├── dependencies.py             # Inyección de dependencias modular
│       └── routers/
│           └── denuncias_router.py     # Endpoints REST y Webhooks
│
├── storage/evidencias/                 # Almacenamiento local automático de evidencia (Fallback)
├── scripts/
│   └── seed_denuncias_mongodb.py       # Seeder masivo con 60 incidentes de Santa Cruz
└── tests/
    ├── test_api_integration.py        # Pruebas de integración HTTP y validación de esquemas
    ├── test_domain_hexagonal.py       # Pruebas de invariantes de negocio y casos extremos
    ├── test_evidence_s3_and_vision.py # Pruebas del adaptador S3, YOLOv8 y subida de archivos
    └── test_mongo_persistence_live.py # Pruebas de integración directa contra MongoDB
```

---

## 3. Almacenamiento en AWS S3 Bucket con Fallback Local Híbrido

### 3.1. Filosofía de Diseño: Resiliencia de Misión Crítica (Zero-Crash)
En una plataforma de bomberos, un fallo de conexión a AWS o la falta temporal de credenciales **nunca debe impedir registrar una denuncia ciudadana**.
Por ello, `S3StorageAdapter` implementa un patrón híbrido:

1. **Si las credenciales de AWS están presentes en `.env`:**
   - Sube el archivo binario directamente al Bucket de S3 vía `boto3`.
   - Asigna cabeceras `ContentType` adecuadas (ej. `image/jpeg`).
   - Retorna la URL pública de AWS:  
     `https://{bucket}.s3.{region}.amazonaws.com/evidencias/{uuid}_{nombre}.jpg`
2. **Si las credenciales no existen o si AWS rechaza la conexión:**
   - Detecta la ausencia de credenciales o captura `BotoCoreError`/`ClientError`.
   - Guarda físicamente el archivo en el directorio local del servidor `storage/evidencias/`.
   - Genera una URL servida por el propio microservicio:  
     `http://localhost:8083/evidencias/{uuid}_{nombre}.jpg`
   - El sistema opera al 100% sin una sola línea roja en consola.

### 3.2. Configuración en `.env`
```env
# =========================================================================
# CONFIGURACIÓN AWS S3 STORAGE
# Si se dejan en blanco, el microservicio utiliza automáticamente el
# almacenamiento local en storage/evidencias/ sin fallar.
# =========================================================================
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=us-east-1
AWS_S3_BUCKET_NAME=bomberos-scz-evidencias
AWS_S3_PUBLIC_BASE_URL=
LOCAL_STORAGE_BASE_URL=http://localhost:8083
```

### 3.3. Paso a Paso para la Creación del Bucket en AWS Console
1. Iniciar sesión en la consola de AWS y entrar a **Amazon S3**.
2. Hacer clic en **Create bucket**:
   - **Bucket name:** `bomberos-scz-evidencias` (debe ser globalmente único).
   - **AWS Region:** `us-east-1` (US East N. Virginia) o `sa-east-1` (São Paulo).
   - Desmarcar *Block all public access* para permitir la visualización de evidencias por la Sala de Crisis (o configurar una política de lectura de objetos `s3:GetObject`).
3. En **IAM (Identity and Access Management)**:
   - Crear un usuario con acceso programático (ej. `bomberos-backend-user`).
   - Asignar una política de permisos restringida al bucket:
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Effect": "Allow",
           "Action": [
             "s3:PutObject",
             "s3:GetObject",
             "s3:PutObjectAcl"
           ],
           "Resource": "arn:aws:s3:::bomberos-scz-evidencias/*"
         }
       ]
     }
     ```
   - Generar las **Access Keys** y pegarlas en el `.env` de `ms4_ciudadano_backend`.

---

## 4. Deep Learning con Visión Artificial (YOLOv8) y Triaje NLP

### 4.1. ¿Cómo funciona la Inferencia Cognitiva?
Cuando un ciudadano envía una foto mediante `POST /api/v1/denuncias/con-foto`:
1. `DenunciasApplicationService` toma los bytes en memoria de la imagen.
2. Invoca el método `validar_imagen_bytes()` del puerto `IIAValidatorPort`.
3. El adaptador `HttpIAAdapter` envía la imagen por HTTP multipart a **MS-05 IA Core**:
   - `POST http://127.0.0.1:8005/api/v1/vision/validar-evidencia`
4. En **MS-05**, el motor `inferir_evidencia_imagen()` procesa el tensor con **YOLOv8 Nano (`yolov8n.pt`)** y combina los resultados con un análisis de **ratio de píxeles térmicos (RGB en canal rojo)**:
   ```json
   {
     "verificado_automaticamente": true,
     "nivel_confianza": 0.94,
     "total_detecciones": 2,
     "detalles": [
       {"clase": "fuego_activo", "confianza": 0.94, "bbox": [120, 80, 450, 390]},
       {"clase": "humo_denso", "confianza": 0.88, "bbox": [50, 20, 600, 300]}
     ],
     "motor": "YOLOv8 Deep Learning & Thermal Pixel Ratio"
   }
   ```
5. Simultáneamente, el texto descriptivo del ciudadano se envía a:
   - `POST http://127.0.0.1:8005/api/v1/nlp/clasificar-urgencia`
   - Retorna la categoría semántica (ej. `CRITICO_ESTRUCTURAL`, `CRITICO_GAS`, `ALTO_FORESTAL`).

### 4.2. Regla de Negocio de Alta Prioridad
En el modelo de dominio `DenunciaCiudadana`:
$$\text{es\_prioridad\_alta} = (\text{score\_fuego\_ia} \ge 0.85) \lor (\text{categoria\_nlp empieza con 'CRITICO'})$$
Si se cumple:
- Se actualizan automáticamente las instrucciones de seguridad a:
  > *"ALERTA MÁXIMA: Evacúe a favor del viento y corte suministros de gas y electricidad. Unidades despachadas con prioridad."*
- Se activa la notificación HTTP hacia la Sala de Crisis de Nataly (MS-01).

---

## 5. Integración con MS-01 (Comandos) y Automatización con n8n

### 5.1. Despacho hacia MS-01 Comandos
El adaptador `HttpComandosAdapter` intercepta toda denuncia con prioridad alta y despacha:
- **Destino:** `POST http://localhost:3000/api/v1/incidentes`
- **Mapeo Inteligente de Categorías:**
  - `CRITICO_ESTRUCTURAL` $\rightarrow$ `INCENDIO_ESTRUCTURAL`
  - `CRITICO_GAS` $\rightarrow$ `FUGA_DE_GAS`
  - `ALTO_FORESTAL` $\rightarrow$ `INCENDIO_FORESTAL`
  - `ALTO_VEHICULAR` $\rightarrow$ `ACCIDENTE_VEHICULAR`
- **Payload Enviado:**
  ```json
  {
    "tipoIncidente": "INCENDIO_ESTRUCTURAL",
    "severidad": "CRITICA",
    "descripcion": "[REPORTE CIUDADANO RAD-B9F2A1] Tinglado industrial de plásticos en llamas",
    "latitud": -17.7680,
    "longitud": -63.1420,
    "denuncianteNombre": "Portal Ciudadano SCZ",
    "denuncianteTelefono": "+59178012345",
    "denuncianteEmail": "denuncias@bomberos.gob.bo"
  }
  ```
- **Resiliencia:** Si el servidor de comandos está apagado o protegido con token JWT en desarrollo, el adaptador registra un log táctico informativo y la denuncia se preserva intacta en MongoDB.

### 5.2. Ingesta desde WhatsApp con n8n
El router cuenta con el endpoint dedicado:
- `POST /api/v1/webhook/n8n-whatsapp`
- Permite que el bot de WhatsApp reciba la foto y el mensaje del vecino, consulte a MS-05 e inserte el reporte directamente en MS-04, retornando el ticket generado de vuelta al chat del vecino.

---

## 6. Seeder de Datos Masivos para MongoDB

Para la defensa ante el docente y pruebas operativas de la Sala de Crisis, se incluye un script seeder con 60 emergencias simuladas en puntos estratégicos de Santa Cruz de la Sierra:

### ¿Cómo ejecutar el seeder?
```bash
# Estando en la carpeta ms4_ciudadano_backend:
python scripts/seed_denuncias_mongodb.py 60
```

### Estadísticas que genera el script:
- **Total de registros:** 60 documentos en MongoDB (`bomberos_ciudadano.denuncias`).
- **Georreferenciación:** Coordenadas reales con variación métrica en 15 zonas clave: Casco Viejo, Parque Industrial, Plan 3000, Equipetrol, Villa 1ro de Mayo, Pampa de la Isla, Doble Vía La Guardia, Km 8 Norte, Urubó, Los Pozos, La Ramada, etc.
- **Evidencias:** Enlaces a S3 y archivos locales.
- **Scores IA:** Calibrados entre 0.05 y 0.98.
- **Prioridad Crítica:** ~35% de los incidentes son catalogados como `ALTA PRIORIDAD` para probar el sonido de sirenas y filtros en el frontend.

---

## 7. Catálogo Completo de Endpoints de la API

| Método | Endpoint | Content-Type | Descripción |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/denuncias/con-foto` | `multipart/form-data` | **Endpoint Estrella:** Sube foto a S3, evalúa con YOLOv8 en MS-05, persiste en Mongo y notifica a Comandos. |
| `POST` | `/api/v1/denuncias` | `application/json` | Registro estándar de denuncia ciudadana por texto y coordenadas (retrocompatible). |
| `GET` | `/api/v1/denuncias/{ticketId}` | `application/json` | Consulta de evolución de estado y recomendaciones de seguridad por ticket radial. |
| `POST` | `/api/v1/webhook/n8n-whatsapp` | `application/json` | Webhook de entrada omnicanal para el bot de n8n. |
| `GET` | `/api/v1/denuncias` | `application/json` | Listado paginado de denuncias recientes para monitoreo y auditoría. |
| `GET` | `/evidencias/{archivo}` | `image/jpeg` / etc. | Acceso estático a las fotografías almacenadas en modo fallback local. |
| `GET` | `/health` | `application/json` | Chequeo de salud del servicio (liveness probe). |

---

## 8. Ejemplos Concretos de Invocación con cURL

### A. Registro con Evidencia Fotográfica Directa (S3 + YOLOv8)
```bash
curl -X POST "http://localhost:8083/api/v1/denuncias/con-foto" \
  -F "foto=@foto_incendio.jpg;type=image/jpeg" \
  -F "descripcion=Fuego descontrolado en tinglado de reciclaje de plasticos" \
  -F "latitud=-17.7680" \
  -F "longitud=-63.1420" \
  -F "telefono_contacto=+59178012345"
```
**Respuesta (HTTP 201 Created):**
```json
{
  "ticket_id": "RAD-B9F2A1",
  "estado": "RECIBIDO_EN_TRIAJE",
  "confianza_verificacion_ia": 0.96,
  "categoria_predicha": "CRITICO_ESTRUCTURAL",
  "es_prioridad_alta": true,
  "imagen_url": "https://bomberos-scz-evidencias.s3.us-east-1.amazonaws.com/evidencias/9f3a1e_foto_incendio.jpg",
  "instrucciones_seguridad": "ALERTA MÁXIMA: Evacue a favor del viento y corte suministros de gas y electricidad. Unidades despachadas con prioridad.",
  "detecciones_vision": [
    {"clase": "fire", "confianza": 0.96, "bbox": [10.0, 20.0, 150.0, 200.0]}
  ],
  "motor_vision": "YOLOv8 Deep Learning & Thermal Pixel Ratio",
  "mensaje": "Evidencia visual analizada con Deep Learning y reporte encolado exitosamente."
}
```

### B. Consulta de Estado de la Denuncia
```bash
curl -X GET "http://localhost:8083/api/v1/denuncias/RAD-B9F2A1"
```

---

## 9. Comandos para Pruebas Unitarias y Despliegue

### 9.1. Ejecución de la Batería de Pruebas
Todas las pruebas están diseñadas con `pytest` y `pytest-asyncio`:
```bash
# Estando en la carpeta raíz del proyecto:
pytest ms4_ciudadano_backend/tests -v
```
**Resultado:** 13 pruebas unitarias y de integración pasando al 100% (incluye persistencia real en MongoDB y mocks de adaptadores).

### 9.2. Levantamiento Local con Uvicorn
```bash
cd ms4_ciudadano_backend
uvicorn app.api.main:app --host 0.0.0.0 --port 8083 --reload
```

### 9.3. Construcción y Despliegue con Docker
```bash
docker build -t bomberos-ms4-ciudadano:latest .
docker run -d --name ms4_ciudadano -p 8083:8083 --env-file .env bomberos-ms4-ciudadano:latest
```
