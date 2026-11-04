import asyncio
import random
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from database import (
    SessionLocal,
    MapPointModel,
    MapMeasurementHistoryModel,
    HistoryEventModel,
    OccurrenceModel,
    AlertModel,
    AppUserModel,
    TenantSettingsModel,
)

logger = logging.getLogger(__name__)

# Estado em memória isolado por tenant_id (ativo por padrão para cada tenant)
_telemetria_por_tenant: Dict[str, bool] = {}
_intervalo_segundos: int = 4


def _ler_status_tenant(tenant_id: str, db: Optional[Session] = None) -> bool:
    if db is not None:
        try:
            cfg = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
            if cfg is not None:
                ativo = bool(cfg.telemetry_active)
                _telemetria_por_tenant[tenant_id] = ativo
                return ativo
        except Exception:
            pass
    return _telemetria_por_tenant.get(tenant_id, True)


def obter_status_telemetria(tenant_id: str, db: Optional[Session] = None) -> dict:
    """Retorna o status atual do serviço de telemetria autônoma exclusivo para o tenant."""
    ativo = _ler_status_tenant(tenant_id, db=db)
    return {
        "active": ativo,
        "interval_seconds": _intervalo_segundos,
    }


def definir_status_telemetria(ativo: bool, tenant_id: str, db: Optional[Session] = None) -> dict:
    """Ativa ou desativa a telemetria autônoma exclusivamente para o tenant autenticado."""
    _telemetria_por_tenant[tenant_id] = bool(ativo)
    if db is not None:
        try:
            cfg = db.query(TenantSettingsModel).filter(TenantSettingsModel.tenant_id == tenant_id).first()
            if not cfg:
                cfg = TenantSettingsModel(
                    tenant_id=tenant_id,
                    telemetry_active=1 if ativo else 0,
                )
                db.add(cfg)
            else:
                cfg.telemetry_active = 1 if ativo else 0
            db.commit()
        except Exception:
            db.rollback()

    logger.info(
        f"📡 [Telemetria][Tenant {tenant_id[:8]}] Estado alterado para: {'ATIVO' if ativo else 'PAUSADO'}"
    )
    return obter_status_telemetria(tenant_id=tenant_id, db=db)


def _obter_responsavel_do_tenant(db: Session, tenant_id: str, ponto: MapPointModel) -> str:
    """Busca o responsável cadastrado no próprio tenant para este ponto (sem vazar nomes de outros tenants)."""
    try:
        usuario_ponto = (
            db.query(AppUserModel)
            .filter(
                AppUserModel.tenant_id == tenant_id,
                AppUserModel.status_user == "active",
                AppUserModel.responsible_point_user == ponto.name_map_point,
            )
            .first()
        )
        if usuario_ponto and usuario_ponto.name_user:
            return usuario_ponto.name_user

        qualquer_usuario = (
            db.query(AppUserModel)
            .filter(
                AppUserModel.tenant_id == tenant_id,
                AppUserModel.status_user == "active",
            )
            .first()
        )
        if qualquer_usuario and qualquer_usuario.name_user:
            return qualquer_usuario.name_user
    except Exception:
        pass
    return "Responsável Local"


