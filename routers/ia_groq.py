"""
Router de IA integrada com Groq (Llama 3.3) — Plataforma Cana
Rotas de Simulação Preditiva e Análise Diária da Plataforma com Cache
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
import asyncio
import json
import logging

from database import (
    get_db,
    SessionLocal,
    AIDailyAnalysisModel,
    OccurrenceModel,
    MapPointModel,
    HistoryEventModel,
    AppUserModel,
    Base,
    engine
)
from schemas import (
    AISimulationRequest,
    AISimulationResponse,
    AIDailyAnalysisResponse
)
from services.groq_client import call_groq_chat, SYSTEM_PROMPT, get_groq_credentials

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Inteligência Artificial (Groq)"])

def executar_e_persistir_analise_diaria(db: Session, forcar_atualizacao: bool = False) -> dict:
    """
    Função síncrona reutilizável que consulta o banco, monta o prompt com os dados consolidados,
    solicita a análise do Groq e grava/atualiza o registro na tabela AI_Daily_Analysis.
    """
    hoje = date.today()
    hoje_str = hoje.isoformat()
    _, model = get_groq_credentials()

    # 1. Verifica se já existe cache do dia de hoje no banco
    try:
        registro_cache = db.query(AIDailyAnalysisModel).filter(AIDailyAnalysisModel.analysis_date == hoje).first()
        if registro_cache and not forcar_atualizacao:
            dados_salvos = json.loads(registro_cache.analysis_json)
            dados_salvos["from_cache"] = True
            return dados_salvos
    except Exception as e:
        try:
            Base.metadata.create_all(bind=engine)
        except Exception:
            pass

    # 2. Coleta dados reais consolidados da plataforma para contexto
    dados_contexto = {
        "ocorrencias_ativas": [],
        "pontos_criticos": [],
        "total_pontos": 0,
        "ultimos_eventos": []
    }

    try:
        ocorrencias = db.query(OccurrenceModel).all()
        dados_contexto["ocorrencias_ativas"] = [
            f"{o.code_occurrence or 'OCR'}: {o.title_occurrence} ({o.location_occurrence}, risco {o.risk_occurrence}, status {o.status_occurrence})"
            for o in ocorrencias if o.status_occurrence != "encerradas"
        ]

        pontos = db.query(MapPointModel).all()
        dados_contexto["total_pontos"] = len(pontos)
        dados_contexto["pontos_criticos"] = [
            f"{p.name_map_point} (pH {p.ph_map_point}, Turbidez {p.turbidity_map_point} NTU, Risco {p.risk_map_point})"
            for p in pontos if p.risk_map_point in ["critical", "medium"]
        ]

        eventos = db.query(HistoryEventModel).order_by(HistoryEventModel.datetime_history.desc()).limit(10).all()
        dados_contexto["ultimos_eventos"] = [
            f"[{e.event_type.upper()}] {e.event_point}: {e.event_description}"
            for e in eventos
        ]
    except Exception as db_err:
        logger.warning(f"Aviso ao consultar dados consolidados para IA: {db_err}")

    prompt_analise = f"""Realize a ANÁLISE GERAL DIÁRIA da plataforma de tratamento de água e efluentes canavieiros para a data de {hoje_str}.
Contexto real consolidado da plataforma neste momento:
- Total de pontos de monitoramento: {dados_contexto['total_pontos']}
- Pontos com atenção ou críticos: {json.dumps(dados_contexto['pontos_criticos'], ensure_ascii=False)}
- Ocorrências ativas em andamento: {json.dumps(dados_contexto['ocorrencias_ativas'], ensure_ascii=False)}
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
        {"role": "user", "content": prompt_analise}
    ]

    resultado = call_groq_chat(messages, temperature=0.2)
    agora_iso = datetime.now().strftime("%d/%m/%Y às %H:%M")

    resposta_final = {
        "analysis_date": hoje_str,
        "analysis_text": resultado.get("analysis_text", "Monitoramento diário consolidado da usina."),
        "stress_probability": resultado.get("stress_probability", "50.0%"),
        "confidence_index": resultado.get("confidence_index", "90.0%"),
        "variables": resultado.get("variables", []),
        "recommended_action_title": resultado.get("recommended_action_title", "Ação Recomendada"),
        "recommended_action_desc": resultado.get("recommended_action_desc", "Manter rotina padrão de inspeção."),
        "from_cache": False,
        "generated_at": agora_iso,
        "model_used": model
    }

    # 3. Salva no banco de dados para reutilização nas próximas requisições do mesmo dia
    try:
        registro_existente = db.query(AIDailyAnalysisModel).filter(AIDailyAnalysisModel.analysis_date == hoje).first()
        if registro_existente:
            registro_existente.analysis_json = json.dumps(resposta_final, ensure_ascii=False)
        else:
            novo_registro = AIDailyAnalysisModel(
                analysis_date=hoje,
                analysis_json=json.dumps(resposta_final, ensure_ascii=False)
            )
            db.add(novo_registro)
        db.commit()
    except Exception as cache_err:
        logger.warning(f"Não foi possível persistir cache da IA no banco: {cache_err}")

    return resposta_final


