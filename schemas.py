"""
Contratos e Schemas Pydantic v2 — Plataforma Cana.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


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
    model_config = ConfigDict(from_attributes=True)

    id_occurrence: int
    datetime_occurrence_creation: Optional[datetime] = None


# ==========================================
# SCHEMAS DE USUÁRIO
# ==========================================
class UserBase(BaseModel):
    name_user: str
    email_user: str
    role_user: str = "Operador"
    responsible_point_user: str
    status_user: str = "active"


class UserCriar(UserBase):
    pass


class UserAtualizar(BaseModel):
    name_user: Optional[str] = None
    email_user: Optional[str] = None
    role_user: Optional[str] = None
    responsible_point_user: Optional[str] = None
    status_user: Optional[str] = None


class UserResposta(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id_user: int
    last_access_datetime: Optional[datetime] = None
    datetime_user_creation: Optional[datetime] = None


# ==========================================
# SCHEMAS DE MAPA E TELEMETRIA
# ==========================================
class TelemetriaToggleRequest(BaseModel):
    active: bool


class MapBase(BaseModel):
    code_map_point: str
    name_map_point: str
    grid_coordinate_map_point: Optional[str] = None
    geo_coordinate_map_point: Optional[str] = None
    pos_x_map_point: float
    pos_y_map_point: float
    ph_map_point: float = 7.2
    turbidity_map_point: float = 20.0
    contaminant_map_point: float = 0.6
    volume_map_point: float = 2800.0
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
    model_config = ConfigDict(from_attributes=True)

    id_map_point: int
    datetime_map_point_creation: Optional[datetime] = None
    datetime_map_point_update: Optional[datetime] = None


class MapMeasurementHistoryResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_measurement: int
    code_map_point: str
    name_map_point: str
    ph: float
    turbidity: float
    contaminant: float
    volume: float
    risk: str
    recorded_at: datetime


# ==========================================
# SCHEMAS DE HISTÓRICO
# ==========================================
class HistoryEventBase(BaseModel):
    event_type: str
    event_label: str
    event_point: str
    event_description: str
    event_severity: str = "normal"
    id_reference: Optional[int] = None
    reference_type: Optional[str] = None
    created_by: Optional[str] = None


class HistoryEventResposta(HistoryEventBase):
    model_config = ConfigDict(from_attributes=True)

    id_history: int
    datetime_history: Optional[datetime] = None


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
    risk_level: str
    risk_score_evaluation: str
    summary: str
    technical_considerations: str
    recommendations: List[str]
    alerts_suggested: List[str]
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
# SCHEMAS DE ALERTAS E CONFIGURAÇÕES DO TENANT
# ==========================================
class AlertResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class NotificationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email_alerts: Optional[bool] = None
    push_alerts: Optional[bool] = None
    user_email: Optional[str] = None


class GeneralSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    unit: Optional[str] = None
    frequency: Optional[str | int] = None
    timezone: Optional[str] = None


# ==========================================
# SCHEMAS DO CICLO HÍDRICO, LAUDOS E LICENCIAMENTO
# ==========================================
class WaterSellerCriar(BaseModel):
    cnpj_seller: Optional[str] = None
    name_seller: str
    license_number_seller: Optional[str] = None


class WaterSellerResposta(WaterSellerCriar):
    model_config = ConfigDict(from_attributes=True)

    id_seller: int


class PropertyCriar(BaseModel):
    property_address: str
    property_city: str


class PropertyResposta(PropertyCriar):
    model_config = ConfigDict(from_attributes=True)

    id_property: int


class EnvironmentalRegulatorCriar(BaseModel):
    name_regulator: str
    jurisdiction_regulator: str


class EnvironmentalRegulatorResposta(EnvironmentalRegulatorCriar):
    model_config = ConfigDict(from_attributes=True)

    id_regulator: int


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
    model_config = ConfigDict(from_attributes=True)

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


class WaterBatchCriar(BaseModel):
    id_seller: int
    id_property: int
    datetime_batch_creation: Optional[datetime] = None


class WaterBatchResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_batch: int
    id_seller: Optional[int] = None
    id_property: Optional[int] = None
    seller_name: Optional[str] = None
    seller_license: Optional[str] = None
    property_label: Optional[str] = None
    datetime_batch_creation: Optional[datetime] = None


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
    model_config = ConfigDict(from_attributes=True)

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


class WaterAdmissionCriar(BaseModel):
    id_batch: int
    volume_admitted: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementCriar] = None


class WaterAdmissionResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_admission: int
    id_batch: Optional[int] = None
    batch_label: Optional[str] = None
    volume_admitted: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementResposta] = None


class WaterStorageCriar(BaseModel):
    id_property: int
    volume_stored: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementCriar] = None


class WaterStorageResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_storage: int
    id_property: Optional[int] = None
    property_label: Optional[str] = None
    volume_stored: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementResposta] = None


class WaterDisposalCriar(BaseModel):
    id_disposal_area: int
    volume_disposed: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementCriar] = None


class WaterDisposalResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_disposal: int
    id_disposal_area: Optional[int] = None
    disposal_area_label: Optional[str] = None
    is_area_validated: bool = True
    volume_disposed: float
    id_measurement: Optional[int] = None
    measurement: Optional[MeasurementResposta] = None
    generated_alert_code: Optional[str] = None
    generated_occurrence_code: Optional[str] = None


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
