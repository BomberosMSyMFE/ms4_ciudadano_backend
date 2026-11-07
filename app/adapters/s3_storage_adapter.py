import os
import uuid
import re
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from app.ports.evidence_storage_port import IEvidenceStoragePort

# Carga automatica de .env buscando en el microservicio o raiz
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.exists():
    load_dotenv(dotenv_path=_env_file)
else:
    load_dotenv()

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    BotoCoreError = Exception
    ClientError = Exception


class S3StorageAdapter(IEvidenceStoragePort):
    """
    Adaptador de Almacenamiento de Evidencias en AWS S3 con Respaldo Local (Fallback).
    
    Patron Hibrido Resiliente:
    - Si las credenciales de AWS estan presentes en las variables de entorno,
      sube directamente al Bucket S3 de Produccion.
    - Si faltan credenciales o AWS no responde/falla, almacena automaticamente
      en el disco local dentro de 'storage/evidencias/' y expone la URL local.
    """

    def __init__(
        self,
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        aws_region: Optional[str] = None,
        bucket_name: Optional[str] = None,
        local_base_url: Optional[str] = None,
        storage_dir: Optional[str] = None
    ):
        self.aws_access_key = aws_access_key if aws_access_key is not None else os.getenv("AWS_ACCESS_KEY_ID", "").strip()
        self.aws_secret_key = aws_secret_key if aws_secret_key is not None else os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
        self.aws_region = aws_region if aws_region is not None else os.getenv("AWS_REGION", "us-east-1").strip()
        self.bucket_name = bucket_name if bucket_name is not None else os.getenv("AWS_S3_BUCKET_NAME", "bomberos-scz-evidencias").strip()
        self.public_base_url = os.getenv("AWS_S3_PUBLIC_BASE_URL", "").strip()
        self.local_base_url = (local_base_url or os.getenv("LOCAL_STORAGE_BASE_URL", "http://localhost:8083")).rstrip("/")
        
        # Directorio de respaldo local
        self.storage_dir = Path(storage_dir or os.getenv("LOCAL_STORAGE_DIR", "storage/evidencias"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._s3_client = None
        self._s3_configured = False

        if BOTO3_AVAILABLE and self.aws_access_key and self.aws_secret_key and self.bucket_name:
            try:
                self._s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=self.aws_access_key,
                    aws_secret_access_key=self.aws_secret_key,
                    region_name=self.aws_region
                )
                self._s3_configured = True
            except Exception as e:
                print(f"[ALMACENAMIENTO S3] Error al inicializar cliente boto3: {e}. Se utilizara fallback local.")

    @property
    def is_s3_active(self) -> bool:
        return self._s3_configured and self._s3_client is not None

    async def subir_evidencia(
        self,
        archivo_bytes: bytes,
        nombre_archivo: str,
        content_type: str = "image/jpeg"
    ) -> str:
        # Sanitizar nombre de archivo
        nombre_limpio = re.sub(r"[^a-zA-Z0-9_.-]", "_", nombre_archivo)
        safe_name = f"{uuid.uuid4().hex[:8]}_{nombre_limpio}"

        # 1. Intentar subida a AWS S3 si esta configurado
        if self.is_s3_active:
            try:
                s3_key = f"evidencias/{safe_name}"
                self._s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=archivo_bytes,
                    ContentType=content_type
                )
                if self.public_base_url:
                    return f"{self.public_base_url}/{s3_key}"
                return f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{s3_key}"
            except (BotoCoreError, ClientError, Exception) as s3_err:
                print(f"[ALMACENAMIENTO S3] Fallo subida a AWS S3 ({s3_err}). Activando fallback local.")

        # 2. Fallback de Almacenamiento Local
        ruta_archivo = self.storage_dir / safe_name
        with open(ruta_archivo, "wb") as f:
            f.write(archivo_bytes)

        return f"{self.local_base_url}/evidencias/{safe_name}"
