"""
Serviço autônomo de Telemetria em Tempo Real — Plataforma Cana.
Opera isoladamente por `tenant_id`, utilizando avaliação de risco, configurações em lote e
criação de incidentes centralizadas em `services/` e executando I/O de banco em thread separada.
"""

import asyncio
import logging
import random
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from database import MapPointModel, SessionLocal
from services.incident_service import (
    obter_responsavel_tenant,
    registrar_incidente_critico,
    registrar_snapshot_medicao_mapa,
)
from services.tenant_settings_service import (
    get_telemetry_active,
    load_tenant_settings_batch,
    set_telemetry_active,
)
from services.water_quality_service import (
    POINT_THRESHOLDS,
    evaluate_point_parameters,
    utcnow,
)

logger = logging.getLogger(__name__)

_intervalo_segundos: int = 4


def obter_status_telemetria(tenant_id: str, db: Optional[Session] = None) -> dict:
    """Retorna o status atual do serviço de telemetria autônoma exclusivo para o tenant."""
    return {
        "active": get_telemetry_active(tenant_id, db=db),
        "interval_seconds": _intervalo_segundos,
    }


def definir_status_telemetria(ativo: bool, tenant_id: str, db: Optional[Session] = None) -> dict:
    """Ativa ou desativa a telemetria autônoma exclusivamente para o tenant autenticado."""
    novo_estado = set_telemetry_active(tenant_id=tenant_id, active=bool(ativo), db=db)
    logger.info(
        f"[Telemetria][Tenant {tenant_id[:8]}] Estado alterado para: {'ATIVO' if novo_estado else 'PAUSADO'}"
    )
    return {
        "active": novo_estado,
        "interval_seconds": _intervalo_segundos,
    }


def _aplicar_pico_anomalo(ponto: MapPointModel, indices: List[int]) -> None:
    for idx in indices:
        if idx == 0:
            ponto.ph_map_point = 9.4 if random.random() < 0.5 else 5.2
        elif idx == 1:
            ponto.turbidity_map_point = 68.0
        elif idx == 2:
            ponto.volume_map_point = 4950.0
        else:
            ponto.contaminant_map_point = 3.6


