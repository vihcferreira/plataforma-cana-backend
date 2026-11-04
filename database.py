from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Date,
    Enum,
    Float,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

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
    __table_args__ = (
        UniqueConstraint("tenant_id", "code_occurrence", name="uq_occurrence_tenant_code"),
    )

    id_occurrence = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    code_occurrence = Column(String(20), index=True, nullable=True)
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
    __table_args__ = (
        UniqueConstraint("tenant_id", "email_user", name="uq_app_user_tenant_email"),
    )

    id_user = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    name_user = Column(String(255), nullable=False)
    email_user = Column(String(255), index=True, nullable=False)
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
    __table_args__ = (
        UniqueConstraint("tenant_id", "code_map_point", name="uq_map_point_tenant_code"),
    )

    id_map_point = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    code_map_point = Column(String(10), index=True, nullable=False)
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
    tenant_id = Column(String(128), index=True, nullable=False)
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
    tenant_id = Column(String(128), index=True, nullable=False)
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
    __table_args__ = (
        UniqueConstraint("tenant_id", "analysis_date", name="uq_ai_daily_tenant_date"),
    )

    id_analysis = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    analysis_date = Column(Date, index=True, nullable=False)
    analysis_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# ==========================================
# MODELO SQLALCHEMY DA TABELA ALERT
# ==========================================
class AlertModel(Base):
    __tablename__ = "Alert"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code_alert", name="uq_alert_tenant_code"),
    )

    id_alert = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    code_alert = Column(String(20), index=True, nullable=False)
    point_name = Column(String(255), nullable=False)
    severity = Column(String(50), nullable=False, default="critical")  # 'critical', 'medium', 'preventive', 'resolved'
    status = Column(String(50), nullable=False, default="active")      # 'active', 'resolved'
    message = Column(Text, nullable=False)
    params_json = Column(Text, nullable=False)                         # JSON array de strings: '["pH: 9.3", "Turbidez: 68 NTU"]'
    recommendation = Column(Text, nullable=False)
    responsible = Column(String(255), nullable=False, default="Responsável Local")
    id_occurrence = Column(Integer, nullable=True)                     # Referência à ocorrência criada
    code_occurrence = Column(String(20), nullable=True)                # Código da ocorrência (ex: OCR-1082)
    is_viewed = Column(Integer, default=0)                             # 0 = não visualizado, 1 = visualizado
    datetime_alert = Column(DateTime, default=datetime.utcnow, index=True)

