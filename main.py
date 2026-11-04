from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import secrets
import logging

# 1. Importações dos routers
from routers import tarefas, ia, dashboard, usuarios, ocorrencias, app_user, mapa, historico, ia_groq, alertas
from database import init_db

# ==========================================
# 0. CONFIGURAÇÃO DE LOGS
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="API Plataforma Cana", version="2.1.0")

# ==========================================
# 1. LIBERAÇÃO DO CORS
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5500",  # Porta padrão do Live Server do VS Code
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. MIDDLEWARE DE SEGURANÇA (CSRF)
# ==========================================
class ProtecaoCSRF(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Requisições autenticadas com Authorization: Bearer (JWT explícito, não enviado automaticamente por cookies)
        # ou rotas da API REST não dependem de cookie CSRF.
        auth_header = request.headers.get("Authorization", "")
        if (
            auth_header.lower().startswith("bearer ")
            or request.url.path == "/prever-qualidade-agua"
            or request.url.path.startswith("/ocorrencias")
            or request.url.path.startswith("/users")
            or request.url.path.startswith("/mapa")
            or request.url.path.startswith("/historico")
            or request.url.path.startswith("/ia")
            or request.url.path.startswith("/alertas")
            or request.url.path.startswith("/tarefas")
        ):
            return await call_next(request)

        cookie_token = request.cookies.get("XSRF-TOKEN")
        
        if request.method in ["POST", "PUT", "DELETE"]:
            header_token = request.headers.get("X-XSRF-TOKEN")
            if not cookie_token or not header_token or cookie_token != header_token:
                return JSONResponse(
                    status_code=403, 
                    content={"detail": "Ataque CSRF bloqueado: Token inválido ou ausente."}
                )
        
        resposta = await call_next(request)
        if not cookie_token:
            novo_token = secrets.token_urlsafe(32)
            resposta.set_cookie(key="XSRF-TOKEN", value=novo_token, httponly=False)
            
        return resposta

app.add_middleware(ProtecaoCSRF)

# ==========================================
# 3. REGISTRO DAS ROTAS
# ==========================================
app.include_router(tarefas.router, prefix="/tarefas")
app.include_router(ia.router)
app.include_router(dashboard.router)
app.include_router(usuarios.router)
app.include_router(ocorrencias.router, prefix="/ocorrencias") 
app.include_router(app_user.router, prefix="/users")
app.include_router(mapa.router, prefix="/mapa")
app.include_router(historico.router, prefix="/historico")
app.include_router(ia_groq.router, prefix="/ia")
app.include_router(alertas.router, prefix="/alertas")

# ==========================================
# 4. EVENTOS DE CICLO DE VIDA (STARTUP)
# ==========================================
import asyncio
from services import telemetry_service

_background_tasks = []

@app.on_event("startup")
async def ao_iniciar_aplicacao():
    logger.info("🚀 Inicializando aplicação FastAPI Plataforma Cana (Multitenancy Ativo)...")
    init_db()
    # Dispara a rotina diária em background para rodar todo dia às 7h da manhã por tenant
    _background_tasks.append(asyncio.create_task(ia_groq.rotina_agendamento_analise_7h()))
    # Dispara o serviço contínuo de telemetria autônoma em background isolado por tenant
    _background_tasks.append(asyncio.create_task(telemetry_service.servico_telemetria_tempo_real()))

@app.on_event("shutdown")
async def ao_encerrar_aplicacao():
    for task in _background_tasks:
        task.cancel()
    _background_tasks.clear()
