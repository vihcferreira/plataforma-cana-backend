"""
Router de Alertas Operacionais e Preferências do Tenant — Plataforma Cana / AquaGuard
Gerenciamento de alertas gerados por telemetria e configurações isoladas por usuário (tenant_id).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
import json
import random

from auth_tenant import get_current_tenant, get_current_tenant_context, TenantContext
from database import get_db, AlertModel, TenantSettingsModel
from schemas import AlertCriar, AlertResposta

router = APIRouter(tags=["Alertas"])

# Fallback em memória indexado por tenant_id caso o banco esteja indisponível
_config_notificacoes_por_tenant: Dict[str, dict] = {}
_config_gerais_por_tenant: Dict[str, dict] = {}


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


def _gerar_codigo_alerta_unico(db: Session, tenant_id: str) -> str:
    for _ in range(20):
        candidato = f"AL-{random.randint(100, 999)}"
        existe = (
            db.query(AlertModel)
            .filter(
                AlertModel.tenant_id == tenant_id,
                AlertModel.code_alert == candidato,
            )
            .first()
        )
        if not existe:
            return candidato
    return f"AL-{random.randint(1000, 9999)}"


def obter_config_notificacoes_do_tenant(tenant_id: str, db: Optional[Session] = None, default_email: str = "") -> dict:
    """Retorna as preferências de notificação exclusivas de um tenant_id."""
    if db is not None:
        try:
            row = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
            if row:
                cfg = {
                    "email_alerts": bool(row.email_alerts),
                    "push_alerts": bool(row.push_alerts),
                    "user_email": row.user_email or default_email or "",
                }
                _config_notificacoes_por_tenant[tenant_id] = cfg
                return cfg
        except Exception:
            pass

    return _config_notificacoes_por_tenant.get(
        tenant_id,
        {
            "email_alerts": True,
            "push_alerts": True,
            "user_email": default_email or "",
        },
    )


@router.get("/", response_model=List[AlertResposta], summary="Listar todos os alertas do usuário")
def listar_alertas(
    severidade: Optional[str] = Query(None, description="Filtrar por severidade: critical, medium, preventive, resolved"),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    query = db.query(AlertModel).filter(AlertModel.tenant_id == tenant_id)
    if severidade and severidade != "todos":
        query = query.filter(AlertModel.severity == severidade)

    alertas = query.order_by(AlertModel.id_alert.desc()).all()
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


@router.post("/", response_model=AlertResposta, status_code=status.HTTP_201_CREATED, summary="Criar alerta manual")
def criar_alerta(
    dados: AlertCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    codigo = dados.code_alert or _gerar_codigo_alerta_unico(db, tenant_id)
    params_str = json.dumps(dados.params) if isinstance(dados.params, list) else str(dados.params)

    novo_alerta = AlertModel(
        tenant_id=tenant_id,
        code_alert=codigo,
        point_name=dados.point_name,
        severity=dados.severity,
        status=dados.status,
        message=dados.message,
        params_json=params_str,
        recommendation=dados.recommendation,
        responsible=dados.responsible,
        id_occurrence=dados.id_occurrence,
        code_occurrence=dados.code_occurrence,
        is_viewed=0,
    )
    db.add(novo_alerta)
    db.commit()
    db.refresh(novo_alerta)
    return alert_model_to_dict(novo_alerta)


@router.get("/config-notificacoes", summary="Obter configurações atuais de notificação do usuário")
def obter_config_notificacoes(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    return obter_config_notificacoes_do_tenant(
        tenant_id=ctx.tenant_id,
        db=db,
        default_email=ctx.email or "",
    )


@router.post("/config-notificacoes", summary="Atualizar configurações de notificação do usuário")
def atualizar_config_notificacoes(
    dados: dict,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_db),
):
    tenant_id = ctx.tenant_id
    atual = obter_config_notificacoes_do_tenant(tenant_id, db=db, default_email=ctx.email or "")

    email_alerts = bool(dados["email_alerts"]) if "email_alerts" in dados else atual["email_alerts"]
    push_alerts = bool(dados["push_alerts"]) if "push_alerts" in dados else atual["push_alerts"]
    user_email = str(dados.get("user_email") or ctx.email or atual.get("user_email") or "")

    nova_cfg = {
        "email_alerts": email_alerts,
        "push_alerts": push_alerts,
        "user_email": user_email,
    }
    _config_notificacoes_por_tenant[tenant_id] = nova_cfg

    try:
        row = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
        if not row:
            row = TenantSettingsModel(
                tenant_id=tenant_id,
                email_alerts=1 if email_alerts else 0,
                push_alerts=1 if push_alerts else 0,
                user_email=user_email,
            )
            db.add(row)
        else:
            row.email_alerts = 1 if email_alerts else 0
            row.push_alerts = 1 if push_alerts else 0
            row.user_email = user_email
        db.commit()
    except Exception:
        db.rollback()

    return {"success": True, "config": nova_cfg}


@router.get("/config-gerais", summary="Obter configurações gerais da plataforma para o usuário")
def obter_config_gerais(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    try:
        row = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
        if row:
            cfg = {
                "unit": row.unit_select or "vale-verde-norte",
                "frequency": str(row.frequency_minutes or 15),
                "timezone": row.timezone or "America/Sao_Paulo",
            }
            _config_gerais_por_tenant[tenant_id] = cfg
            return cfg
    except Exception:
        pass

    return _config_gerais_por_tenant.get(
        tenant_id,
        {
            "unit": "vale-verde-norte",
            "frequency": "15",
            "timezone": "America/Sao_Paulo",
        },
    )


@router.post("/config-gerais", summary="Salvar configurações gerais da plataforma para o usuário")
def atualizar_config_gerais(
    dados: dict,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    unit = str(dados.get("unit") or "vale-verde-norte")
    try:
        freq_int = int(dados.get("frequency") or 15)
    except (TypeError, ValueError):
        freq_int = 15
    tz = str(dados.get("timezone") or "America/Sao_Paulo")

    cfg = {
        "unit": unit,
        "frequency": str(freq_int),
        "timezone": tz,
    }
    _config_gerais_por_tenant[tenant_id] = cfg

    try:
        row = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
        if not row:
            row = TenantSettingsModel(
                tenant_id=tenant_id,
                unit_select=unit,
                frequency_minutes=freq_int,
                timezone=tz,
            )
            db.add(row)
        else:
            row.unit_select = unit
            row.frequency_minutes = freq_int
            row.timezone = tz
        db.commit()
    except Exception:
        db.rollback()

    return {"success": True, "config": cfg}


@router.delete("/{id_alert}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir alerta")
def excluir_alerta(
    id_alert: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    alerta = (
        db.query(AlertModel)
        .filter(
            AlertModel.id_alert == id_alert,
            AlertModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta não encontrado.")
    db.delete(alerta)
    db.commit()
    return None
