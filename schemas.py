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
        from_attributes = True  # Permite serializar o modelo SQLAlchemy diretamente

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
        from_attributes = True

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
    volume_map_point: float = 4000.0
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
    volume_map_point: Optional[float] = None
    risk_map_point: Optional[str] = None

class MapResposta(MapBase):
    id_map_point: int
    datetime_map_point_creation: Optional[datetime] = None
    datetime_map_point_update: Optional[datetime] = None

    class Config:
        from_attributes = True

class MapMeasurementHistoryResposta(BaseModel):
    id_measurement: int
    code_map_point: str
    name_map_point: str
    ph: float
    turbidity: float
    contaminant: float
    volume: float
    risk: str
    recorded_at: datetime

    class Config:
        from_attributes = True


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
        from_attributes = True

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

# ==========================================
# SCHEMAS PARA ALERTAS (TELA DE ALERTAS & NOTIFICAÇÕES)
# ==========================================
class AlertCriar(BaseModel):
    code_alert: Optional[str] = None
    point_name: str
    severity: str = "critical"
    status: str = "active"
    message: str
    params: List[str] = []
    recommendation: str
    responsible: str = "Responsável Local"
    id_occurrence: Optional[int] = None
    code_occurrence: Optional[str] = None

class AlertResposta(BaseModel):
    id_alert: int
    code_alert: str
    point_name: str
    severity: str
    status: str
    message: str
    params: List[str] = []
    recommendation: str
    responsible: str
    id_occurrence: Optional[int] = None
    code_occurrence: Optional[str] = None
    is_viewed: int
    datetime_alert: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==========================================
# SCHEMAS DO CICLO HÍDRICO, LAUDOS E LICENCIAMENTO
# ==========================================
class WaterSellerCriar(BaseModel):
    cnpj_seller: Optional[str] = None
    name_seller: str
    license_number_seller: Optional[str] = None

class WaterSellerResposta(WaterSellerCriar):
    id_seller: int

    class Config:
        from_attributes = True


class PropertyCriar(BaseModel):
    property_address: str
    property_city: str

class PropertyResposta(PropertyCriar):
    id_property: int

    class Config:
        from_attributes = True


class EnvironmentalRegulatorCriar(BaseModel):
    name_regulator: str
    jurisdiction_regulator: str

class EnvironmentalRegulatorResposta(EnvironmentalRegulatorCriar):
    id_regulator: int

    class Config:
        from_attributes = True


class MeasurementCriar(BaseModel):
    ph_measurement: float = 7.0
    o2_dissolved_measurement: float = 6.0
    turbidity_measurement: float = 20.0
    conductivity_measurement: float = 350.0
    bod_measurement: float = 15.0
    cod_measurement: float = 45.0
    nitrogen_phosphorus_measurement: float = 8.0
    datetime_measurement: Optional[datetime] = None

class MeasurementResposta(BaseModel):
    id_measurement: int
    datetime_measurement: Optional[datetime] = None
    ph_measurement: float
    o2_dissolved_measurement: float
    turbidity_measurement: float
    conductivity_measurement: float
    bod_measurement: float
    cod_measurement: float
    nitrogen_phosphorus_measurement: float
    ml_status: str = "Própria"
    conama_compliant: bool = True

    class Config:
        from_attributes = True


class WaterBatchCriar(BaseModel):
    id_seller: int
    id_property: int
    datetime_batch_creation: Optional[datetime] = None

class WaterBatchResposta(BaseModel):
    id_batch: int
    id_seller: Optional[int] = None
    id_property: Optional[int] = None
    seller_name: Optional[str] = None
    seller_license: Optional[str] = None
    property_label: Optional[str] = None
    datetime_batch_creation: Optional[datetime] = None

    class Config:
        from_attributes = True


class AreaOfDisposalCriar(BaseModel):
    id_property: int
    x_coordinate: float = 50.0
    y_coordinate: float = 50.0
    is_validated_for_disposal: bool = True
    license_number_disposal: Optional[str] = None
    id_regulator: int

class AreaOfDisposalAtualizar(BaseModel):
    id_property: Optional[int] = None
    x_coordinate: Optional[float] = None
    y_coordinate: Optional[float] = None
    is_validated_for_disposal: Optional[bool] = None
    license_number_disposal: Optional[str] = None
    id_regulator: Optional[int] = None

class AreaOfDisposalResposta(BaseModel):
    id_disposal_area: int
    id_property: Optional[int] = None
    property_label: Optional[str] = None
    x_coordinate: float
    y_coordinate: float
    is_validated_for_disposal: bool
    license_number_disposal: Optional[str] = None
    id_regulator: Optional[int] = None
    regulator_name: Optional[str] = None
    regulator_jurisdiction: Optional[str] = None

    class Config:
        from_attributes = True


class WaterAdmissionCriar(BaseModel):
    id_batch: int
    volume_admitted: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementCriar] = None

class WaterAdmissionResposta(BaseModel):
    id_admission: int
    id_batch: Optional[int] = None
    batch_label: Optional[str] = None
    volume_admitted: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementResposta] = None

    class Config:
        from_attributes = True


class WaterStorageCriar(BaseModel):
    id_property: int
    volume_stored: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementCriar] = None

class WaterStorageResposta(BaseModel):
    id_storage: int
    id_property: Optional[int] = None
    property_label: Optional[str] = None
    volume_stored: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementResposta] = None

    class Config:
        from_attributes = True


class WaterDisposalCriar(BaseModel):
    id_disposal_area: int
    volume_disposed: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementCriar] = None

class WaterDisposalResposta(BaseModel):
    id_disposal: int
    id_disposal_area: Optional[int] = None
    disposal_area_label: Optional[str] = None
    is_area_validated: bool = True
    volume_disposed: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementResposta] = None
    generated_alert_code: Optional[str] = None
    generated_occurrence_code: Optional[str] = None

    class Config:
        from_attributes = True


class WaterCycleSummaryResponse(BaseModel):
    total_admitted_m3: float
    total_stored_m3: float
    total_disposed_m3: float
    net_balance_m3: float
    properties_count: int
    sellers_count: int
    regulators_count: int
    batches_count: int
    areas_count: int
    validated_areas_count: int
    measurements_count: int
    admissions_count: int
    storages_count: int
    disposals_count: int
    conama_compliance_pct: Optional[float] = None
    avg_ph: Optional[float] = None
    avg_od: Optional[float] = None
    avg_turbidity: Optional[float] = None
    avg_conductivity: Optional[float] = None
    avg_bod: Optional[float] = None
    avg_cod: Optional[float] = None
    avg_npk: Optional[float] = None
