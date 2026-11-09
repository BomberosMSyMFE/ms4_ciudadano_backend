import os
from fastapi import Depends
from app.ports.storage_port import IDenunciaStoragePort
from app.ports.ia_validator_port import IIAValidatorPort
from app.ports.notification_port import INotificationPort
from app.ports.evidence_storage_port import IEvidenceStoragePort
from app.adapters.mongo_adapter import MotorMongoAdapter
from app.adapters.memory_adapter import InMemoryDenunciaAdapter
from app.adapters.http_ia_adapter import HttpIAAdapter
from app.adapters.http_comandos_adapter import HttpComandosAdapter
from app.adapters.s3_storage_adapter import S3StorageAdapter
from app.services.denuncias_service import DenunciasApplicationService

_in_memory_singleton = InMemoryDenunciaAdapter()

def get_storage() -> IDenunciaStoragePort:
    mongo_uri = os.getenv("MONGO_URI", "")
    if not mongo_uri or mongo_uri.lower() in ["memory", "none"]:
        return _in_memory_singleton
    mongo_db = os.getenv("MONGO_DB", "bomberos_ciudadano")
    return MotorMongoAdapter(uri=mongo_uri, db_name=mongo_db)

def get_ia_validator() -> IIAValidatorPort:
    ia_url = os.getenv("IA_CORE_URL", "http://127.0.0.1:8005")
    return HttpIAAdapter(base_url=ia_url)

def get_notifier() -> INotificationPort:
    comandos_url = os.getenv("COMANDOS_MS1_URL", "https://bomberos-uagrm-scz.duckdns.org")
    return HttpComandosAdapter(comandos_base_url=comandos_url)

def get_evidence_storage() -> IEvidenceStoragePort:
    return S3StorageAdapter()

def get_denuncias_service(
    storage: IDenunciaStoragePort = Depends(get_storage),
    ia_validator: IIAValidatorPort = Depends(get_ia_validator),
    notifier: INotificationPort = Depends(get_notifier),
    evidence_storage: IEvidenceStoragePort = Depends(get_evidence_storage)
) -> DenunciasApplicationService:
    return DenunciasApplicationService(
        storage=storage,
        ia_validator=ia_validator,
        notifier=notifier,
        evidence_storage=evidence_storage
    )