def _processar_ponto_do_tenant(db: Session, tenant_id: str, ponto: MapPointModel) -> None:
    """Atualiza telemetria de um ponto específico mantendo todos os artefatos estritamente no mesmo tenant_id."""
    # Micro-oscilações realistas gravitando em torno de níveis seguros
    # 1. pH (Normal: 6.2 a 8.4 | Alvo ~7.2)
    target_ph = 7.2
    ph_pull = (target_ph - ponto.ph_map_point) * 0.15
    ph_noise = (random.random() - 0.5) * 0.25
    ponto.ph_map_point = round(min(9.5, max(5.0, ponto.ph_map_point + ph_pull + ph_noise)), 1)

    # 2. Turbidez (Normal: <= 30 NTU | Alvo ~22 NTU)
    target_turb = 22.0
    turb_pull = (target_turb - ponto.turbidity_map_point) * 0.15
    turb_noise = (random.random() - 0.48) * 3.5
    ponto.turbidity_map_point = round(min(75.0, max(8.0, ponto.turbidity_map_point + turb_pull + turb_noise)), 0)

    # 3. Volume (Normal: <= 3800 m³ | Alvo ~2800 m³)
    current_vol = getattr(ponto, "volume_map_point", 2800.0) or 2800.0
    target_vol = 2800.0
    vol_pull = (target_vol - current_vol) * 0.12
    vol_noise = (random.random() - 0.48) * 60.0
    ponto.volume_map_point = round(min(5200.0, max(1500.0, current_vol + vol_pull + vol_noise)), 0)

    # 4. Contaminantes (Normal: <= 1.2 mg/L | Alvo ~0.6 mg/L)
    target_contam = 0.6
    contam_pull = (target_contam - ponto.contaminant_map_point) * 0.15
    contam_noise = (random.random() - 0.5) * 0.12
    ponto.contaminant_map_point = round(min(4.0, max(0.1, ponto.contaminant_map_point + contam_pull + contam_noise)), 1)

    # Ocorrência transitória rara (~7% de probabilidade de pico anômalo)
    eh_pico_anomalo = random.random() < 0.07
    if eh_pico_anomalo:
        tipo_anomalia = random.randint(0, 3)
        if tipo_anomalia == 0:
            ponto.ph_map_point = 9.3 if random.random() < 0.5 else 5.2
        elif tipo_anomalia == 1:
            ponto.turbidity_map_point = 68.0
        elif tipo_anomalia == 2:
            ponto.volume_map_point = 4950.0
        else:
            ponto.contaminant_map_point = 3.6

    # Determina severidades
    ph_crit = ponto.ph_map_point < 5.5 or ponto.ph_map_point > 9.2
    turb_crit = ponto.turbidity_map_point > 60.0
    vol_crit = ponto.volume_map_point > 4800.0
    contam_crit = ponto.contaminant_map_point > 3.2

    crit_count = sum([ph_crit, turb_crit, vol_crit, contam_crit])
    warn_count = sum([
        5.5 <= ponto.ph_map_point < 6.2 or 8.4 < ponto.ph_map_point <= 9.2,
        30.0 < ponto.turbidity_map_point <= 60.0,
        3800.0 < ponto.volume_map_point <= 4800.0,
        1.2 < ponto.contaminant_map_point <= 3.2,
    ])

    # Classificação de Risco
    if crit_count >= 2:
        novo_risco = "critical"
    elif crit_count == 1 or warn_count >= 2:
        novo_risco = "medium"
    else:
        novo_risco = "low"

    ponto.risk_map_point = novo_risco
    agora_utc = datetime.utcnow()
    ponto.datetime_map_point_update = agora_utc

    # Salva medição no histórico de medições isolado por tenant_id
    hist_medicao = MapMeasurementHistoryModel(
        tenant_id=tenant_id,
        code_map_point=ponto.code_map_point,
        name_map_point=ponto.name_map_point,
        ph=ponto.ph_map_point,
        turbidity=ponto.turbidity_map_point,
        contaminant=ponto.contaminant_map_point,
        volume=ponto.volume_map_point,
        risk=novo_risco,
        recorded_at=agora_utc,
    )
    db.add(hist_medicao)

    # GERAÇÃO DE OCORRÊNCIA, ALERTA E HISTÓRICO SE O RISCO FOR CRÍTICO (no mesmo tenant_id)
    if novo_risco == "critical":
        detalhes = []
        if ph_crit:
            detalhes.append(f"pH {ponto.ph_map_point:.1f}")
        if turb_crit:
            detalhes.append(f"Turbidez {ponto.turbidity_map_point:.0f} NTU")
        if contam_crit:
            detalhes.append(f"Contaminantes {ponto.contaminant_map_point:.1f} mg/L")
        if vol_crit:
            detalhes.append(f"Volume {ponto.volume_map_point:.0f} m³")

        if not detalhes:
            detalhes.append("Parâmetros anômalos detectados")

        responsavel_nome = _obter_responsavel_do_tenant(db, tenant_id, ponto)

        # 1. Cria a Ocorrência formal no banco vinculada ao tenant_id
        codigo_ocr = f"OCR-{random.randint(1000, 9999)}"
        metricas_formatadas = (
            f"PH: {ponto.ph_map_point:.1f} | "
            f"TUR: {ponto.turbidity_map_point:.0f} NTU | "
            f"CONT: {ponto.contaminant_map_point:.1f} mg/L | "
            f"VOL: {ponto.volume_map_point:.0f} m³"
        )

        nova_ocorrencia = OccurrenceModel(
            tenant_id=tenant_id,
            code_occurrence=codigo_ocr,
            title_occurrence=f"Nível Crítico — {ponto.name_map_point}",
            location_occurrence=f"{ponto.code_map_point} - {ponto.name_map_point}",
            responsible_occurrence=responsavel_nome,
            metrics_occurrence=metricas_formatadas,
            status_occurrence="analise",
            risk_occurrence="critico",
            datetime_occurrence_creation=agora_utc,
        )
        db.add(nova_ocorrencia)
        db.flush()

        # 2. Recomendação operacional contextualizada
        if contam_crit:
            recomendacao = "Interromper descarte de efluentes imediatamente e acionar equipe de campo para estancar vazamento."
        elif ph_crit:
            recomendacao = "Ajustar dosagem de neutralização química e calibrar sondas de monitoramento."
        elif turb_crit:
            recomendacao = "Acionar bacias de decantação suplementares e inspecionar filtros de retenção."
        else:
            recomendacao = "Inspecionar comportas de vazão e reforçar barreiras de contenção operacional."

        mensagem_critica = (
            f"Múltiplos parâmetros acima do limite aceitável simultaneamente: {', '.join(detalhes)}"
            if len(detalhes) > 1
            else f"Parâmetro anômalo com risco crítico detectado: {detalhes[0]}"
        )

        params_chips = [
            f"pH: {ponto.ph_map_point:.1f}",
            f"Turbidez: {ponto.turbidity_map_point:.0f} NTU",
            f"Contaminantes: {ponto.contaminant_map_point:.1f} mg/L",
            f"Volume: {ponto.volume_map_point:.0f} m³",
        ]

        # 3. Cria o Alerta vinculado exclusivamente a este tenant_id
        codigo_alerta = f"AL-{random.randint(100, 999)}"
        novo_alerta = AlertModel(
            tenant_id=tenant_id,
            code_alert=codigo_alerta,
            point_name=ponto.name_map_point,
            severity="critical",
            status="active",
            message=mensagem_critica,
            params_json=json.dumps(params_chips),
            recommendation=recomendacao,
            responsible=responsavel_nome,
            id_occurrence=nova_ocorrencia.id_occurrence,
            code_occurrence=nova_ocorrencia.code_occurrence,
            is_viewed=0,
            datetime_alert=agora_utc,
        )
        db.add(novo_alerta)

        # 4. Registra evento na timeline do Histórico deste tenant_id
        evento_alerta = HistoryEventModel(
            tenant_id=tenant_id,
            event_type="alerta",
            event_label="Alerta Crítico de Qualidade",
            event_point=f"{ponto.code_map_point} - {ponto.name_map_point}",
            event_description=f"Telemetria detectou {', '.join(detalhes)}. Ocorrência #{codigo_ocr} e Alerta #{codigo_alerta} gerados.",
            event_severity="critico",
            id_reference=ponto.id_map_point,
            reference_type="map_point",
            created_by="Telemetria Automática",
            datetime_history=agora_utc,
        )
        db.add(evento_alerta)
        logger.warning(
            f"🚨 [Telemetria][Tenant {tenant_id[:8]}] Alerta Crítico {codigo_alerta} e Ocorrência {codigo_ocr} gerados para {ponto.name_map_point}"
        )

        try:
            from routers.alertas import obter_config_notificacoes_do_tenant
            cfg_notif = obter_config_notificacoes_do_tenant(tenant_id=tenant_id, db=db)
            if cfg_notif.get("email_alerts") and cfg_notif.get("user_email"):
                logger.info(
                    f"📧 [Email Alert][Tenant {tenant_id[:8]}] Alerta Crítico {codigo_alerta} ({ponto.name_map_point}) disparado para: {cfg_notif.get('user_email')}"
                )
        except Exception as err:
            logger.debug(f"[Telemetria] Notificação por e-mail: {err}")


