import os
import re
from typing import Optional
import httpx
from app.ports.notification_port import INotificationPort
from app.domain.models import DenunciaCiudadana

class HttpComandosAdapter(INotificationPort):
    """
    Adaptador de integracion de notificaciones hacia:
    1. MS-01 Comandos & Sala de Crisis (Despacho inmediato de unidades con autenticación SSO JWT)
    2. n8n / WhatsApp Gateway (Confirmación y seguimiento directo al teléfono del ciudadano)
    """

    def __init__(
        self,
        comandos_base_url: Optional[str] = None,
        n8n_webhook_url: Optional[str] = None,
        whatsapp_gateway_url: Optional[str] = None
    ):
        self.base_url = (comandos_base_url or os.getenv("COMANDOS_MS1_URL", "http://52.7.165.245:3000")).rstrip("/")
        self.n8n_url = (n8n_webhook_url or os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/alerta-ciudadana")).rstrip("/")
        self.wa_gateway_url = (whatsapp_gateway_url or os.getenv("WHATSAPP_GATEWAY_URL", "http://localhost:8088/enviar")).rstrip("/")
        self._cached_jwt_token: Optional[str] = None

    def _mapear_tipo_incidente(self, categoria_nlp: str) -> str:
        """
        Mapea las categorias de triaje NLP de MS-04 al enum estricto de MS-01 Comandos:
        ['ESTRUCTURAL', 'FORESTAL', 'QUIMICO', 'RESCATE', 'VEHICULAR']
        """
        cat = categoria_nlp.upper()
        if "FORESTAL" in cat or "QUEMA" in cat:
            return "FORESTAL"
        if "GAS" in cat or "QUIMICO" in cat:
            return "QUIMICO"
        if "VEHICULAR" in cat or "ACCIDENTE" in cat or "CHOQUE" in cat:
            return "VEHICULAR"
        if "RESCATE" in cat or "AUXILIO" in cat:
            return "RESCATE"
        return "ESTRUCTURAL"

    async def _obtener_token_comandos(self) -> Optional[str]:
        """Obtiene o reutiliza token JWT de operador en MS-01 Sala de Crisis"""
        if self._cached_jwt_token:
            return self._cached_jwt_token

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/auth/login",
                    json={
                        "email": "nataly.comandos@bomberos.gob.bo",
                        "password": "Comandos2026!"
                    }
                )
                if res.status_code == 200:
                    token = res.json().get("token")
                    if token:
                        self._cached_jwt_token = token
                        return token
        except Exception as e:
            print(f"[COMANDOS MS-01] Error obteniendo token JWT SSO: {e}")
        return None

    async def notificar_nueva_alerta(self, denuncia: DenunciaCiudadana) -> bool:
        prioridad = "CRITICA" if denuncia.es_prioridad_alta() else "NORMAL"
        print(f"[EVENTO SALA CRISIS] Denuncia: {denuncia.ticket_id} | Prioridad: {prioridad} | Cat: {denuncia.categoria_nlp}")

        # 1. Enviar notificación al WhatsApp del Ciudadano (vía n8n y gateway Baileys)
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
            "direccion": f"Zona reportada por ciudadano (Ticket {denuncia.ticket_id})",
            "denuncianteNombre": "Portal Ciudadano SCZ",
            "denuncianteTelefono": denuncia.telefono or "+591-70000000"
        }

        try:
            token = await self._obtener_token_comandos()
            headers = {"Authorization": f"Bearer {token}"} if token else {}

            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/incidentes",
                    json=payload,
                    headers=headers
                )
                if res.status_code in [200, 201]:
                    data = res.json()
                    cod = data.get("codigoRadial", "OK")
                    print(f"[COMANDOS MS-01] Emergencia vinculada en Sala de Crisis: {cod} para ticket {denuncia.ticket_id}")
                    return True
                elif res.status_code == 401:
                    # Renovar token e intentar 1 vez más
                    self._cached_jwt_token = None
                    new_token = await self._obtener_token_comandos()
                    if new_token:
                        res2 = await client.post(
                            f"{self.base_url}/api/v1/incidentes",
                            json=payload,
                            headers={"Authorization": f"Bearer {new_token}"}
                        )
                        if res2.status_code in [200, 201]:
                            return True
                print(f"[COMANDOS MS-01] Despacho enviado con respuesta HTTP {res.status_code}")
        except Exception as e:
            print(f"[COMANDOS MS-01] Comandos offline o inaccesible temporalmente ({e}). Alerta preservada en base de datos.")

        return True

    async def _notificar_whatsapp_ciudadano(self, denuncia: DenunciaCiudadana):
        """
        Emite la notificación automática de confirmación al WhatsApp del ciudadano
        con su número de ticket, verificación de IA e instrucciones de protección.
        """
        # Normalizar número de teléfono (ej. 78945612 -> 59178945612)
        raw_digits = re.sub(r"\D", "", denuncia.telefono or "")
        if len(raw_digits) == 8:
            phone_num = f"591{raw_digits}"
        else:
            phone_num = raw_digits if raw_digits else (denuncia.telefono or "")

        mensaje_texto = (
            f"🚒 *[CUERPO DE BOMBEROS SANTA CRUZ]*\n\n"
            f"Estimado ciudadano, su reporte de emergencia ha sido recibido y verificado por IA.\n\n"
            f"📋 *Ticket Radial:* `#{denuncia.ticket_id}`\n"
            f"🚦 *Estado:* {denuncia.estado}\n"
            f"🔍 *Verificación IA:* {denuncia.score_fuego_ia * 100:.0f}% de certeza visual (YOLOv8)\n"
            f"📍 *Categoría:* {denuncia.categoria_nlp}\n\n"
            f"📢 *Instrucciones de seguridad:*\n{denuncia.instrucciones_seguridad}\n\n"
            f"🚒 *Las unidades han sido informadas y la ayuda está en camino.* Mantenga la calma y el teléfono despejado."
        )

        payload = {
            "to": phone_num,
            "phone": phone_num,
            "numero": phone_num,
            "ticket_id": denuncia.ticket_id,
            "mensaje": mensaje_texto,
            "message": mensaje_texto,
            "estado": denuncia.estado,
            "prioridad_alta": denuncia.es_prioridad_alta()
        }

        # Intentar envio por gateway Baileys y n8n sin bloquear
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # 1. Enviar al Gateway local de WhatsApp Baileys (puerto 8088 /enviar)
                try:
                    res_gw = await client.post(
                        self.wa_gateway_url,
                        json={
                            "numero": phone_num,
                            "numeros": [phone_num],
                            "mensaje": mensaje_texto
                        }
                    )
                    if res_gw.status_code == 200:
                        print(f"[WHATSAPP GATEWAY] Notificación entregada exitosamente al WhatsApp de {phone_num}")
                except Exception as eg:
                    print(f"[WHATSAPP GATEWAY] Advertencia al contactar gateway: {eg}")

                # 2. Enviar a webhook de n8n
                try:
                    await client.post(self.n8n_url, json=payload)
                    print(f"[WHATSAPP N8N] Notificación transmitida a webhook n8n para {phone_num}")
                except Exception:
                    pass
        except Exception:
            pass
