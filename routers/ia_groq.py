"""
Router de IA integrada com Groq — Plataforma Cana
Rotas de Simulação Preditiva e Análise Diária da Plataforma com Cache isolado por Tenant
"""

import asyncio
from datetime import datetime, time, timedelta
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth_tenant import get_current_tenant
from database import (
    AIDailyAnalysisModel,
    HistoryEventModel,
    MapPointModel,
    OccurrenceModel,
    SessionLocal,
    get_db,
)
from routers.ciclo_hidrico import calcular_resumo_ciclo_hidrico
from schemas import (
    AIDailyAnalysisResponse,
    AISimulationRequest,
    AISimulationResponse,
)
from services.groq_client import SYSTEM_PROMPT, call_groq_chat, get_groq_credentials
from services.water_quality_service import sao_paulo_now

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Inteligência Artificial (Groq)"])


def _sanitize_for_llm(value: str | None, max_len: int = 160) -> str:
    """
    Sanitiza strings de banco antes de enviá-las à API externa da Groq:
    - Mitiga Indirect Prompt Injection removendo quebras de linha e tags.
    - Garante conformidade LGPD (Art. 33) mascarando e-mails e nomes de colaboradores.
    """
    if not value:
        return ""
    cleaned = re.sub(r"[\r\n\t]+", " ", str(value))
    cleaned = re.sub(r"[<>]", "", cleaned)
    cleaned = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL_PROTEGIDO]", cleaned)
    cleaned = re.sub(r"criada por [^:]+:", "criada por [OPERADOR]:", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"por [A-Za-zÀ-ÿ\s]{2,40}\.", "por [OPERADOR].", cleaned)
    return cleaned[:max_len].strip()


