from typing import Optional, Dict, Any
import httpx
from app.ports.ia_validator_port import IIAValidatorPort

class HttpIAAdapter(IIAValidatorPort):
    def __init__(self, base_url: str = "http://127.0.0.1:8005"):
        self.base_url = base_url.rstrip("/")

    async def validar_imagen_fuego(self, imagen_url: Optional[str]) -> Dict[str, Any]:
        if not imagen_url:
            return {"verificado_por_ia": False, "nivel_confianza": 0.0, "detecciones": []}

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/vision/validar-evidencia-url",
                    json={"imagen_url": imagen_url}
                )
                if res.status_code == 200:
                    return res.json()
        except Exception:
            pass

        return {"verificado_por_ia": False, "nivel_confianza": 0.0, "detecciones": []}

    async def clasificar_urgencia_texto(self, texto: str) -> Dict[str, Any]:
        if not texto:
            return {"categoria_predicha": "PENDIENTE_TRIAJE", "confianza": 0.5}

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/nlp/clasificar-urgencia",
                    json={"texto": texto}
                )
                if res.status_code == 200:
                    return res.json()
        except Exception:
            pass

        texto_lower = texto.lower()
        if any(w in texto_lower for w in ["fuego", "llamas", "quema", "incendio", "humo"]):
            return {"categoria_predicha": "CRITICO_ESTRUCTURAL", "confianza": 0.88}
        if any(w in texto_lower for w in ["gas", "garrafa", "fuga"]):
            return {"categoria_predicha": "CRITICO_GAS", "confianza": 0.90}
        if any(w in texto_lower for w in ["choque", "accidente", "atrapado"]):
            return {"categoria_predicha": "ALTO_VEHICULAR", "confianza": 0.82}

        return {"categoria_predicha": "PENDIENTE_TRIAJE", "confianza": 0.50}
