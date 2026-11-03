from fastapi import APIRouter, Depends
from auth_tenant import get_current_tenant

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/metricas", summary="Obter Metricas do Tenant")
def obter_metricas(tenant_id: str = Depends(get_current_tenant)):
    return {
        "status": "sucesso",
        "tenant_id": tenant_id,
        "mensagem": "Métricas carregadas com sucesso",
    }
