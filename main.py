"""
Ponto de entrada da API FastAPI — Plataforma Cana.
"""

import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth_tenant import close_auth_http_client
from database import init_db
from routers import alertas, app_user, ciclo_hidrico, historico, ia_groq, mapa, ocorrencias
from services import telemetry_service
from services.groq_client import close_groq_http_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


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


app = FastAPI(title="API Plataforma Cana", version="2.2.0", lifespan=lifespan)

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
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro exclusivo das rotas ativas da plataforma
app.include_router(ocorrencias.router, prefix="/ocorrencias")
app.include_router(app_user.router, prefix="/users")
app.include_router(mapa.router, prefix="/mapa")
app.include_router(historico.router, prefix="/historico")
app.include_router(ia_groq.router, prefix="/ia")
app.include_router(alertas.router, prefix="/alertas")
app.include_router(ciclo_hidrico.router, prefix="/ciclo-hidrico")
