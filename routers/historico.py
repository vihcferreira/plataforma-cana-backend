from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from datetime import datetime, timedelta

from database import get_db, HistoryEventModel
from schemas import HistoryEventCriar, HistoryEventResposta

router = APIRouter(tags=["Histórico"])

@router.get("/", response_model=List[HistoryEventResposta])
def listar_historico(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: medicao, providencia, ocorrencia, alerta"),
    busca: Optional[str] = Query(None, description="Busca textual em descrição, ponto ou label"),
    dias: Optional[int] = Query(None, description="Limitar aos últimos N dias (ex: 7, 30)"),
    db: Session = Depends(get_db)
):
    query = db.query(HistoryEventModel)

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
        data_limite = datetime.utcnow() - timedelta(days=dias)
        query = query.filter(HistoryEventModel.datetime_history >= data_limite)

    # Ordena pelos eventos mais recentes primeiro
    eventos = query.order_by(HistoryEventModel.datetime_history.desc()).all()
    return eventos

@router.get("/{id_history}", response_model=HistoryEventResposta)
def obter_evento_historico(id_history: int, db: Session = Depends(get_db)):
    evento = db.query(HistoryEventModel).filter(HistoryEventModel.id_history == id_history).first()
    if not evento:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento de histórico não encontrado."
        )
    return evento

@router.post("/", response_model=HistoryEventResposta, status_code=status.HTTP_201_CREATED)
def criar_evento_historico(dados: HistoryEventCriar, db: Session = Depends(get_db)):
    novo_evento = HistoryEventModel(**dados.dict())
    db.add(novo_evento)
    db.commit()
    db.refresh(novo_evento)
    return novo_evento

@router.delete("/{id_history}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_evento_historico(id_history: int, db: Session = Depends(get_db)):
    evento = db.query(HistoryEventModel).filter(HistoryEventModel.id_history == id_history).first()
    if not evento:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evento de histórico não encontrado."
        )
    db.delete(evento)
    db.commit()
    return None
