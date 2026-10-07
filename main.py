from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import secrets
import logging

# Agora os arquivos existem, podemos importar todos!
from routers import tarefas, ia, dashboard, usuarios

# ==========================================
# 0. CONFIGURAÇÃO DE LOGS
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="API Modularizada (Tarefas, IA, CSRF e CORS)", version="2.0.0")

# ==========================================
# 1. LIBERAÇÃO DO CORS
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
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
        if request.url.path == "/prever-qualidade-agua" and request.method == "POST":
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