def executar_e_persistir_analise_diaria(
    db: Session,
    tenant_id: str,
    forcar_atualizacao: bool = False,
) -> dict:
    """
    Consulta exclusivamente os dados pertencentes ao `tenant_id`, monta o prompt consolidado,
    solicita a análise do Groq e grava/atualiza o cache diário isolado por `(tenant_id, analysis_date)`.
    """
    agora_sp = sao_paulo_now()
    hoje = agora_sp.date()
    hoje_str = hoje.isoformat()
    _, model = get_groq_credentials()

    if not forcar_atualizacao:
        registro_cache = (
            db.query(AIDailyAnalysisModel)
            .filter(
                AIDailyAnalysisModel.tenant_id == tenant_id,
                AIDailyAnalysisModel.analysis_date == hoje,
            )
            .first()
        )
        if registro_cache:
            dados_salvos = json.loads(registro_cache.analysis_json)
            dados_salvos["from_cache"] = True
            return dados_salvos

    dados_contexto = {
        "ocorrencias_ativas": [],
        "pontos_criticos": [],
        "total_pontos": 0,
        "ultimos_eventos": [],
        "balanco_ciclo_hidrico": {},
    }

    try:
        ocorrencias = (
            db.query(OccurrenceModel)
            .filter(
                OccurrenceModel.tenant_id == tenant_id,
                OccurrenceModel.status_occurrence != "encerradas",
            )
            .all()
        )
        dados_contexto["ocorrencias_ativas"] = [
            f"{_sanitize_for_llm(o.code_occurrence or 'OCR', 20)}: "
            f"{_sanitize_for_llm(o.title_occurrence, 100)} "
            f"({_sanitize_for_llm(o.location_occurrence, 80)}, risco {_sanitize_for_llm(o.risk_occurrence, 20)}, "
            f"status {_sanitize_for_llm(o.status_occurrence, 20)})"
            for o in ocorrencias
        ]

        pontos = (
            db.query(MapPointModel)
            .filter(MapPointModel.tenant_id == tenant_id)
            .all()
        )
        dados_contexto["total_pontos"] = len(pontos)
        dados_contexto["pontos_criticos"] = [
            f"{_sanitize_for_llm(p.name_map_point, 80)} (pH {p.ph_map_point}, Turbidez {p.turbidity_map_point} NTU, Risco {_sanitize_for_llm(p.risk_map_point, 20)})"
            for p in pontos
            if p.risk_map_point in ("critical", "medium")
        ]

        eventos = (
            db.query(HistoryEventModel)
            .filter(HistoryEventModel.tenant_id == tenant_id)
            .order_by(HistoryEventModel.datetime_history.desc())
            .limit(10)
            .all()
        )
        dados_contexto["ultimos_eventos"] = [
            f"[{_sanitize_for_llm(e.event_type, 20).upper()}] {_sanitize_for_llm(e.event_point, 80)}: {_sanitize_for_llm(e.event_description, 160)}"
            for e in eventos
        ]

        dados_contexto["balanco_ciclo_hidrico"] = calcular_resumo_ciclo_hidrico(db=db, tenant_id=tenant_id)
    except Exception as db_err:
        logger.warning(f"Aviso ao consultar dados consolidados para IA do tenant {tenant_id[:8]}: {db_err}")

    prompt_analise = f"""Realize a ANÁLISE GERAL DIÁRIA da plataforma de tratamento de água e efluentes canavieiros para a data de {hoje_str}.
Contexto real consolidado da unidade deste usuário neste momento:
- Total de pontos de monitoramento cadastrados: {dados_contexto['total_pontos']}
- Pontos com atenção ou críticos: {json.dumps(dados_contexto['pontos_criticos'], ensure_ascii=False)}
- Ocorrências ativas em andamento: {json.dumps(dados_contexto['ocorrencias_ativas'], ensure_ascii=False)}
- Balanço hídrico operacional e laudos laboratoriais (Admissão/Armazenamento/Descarte/CONAMA): {json.dumps(dados_contexto['balanco_ciclo_hidrico'], ensure_ascii=False)}
- Últimos eventos registrados no histórico: {json.dumps(dados_contexto['ultimos_eventos'], ensure_ascii=False)}

Gere um JSON rigoroso com a seguinte estrutura para preencher o card de análise da tela principal:
{{
  "analysis_text": "Texto executivo e técnico (2 a 3 frases) sintetizando a saúde hídrica da usina hoje, destacando eventuais pontos que exigem ação preventiva ou corretiva imediata na cana-de-açúcar.",
  "stress_probability": "Porcentagem estimada de probabilidade de estresse ambiental/hídrico hoje (ex: '68.5%')",
  "confidence_index": "Índice de confiança da análise da IA hoje (ex: '94.2%')",
  "variables": [
    {{
      "name": "Déficit Hídrico do Solo (mm)",
      "status_label": "Crítico (78%)" | "Elevado (60%)" | "Estável (35%)",
      "percent": 78,
      "severity_class": "danger" | "warning" | "normal"
    }},
    {{
      "name": "Qualidade do Efluente Fertirrigado",
      "status_label": "Elevado (62%)" | "Controlado (40%)",
      "percent": 62,
      "severity_class": "warning"
    }},
    {{
      "name": "Índice de Dissolução de Oxigênio nos Mananciais",
      "status_label": "Estável (45%)",
      "percent": 45,
      "severity_class": "normal"
    }}
  ],
  "recommended_action_title": "Ação Recomendada Imediata",
  "recommended_action_desc": "Descrição clara e prática da principal medida a ser tomada pelos operadores e engenheiros hoje."
}}
"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_analise},
    ]

    resultado = call_groq_chat(messages, temperature=0.2)
    agora_fmt = sao_paulo_now().strftime("%d/%m/%Y às %H:%M")

    resposta_final = {
        "analysis_date": hoje_str,
        "analysis_text": resultado.get("analysis_text", "Monitoramento diário consolidado da usina."),
        "stress_probability": resultado.get("stress_probability", "50.0%"),
        "confidence_index": resultado.get("confidence_index", "90.0%"),
        "variables": resultado.get("variables", []),
        "recommended_action_title": resultado.get("recommended_action_title", "Ação Recomendada"),
        "recommended_action_desc": resultado.get("recommended_action_desc", "Manter rotina padrão de inspeção."),
        "from_cache": False,
        "generated_at": agora_fmt,
        "model_used": model,
    }

    try:
        registro_existente = (
            db.query(AIDailyAnalysisModel)
            .filter(
                AIDailyAnalysisModel.tenant_id == tenant_id,
                AIDailyAnalysisModel.analysis_date == hoje,
            )
            .first()
        )
        if registro_existente:
            registro_existente.analysis_json = json.dumps(resposta_final, ensure_ascii=False)
        else:
            db.add(
                AIDailyAnalysisModel(
                    tenant_id=tenant_id,
                    analysis_date=hoje,
                    analysis_json=json.dumps(resposta_final, ensure_ascii=False),
                )
            )
        db.commit()
    except Exception as cache_err:
        db.rollback()
        logger.warning(f"Não foi possível persistir cache da IA no banco: {cache_err}")

    return resposta_final


def _executar_lote_diario_7h_sync() -> None:
    """Roda o lote de análises diárias em thread dedicada sem bloquear o event loop."""
    db = SessionLocal()
    try:
        tenants_ativos = [
            row[0]
            for row in db.query(MapPointModel.tenant_id)
            .filter(MapPointModel.tenant_id != "__legacy__")
            .distinct()
            .all()
            if row[0]
        ]
        for t_id in tenants_ativos:
            try:
                executar_e_persistir_analise_diaria(db, tenant_id=t_id, forcar_atualizacao=True)
            except Exception as tenant_err:
                logger.error(f"Falha na análise diária das 07:00 para tenant {t_id[:8]}: {tenant_err}")
        logger.info(f"Análise diária das 07:00 processada para {len(tenants_ativos)} tenant(s)!")
    except Exception as run_err:
        logger.error(f"Falha ao executar análise diária agendada das 07:00: {run_err}")
    finally:
        db.close()


async def rotina_agendamento_analise_7h() -> None:
    """Agendamento diário às 07:00 (horário de São Paulo) sem bloqueio do event loop."""
    logger.info("Rotina diária multitenant de análise com IA às 07:00 inicializada em background.")
    while True:
        try:
            agora = sao_paulo_now()
            alvo_hoje = datetime.combine(agora.date(), time(7, 0, 0))
            proxima_execucao = alvo_hoje + timedelta(days=1) if agora >= alvo_hoje else alvo_hoje
            segundos_espera = max(1.0, (proxima_execucao - agora).total_seconds())

            logger.info(
                f"Próxima análise diária automática agendada para: {proxima_execucao.strftime('%d/%m/%Y %H:%M:%S')} (em {int(segundos_espera)}s)"
            )

            await asyncio.sleep(segundos_espera)
            logger.info("Executando análise diária automática das 07:00 por tenant...")
            await asyncio.to_thread(_executar_lote_diario_7h_sync)
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Rotina de agendamento das 07:00 finalizada.")
            break
        except Exception as exc:
            logger.error(f"Erro inesperado na rotina diária das 07:00: {exc}")
            await asyncio.sleep(60)


@router.post("/simulacao", response_model=AISimulationResponse, summary="Avaliação de simulação preditiva com IA Groq")
def avaliar_simulacao_ia(
    dados: AISimulationRequest,
    tenant_id: str = Depends(get_current_tenant),
):
    _, model = get_groq_credentials()

    prompt_usuario = f"""Avalie a seguinte simulação de parâmetros de efluente hídrico na usina:
