"""
Cliente de integração com a API do Groq (LLM) — Plataforma Cana
"""

import json
import logging
import os
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)

_env_loaded = False
_http_client: Optional[httpx.Client] = None


def load_env_once() -> None:
    """Carrega variáveis do arquivo `.env` uma única vez sem sobrescrever variáveis já definidas no ambiente."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_path, override=False)
        return
    except ImportError:
        pass

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key:
                    os.environ.setdefault(key, val)
    except Exception as exc:
        logger.warning(f"Erro ao carregar .env: {exc}")


load_env_once()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """Você é o Assistente Especialista em Inteligência Artificial da Plataforma Cana (AquaGuard).
Contexto da aplicação:
- Trata-se de um sistema de gestão hídrica, monitoramento ambiental e tratamento de efluentes (como vinhaça e águas de lavagem) em usinas do setor sucroalcooleiro (cana-de-açúcar).
- Faixas operacionais oficiais dos pontos de monitoramento na usina:
  * pH: Normal entre 6.2 e 8.4 (alvo ~7.2) | Atenção: 5.5 a <6.2 ou >8.4 a 9.2 | Crítico: <5.5 ou >9.2.
  * Turbidez: Normal <= 30 NTU (alvo ~22 NTU) | Atenção: >30 a 60 NTU | Crítico: >60 NTU.
  * Volume de Efluentes: Normal <= 3.800 m³ (alvo ~2.800 m³) | Atenção: >3.800 a 4.800 m³ | Crítico: >4.800 m³.
  * Contaminantes: Normal <= 1.2 mg/L (alvo ~0.6 mg/L) | Atenção: >1.2 a 3.2 mg/L | Crítico: >3.2 mg/L.
  * Chuva intensa: acelera lixiviação, transbordamento de canais de vinhaça e contaminação de mananciais adjacentes.

Diretriz estrita:
Sempre responda em Português do Brasil de forma técnica, objetiva, profissional e contextualizada com a agroindústria canavieira.
Responda EXCLUSIVAMENTE em formato JSON válido, sem blocos markdown extras (como ```json) ou qualquer texto antes ou depois.
"""


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(timeout=30.0)
    return _http_client


def close_groq_http_client() -> None:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        _http_client.close()
    _http_client = None


def get_groq_credentials() -> tuple[str, str]:
    load_env_once()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
    return api_key, model


def call_groq_chat(messages: list, temperature: float = 0.2) -> Dict[str, Any]:
    api_key, model = get_groq_credentials()
    if not api_key:
        raise ValueError("GROQ_API_KEY não configurada no arquivo .env. Por favor, adicione sua chave de API.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    client = _get_http_client()
    response = client.post(GROQ_API_URL, headers=headers, json=payload)
    if response.status_code != 200:
        error_msg = response.text
        try:
            err_json = response.json()
            error_msg = err_json.get("error", {}).get("message", error_msg)
        except Exception:
            pass
        raise RuntimeError(f"Erro na API Groq ({response.status_code}): {error_msg}")

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)
