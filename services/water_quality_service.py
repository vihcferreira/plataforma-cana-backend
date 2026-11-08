"""
Serviço centralizado de Qualidade da Água, Limiares Operacionais e Inferência ML — Plataforma Cana.
Fonte única da verdade para:
1. Utilitários de data/hora sem depreciações (UTC e America/Sao_Paulo).
2. Faixas operacionais e cálculo de risco dos pontos de monitoramento (alinhados ao README.md).
3. Conformidade CONAMA 430 e inferência vetorizada em lote com `modelo_qualidade_agua.pkl`.
"""

from datetime import datetime, timedelta, timezone
import logging
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple
import warnings

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

logger = logging.getLogger(__name__)

# ==========================================
# 1. UTILITÁRIOS DE DATA / FUSO HORÁRIO
# ==========================================
def utcnow() -> datetime:
    """Retorna datetime UTC naive compatível com colunas DATETIME MySQL/SQLite sem DeprecationWarning."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sao_paulo_now() -> datetime:
    """Retorna data/hora atual no fuso America/Sao_Paulo (com fallback UTC-3 caso tzdata não exista)."""
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)


# ==========================================
# 2. FAIXAS OPERACIONAIS OFICIAIS (README.md)
# ==========================================
POINT_THRESHOLDS = {
    "ph": {
        "normal_min": 6.2,
        "normal_max": 8.4,
        "crit_min": 5.5,
        "crit_max": 9.2,
        "target": 7.2,
    },
    "turbidity": {
        "normal_max": 30.0,
        "crit_max": 60.0,
        "target": 22.0,
    },
    "volume": {
        "normal_max": 3800.0,
        "crit_max": 4800.0,
        "target": 2800.0,
    },
    "contaminant": {
        "normal_max": 1.2,
        "crit_max": 3.2,
        "target": 0.6,
    },
}

CONAMA_THRESHOLDS = {
    "ph_min": 6.0,
    "ph_max": 9.0,
    "od_min": 4.0,
    "turbidity_max": 40.0,
    "bod_max": 60.0,
    "cod_max": 150.0,
}


def evaluate_point_parameters(
    ph: float,
    turbidity: float,
    volume: float,
    contaminant: float,
) -> Dict[str, Any]:
    """
    Classifica os 4 parâmetros operacionais de um Map_Point segundo as regras do README.md:
    - critical: crit_count >= 2
    - medium: crit_count == 1 ou warn_count >= 2
    - low: crit_count == 0 e warn_count <= 1
    """
    ph_val = float(ph)
    turb_val = float(turbidity)
    vol_val = float(volume)
    contam_val = float(contaminant)

    ph_crit = ph_val < POINT_THRESHOLDS["ph"]["crit_min"] or ph_val > POINT_THRESHOLDS["ph"]["crit_max"]
    turb_crit = turb_val > POINT_THRESHOLDS["turbidity"]["crit_max"]
    vol_crit = vol_val > POINT_THRESHOLDS["volume"]["crit_max"]
    contam_crit = contam_val > POINT_THRESHOLDS["contaminant"]["crit_max"]

    ph_warn = (
        POINT_THRESHOLDS["ph"]["crit_min"] <= ph_val < POINT_THRESHOLDS["ph"]["normal_min"]
        or POINT_THRESHOLDS["ph"]["normal_max"] < ph_val <= POINT_THRESHOLDS["ph"]["crit_max"]
    )
    turb_warn = POINT_THRESHOLDS["turbidity"]["normal_max"] < turb_val <= POINT_THRESHOLDS["turbidity"]["crit_max"]
    vol_warn = POINT_THRESHOLDS["volume"]["normal_max"] < vol_val <= POINT_THRESHOLDS["volume"]["crit_max"]
    contam_warn = (
        POINT_THRESHOLDS["contaminant"]["normal_max"] < contam_val <= POINT_THRESHOLDS["contaminant"]["crit_max"]
    )

    crit_count = sum((ph_crit, turb_crit, vol_crit, contam_crit))
    warn_count = sum((ph_warn, turb_warn, vol_warn, contam_warn))

    if crit_count >= 2:
        risk = "critical"
    elif crit_count == 1 or warn_count >= 2:
        risk = "medium"
    else:
        risk = "low"

    crit_details: List[str] = []
    if ph_crit:
        crit_details.append(f"pH {ph_val:.1f}")
    if turb_crit:
        crit_details.append(f"Turbidez {turb_val:.0f} NTU")
    if contam_crit:
        crit_details.append(f"Contaminantes {contam_val:.1f} mg/L")
    if vol_crit:
        crit_details.append(f"Volume {vol_val:.0f} m³")

    if contam_crit:
        recommendation = (
            "Interromper descarte de efluentes imediatamente e acionar equipe de campo para estancar vazamento."
        )
    elif ph_crit:
        recommendation = "Ajustar dosagem de neutralização química e calibrar sondas de monitoramento."
    elif turb_crit:
        recommendation = "Acionar bacias de decantação suplementares e inspecionar filtros de retenção."
    else:
        recommendation = "Inspecionar comportas de vazão e reforçar barreiras de contenção operacional."

    return {
        "risk": risk,
        "crit_count": crit_count,
        "warn_count": warn_count,
        "ph_crit": ph_crit,
        "turb_crit": turb_crit,
        "vol_crit": vol_crit,
        "contam_crit": contam_crit,
        "crit_details": crit_details,
        "recommendation": recommendation,
    }


def calculate_point_risk(ph: float, turbidity: float, volume: float, contaminant: float) -> str:
    """Atalho que retorna apenas o nível de risco ('low', 'medium' ou 'critical')."""
    return evaluate_point_parameters(ph, turbidity, volume, contaminant)["risk"]


# ==========================================
# 3. CARREGAMENTO E INFERÊNCIA EM LOTE DO MODELO ML + CONAMA 430
# ==========================================
import hashlib

_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "IA", "modelo_qualidade_agua.pkl")
_DEFAULT_MODEL_SHA256 = "b679da26860f04e701b219b1c858f77640ffcf8b02eb15f8019aca7a8aacbb9c"


def _verify_model_integrity(path: str) -> bool:
    """Valida o hash SHA-256 do artefato .pkl antes de deserializar com joblib/pickle (OWASP A08)."""
    expected_hash = (os.getenv("WATER_QUALITY_MODEL_SHA256") or _DEFAULT_MODEL_SHA256).strip().lower()
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    actual_hash = hasher.hexdigest().lower()
    if actual_hash != expected_hash:
        logger.error(
            f"[Security][ML] Falha na verificação de integridade SHA-256 de {path}. "
            "Carregamento bloqueado para prevenir deserialização insegura."
        )
        return False
    return True


def _load_ml_model() -> Any:
    if not os.path.exists(_MODEL_PATH):
        logger.warning(f"[ML] Arquivo de modelo não encontrado em {_MODEL_PATH}. Usando fallback CONAMA 430.")
        return None
    if not _verify_model_integrity(_MODEL_PATH):
        return None
    try:
        import joblib

        model = joblib.load(_MODEL_PATH)
        logger.info("[ML] Modelo supervisionado modelo_qualidade_agua.pkl verificado (SHA-256) e carregado com sucesso.")
        return model
    except Exception as exc:
        logger.warning(f"[ML] Não foi possível carregar modelo em {_MODEL_PATH} (usando fallback CONAMA 430): {exc}")
        return None


modelo_ia = _load_ml_model()


def avaliar_conama(m: Any) -> bool:
    """Avaliação aritmética rápida dos limites físico-químicos CONAMA 430 (sem custo de ML)."""
    ph = float(m.ph_measurement if m.ph_measurement is not None else 7.0)
    od = float(m.o2_dissolved_measurement if m.o2_dissolved_measurement is not None else 6.0)
    turb = float(m.turbidity_measurement if m.turbidity_measurement is not None else 20.0)
    dbo = float(m.bod_measurement if m.bod_measurement is not None else 15.0)
    dqo = float(m.cod_measurement if m.cod_measurement is not None else 45.0)

    return (
        CONAMA_THRESHOLDS["ph_min"] <= ph <= CONAMA_THRESHOLDS["ph_max"]
        and od >= CONAMA_THRESHOLDS["od_min"]
        and turb <= CONAMA_THRESHOLDS["turbidity_max"]
        and dbo <= CONAMA_THRESHOLDS["bod_max"]
        and dqo <= CONAMA_THRESHOLDS["cod_max"]
    )


def avaliar_qualidade_medicoes_lote(medicoes: Sequence[Any]) -> List[Tuple[str, bool]]:
    """
    Avalia uma lista de MeasurementModel executando no máximo 1 única chamada vetorizada a `modelo_ia.predict`.
    Retorna lista de tuplas `(ml_status, conama_ok)` na mesma ordem.
    """
    if not medicoes:
        return []

    conama_flags = [avaliar_conama(m) for m in medicoes]
    preds: Optional[Sequence[Any]] = None

    if modelo_ia is not None:
        try:
            batch_rows = [
                [
                    float(m.ph_measurement if m.ph_measurement is not None else 7.0),
                    25.0,
                    float(m.bod_measurement if m.bod_measurement is not None else 15.0),
                    float(m.turbidity_measurement if m.turbidity_measurement is not None else 20.0),
                ]
                for m in medicoes
            ]
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*valid feature names.*")
                preds = modelo_ia.predict(batch_rows)
        except Exception as exc:
            logger.debug(f"[ML] Fallback CONAMA na inferência em lote: {exc}")
            preds = None

    resultados: List[Tuple[str, bool]] = []
    for idx, conama_ok in enumerate(conama_flags):
        if preds is not None:
            aprovado = int(preds[idx]) == 1 and conama_ok
        else:
            aprovado = conama_ok
        status_str = "Própria" if aprovado else "Poluída (Risco de Efluentes)"
        resultados.append((status_str, conama_ok))

    return resultados


def avaliar_qualidade_medicao(m: Any) -> Tuple[str, bool]:
    """Avalia uma única medição delegando para o avaliador unificado."""
    return avaliar_qualidade_medicoes_lote([m])[0]


def serialize_measurements_map(medicoes: Sequence[Any]) -> Dict[int, dict]:
    """Serializa múltiplas medições em 1 única passada vetorizada, indexadas por `id_measurement`."""
    validas = [m for m in medicoes if m is not None]
    if not validas:
        return {}

    avaliacoes = avaliar_qualidade_medicoes_lote(validas)
    saida: Dict[int, dict] = {}
    for m, (ml_status, conama_ok) in zip(validas, avaliacoes):
        saida[m.id_measurement] = {
            "id_measurement": m.id_measurement,
            "datetime_measurement": m.datetime_measurement,
            "ph_measurement": m.ph_measurement,
            "o2_dissolved_measurement": m.o2_dissolved_measurement,
            "turbidity_measurement": m.turbidity_measurement,
            "conductivity_measurement": m.conductivity_measurement,
            "bod_measurement": m.bod_measurement,
            "cod_measurement": m.cod_measurement,
            "nitrogen_phosphorus_measurement": m.nitrogen_phosphorus_measurement,
            "ml_status": ml_status,
            "conama_compliant": conama_ok,
        }
    return saida


def serialize_measurement(m: Optional[Any]) -> Optional[dict]:
    """Serializa um único registro MeasurementModel."""
    if not m:
        return None
    return serialize_measurements_map([m]).get(m.id_measurement)

