"""
Autenticação e Isolamento Multitenancy — Plataforma Cana
Valida criptograficamente o Firebase ID Token (RS256) e extrai o identificador único
do usuário autenticado (uid -> tenant_id), garantindo isolamento estrito entre contas.
"""

import base64
from dataclasses import dataclass
import json
import logging
import os
import re
import threading
import time
from typing import Callable, Dict, Optional

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx

from services.groq_client import load_env_once

load_env_once()

logger = logging.getLogger(__name__)

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "plataforma-efluentes-250eb")
GOOGLE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)
CLOCK_SKEW_SECONDS = 60

security_scheme = HTTPBearer(auto_error=False)

_certs_lock = threading.Lock()
_cached_certs: Dict[str, str] = {}
_certs_expires_at: float = 0.0
_certs_http_client: Optional[httpx.Client] = None


@dataclass(frozen=True)
class TenantContext:
    """Representa o contexto autenticado do tenant (usuário proprietário dos dados)."""

    tenant_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    email_verified: bool = False
    role: str = "Administrador"


def _get_certs_client() -> httpx.Client:
    global _certs_http_client
    if _certs_http_client is None or _certs_http_client.is_closed:
        _certs_http_client = httpx.Client(timeout=5.0)
    return _certs_http_client


def close_auth_http_client() -> None:
    global _certs_http_client
    if _certs_http_client is not None and not _certs_http_client.is_closed:
        _certs_http_client.close()
    _certs_http_client = None


def _b64url_decode(segment: str) -> bytes:
    rem = len(segment) % 4
    if rem:
        segment += "=" * (4 - rem)
    return base64.urlsafe_b64decode(segment.encode("ascii"))


def _parse_max_age(cache_control: str) -> int:
    match = re.search(r"max-age=(\d+)", cache_control or "")
    if match:
        return max(60, int(match.group(1)))
    return 3600


def _get_google_public_certs(force_refresh: bool = False) -> Dict[str, str]:
    """Busca e armazena em cache os certificados públicos X.509 do Firebase Auth."""
    global _cached_certs, _certs_expires_at

    now = time.time()
    with _certs_lock:
        if not force_refresh and _cached_certs and now < _certs_expires_at:
            return _cached_certs

        try:
            response = _get_certs_client().get(GOOGLE_CERTS_URL)
            response.raise_for_status()
            certs = response.json()
            if not isinstance(certs, dict) or not certs:
                raise ValueError("Resposta de certificados públicos vazia ou inválida.")

            ttl = _parse_max_age(response.headers.get("Cache-Control", ""))
            _cached_certs = certs
            _certs_expires_at = now + ttl
            return _cached_certs
        except Exception as exc:
            if _cached_certs:
                logger.warning(f"[AuthTenant] Falha ao atualizar certificados Google, usando cache existente: {exc}")
                return _cached_certs
            logger.error(f"[AuthTenant] Não foi possível obter certificados públicos do Firebase: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Serviço de validação de autenticação temporariamente indisponível.",
            )


def verify_firebase_id_token(token: str, project_id: str = FIREBASE_PROJECT_ID) -> TenantContext:
    """Verifica a assinatura RS256 e as claims obrigatórias de um Firebase ID Token."""
    if not token or token.count(".") != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação malformado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    header_b64, payload_b64, signature_b64 = token.split(".")

    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        signature = _b64url_decode(signature_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não foi possível decodificar o token de autenticação.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if header.get("alg") != "RS256":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Algoritmo de assinatura não suportado.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    kid = header.get("kid")
    if not kid or not isinstance(kid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identificador de chave (kid) ausente no token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    certs = _get_google_public_certs(force_refresh=False)
    cert_pem = certs.get(kid)
    if not cert_pem:
        certs = _get_google_public_certs(force_refresh=True)
        cert_pem = certs.get(kid)

    if not cert_pem:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave pública de assinatura não reconhecida.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        cert_obj = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        public_key = cert_obj.public_key()
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Assinatura do token inválida.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as exc:
        logger.warning(f"[AuthTenant] Erro ao validar certificado/assinatura: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falha na validação criptográfica do token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = time.time()
    expected_issuer = f"https://securetoken.google.com/{project_id}"

    aud = payload.get("aud")
    iss = payload.get("iss")
    exp = payload.get("exp")
    iat = payload.get("iat")
    sub = payload.get("sub")

    if aud != project_id or iss != expected_issuer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token emitido para projeto ou emissor inválido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not isinstance(exp, (int, float)) or now >= (exp + CLOCK_SKEW_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada. Faça login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not isinstance(iat, (int, float)) or iat > (now + CLOCK_SKEW_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Data de emissão do token inválida.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not sub or not isinstance(sub, str) or len(sub.strip()) == 0 or len(sub) > 128:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identificador de usuário (uid) inválido no token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email_verified = bool(payload.get("email_verified", False))
    require_verified = os.getenv("REQUIRE_EMAIL_VERIFIED", "false").lower() in ("1", "true", "yes")
    if require_verified and not email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verificação de e-mail obrigatória para acessar este recurso.",
        )

    raw_email = payload.get("email")
    clean_email = str(raw_email).strip().lower() if raw_email else None
    custom_role = str(payload.get("role") or "Administrador").strip()

    return TenantContext(
        tenant_id=sub.strip(),
        email=clean_email,
        name=payload.get("name"),
        email_verified=email_verified,
        role=custom_role,
    )


def get_current_tenant_context(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> TenantContext:
    """Dependência FastAPI que exige Bearer token válido e retorna o TenantContext."""
    if not credentials or not credentials.credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação obrigatória. Token Bearer ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_firebase_id_token(credentials.credentials)


def get_current_tenant(
    context: TenantContext = Depends(get_current_tenant_context),
) -> str:
    """Dependência FastAPI que retorna diretamente o tenant_id (uid do usuário autenticado)."""
    return context.tenant_id


def require_roles(*allowed_roles: str) -> Callable:
    """Dependência FastAPI para impor Controle de Acesso Baseado em Papéis (RBAC)."""
    allowed_set = {r.strip() for r in allowed_roles if r.strip()}

    def _role_checker(
        context: TenantContext = Depends(get_current_tenant_context),
    ) -> TenantContext:
        if allowed_set and context.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado. Perfil necessário: {', '.join(sorted(allowed_set))}.",
            )
        return context

    return _role_checker
