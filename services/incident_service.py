"""
Serviço centralizado de Incidentes, Alertas, Ocorrências e Histórico — Plataforma Cana.
Unifica:
- Geração sem colisão de códigos `OCR-xxxx` e `AL-xxx` por tenant.
- Resolução de responsável ativo do tenant.
- Criação padronizada de `HistoryEventModel`, `MapMeasurementHistoryModel` e da tríade crítica
  (`OccurrenceModel` + `AlertModel` + `HistoryEventModel`).
"""

from datetime import datetime
import json
import secrets
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from database import (
    AlertModel,
    AppUserModel,
    HistoryEventModel,
    MapMeasurementHistoryModel,
    MapPointModel,
    OccurrenceModel,
)
from services.water_quality_service import utcnow


def gerar_codigo_ocorrencia_unico(db: Session, tenant_id: str) -> str:
    """Gera um código OCR único dentro do escopo do tenant usando CSPRNG (secrets) e limite de tentativas."""
    for _ in range(25):
        numero = 1000 + secrets.randbelow(9000)
        candidato = f"OCR-{numero}"
        existe = (
            db.query(OccurrenceModel.id_occurrence)
            .filter(
                OccurrenceModel.tenant_id == tenant_id,
                OccurrenceModel.code_occurrence == candidato,
            )
            .first()
        )
        if not existe:
            return candidato

    for _ in range(100):
        numero = 10000 + secrets.randbelow(990000)
        candidato = f"OCR-{numero}"
        existe = (
            db.query(OccurrenceModel.id_occurrence)
            .filter(
                OccurrenceModel.tenant_id == tenant_id,
                OccurrenceModel.code_occurrence == candidato,
            )
            .first()
        )
        if not existe:
            return candidato

    return f"OCR-{secrets.token_hex(4).upper()}"


def gerar_codigo_alerta_unico(db: Session, tenant_id: str) -> str:
    """Gera um código AL único dentro do escopo do tenant usando CSPRNG (secrets) e sem loop infinito."""
    for _ in range(25):
        numero = 100 + secrets.randbelow(900)
        candidato = f"AL-{numero}"
        existe = (
            db.query(AlertModel.id_alert)
            .filter(
                AlertModel.tenant_id == tenant_id,
                AlertModel.code_alert == candidato,
            )
            .first()
        )
        if not existe:
            return candidato

    for _ in range(100):
        numero = 1000 + secrets.randbelow(999000)
        candidato = f"AL-{numero}"
        existe = (
            db.query(AlertModel.id_alert)
            .filter(
                AlertModel.tenant_id == tenant_id,
                AlertModel.code_alert == candidato,
            )
            .first()
        )
        if not existe:
            return candidato

    return f"AL-{secrets.token_hex(4).upper()}"


def obter_responsavel_tenant(
    db: Session,
    tenant_id: str,
    point_name: Optional[str] = None,
    fallback: str = "Responsável Local",
) -> str:
    """Busca o responsável ativo vinculado ao ponto (ou o primeiro usuário ativo da conta)."""
    try:
        if point_name:
            usuario_ponto = (
                db.query(AppUserModel.name_user)
                .filter(
                    AppUserModel.tenant_id == tenant_id,
                    AppUserModel.status_user == "active",
                    AppUserModel.responsible_point_user == point_name,
                )
                .first()
            )
            if usuario_ponto and usuario_ponto[0]:
                return usuario_ponto[0]

        qualquer_usuario = (
            db.query(AppUserModel.name_user)
            .filter(
                AppUserModel.tenant_id == tenant_id,
                AppUserModel.status_user == "active",
            )
            .first()
        )
        if qualquer_usuario and qualquer_usuario[0]:
            return qualquer_usuario[0]
    except Exception:
        pass
    return fallback


