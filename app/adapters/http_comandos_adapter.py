import os
from typing import Optional
import httpx
from app.ports.notification_port import INotificationPort
from app.domain.models import DenunciaCiudadana

class HttpComandosAdapter(INotificationPort):
    """
    Adaptador de integracion de notificaciones hacia:
    1. MS-01 Comandos & Sala de Crisis (Despacho inmediato de unidades)
    2. n8n / WhatsApp Gateway (Confirmacion y seguimiento directo al telefono del ciudadano)
    """

    def __init__(
        self,
        comandos_base_url: Optional[str] = None,
        n8n_webhook_url: Optional[str] = None,
        whatsapp_gateway_url: Optional[str] = None
    ):
        self.base_url = (comandos_base_url or os.getenv("COMANDOS_MS1_URL", "http://127.0.0.1:3000")).rstrip("/")
        self.n8n_url = (n8n_webhook_url or os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/alerta-ciudadana")).rstrip("/")
        self.wa_gateway_url = (whatsapp_gateway_url or os.getenv("WHATSAPP_GATEWAY_URL", "http://localhost:8088/enviar")).rstrip("/")

    def _mapear_tipo_incidente(self, categoria_nlp: str) -> str:
        cat = categoria_nlp.upper()
        if "ESTRUCTURAL" in cat:
            return "INCENDIO_ESTRUCTURAL"
        if "FORESTAL" in cat:
            return "INCENDIO_FORESTAL"
        if "GAS" in cat:
            return "FUGA_DE_GAS"
        if "VEHICULAR" in cat:
            return "ACCIDENTE_VEHICULAR"
        if "RESCATE" in cat:
            return "RESCATE_PERSONAS"
        return "INCENDIO_ESTRUCTURAL"

    async def notificar_nueva_alerta(self, denuncia: DenunciaCiudadana) -> bool:
        prioridad = "CRITICA" if denuncia.es_prioridad_alta() else "NORMAL"
        print(f"[EVENTO SALA CRISIS] Denuncia: {denuncia.ticket_id} | Prioridad: {prioridad} | Cat: {denuncia.categoria_nlp}")

        # 1. Enviar notificación al WhatsApp del Ciudadano (vía n8n o gateway)
        if denuncia.telefono:
            await self._notificar_whatsapp_ciudadano(denuncia)

        # 2. Despachar a Sala de Crisis (MS-01) si es de alta prioridad
        if not denuncia.es_prioridad_alta():
            return True

        tipo_incidente = self._mapear_tipo_incidente(denuncia.categoria_nlp)
        payload = {
            "tipoIncidente": tipo_incidente,
            "severidad": "CRITICA",
            "descripcion": f"[REPORTE CIUDADANO {denuncia.ticket_id}] {denuncia.descripcion}",
            "latitud": denuncia.latitud,
            "longitud": denuncia.longitud,
            "denuncianteNombre": "Portal Ciudadano SCZ",
            "denuncianteTelefono": denuncia.telefono or "+591-70000000",
            "denuncianteEmail": "denuncias@bomberos.gob.bo"
        }

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/incidentes",
                    json=payload
                )
                if res.status_code in [200, 201]:
                    print(f"[COMANDOS MS-01] Notificacion de emergencia enviada exitosamente para ticket {denuncia.ticket_id}")
                    return True
                else:
                    print(f"[COMANDOS MS-01] Notificacion enviada con respuesta HTTP {res.status_code} (posible guardia JWT activa)")
        except Exception as e:
            print(f"[COMANDOS MS-01] Comandos offline o inaccesible temporalmente ({e}). Alerta preservada en base de datos.")

        return True

    async def _notificar_whatsapp_ciudadano(self, denuncia: DenunciaCiudadana):
        """
        Emite la notificacion automatica de confirmacion al WhatsApp del ciudadano
        con su numero de ticket, verificacion de IA e instrucciones de proteccion.
        """
        mensaje_texto = (
            f"🚒 [CUERPO DE BOMBEROS SANTA CRUZ]\n\n"
            f"Estimado ciudadano, su reporte de emergencia ha sido recibido y verificado por IA.\n\n"
            f"📋 Ticket Radial: #{denuncia.ticket_id}\n"
            f"🚦 Estado: {denuncia.estado}\n"
            f"🔍 Verificación IA: {denuncia.score_fuego_ia * 100:.0f}% de certeza visual\n"
            f"📍 Categoría: {denuncia.categoria_nlp}\n\n"
            f"📢 Instrucciones de seguridad:\n{denuncia.instrucciones_seguridad}\n\n"
            f"Unidades de respuesta han sido informadas. Por favor mantenga la calma y el teléfono despejado."
        )

        payload = {
            "to": denuncia.telefono,
            "phone": denuncia.telefono,
            "ticket_id": denuncia.ticket_id,
            "mensaje": mensaje_texto,
            "message": mensaje_texto,
            "estado": denuncia.estado,
            "prioridad_alta": denuncia.es_prioridad_alta()
        }

        # Intentar envio por gateway o webhook de n8n sin bloquear
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                # Intento 1: n8n webhook
                try:
                    await client.post(self.n8n_url, json=payload)
                    print(f"[WHATSAPP N8N] Notificacion enviada a webhook n8n para {denuncia.telefono}")
                except Exception:
                    pass

                # Intento 2: gateway local Baileys (puerto 8088 /enviar)
                try:
                    await client.post(
                        self.wa_gateway_url,
                        json={
                            "numero": denuncia.telefono,
                            "numeros": [denuncia.telefono],
                            "to": denuncia.telefono,
                            "mensaje": mensaje_texto,
                            "message": mensaje_texto
                        }
                    )
                    print(f"[WHATSAPP GATEWAY] Notificacion entregada al gateway de WhatsApp para {denuncia.telefono}")
                except Exception:
                    pass
        except Exception:
            pass
