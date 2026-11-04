from fastapi import APIRouter, Depends
from auth_tenant import get_current_tenant_context, TenantContext

router = APIRouter(tags=["Usuários e Autenticação"])


@router.get("/me", summary="Obter perfil autenticado do tenant atual")
def obter_perfil_atual(ctx: TenantContext = Depends(get_current_tenant_context)):
    return {
        "tenant_id": ctx.tenant_id,
        "email": ctx.email,
        "name": ctx.name,
    }
