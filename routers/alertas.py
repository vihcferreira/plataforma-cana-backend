"""
Router de Alertas Operacionais — Plataforma Cana / AquaGuard
Gerenciamento de alertas gerados por telemetria e notificações da plataforma.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import random
from datetime import datetime

from database import get_db, AlertModel
from schemas import AlertCriar, AlertResposta

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
        "datetime_alert": alert.datetime_alert
    }

@router.get("/", response_model=List[AlertResposta], summary="Listar todos os alertas")
def listar_alertas(
    severidade: Optional[str] = Query(None, description="Filtrar por severidade: critical, medium, preventive, resolved"),
    db: Session = Depends(get_db)
):
    query = db.query(AlertModel)
    if severidade and severidade != "todos":
        query = query.filter(AlertModel.severity == severidade)
    
    alertas = query.order_by(AlertModel.id_alert.desc()).all()
    return [alert_model_to_dict(a) for a in alertas]

@router.get("/contagem-nao-lidos", summary="Obter contagem de alertas não lidos para a navbar")
def contagem_nao_lidos(db: Session = Depends(get_db)):
    count = db.query(AlertModel).filter(AlertModel.is_viewed == 0).count()
    return {"unread_count": count}

@router.post("/marcar-lidos", summary="Marcar todos os alertas como lidos/visualizados")
def marcar_alertas_como_lidos(db: Session = Depends(get_db)):
    db.query(AlertModel).filter(AlertModel.is_viewed == 0).update({"is_viewed": 1})
    db.commit()
    return {"success": True, "message": "Alertas marcados como visualizados."}

@router.post("/", response_model=AlertResposta, status_code=status.HTTP_201_CREATED, summary="Criar alerta manual")
def criar_alerta(dados: AlertCriar, db: Session = Depends(get_db)):
    codigo = dados.code_alert or f"AL-{random.randint(100, 999)}"
    params_str = json.dumps(dados.params) if isinstance(dados.params, list) else str(dados.params)
    
    novo_alerta = AlertModel(
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
        is_viewed=0
    )
    db.add(novo_alerta)
    db.commit()
    db.refresh(novo_alerta)
    return alert_model_to_dict(novo_alerta)

@router.delete("/{id_alert}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir alerta")
def excluir_alerta(id_alert: int, db: Session = Depends(get_db)):
    alerta = db.query(AlertModel).filter(AlertModel.id_alert == id_alert).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta não encontrado.")
    db.delete(alerta)
    db.commit()
    return None

# Estado global da configuração de notificações de alertas
_config_notificacoes = {
    "email_alerts": True,
    "push_alerts": True,
    "user_email": ""
}

@router.get("/config-notificacoes", summary="Obter configurações atuais de notificação")
def obter_config_notificacoes():
    return _config_notificacoes

@router.post("/config-notificacoes", summary="Atualizar configurações de notificação")
def atualizar_config_notificacoes(dados: dict):
    global _config_notificacoes
    if "email_alerts" in dados:
        _config_notificacoes["email_alerts"] = bool(dados["email_alerts"])
    if "push_alerts" in dados:
        _config_notificacoes["push_alerts"] = bool(dados["push_alerts"])
    if "user_email" in dados and dados["user_email"]:
        _config_notificacoes["user_email"] = str(dados["user_email"])
    return {"success": True, "config": _config_notificacoes}