async def servico_telemetria_tempo_real():
    """
    Serviço assíncrono em background executado continuamente no FastAPI.
    Opera de maneira isolada por tenant_id: respeita o status ativo/pausado de cada conta
    e propaga o tenant_id em todas as medições, ocorrências, alertas e eventos gerados.
    """
    logger.info("🛰️ [Telemetria] Serviço autônomo multitenant em background iniciado com sucesso.")

    while True:
        try:
            await asyncio.sleep(_intervalo_segundos)

            db = SessionLocal()
            try:
                todos_pontos = (
                    db.query(MapPointModel)
                    .filter(MapPointModel.tenant_id != "__legacy__")
                    .all()
                )
                if not todos_pontos:
                    continue

                pontos_por_tenant: Dict[str, List[MapPointModel]] = {}
                for pt in todos_pontos:
                    if pt.tenant_id:
                        pontos_por_tenant.setdefault(pt.tenant_id, []).append(pt)

                houve_atualizacao = False
                for t_id, lista_pontos in pontos_por_tenant.items():
                    if not _ler_status_tenant(t_id, db=db):
                        continue
                    ponto_escolhido = random.choice(lista_pontos)
                    _processar_ponto_do_tenant(db=db, tenant_id=t_id, ponto=ponto_escolhido)
                    houve_atualizacao = True

                if houve_atualizacao:
                    db.commit()

            except Exception as e:
                db.rollback()
                logger.error(f"❌ [Telemetria] Erro no ciclo de telemetria: {e}")
            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("🛑 [Telemetria] Serviço assíncrono cancelado.")
            break
        except Exception as e:
            logger.error(f"❌ [Telemetria] Erro inesperado: {e}")
            await asyncio.sleep(2)
