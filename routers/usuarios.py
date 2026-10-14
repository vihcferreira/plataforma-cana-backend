from fastapi import APIRouter

router = APIRouter(tags=["Usuários e Autenticação"])

@router.post("/login", summary="Fazer Login")
def fazer_login():
    return {"status": "logado"}

@router.get("/usuarios", summary="Listar Usuarios")
def listar_usuarios():
    return []

@router.post("/usuarios", summary="Cadastrar Usuario")
def cadastrar_usuario():
    return {"status": "Usuário criado"}