def _processar_ponto_do_tenant(
    db: Session,
    tenant_id: str,
    ponto: MapPointModel,
    tenant_cfg: Optional[dict] = None,
) -> None:
    """Atualiza telemetria de um ponto específico mantendo todos os artefatos no mesmo `tenant_id`."""
    # 1. pH (Normal: 6.2 a 8.4 | Alvo ~7.2)
    ph_pull = (POINT_THRESHOLDS["ph"]["target"] - ponto.ph_map_point) * 0.15
    ph_noise = (random.random() - 0.5) * 0.25
    ponto.ph_map_point = round(min(9.5, max(5.0, ponto.ph_map_point + ph_pull + ph_noise)), 1)

    # 2. Turbidez (Normal: <= 30 NTU | Alvo ~22 NTU)
    turb_pull = (POINT_THRESHOLDS["turbidity"]["target"] - ponto.turbidity_map_point) * 0.15
    turb_noise = (random.random() - 0.48) * 3.5
    ponto.turbidity_map_point = round(min(75.0, max(8.0, ponto.turbidity_map_point + turb_pull + turb_noise)), 0)

    # 3. Volume (Normal: <= 3800 m³ | Alvo ~2800 m³)
    current_vol = getattr(ponto, "volume_map_point", 2800.0) or 2800.0
    vol_pull = (POINT_THRESHOLDS["volume"]["target"] - current_vol) * 0.12
    vol_noise = (random.random() - 0.48) * 60.0
    ponto.volume_map_point = round(min(5200.0, max(1500.0, current_vol + vol_pull + vol_noise)), 0)

    # 4. Contaminantes (Normal: <= 1.2 mg/L | Alvo ~0.6 mg/L)
    contam_pull = (POINT_THRESHOLDS["contaminant"]["target"] - ponto.contaminant_map_point) * 0.15
    contam_noise = (random.random() - 0.5) * 0.12
    ponto.contaminant_map_point = round(min(4.0, max(0.1, ponto.contaminant_map_point + contam_pull + contam_noise)), 1)

    # Ocorrência transitória rara (~7% de probabilidade: 1 parâmetro para atenção/médio ou 2 para crítico)
    if random.random() < 0.07:
        qtd_anomalias = 2 if random.random() < 0.35 else 1
        _aplicar_pico_anomalo(ponto, random.sample([0, 1, 2, 3], k=qtd_anomalias))

    avaliacao = evaluate_point_parameters(
        ph=ponto.ph_map_point,
        turbidity=ponto.turbidity_map_point,
        volume=ponto.volume_map_point,
        contaminant=ponto.contaminant_map_point,
    )
    novo_risco = avaliacao["risk"]
    agora_utc = utcnow()

    ponto.risk_map_point = novo_risco
    ponto.datetime_map_point_update = agora_utc

    registrar_snapshot_medicao_mapa(db=db, tenant_id=tenant_id, ponto=ponto, recorded_at=agora_utc)

    if novo_risco == "critical":
        detalhes = avaliacao["crit_details"]
        responsavel_nome = obter_responsavel_tenant(
            db=db,
            tenant_id=tenant_id,
            point_name=ponto.name_map_point,
            fallback="Responsável Local",
        )
        metricas_formatadas = (
            f"PH: {ponto.ph_map_point:.1f} | "
            f"TUR: {ponto.turbidity_map_point:.0f} NTU | "
            f"CONT: {ponto.contaminant_map_point:.1f} mg/L | "
            f"VOL: {ponto.volume_map_point:.0f} m³"
        )
        params_chips = [
            f"pH: {ponto.ph_map_point:.1f}",
            f"Turbidez: {ponto.turbidity_map_point:.0f} NTU",
            f"Contaminantes: {ponto.contaminant_map_point:.1f} mg/L",
            f"Volume: {ponto.volume_map_point:.0f} m³",
        ]
        mensagem_critica = (
            f"Múltiplos parâmetros acima do limite aceitável simultaneamente: {', '.join(detalhes)}"
        )

        nova_ocr, novo_alerta, _ = registrar_incidente_critico(
            db=db,
            tenant_id=tenant_id,
            occurrence_title=f"Nível Crítico — {ponto.name_map_point}",
            location_label=f"{ponto.code_map_point} - {ponto.name_map_point}",
            point_name=ponto.name_map_point,
            responsible=responsavel_nome,
            metrics_summary=metricas_formatadas,
            alert_message=mensagem_critica,
            params_chips=params_chips,
            recommendation=avaliacao["recommendation"],
            history_label="Alerta Crítico de Qualidade",
            history_description_prefix=f"Telemetria detectou {', '.join(detalhes)}.",
            id_reference=ponto.id_map_point,
            reference_type="map_point",
            created_by="Telemetria Automática",
            created_at=agora_utc,
        )

        logger.warning(
            f"[Telemetria][Tenant {tenant_id[:8]}] Alerta {novo_alerta.code_alert} e Ocorrência {nova_ocr.code_occurrence} gerados para {ponto.name_map_point}"
        )

        if tenant_cfg and tenant_cfg.get("email_alerts") and tenant_cfg.get("user_email"):
            logger.info(
                f"[Email Alert][Tenant {tenant_id[:8]}] Alerta Crítico {novo_alerta.code_alert} ({ponto.name_map_point}) disparado para: {tenant_cfg.get('user_email')}"
            )


def _executar_ciclo_telemetria_sync() -> None:
    """Executa um ciclo síncrono de atualização em thread de worker sem bloquear o event loop."""
    db = SessionLocal()
    try:
        todos_pontos = (
            db.query(MapPointModel)
            .filter(MapPointModel.tenant_id != "__legacy__")
            .all()
        )
        if not todos_pontos:
            return

        pontos_por_tenant: Dict[str, List[MapPointModel]] = {}
        for pt in todos_pontos:
            if pt.tenant_id:
                pontos_por_tenant.setdefault(pt.tenant_id, []).append(pt)

        # 1 única query em lote para carregar configurações de todos os tenants presentes
        configs_por_tenant = load_tenant_settings_batch(db, pontos_por_tenant.keys())

        houve_atualizacao = False
        for t_id, lista_pontos in pontos_por_tenant.items():
            cfg = configs_por_tenant.get(t_id, {})
            if not cfg.get("telemetry_active", True):
                continue
            ponto_escolhido = random.choice(lista_pontos)
            _processar_ponto_do_tenant(
                db=db,
                tenant_id=t_id,
                ponto=ponto_escolhido,
                tenant_cfg=cfg,
            )
            houve_atualizacao = True

        if houve_atualizacao:
            db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"[Telemetria] Erro no ciclo de telemetria: {exc}")
    finally:
        db.close()


async def servico_telemetria_tempo_real() -> None:
    """Serviço assíncrono em background que delega I/O de banco ao threadpool."""
    logger.info("[Telemetria] Serviço autônomo multitenant em background iniciado com sucesso.")
    while True:
        try:
            await asyncio.sleep(_intervalo_segundos)
            await asyncio.to_thread(_executar_ciclo_telemetria_sync)
        except asyncio.CancelledError:
            logger.info("[Telemetria] Serviço assíncrono cancelado.")
            break
        except Exception as exc:
            logger.error(f"[Telemetria] Erro inesperado: {exc}")
            await asyncio.sleep(2)
