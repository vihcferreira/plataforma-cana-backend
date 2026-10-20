from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import random

from database import get_db, OccurrenceModel
from schemas import OcorrenciaCriar, OcorrenciaAtualizar, OcorrenciaResposta

router = APIRouter(tags=["Ocorrências"])

@router.get("/", response_model=List[OcorrenciaResposta], summary="Listar todas as ocorrências")
def listar_ocorrencias(db: Session = Depends(get_db)):
    return db.query(OccurrenceModel).order_by(OccurrenceModel.id_occurrence.desc()).all()

@router.get("/{id_occurrence}", response_model=OcorrenciaResposta, summary="Buscar ocorrência por ID")
def buscar_ocorrencia(id_occurrence: int, db: Session = Depends(get_db)):
    ocorrencia = db.query(OccurrenceModel).filter(OccurrenceModel.id_occurrence == id_occurrence).first()
    if not ocorrencia:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada.")
    return ocorrencia

@router.post("/", response_model=OcorrenciaResposta, status_code=status.HTTP_201_CREATED, summary="Criar nova ocorrência")
def criar_ocorrencia(dados: OcorrenciaCriar, db: Session = Depends(get_db)):
    # Se o frontend não enviar um código (ex: 'OCR-1234'), geramos um automaticamente
    codigo = dados.code_occurrence or f"OCR-{random.randint(1000, 9999)}"
    
    nova_ocorrencia = OccurrenceModel(
        code_occurrence=codigo,
        title_occurrence=dados.title_occurrence,
        location_occurrence=dados.location_occurrence,
        responsible_occurrence=dados.responsible_occurrence,
        metrics_occurrence=dados.metrics_occurrence,
        status_occurrence=dados.status_occurrence,
        risk_occurrence=dados.risk_occurrence
    )
    
    db.add(nova_ocorrencia)
    db.commit()
    db.refresh(nova_ocorrencia)
    return nova_ocorrencia

@router.put("/{id_occurrence}", response_model=OcorrenciaResposta, summary="Atualizar ocorrência")
def atualizar_ocorrencia(id_occurrence: int, dados: OcorrenciaAtualizar, db: Session = Depends(get_db)):
    ocorrencia = db.query(OccurrenceModel).filter(OccurrenceModel.id_occurrence == id_occurrence).first()
    if not ocorrencia:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada.")
    
    # Atualiza apenas os campos enviados no JSON
    for campo, valor in dados.dict(exclude_unset=True).items():
        setattr(ocorrencia, campo, valor)
        
    db.commit()
    db.refresh(ocorrencia)
    return ocorrencia

@router.delete("/{id_occurrence}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir ocorrência")
def excluir_ocorrencia(id_occurrence: int, db: Session = Depends(get_db)):
    ocorrencia = db.query(OccurrenceModel).filter(OccurrenceModel.id_occurrence == id_occurrence).first()
    if not ocorrencia:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada.")
        
    db.delete(ocorrencia)
    db.commit()
    return None