- pH: {dados.ph:.1f} (Faixa normal: 6.2 a 8.4 | Crítico: < 5.5 ou > 9.2)
- Turbidez: {dados.turbidity:.0f} NTU (Normal: <= 30 NTU | Crítico: > 60 NTU)
- Volume de Efluentes: {dados.volume:.0f} m³ (Normal: <= 3.800 m³ | Crítico: > 4.800 m³)
- Contaminantes: {dados.contaminants:.1f} mg/L (Normal: <= 1.2 mg/L | Crítico: > 3.2 mg/L)
- Previsão de Chuva Intensa: {"SIM (Risco aumentado de lixiviação e transbordo)" if dados.rain else "NÃO"}
- Pontuação de risco pré-calculada pelo frontend (0 a 100): {dados.calculated_score if dados.calculated_score is not None else "Não informado"}
- Nível de risco pré-classificado: {dados.calculated_risk or "Não informado"}

Retorne um JSON estrito com esta estrutura:
{{
  "risk_level": "Baixo" | "Médio" | "Crítico",
  "risk_score_evaluation": "string curta explicando a gravidade da pontuação",
  "summary": "1 ou 2 parágrafos de síntese da simulação",
  "technical_considerations": "Análise técnica detalhada considerando os impactos na cultura de cana-de-açúcar, fertirrigação com vinhaça, bacia hidrográfica e solo",
  "recommendations": ["Recomendação técnica 1", "Recomendação técnica 2", "Recomendação técnica 3"],
  "alerts_suggested": ["Alerta operacional sugerido 1", "Alerta operacional sugerido 2"]
}}
"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt_usuario},
    ]

    try:
        resultado = call_groq_chat(messages, temperature=0.3)
        return AISimulationResponse(
            risk_level=resultado.get("risk_level", dados.calculated_risk or "Médio"),
            risk_score_evaluation=resultado.get("risk_score_evaluation", f"Score estimado: {dados.calculated_score}"),
            summary=resultado.get("summary", "Simulação processada com sucesso."),
            technical_considerations=resultado.get("technical_considerations", "Sem considerações adicionais."),
            recommendations=resultado.get("recommendations", ["Monitorar parâmetros"]),
            alerts_suggested=resultado.get("alerts_suggested", []),
            model_used=model,
        )
    except ValueError as ve:
        logger.warning(f"Erro de validação na simulação IA (tenant {tenant_id[:8]}): {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parâmetros inválidos ou serviço de IA não configurado.",
        )
    except Exception as exc:
        logger.error(f"Erro ao processar simulação na IA (tenant {tenant_id[:8]}): {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Serviço de inteligência artificial temporariamente indisponível. Tente novamente em instantes.",
        )


@router.get("/analise-diaria", response_model=AIDailyAnalysisResponse, summary="Análise diária geral da conta do usuário (1x ao dia)")
def obter_analise_diaria(
    forcar_atualizacao: bool = False,
    tenant_id: str = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    try:
        resultado = executar_e_persistir_analise_diaria(
            db,
            tenant_id=tenant_id,
            forcar_atualizacao=forcar_atualizacao,
        )
        return AIDailyAnalysisResponse(**resultado)
    except ValueError as ve:
        logger.warning(f"Erro de validação na análise diária IA (tenant {tenant_id[:8]}): {ve}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parâmetros inválidos ou serviço de IA não configurado.",
        )
    except Exception as exc:
        logger.error(f"Erro ao processar análise diária no Groq (tenant {tenant_id[:8]}): {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Serviço de inteligência artificial temporariamente indisponível. Tente novamente em instantes.",
        )
