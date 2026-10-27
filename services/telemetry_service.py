import asyncio
import random
import logging
from datetime import datetime

from database import SessionLocal, MapPointModel, MapMeasurementHistoryModel, HistoryEventModel

logger = logging.getLogger(__name__)

# Estado global da telemetria (ativo por padrão)
_telemetria_ativa: bool = True
_intervalo_segundos: int = 4

def obter_status_telemetria() -> dict:
    """Retorna o status atual do serviço de telemetria autônoma."""
    return {
        "active": _telemetria_ativa,
        "interval_seconds": _intervalo_segundos
    }

def definir_status_telemetria(ativo: bool) -> dict:
    """Ativa ou desativa a telemetria autônoma no servidor."""
    global _telemetria_ativa
    _telemetria_ativa = ativo
    logger.info(f"📡 [Telemetria] Estado alterado para: {'ATIVO' if ativo else 'PAUSADO'}")
    return obter_status_telemetria()

async def servico_telemetria_tempo_real():
    """
    Serviço assíncrono em background executado continuamente no FastAPI.
    Opera mesmo se nenhum usuário estiver conectado à plataforma.
    A cada ciclo, atualiza um ponto de monitoramento e, em caso de leitura crítica,
    registra automaticamente um evento na timeline de Histórico (History_Event).
    """
    logger.info("🛰️ [Telemetria] Serviço autônomo em background iniciado com sucesso.")

    while True:
        try:
            await asyncio.sleep(_intervalo_segundos)

            if not _telemetria_ativa:
                continue

            db = SessionLocal()
            try:
                pontos = db.query(MapPointModel).all()
                if not pontos:
                    continue

                # Seleciona aleatoriamente um ponto cadastrado
                ponto = random.choice(pontos)

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

                # Ocorrência transitória rara (~5% de probabilidade de pico crítico)
                eh_pico_anomalo = random.random() < 0.05
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
                    1.2 < ponto.contaminant_map_point <= 3.2
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

                # Salva medição no histórico de medições para gráficos
                hist_medicao = MapMeasurementHistoryModel(
                    code_map_point=ponto.code_map_point,
                    name_map_point=ponto.name_map_point,
                    ph=ponto.ph_map_point,
                    turbidity=ponto.turbidity_map_point,
                    contaminant=ponto.contaminant_map_point,
                    volume=ponto.volume_map_point,
                    risk=novo_risco,
                    recorded_at=agora_utc
                )
                db.add(hist_medicao)

                # ATUALIZAÇÃO DA TIMELINE DO HISTÓRICO SE HOUVER ATUALIZAÇÃO CRÍTICA
                if novo_risco == "critical" or crit_count > 0:
                    detalhes = []
                    if ph_crit:
                        detalhes.append(f"pH {ponto.ph_map_point:.1f}")
                    if turb_crit:
                        detalhes.append(f"Turbidez {ponto.turbidity_map_point:.0f} NTU")
                    if contam_crit:
                        detalhes.append(f"Contaminantes {ponto.contaminant_map_point:.1f} mg/L")
                    if vol_crit:
                        detalhes.append(f"Volume {ponto.volume_map_point:.0f} m³")

                    descricao_alerta = (
                        f"Telemetria detectou parâmetros críticos no ponto {ponto.name_map_point}: "
                        f"{', '.join(detalhes)}. Classificado com Risco Crítico."
                    )

                    evento_alerta = HistoryEventModel(
                        event_type="alerta",
                        event_label="Alerta Crítico de Qualidade",
                        event_point=f"{ponto.code_map_point} - {ponto.name_map_point}",
                        event_description=descricao_alerta,
                        event_severity="critico",
                        id_reference=ponto.id_map_point,
                        reference_type="map_point",
                        created_by="Telemetria Automática",
                        datetime_history=agora_utc
                    )
                    db.add(evento_alerta)
                    logger.warning(f"🚨 [Telemetria] Alerta Crítico registrado na timeline do Histórico para {ponto.code_map_point}")

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
