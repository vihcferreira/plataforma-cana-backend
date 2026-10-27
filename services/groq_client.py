"""
Cliente de integração com a API do Groq (LLM) — Plataforma Cana
"""
import os
import json
import logging
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Carregamento simples de arquivo .env sem necessidade de bibliotecas extras
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
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
                        os.environ[key] = val
        except Exception as e:
            logger.warning(f"Erro ao carregar .env: {e}")

load_env_file()

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """Você é o Assistente Especialista em Inteligência Artificial da Plataforma Cana (AquaGuard).
Contexto da aplicação:
- Trata-se de um sistema de gestão hídrica, monitoramento ambiental e tratamento de efluentes (como vinhaça e águas de lavagem) em usinas do setor sucroalcooleiro (cana-de-açúcar).
- Parâmetros operacionais e limites máximos permitidos na usina:
  * pH ideal: entre 6.0 e 9.0 (valores acima de 9.0 são alcalinos/críticos, comuns em desvios de calagem/tratamento).
  * Turbidez: limite máximo de 50 NTU (valores acima indicam alta carga de sólidos em suspensão ou arraste de solo/vinhaça).
  * Volume de Efluentes: limite operacional de 4.000 m³ (acima disso há sobrecarga nas lagoas de estabilização).
  * Contaminantes: limite máximo de 3.0 mg/L (compostos orgânicos e químicos).
  * Chuva intensa: acelera lixiviação, transbordamento de canais de vinhaça e contaminação de mananciais adjacentes.

Diretriz estrita:
Sempre responda em Português do Brasil de forma técnica, objetiva, profissional e contextualizada com a agroindústria canavieira.
Responda EXCLUSIVAMENTE em formato JSON válido, sem blocos markdown extras (como ```json) ou qualquer texto antes ou depois.
"""

def get_groq_credentials():
    load_env_file()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b"
    return api_key, model


def call_groq_chat(messages: list, temperature: float = 0.2) -> Dict[str, Any]:
    api_key, model = get_groq_credentials()
    if not api_key:
        raise ValueError("GROQ_API_KEY não configurada no arquivo .env. Por favor, adicione sua chave de API.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"}
    }

    with httpx.Client(timeout=30.0) as client:
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
