from pydantic import BaseModel, Field
from typing import Optional
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
