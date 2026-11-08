from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth_tenant import get_current_tenant
from database import HistoryEventModel, get_db
from schemas import HistoryEventResposta
from services.water_quality_service import utcnow

router = APIRouter(tags=["Histórico"])


@router.get("/", response_model=List[HistoryEventResposta])
def listar_historico(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: medicao, providencia, ocorrencia, alerta"),
    busca: Optional[str] = Query(None, description="Busca textual em descrição, ponto ou label"),
    dias: Optional[int] = Query(None, description="Limitar aos últimos N dias (ex: 7, 30)"),
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    query = db.query(HistoryEventModel).filter(HistoryEventModel.tenant_id == tenant_id)

    if tipo and tipo != "all":
        query = query.filter(HistoryEventModel.event_type == tipo)

    if busca:
        termo = f"%{busca}%"
        query = query.filter(
            or_(
                HistoryEventModel.event_description.ilike(termo),
                HistoryEventModel.event_point.ilike(termo),
                HistoryEventModel.event_label.ilike(termo),
                HistoryEventModel.created_by.ilike(termo),
            )
        )

    if dias and dias > 0:
        data_limite = utcnow() - timedelta(days=dias)
        query = query.filter(HistoryEventModel.datetime_history >= data_limite)

    return query.order_by(HistoryEventModel.datetime_history.desc()).limit(500).all()