def registrar_snapshot_medicao_mapa(
    db: Session,
    tenant_id: str,
    ponto: MapPointModel,
    recorded_at: Optional[datetime] = None,
) -> MapMeasurementHistoryModel:
    """Adiciona um snapshot em `Map_Measurement_History` na transação atual (sem commit implícito)."""
    hist = MapMeasurementHistoryModel(
        tenant_id=tenant_id,
        code_map_point=ponto.code_map_point,
        name_map_point=ponto.name_map_point,
        ph=ponto.ph_map_point,
        turbidity=ponto.turbidity_map_point,
        contaminant=ponto.contaminant_map_point,
        volume=ponto.volume_map_point if ponto.volume_map_point is not None else 2800.0,
        risk=ponto.risk_map_point,
        recorded_at=recorded_at or utcnow(),
    )
    db.add(hist)
    return hist


def registrar_evento_historico(
    db: Session,
    tenant_id: str,
    event_type: str,
    event_label: str,
    event_point: str,
    event_description: str,
    event_severity: str = "normal",
    id_reference: Optional[int] = None,
    reference_type: Optional[str] = None,
    created_by: Optional[str] = None,
    datetime_history: Optional[datetime] = None,
) -> HistoryEventModel:
    """Adiciona um evento na timeline `History_Event` na transação atual."""
    evento = HistoryEventModel(
        tenant_id=tenant_id,
        event_type=event_type,
        event_label=event_label,
        event_point=event_point,
        event_description=event_description,
        event_severity=event_severity,
        id_reference=id_reference,
        reference_type=reference_type,
        created_by=created_by,
        datetime_history=datetime_history or utcnow(),
    )
    db.add(evento)
    return evento


def registrar_incidente_critico(
    db: Session,
    tenant_id: str,
    occurrence_title: str,
    location_label: str,
    point_name: str,
    responsible: str,
    metrics_summary: str,
    alert_message: str,
    params_chips: List[str],
    recommendation: str,
    history_label: str,
    history_description_prefix: str,
    id_reference: Optional[int] = None,
    reference_type: Optional[str] = None,
    created_by: str = "Sistema",
    created_at: Optional[datetime] = None,
) -> Tuple[OccurrenceModel, AlertModel, HistoryEventModel]:
    """
    Cria de forma padronizada a tríade crítica (`Occurrence` + `Alert` + `History_Event`)
    com códigos garantidamente únicos para o `tenant_id`.
    """
    agora = created_at or utcnow()
    ocr_code = gerar_codigo_ocorrencia_unico(db, tenant_id)
    al_code = gerar_codigo_alerta_unico(db, tenant_id)

    nova_ocorrencia = OccurrenceModel(
        tenant_id=tenant_id,
        code_occurrence=ocr_code,
        title_occurrence=occurrence_title,
        location_occurrence=location_label,
        responsible_occurrence=responsible,
        metrics_occurrence=metrics_summary,
        status_occurrence="analise",
        risk_occurrence="critico",
        datetime_occurrence_creation=agora,
    )
    db.add(nova_ocorrencia)
    db.flush()

    novo_alerta = AlertModel(
        tenant_id=tenant_id,
        code_alert=al_code,
        point_name=point_name,
        severity="critical",
        status="active",
        message=alert_message,
        params_json=json.dumps(params_chips, ensure_ascii=False),
        recommendation=recommendation,
        responsible=responsible,
        id_occurrence=nova_ocorrencia.id_occurrence,
        code_occurrence=ocr_code,
        is_viewed=0,
        datetime_alert=agora,
    )
    db.add(novo_alerta)

    evento = registrar_evento_historico(
        db=db,
        tenant_id=tenant_id,
        event_type="alerta",
        event_label=history_label,
        event_point=location_label,
        event_description=f"{history_description_prefix} Ocorrência #{ocr_code} e Alerta #{al_code} gerados.",
        event_severity="critico",
        id_reference=id_reference,
        reference_type=reference_type,
        created_by=created_by,
        datetime_history=agora,
    )

    return nova_ocorrencia, novo_alerta, evento
