from fastapi import APIRouter, HTTPException
from schemas import DadosAgua
import pandas as pd
import joblib
import logging
import os

logger = logging.getLogger(__name__)

# Cria o agrupador de rotas para a IA
router = APIRouter(tags=["Inteligência Artificial"])

# Ajustando o caminho para encontrar o modelo dentro da pasta 'ia'
caminho_modelo = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'IA', 'modelo_qualidade_agua.pkl')

try:
    modelo_ia = joblib.load(caminho_modelo)
    logger.info("✅ Modelo de Inteligência Artificial carregado com sucesso pelo Router!")
except Exception as e:
    logger.warning(f"⚠️ Aviso: Modelo de IA não encontrado em {caminho_modelo}. Detalhe: {e}")
    modelo_ia = None

@router.post("/prever-qualidade-agua", summary="Prever qualidade da água com IA")
def prever_agua(dados: DadosAgua):
    if modelo_ia is None:
        raise HTTPException(status_code=500, detail="Modelo de IA não carregado no servidor.")
    
    valores = pd.DataFrame([{
        'pH': dados.ph,
        'Temperatura_C': dados.temperatura_c,
        'DBO_mgL': dados.dbo_mgl,
        'Turbidez_NTU': dados.turbidez_ntu
    }])
    
    resultado_ia = modelo_ia.predict(valores)
    
    status_agua = "Própria" if resultado_ia[0] == 1 else "Poluída (Risco de Efluentes)"
    
    return {
        "status_agua": status_agua,
        "dados_analisados": dados
    }