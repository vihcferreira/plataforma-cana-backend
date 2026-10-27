from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# ==========================================
# ESQUEMAS / CONTRATOS (Pydantic)
# ==========================================
class TarefaBase(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=100)
    descricao: Optional[str] = Field(None, max_length=300)
    concluida: bool = Field(default=False)

class TarefaCriar(TarefaBase):
    cep: Optional[str] = Field(None, json_schema_extra={"example": "01001000"}, description="CEP para buscar o endereço da tarefa")

class TarefaAtualizar(BaseModel):
    titulo: Optional[str] = Field(None, min_length=3, max_length=100)
    descricao: Optional[str] = Field(None, max_length=300)
    concluida: Optional[bool] = None

class TarefaResposta(TarefaBase):
    id: int

class DadosAgua(BaseModel):
    ph: float = Field(..., json_schema_extra={"example": 6.5}, description="Nível de pH da água")
    temperatura_c: float = Field(..., json_schema_extra={"example": 25.0}, description="Temperatura em graus Celsius")
    dbo_mgl: float = Field(..., json_schema_extra={"example": 10.0}, description="Demanda Biológica de Oxigênio")
    turbidez_ntu: float = Field(..., json_schema_extra={"example": 15.0}, description="Nível de Turbidez")

# ==========================================
# SCHEMAS DE OCORRÊNCIA
# ==========================================
class OcorrenciaBase(BaseModel):
    title_occurrence: str
    location_occurrence: str
    responsible_occurrence: str
    metrics_occurrence: str
    status_occurrence: str = "analise"
    risk_occurrence: str = "medio"
    code_occurrence: Optional[str] = None

class OcorrenciaCriar(OcorrenciaBase):
    pass

class OcorrenciaAtualizar(BaseModel):
    title_occurrence: Optional[str] = None
    location_occurrence: Optional[str] = None
    responsible_occurrence: Optional[str] = None
    metrics_occurrence: Optional[str] = None
    status_occurrence: Optional[str] = None
    risk_occurrence: Optional[str] = None

class OcorrenciaResposta(OcorrenciaBase):
    id_occurrence: int
    datetime_occurrence_creation: Optional[datetime] = None
    
    class Config:
        orm_mode = True  # Permite serializar o modelo SQLAlchemy diretamente

# ==========================================
# SCHEMAS DE USUÁRIO
# ==========================================
class UserBase(BaseModel):
    name_user: str
    email_user: str
    role_user: str = 'Operador'
    responsible_point_user: str
    status_user: str = 'active'

class UserCriar(UserBase):
    pass

class UserAtualizar(BaseModel):
    name_user: Optional[str] = None
    email_user: Optional[str] = None
    role_user: Optional[str] = None
    responsible_point_user: Optional[str] = None
    status_user: Optional[str] = None

class UserResposta(UserBase):
    id_user: int
    last_access_datetime: Optional[datetime] = None
    datetime_user_creation: Optional[datetime] = None

    class Config:
        orm_mode = True

# ==========================================
# SCHEMAS DE MAPA
# ==========================================
class MapBase(BaseModel):
    code_map_point: str
    name_map_point: str
    grid_coordinate_map_point: Optional[str] = None
    geo_coordinate_map_point: Optional[str] = None
    pos_x_map_point: float
    pos_y_map_point: float
    ph_map_point: float = 7.0
    turbidity_map_point: float = 20.0
    contaminant_map_point: float = 0.0
    risk_map_point: str = "low"

class MapCriar(MapBase):
    pass

class MapAtualizar(BaseModel):
    code_map_point: Optional[str] = None
    name_map_point: Optional[str] = None
    grid_coordinate_map_point: Optional[str] = None
    geo_coordinate_map_point: Optional[str] = None
    pos_x_map_point: Optional[float] = None
    pos_y_map_point: Optional[float] = None
    ph_map_point: Optional[float] = None
    turbidity_map_point: Optional[float] = None
    contaminant_map_point: Optional[float] = None
    risk_map_point: Optional[str] = None

class MapResposta(MapBase):
    id_map_point: int
    datetime_map_point_creation: Optional[datetime] = None
    datetime_map_point_update: Optional[datetime] = None

    class Config:
        orm_mode = True

# ==========================================
# SCHEMAS DE HISTÓRICO
# ==========================================
class HistoryEventBase(BaseModel):
    event_type: str  # 'medicao', 'providencia', 'ocorrencia', 'alerta'
    event_label: str
    event_point: str
    event_description: str
    event_severity: str = "normal"  # 'normal', 'medio', 'critico'
    id_reference: Optional[int] = None
    reference_type: Optional[str] = None
    created_by: Optional[str] = None

class HistoryEventCriar(HistoryEventBase):
    pass

class HistoryEventResposta(HistoryEventBase):
    id_history: int
    datetime_history: Optional[datetime] = None

    class Config:
        orm_mode = True

# ==========================================
# SCHEMAS DE INTELIGÊNCIA ARTIFICIAL (GROQ)
# ==========================================
class AISimulationRequest(BaseModel):
    ph: float
    turbidity: float
    volume: float
    contaminants: float
    rain: bool = False
    calculated_score: Optional[int] = None
    calculated_risk: Optional[str] = None

class AISimulationResponse(BaseModel):
    risk_level: str               # "Baixo", "Médio" ou "Crítico"
    risk_score_evaluation: str   # Resumo da avaliação numérica
    summary: str                 # Análise técnica resumida
    technical_considerations: str # Considerações técnicas no contexto sucroalcooleiro
    recommendations: List[str]   # Lista de ações recomendadas
    alerts_suggested: List[str]  # Alertas sugeridos pela IA
    model_used: str

class AIDailyAnalysisResponse(BaseModel):
    analysis_date: str
    analysis_text: str
    stress_probability: str
    confidence_index: str
    variables: List[dict]
    recommended_action_title: str
    recommended_action_desc: str
    from_cache: bool = False
    generated_at: str
    model_used: str


