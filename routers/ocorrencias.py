from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import random

from auth_tenant import get_current_tenant
from database import get_db, OccurrenceModel
from schemas import OcorrenciaCriar, OcorrenciaAtualizar, OcorrenciaResposta

router = APIRouter(tags=["Ocorrências"])


def _gerar_codigo_ocorrencia_unico(db: Session, tenant_id: str) -> str:
    for _ in range(20):
        candidato = f"OCR-{random.randint(1000, 9999)}"
        existe = (
            db.query(OccurrenceModel)
            .filter(
                OccurrenceModel.tenant_id == tenant_id,
                OccurrenceModel.code_occurrence == candidato,
            )
            .first()
        )
        if not existe:
            return candidato
    return f"OCR-{random.randint(10000, 99999)}"


@router.get("/", response_model=List[OcorrenciaResposta], summary="Listar todas as ocorrências do usuário")
def listar_ocorrencias(
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return (
        db.query(OccurrenceModel)
        .filter(OccurrenceModel.tenant_id == tenant_id)
        .order_by(OccurrenceModel.id_occurrence.desc())
        .all()
    )


@router.get("/{id_occurrence}", response_model=OcorrenciaResposta, summary="Buscar ocorrência por ID")
def buscar_ocorrencia(
    id_occurrence: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ocorrencia = (
        db.query(OccurrenceModel)
        .filter(
            OccurrenceModel.id_occurrence == id_occurrence,
            OccurrenceModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not ocorrencia:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada.")
    return ocorrencia


@router.post("/", response_model=OcorrenciaResposta, status_code=status.HTTP_201_CREATED, summary="Criar nova ocorrência")
def criar_ocorrencia(
    dados: OcorrenciaCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    # Se o frontend não enviar um código (ex: 'OCR-1234'), geramos um automaticamente único para este tenant
    codigo = dados.code_occurrence or _gerar_codigo_ocorrencia_unico(db, tenant_id)

    nova_ocorrencia = OccurrenceModel(
        tenant_id=tenant_id,
        code_occurrence=codigo,
        title_occurrence=dados.title_occurrence,
        location_occurrence=dados.location_occurrence,
        responsible_occurrence=dados.responsible_occurrence,
        metrics_occurrence=dados.metrics_occurrence,
        status_occurrence=dados.status_occurrence,
        risk_occurrence=dados.risk_occurrence,
    )

    db.add(nova_ocorrencia)
    db.commit()
    db.refresh(nova_ocorrencia)
    return nova_ocorrencia


@router.put("/{id_occurrence}", response_model=OcorrenciaResposta, summary="Atualizar ocorrência")
def atualizar_ocorrencia(
    id_occurrence: int,
    dados: OcorrenciaAtualizar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ocorrencia = (
        db.query(OccurrenceModel)
        .filter(
            OccurrenceModel.id_occurrence == id_occurrence,
            OccurrenceModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not ocorrencia:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada.")

    # Atualiza apenas os campos enviados no JSON
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(ocorrencia, campo, valor)

    db.commit()
    db.refresh(ocorrencia)
    return ocorrencia


@router.delete("/{id_occurrence}", status_code=status.HTTP_204_NO_CONTENT, summary="Excluir ocorrência")
def excluir_ocorrencia(
    id_occurrence: int,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    ocorrencia = (
        db.query(OccurrenceModel)
        .filter(
            OccurrenceModel.id_occurrence == id_occurrence,
            OccurrenceModel.tenant_id == tenant_id,
        )
        .first()
    )
    if not ocorrencia:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada.")

    db.delete(ocorrencia)
    db.commit()
    return None
