"""
Ponto de entrada da API FastAPI — Plataforma Cana.
"""

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auth_tenant import close_auth_http_client
from database import init_db
from routers import alertas, app_user, ciclo_hidrico, historico, ia_groq, mapa, ocorrencias
from services import telemetry_service
from services.groq_client import close_groq_http_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

IS_PROD = os.getenv("ENVIRONMENT", "development").lower() == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Inicializando aplicação FastAPI Plataforma Cana (Multitenancy Ativo)...")
    await asyncio.to_thread(init_db)

    background_tasks = [
        asyncio.create_task(ia_groq.rotina_agendamento_analise_7h()),
        asyncio.create_task(telemetry_service.servico_telemetria_tempo_real()),
    ]
    try:
        yield
    finally:
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        close_groq_http_client()
        close_auth_http_client()


app = FastAPI(
    title="API Plataforma Cana",
    version="2.2.0",
    lifespan=lifespan,
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Rate Limiting em memória por IP/Rota (Proteção contra DoS e exaustão de cota LLM)
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_AI_RATE_LIMIT = 15  # máx 15 chamadas / 60s para rotas de IA e seed
_GENERAL_RATE_LIMIT = 240  # máx 240 chamadas / 60s para rotas gerais
_RATE_WINDOW_SECONDS = 60.0


@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    if request.method != "OPTIONS":
        client_ip = (request.client.host if request.client else "unknown") or "unknown"
        path = request.url.path
        is_heavy_route = path.startswith("/ia/") or path.endswith("/seed-exemplo")
        bucket_key = f"{client_ip}:{'heavy' if is_heavy_route else 'general'}"
        max_reqs = _AI_RATE_LIMIT if is_heavy_route else _GENERAL_RATE_LIMIT

        now = time.monotonic()
        dq = _rate_buckets[bucket_key]
        while dq and (now - dq[0]) > _RATE_WINDOW_SECONDS:
            dq.popleft()

        if len(dq) >= max_reqs:
            return JSONResponse(
                status_code=429,
                content={"detail": "Muitas requisições em um curto período. Aguarde alguns segundos e tente novamente."},
                headers={"Retry-After": "60"},
            )
        dq.append(now)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if IS_PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Registro exclusivo das rotas ativas da plataforma
app.include_router(ocorrencias.router, prefix="/ocorrencias")
app.include_router(app_user.router, prefix="/users")
app.include_router(mapa.router, prefix="/mapa")
app.include_router(historico.router, prefix="/historico")
app.include_router(ia_groq.router, prefix="/ia")
app.include_router(alertas.router, prefix="/alertas")
app.include_router(ciclo_hidrico.router, prefix="/ciclo-hidrico")
