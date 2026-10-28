from sqlalchemy import create_engine, Column, Integer, String, DateTime, Date, Enum, Float, Text, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date

# URL de conexao com as credenciais do seu docker-compose.yml
DATABASE_URL = "mysql+pymysql://user:password@localhost:3306/water_management?charset=utf8mb4"


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verifica se a conexao ainda esta ativa antes de usar
    pool_recycle=3600,
    connect_args={"connect_timeout": 3}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependencia do FastAPI para injetar a sessao do banco nas rotas
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# MODELO SQLALCHEMY DA TABELA OCCURRENCE
# ==========================================
class OccurrenceModel(Base):
    __tablename__ = "Occurrence"

    id_occurrence = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code_occurrence = Column(String(20), unique=True, index=True, nullable=True)
    title_occurrence = Column(String(255), nullable=False)
    location_occurrence = Column(String(255), nullable=False)
    responsible_occurrence = Column(String(255), nullable=False)
    metrics_occurrence = Column(String(255), nullable=False)
    status_occurrence = Column(String(50), nullable=False, default="analise")
    risk_occurrence = Column(String(50), nullable=False, default="medio")
    datetime_occurrence_creation = Column(DateTime, default=datetime.utcnow)

# ==========================================
# MODELO SQLALCHEMY DA TABELA APP_USER
# ==========================================
class AppUserModel(Base):
    __tablename__ = "App_User"
    id_user = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name_user = Column(String(255), nullable=False)
    email_user = Column(String(255), unique=True, index=True, nullable=False)
    role_user = Column(String(255), nullable=False, default="Operador")
    responsible_point_user = Column(String(255), nullable=False)
    status_user = Column(
        Enum("active", "inactive"),
        nullable=False,
        default="active"
    )
    last_access_datetime = Column(DateTime, nullable=True)
    datetime_user_creation = Column(DateTime, default=datetime.utcnow)

# ==========================================
# MODELO SQLALCHEMY DA TABELA MAP_POINT
# ==========================================
class MapPointModel(Base):
    __tablename__ = "Map_Point"
    id_map_point = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code_map_point = Column(String(10), unique=True, index=True, nullable=False)
    name_map_point = Column(String(255), nullable=False)
    grid_coordinate_map_point = Column(String(10), nullable=True)
    geo_coordinate_map_point = Column(String(50), nullable=True)
    pos_x_map_point = Column(Float, nullable=False)
    pos_y_map_point = Column(Float, nullable=False)
    ph_map_point = Column(Float, nullable=False)
    turbidity_map_point = Column(Float, nullable=False)
    contaminant_map_point = Column(Float, nullable=False)
    volume_map_point = Column(Float, nullable=False, default=4000.0)
    risk_map_point = Column(String(50), nullable=False)
    datetime_map_point_creation = Column(DateTime, default=datetime.utcnow)
    datetime_map_point_update = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ==========================================
# MODELO SQLALCHEMY DE HISTÓRICO DE MEDIÇÕES DOS PONTOS (Para preservar análise nos gráficos)
# ==========================================
class MapMeasurementHistoryModel(Base):
    __tablename__ = "Map_Measurement_History"

    id_measurement = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code_map_point = Column(String(10), nullable=False, index=True)
    name_map_point = Column(String(255), nullable=False)
    ph = Column(Float, nullable=False)
    turbidity = Column(Float, nullable=False)
    contaminant = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=4000.0)
    risk = Column(String(50), nullable=False, default="low")
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)

# ==========================================
# MODELO SQLALCHEMY DA TABELA HISTORY_EVENT
# ==========================================
class HistoryEventModel(Base):
    __tablename__ = "History_Event"

    id_history = Column(Integer, primary_key=True, index=True, autoincrement=True)
    event_type = Column(String(50), nullable=False, index=True)  # 'medicao', 'providencia', 'ocorrencia', 'alerta'
    event_label = Column(String(100), nullable=False)
    event_point = Column(String(255), nullable=False)
    event_description = Column(Text, nullable=False)
    event_severity = Column(String(50), nullable=False, default="normal")  # 'normal', 'medio', 'critico'
    id_reference = Column(Integer, nullable=True)
    reference_type = Column(String(50), nullable=True)
    created_by = Column(String(255), nullable=True)
    datetime_history = Column(DateTime, default=datetime.utcnow, index=True)

# ==========================================
# MODELO SQLALCHEMY DA TABELA AI_DAILY_ANALYSIS
# ==========================================
class AIDailyAnalysisModel(Base):
    __tablename__ = "AI_Daily_Analysis"

    id_analysis = Column(Integer, primary_key=True, index=True, autoincrement=True)
    analysis_date = Column(Date, unique=True, index=True, nullable=False)
    analysis_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# ==========================================
# MODELO SQLALCHEMY DA TABELA ALERT
# ==========================================
class AlertModel(Base):
    __tablename__ = "Alert"

    id_alert = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code_alert = Column(String(20), unique=True, index=True, nullable=False)
    point_name = Column(String(255), nullable=False)
    severity = Column(String(50), nullable=False, default="critical")  # 'critical', 'medium', 'preventive', 'resolved'
    status = Column(String(50), nullable=False, default="active")      # 'active', 'resolved'
    message = Column(Text, nullable=False)
    params_json = Column(Text, nullable=False)                         # JSON array de strings: '["pH: 9.3", "Turbidez: 68 NTU"]'
    recommendation = Column(Text, nullable=False)
    responsible = Column(String(255), nullable=False, default="Eng. Carlos Lima")
    id_occurrence = Column(Integer, nullable=True)                     # Referência à ocorrência criada
    code_occurrence = Column(String(20), nullable=True)                # Código da ocorrência (ex: OCR-1082)
    is_viewed = Column(Integer, default=0)                             # 0 = não visualizado, 1 = visualizado
    datetime_alert = Column(DateTime, default=datetime.utcnow, index=True)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        # Executa migration defensiva para adicionar a coluna volume_map_point se a tabela Map_Point já existir
        with engine.connect() as conn:
            try:
                conn.execute(
                    text("ALTER TABLE Map_Point ADD COLUMN volume_map_point FLOAT NOT NULL DEFAULT 4000.0")
                )
                conn.commit()
            except Exception:
                pass
    except Exception as e:
        pass


