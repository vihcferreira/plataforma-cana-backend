from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from auth_tenant import get_current_tenant
from database import get_db
from routers.ciclo_hidrico import calcular_resumo_ciclo_hidrico

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/metricas", summary="Obter Metricas do Tenant")
def obter_metricas(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    resumo_ciclo = calcular_resumo_ciclo_hidrico(db=db, tenant_id=tenant_id)
    return {
        "status": "sucesso",
        "tenant_id": tenant_id,
        "mensagem": "Métricas carregadas com sucesso",
        "ciclo_hidrico": resumo_ciclo,
    }