# ==========================================
# MODELO SQLALCHEMY DA TABELA TENANT_SETTINGS
# Preferências operacionais e status de telemetria isolados por usuário (tenant)
# ==========================================
class TenantSettingsModel(Base):
    __tablename__ = "Tenant_Settings"

    tenant_id = Column(String(128), primary_key=True, index=True)
    unit_select = Column(String(100), nullable=False, default="vale-verde-norte")
    frequency_minutes = Column(Integer, nullable=False, default=15)
    timezone = Column(String(64), nullable=False, default="America/Sao_Paulo")
    email_alerts = Column(Integer, nullable=False, default=1)
    push_alerts = Column(Integer, nullable=False, default=1)
    user_email = Column(String(255), nullable=True, default="")
    telemetry_active = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def _migrate_multitenancy_schema(conn) -> None:
    """
    Executa migração idempotente nas tabelas MySQL existentes para suportar Multitenancy:
    1. Garante coluna `tenant_id` e índice em todas as tabelas de domínio.
    2. Substitui restrições UNIQUE globais antigas por UNIQUE compostas `(tenant_id, campo)`.
    """
    tenant_tables = [
        "Occurrence",
        "App_User",
        "Map_Point",
        "Map_Measurement_History",
        "History_Event",
        "AI_Daily_Analysis",
        "Alert",
    ]

    for tbl in tenant_tables:
        col_exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl AND COLUMN_NAME = 'tenant_id'"
            ),
            {"tbl": tbl},
        ).scalar()

        if not col_exists:
            conn.execute(
                text(f"ALTER TABLE `{tbl}` ADD COLUMN `tenant_id` VARCHAR(128) NOT NULL DEFAULT '__legacy__'")
            )
            conn.commit()
            logger.info(f"🔒 [Multitenancy Migration] Coluna tenant_id adicionada em {tbl}.")

        idx_exists = conn.execute(
            text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl AND COLUMN_NAME = 'tenant_id'"
            ),
            {"tbl": tbl},
        ).scalar()

        if not idx_exists:
            try:
                conn.execute(text(f"CREATE INDEX `idx_{tbl}_tenant_id` ON `{tbl}` (`tenant_id`)"))
                conn.commit()
            except Exception:
                pass

    composite_uniques = [
        ("Occurrence", "code_occurrence", "uq_occurrence_tenant_code"),
        ("App_User", "email_user", "uq_app_user_tenant_email"),
        ("Map_Point", "code_map_point", "uq_map_point_tenant_code"),
        ("AI_Daily_Analysis", "analysis_date", "uq_ai_daily_tenant_date"),
        ("Alert", "code_alert", "uq_alert_tenant_code"),
    ]

    for tbl, col_name, uq_name in composite_uniques:
        rows = conn.execute(
            text(
                "SELECT INDEX_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tbl "
                "AND NON_UNIQUE = 0 AND INDEX_NAME != 'PRIMARY'"
            ),
            {"tbl": tbl},
        ).fetchall()

        indexes_by_name = {}
        for idx_name, c_name in rows:
            indexes_by_name.setdefault(idx_name, set()).add(c_name)

        # Remove qualquer índice UNIQUE antigo sobre a coluna que não inclua tenant_id
        for idx_name, cols in indexes_by_name.items():
            if col_name in cols and "tenant_id" not in cols:
                try:
                    conn.execute(text(f"ALTER TABLE `{tbl}` DROP INDEX `{idx_name}`"))
                    conn.commit()
                    logger.info(f"🔒 [Multitenancy Migration] Índice global '{idx_name}' removido de {tbl}.")
                except Exception as drop_err:
                    logger.warning(f"[Multitenancy Migration] Aviso ao remover índice {idx_name} de {tbl}: {drop_err}")

        # Cria a restrição UNIQUE composta por (tenant_id, col_name) se ainda não existir
        has_composite = any(cols == {"tenant_id", col_name} for cols in indexes_by_name.values())
        if not has_composite:
            try:
                conn.execute(
                    text(f"ALTER TABLE `{tbl}` ADD CONSTRAINT `{uq_name}` UNIQUE (`tenant_id`, `{col_name}`)")
                )
                conn.commit()
                logger.info(f"🔒 [Multitenancy Migration] Constraint composta '{uq_name}' criada em {tbl}.")
            except Exception as uq_err:
                logger.warning(f"[Multitenancy Migration] Aviso ao criar constraint {uq_name} em {tbl}: {uq_err}")


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        with engine.connect() as conn:
            # Migration defensiva para adicionar volume_map_point se Map_Point já existir
            try:
                vol_exists = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Map_Point' "
                        "AND COLUMN_NAME = 'volume_map_point'"
                    )
                ).scalar()
                if not vol_exists:
                    conn.execute(
                        text("ALTER TABLE Map_Point ADD COLUMN volume_map_point FLOAT NOT NULL DEFAULT 4000.0")
                    )
                    conn.commit()
            except Exception:
                pass

            # Migration defensiva para Multitenancy
            try:
                _migrate_multitenancy_schema(conn)
            except Exception as mt_err:
                logger.warning(f"[Multitenancy Migration] Aviso na migração automática: {mt_err}")
    except Exception as e:
        logger.warning(f"[Database] Banco de dados indisponível na inicialização: {e}")
