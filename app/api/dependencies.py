import os
from fastapi import Depends
from app.ports.storage_port import IDenunciaStoragePort
from app.ports.ia_validator_port import IIAValidatorPort
from app.ports.notification_port import INotificationPort
from app.adapters.mongo_adapter import MotorMongoAdapter
from app.adapters.http_ia_adapter import HttpIAAdapter
from app.adapters.console_notification_adapter import ConsoleNotificationAdapter
from app.services.denuncias_service import DenunciasApplicationService

def get_storage() -> IDenunciaStoragePort:
    mongo_uri = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    mongo_db = os.getenv("MONGO_DB", "bomberos_ciudadano")
    return MotorMongoAdapter(uri=mongo_uri, db_name=mongo_db)

def get_ia_validator() -> IIAValidatorPort:
    ia_url = os.getenv("IA_CORE_URL", "http://127.0.0.1:8005")
    return HttpIAAdapter(base_url=ia_url)

def get_notifier() -> INotificationPort:
    return ConsoleNotificationAdapter()

def get_denuncias_service(
    storage: IDenunciaStoragePort = Depends(get_storage),
    ia_validator: IIAValidatorPort = Depends(get_ia_validator),
    notifier: INotificationPort = Depends(get_notifier)
) -> DenunciasApplicationService:
    return DenunciasApplicationService(
        storage=storage,
        ia_validator=ia_validator,
        notifier=notifier
    )
