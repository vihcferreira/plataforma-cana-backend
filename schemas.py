"""
Contratos e Schemas Pydantic v2 — Plataforma Cana.
"""

from datetime import datetime
import re
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

AllowedUserRole = Literal[
    "Administrador",
    "Responsável Técnico",
    "Gestor Ambiental",
    "Operador",
    "Visualizador",
]
AllowedUserStatus = Literal["active", "inactive"]


# ==========================================
# SCHEMAS DE OCORRÊNCIA
# ==========================================
class OcorrenciaBase(BaseModel):
    title_occurrence: str = Field(..., min_length=2, max_length=255)
    location_occurrence: str = Field(..., min_length=1, max_length=255)
    responsible_occurrence: str = Field(..., min_length=1, max_length=255)
    metrics_occurrence: str = Field(..., min_length=1, max_length=255)
    status_occurrence: str = Field(default="analise", max_length=50)
    risk_occurrence: str = Field(default="medio", max_length=50)
    code_occurrence: Optional[str] = Field(default=None, max_length=20)


class OcorrenciaCriar(OcorrenciaBase):
    pass


class OcorrenciaAtualizar(BaseModel):
    title_occurrence: Optional[str] = Field(default=None, min_length=2, max_length=255)
    location_occurrence: Optional[str] = Field(default=None, min_length=1, max_length=255)
    responsible_occurrence: Optional[str] = Field(default=None, min_length=1, max_length=255)
    metrics_occurrence: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status_occurrence: Optional[str] = Field(default=None, max_length=50)
    risk_occurrence: Optional[str] = Field(default=None, max_length=50)


class OcorrenciaResposta(OcorrenciaBase):
    model_config = ConfigDict(from_attributes=True)

    id_occurrence: int
    datetime_occurrence_creation: Optional[datetime] = None


# ==========================================
# SCHEMAS DE USUÁRIO
# ==========================================
class UserBase(BaseModel):
    name_user: str = Field(..., min_length=2, max_length=255)
    email_user: str = Field(..., min_length=5, max_length=254)
    role_user: AllowedUserRole = "Operador"
    responsible_point_user: str = Field(..., min_length=1, max_length=255)
    status_user: AllowedUserStatus = "active"

    @field_validator("email_user")
    @classmethod
    def validate_email_user(cls, v: str) -> str:
        clean = (v or "").strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean):
            raise ValueError("Formato de e-mail inválido.")
        return clean


class UserCriar(UserBase):
    pass


class UserAtualizar(BaseModel):
    name_user: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email_user: Optional[str] = Field(default=None, min_length=5, max_length=254)
    role_user: Optional[AllowedUserRole] = None
    responsible_point_user: Optional[str] = Field(default=None, min_length=1, max_length=255)
    status_user: Optional[AllowedUserStatus] = None

    @field_validator("email_user")
    @classmethod
    def validate_email_user(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean):
            raise ValueError("Formato de e-mail inválido.")
        return clean


class UserResposta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_user: int
    name_user: str
    email_user: str
    role_user: str
    responsible_point_user: str
    status_user: str
    last_access_datetime: Optional[datetime] = None
    datetime_user_creation: Optional[datetime] = None


# ==========================================
# SCHEMAS DE MAPA E TELEMETRIA
# ==========================================
class TelemetriaToggleRequest(BaseModel):
    active: bool


class MapBase(BaseModel):
    code_map_point: str = Field(..., min_length=1, max_length=10)
    name_map_point: str = Field(..., min_length=1, max_length=255)
    grid_coordinate_map_point: Optional[str] = Field(default=None, max_length=10)
    geo_coordinate_map_point: Optional[str] = Field(default=None, max_length=50)
    pos_x_map_point: float = Field(..., ge=0.0, le=100.0)
    pos_y_map_point: float = Field(..., ge=0.0, le=100.0)
    ph_map_point: float = Field(default=7.2, ge=0.0, le=14.0)
    turbidity_map_point: float = Field(default=20.0, ge=0.0, le=10000.0)
    contaminant_map_point: float = Field(default=0.6, ge=0.0, le=10000.0)
    volume_map_point: float = Field(default=2800.0, ge=0.0, le=10000000.0)
    risk_map_point: str = Field(default="low", max_length=50)


class MapCriar(MapBase):
    pass


class MapAtualizar(BaseModel):
    code_map_point: Optional[str] = Field(default=None, min_length=1, max_length=10)
    name_map_point: Optional[str] = Field(default=None, min_length=1, max_length=255)
    grid_coordinate_map_point: Optional[str] = Field(default=None, max_length=10)
    geo_coordinate_map_point: Optional[str] = Field(default=None, max_length=50)
    pos_x_map_point: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    pos_y_map_point: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    ph_map_point: Optional[float] = Field(default=None, ge=0.0, le=14.0)
    turbidity_map_point: Optional[float] = Field(default=None, ge=0.0, le=10000.0)
    contaminant_map_point: Optional[float] = Field(default=None, ge=0.0, le=10000.0)
    volume_map_point: Optional[float] = Field(default=None, ge=0.0, le=10000000.0)
    risk_map_point: Optional[str] = Field(default=None, max_length=50)


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
    ph: float = Field(..., ge=0.0, le=14.0)
    turbidity: float = Field(..., ge=0.0, le=10000.0)
    volume: float = Field(..., ge=0.0, le=10000000.0)
    contaminants: float = Field(..., ge=0.0, le=10000.0)
    rain: bool = False
    calculated_score: Optional[int] = Field(default=None, ge=0, le=100)
    calculated_risk: Optional[str] = Field(default=None, max_length=50)


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
    cnpj_seller: Optional[str] = Field(default=None, max_length=18)
    name_seller: str = Field(..., min_length=2, max_length=255)
    license_number_seller: Optional[str] = Field(default=None, max_length=100)


class WaterSellerResposta(WaterSellerCriar):
    model_config = ConfigDict(from_attributes=True)

    id_seller: int


class PropertyCriar(BaseModel):
    property_address: str = Field(..., min_length=2, max_length=255)
    property_city: str = Field(..., min_length=2, max_length=100)


class PropertyResposta(PropertyCriar):
    model_config = ConfigDict(from_attributes=True)

    id_property: int


class EnvironmentalRegulatorCriar(BaseModel):
    name_regulator: str = Field(..., min_length=2, max_length=255)
    jurisdiction_regulator: str = Field(..., min_length=2, max_length=255)


class EnvironmentalRegulatorResposta(EnvironmentalRegulatorCriar):
    model_config = ConfigDict(from_attributes=True)

    id_regulator: int


class MeasurementCriar(BaseModel):
    ph_measurement: float = Field(default=7.0, ge=0.0, le=14.0)
    o2_dissolved_measurement: float = Field(default=6.0, ge=0.0, le=100.0)
    turbidity_measurement: float = Field(default=20.0, ge=0.0, le=10000.0)
    conductivity_measurement: float = Field(default=350.0, ge=0.0, le=100000.0)
    bod_measurement: float = Field(default=15.0, ge=0.0, le=100000.0)
    cod_measurement: float = Field(default=45.0, ge=0.0, le=100000.0)
    nitrogen_phosphorus_measurement: float = Field(default=8.0, ge=0.0, le=100000.0)
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
    volume_admitted: float = Field(..., ge=0.0, le=10000000.0)
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
    volume_stored: float = Field(..., ge=0.0, le=10000000.0)
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
    volume_disposed: float = Field(..., ge=0.0, le=10000000.0)
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