async def rotina_agendamento_analise_7h():
    """
    Rotina assíncrona em background para executar a análise diária automaticamente
    todos os dias pontualmente às 07:00 da manhã.
    """
    logger.info("⏰ Rotina diária de análise com IA às 07:00 inicializada em background.")
    while True:
        try:
            agora = datetime.now()
            # Alvo: hoje às 07:00
            alvo_hoje = datetime.combine(agora.date(), time(7, 0, 0))

            if agora >= alvo_hoje:
                # Se já passou das 07:00 hoje, o próximo alvo é amanhã às 07:00
                proxima_execucao = alvo_hoje + timedelta(days=1)
            else:
                proxima_execucao = alvo_hoje

            segundos_espera = (proxima_execucao - agora).total_seconds()
            logger.info(f"⏳ Próxima análise diária automática agendada para: {proxima_execucao.strftime('%d/%m/%Y %H:%M:%S')} (em {int(segundos_espera)}s)")

            await asyncio.sleep(segundos_espera)

            # Executa a análise das 7h
            logger.info("☀️ Executando análise diária automática das 07:00...")
            db = SessionLocal()
            try:
                executar_e_persistir_analise_diaria(db, forcar_atualizacao=True)
                logger.info("✅ Análise diária das 07:00 concluída e persistida com sucesso no banco!")
            except Exception as run_err:
                logger.error(f"❌ Falha ao executar análise diária agendada das 07:00: {run_err}")
            finally:
                db.close()

            # Pequena pausa de 60s para evitar disparo duplo no mesmo minuto
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logger.info("🛑 Rotina de agendamento das 07:00 finalizada.")
            break
        except Exception as e:
            logger.error(f"Erro inesperado na rotina diária das 07:00: {e}")
            await asyncio.sleep(60)


@router.post("/simulacao", response_model=AISimulationResponse, summary="Avaliação de simulação preditiva com IA Groq")
def avaliar_simulacao_ia(dados: AISimulationRequest):
    """
    Recebe os parâmetros ajustados na tela de simulação (sliders) e solicita ao Groq
    uma análise técnica aprofundada no contexto da cana-de-açúcar.
    """
    _, model = get_groq_credentials()

    prompt_usuario = f"""Avalie a seguinte simulação de parâmetros de efluente hídrico na usina:
- pH: {dados.ph:.1f} (Limite: 9.0)
- Turbidez: {dados.turbidity:.0f} NTU (Limite: 50 NTU)
- Volume de Efluentes: {dados.volume:.0f} m³ (Limite: 4000 m³)
- Contaminantes: {dados.contaminants:.1f} mg/L (Limite: 3.0 mg/L)
- Previsão de Chuva Intensa: {"SIM (Risco aumentado de lixiviação e transbordo)" if dados.rain else "NÃO"}
- Pontuação de risco pré-calculada pelo frontend: {dados.calculated_score if dados.calculated_score is not None else "Não informado"}
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
        {"role": "user", "content": prompt_usuario}
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
            model_used=model
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Erro ao processar simulação na IA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha na comunicação com o Groq: {str(e)}"
        )


@router.get("/analise-diaria", response_model=AIDailyAnalysisResponse, summary="Análise diária geral da plataforma (1x ao dia)")
def obter_analise_diaria(forcar_atualizacao: bool = False, db: Session = Depends(get_db)):
    """
    Retorna a análise da IA sobre o estado consolidado da plataforma.
    Para economizar tokens, a avaliação é realizada apenas UMA vez ao dia e salva em cache no banco.
    """
    try:
        resultado = executar_e_persistir_analise_diaria(db, forcar_atualizacao=forcar_atualizacao)
        return AIDailyAnalysisResponse(**resultado)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Erro ao processar análise diária no Groq: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha na comunicação com o Groq: {str(e)}"
        )

