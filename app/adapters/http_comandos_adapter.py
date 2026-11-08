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
    2. n8n / WhatsApp Gateway (Notificación al ciudadano ÚNICAMENTE cuando Comandos valida y despacha unidades)
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
            async with httpx.AsyncClient(timeout=6.0, verify=False) as client:
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
        """
        Envía el reporte verificado a MS-01 Sala de Crisis para que el operador lo valide y despache unidades.
        """
        prioridad = "CRITICA" if denuncia.es_prioridad_alta() else "MEDIA"
        print(f"[EVENTO SALA CRISIS] Denuncia recibida: {denuncia.ticket_id} | Prioridad: {prioridad} | Cat: {denuncia.categoria_nlp} | Verificado IA: {denuncia.score_fuego_ia}")

        tipo_incidente = self._mapear_tipo_incidente(denuncia.categoria_nlp)
        payload = {
            "tipoIncidente": tipo_incidente,
            "severidad": prioridad,
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

            async with httpx.AsyncClient(timeout=7.0, verify=False) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/incidentes",
                    json=payload,
                    headers=headers
                )
                if res.status_code in [200, 201]:
                    data = res.json()
                    cod = data.get("codigoRadial", "OK")
                    print(f"[COMANDOS MS-01] Emergencia vinculada en Sala de Crisis: {cod} para ticket {denuncia.ticket_id}. En espera de despacho de unidades.")
                    return True
                elif res.status_code == 401:
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
                print(f"[COMANDOS MS-01] Alerta enviada con respuesta HTTP {res.status_code}")
        except Exception as e:
            print(f"[COMANDOS MS-01] Comandos offline o inaccesible temporalmente ({e}). Alerta preservada en base de datos.")

        return True

    async def notificar_despacho_whatsapp(
        self,
        telefono: str,
        ticket_id: str,
        codigo_radial: str,
        estado: str = "DESPACHADO",
        unidades: int = 1
    ):
        """
        Emite la notificación oficial al WhatsApp del ciudadano SOLO cuando Comandos
        ha asignado unidades y el vehículo de bomberos va en camino.
        """
        raw_digits = re.sub(r"\D", "", telefono or "")
        if len(raw_digits) == 8:
            phone_num = f"591{raw_digits}"
        else:
            phone_num = raw_digits if raw_digits else (telefono or "")

        mensaje_texto = (
            f"🚒 *[CUERPO DE BOMBEROS SANTA CRUZ]*\n\n"
            f"🚨 *¡LA AYUDA ESTÁ EN CAMINO!*\n\n"
            f"Central de Crisis ha validado tu reporte radial *#{ticket_id}* (`{codigo_radial}`).\n"
            f"Se ha confirmado el despacho de *{unidades} unidad(es)* de bomberos hacia tu ubicación.\n\n"
            f"🚦 *Estado:* {estado}\n"
            f"📢 *Recomendaciones:* Por favor mantén el acceso despejado para los camiones cisterna y permanece a resguardo en una zona segura.\n\n"
            f"Para cualquier novedad urgente, comunícate a la línea gratuita 119."
        )

        payload = {
            "to": phone_num,
            "phone": phone_num,
            "numero": phone_num,
            "ticket_id": ticket_id,
            "codigo_radial": codigo_radial,
            "mensaje": mensaje_texto,
            "message": mensaje_texto,
            "estado": estado,
            "unidades": unidades
        }

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                try:
                    res_gw = await client.post(
                        self.wa_gateway_url,
                        json={"numero": phone_num, "mensaje": mensaje_texto}
                    )
                    if res_gw.status_code == 200:
                        print(f"[WHATSAPP GATEWAY] Notificación oficial de despacho entregada a {phone_num}")
                except Exception as eg:
                    print(f"[WHATSAPP GATEWAY] Error gateway: {eg}")

                try:
                    await client.post(self.n8n_url, json=payload)
                    print(f"[WHATSAPP N8N] Notificación de despacho transmitida a n8n para {phone_num}")
                except Exception:
                    pass
        except Exception:
            pass
