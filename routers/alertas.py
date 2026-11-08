"""
Router de Alertas Operacionais e Preferências do Tenant — Plataforma Cana / AquaGuard
"""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth_tenant import TenantContext, get_current_tenant, get_current_tenant_context
from database import AlertModel, get_db
from schemas import AlertResposta, GeneralSettingsUpdate, NotificationSettingsUpdate
from services.tenant_settings_service import (
    get_general_settings,
    get_notification_settings,
    update_general_settings,
    update_notification_settings,
)

router = APIRouter(tags=["Alertas"])


def alert_model_to_dict(alert: AlertModel) -> dict:
    try:
        params_list = json.loads(alert.params_json) if alert.params_json else []
    except Exception:
        params_list = [alert.params_json] if alert.params_json else []

    return {
        "id_alert": alert.id_alert,
        "code_alert": alert.code_alert,
        "point_name": alert.point_name,
        "severity": alert.severity,
        "status": alert.status,
        "message": alert.message,
        "params": params_list,
        "recommendation": alert.recommendation,
        "responsible": alert.responsible,
        "id_occurrence": alert.id_occurrence,
        "code_occurrence": alert.code_occurrence,
        "is_viewed": alert.is_viewed,
        "datetime_alert": alert.datetime_alert,
    }


@router.get("/", response_model=List[AlertResposta], summary="Listar todos os alertas do usuário")
def listar_alertas(
    severidade: Optional[str] = Query(None, description="Filtrar por severidade: critical, medium, preventive, resolved"),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    query = db.query(AlertModel).filter(AlertModel.tenant_id == tenant_id)
    if severidade and severidade != "todos":
        query = query.filter(AlertModel.severity == severidade)

    alertas = query.order_by(AlertModel.id_alert.desc()).limit(500).all()
    return [alert_model_to_dict(a) for a in alertas]


@router.get("/contagem-nao-lidos", summary="Obter contagem de alertas não lidos do usuário para a navbar")
def contagem_nao_lidos(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    count = (
        db.query(AlertModel)
        .filter(
            AlertModel.tenant_id == tenant_id,
            AlertModel.is_viewed == 0,
        )
        .count()
    )
    return {"unread_count": count}


@router.post("/marcar-lidos", summary="Marcar todos os alertas do usuário como lidos/visualizados")
def marcar_alertas_como_lidos(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    (
        db.query(AlertModel)
        .filter(
            AlertModel.tenant_id == tenant_id,
            AlertModel.is_viewed == 0,
        )
        .update({"is_viewed": 1})
    )
    db.commit()
    return {"success": True, "message": "Alertas marcados como visualizados."}


@router.get("/config-notificacoes", summary="Obter configurações atuais de notificação do usuário")
def obter_config_notificacoes(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    return get_notification_settings(
        tenant_id=ctx.tenant_id,
        db=db,
        default_email=ctx.email or "",
    )


@router.post("/config-notificacoes", summary="Atualizar configurações de notificação do usuário")
def atualizar_config_notificacoes(
    dados: NotificationSettingsUpdate,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    payload = dados if isinstance(dados, NotificationSettingsUpdate) else NotificationSettingsUpdate(**dados)
    nova_cfg = update_notification_settings(
        tenant_id=ctx.tenant_id,
        email_alerts=payload.email_alerts,
        push_alerts=payload.push_alerts,
        user_email=payload.user_email,
        default_email=ctx.email or "",
        db=db,
    )
    return {"success": True, "config": nova_cfg}


@router.get("/config-gerais", summary="Obter configurações gerais da plataforma para o usuário")
def obter_config_gerais(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return get_general_settings(tenant_id=tenant_id, db=db)


@router.post("/config-gerais", summary="Salvar configurações gerais da plataforma para o usuário")
def atualizar_config_gerais(
    dados: GeneralSettingsUpdate,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    payload = dados if isinstance(dados, GeneralSettingsUpdate) else GeneralSettingsUpdate(**dados)
    cfg = update_general_settings(
        tenant_id=tenant_id,
        unit=payload.unit,
        frequency=payload.frequency,
        timezone_name=payload.timezone,
        db=db,
    )
    return {"success": True, "config": cfg}
