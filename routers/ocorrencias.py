from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_tenant import get_current_tenant
from database import OccurrenceModel, get_db
from schemas import OcorrenciaAtualizar, OcorrenciaCriar, OcorrenciaResposta
from services.incident_service import gerar_codigo_ocorrencia_unico, registrar_evento_historico

router = APIRouter(tags=["Ocorrências"])


def _mapear_severidade_historico(risco: str) -> str:
    r = (risco or "").strip().lower()
    if r.startswith("crit") or r == "high":
        return "critico"
    if r.startswith("med"):
        return "medio"
    return "normal"


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


@router.post("/", response_model=OcorrenciaResposta, status_code=status.HTTP_201_CREATED, summary="Criar nova ocorrência")
def criar_ocorrencia(
    dados: OcorrenciaCriar,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    codigo = dados.code_occurrence or gerar_codigo_ocorrencia_unico(db, tenant_id)

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
    db.flush()

    registrar_evento_historico(
        db=db,
        tenant_id=tenant_id,
        event_type="ocorrencia",
        event_label="Nova Ocorrência",
        event_point=nova_ocorrencia.location_occurrence,
        event_description=(
            f"Ocorrência #{nova_ocorrencia.code_occurrence} registrada: "
            f"{nova_ocorrencia.title_occurrence} ({nova_ocorrencia.metrics_occurrence})"
        ),
        event_severity=_mapear_severidade_historico(nova_ocorrencia.risk_occurrence),
        id_reference=nova_ocorrencia.id_occurrence,
        reference_type="occurrence",
        created_by=nova_ocorrencia.responsible_occurrence,
    )

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

    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(ocorrencia, campo, valor)

    eh_encerrada = (ocorrencia.status_occurrence or "").lower() in ("encerradas", "resolvido")
    registrar_evento_historico(
        db=db,
        tenant_id=tenant_id,
        event_type="providencia" if eh_encerrada else "ocorrencia",
        event_label="Ocorrência Encerrada" if eh_encerrada else "Atualização de Ocorrência",
        event_point=ocorrencia.location_occurrence,
        event_description=(
            f"Ocorrência #{ocorrencia.code_occurrence} atualizada para status "
            f"'{ocorrencia.status_occurrence}'. {ocorrencia.title_occurrence}."
        ),
        event_severity="normal" if eh_encerrada else _mapear_severidade_historico(ocorrencia.risk_occurrence),
        id_reference=ocorrencia.id_occurrence,
        reference_type="occurrence",
        created_by=ocorrencia.responsible_occurrence,
    )

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
