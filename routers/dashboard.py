from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/metricas", summary="Obter Metricas")
def obter_metricas():
    return {"status": "sucesso", "mensagem": "Métricas carregadas com sucesso"}