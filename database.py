"""
Configuração SQLAlchemy, Modelos ORM Multitenant e Migração Otimizada em Lote — Plataforma Cana.
"""

from datetime import datetime, timezone
import logging
import os
import re

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
     DDL,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    bindparam,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from services.groq_client import load_env_once

load_env_once()

logger = logging.getLogger(__name__)

_SAFE_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _validate_sql_identifier(identifier: str) -> str:
    """Valida estritamente identificadores SQL (tabelas, colunas, índices) contra injeção em DDL."""
    if not isinstance(identifier, str) or not _SAFE_SQL_IDENTIFIER.match(identifier):
        raise ValueError(f"Identificador SQL inválido ou potencialmente inseguro: {identifier!r}")
    return identifier


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _resolve_database_url() -> tuple[str, bool]:
    env_url = (os.getenv("DATABASE_URL") or "").strip()
    if not env_url:
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            raise RuntimeError("DATABASE_URL é obrigatória em ambiente de produção.")
        logger.warning(
            "[Security] DATABASE_URL ausente no ambiente; utilizando conexão local de desenvolvimento."
        )
        return "mysql+pymysql://user:password@localhost:3306/water_management?charset=utf8mb4", False

    # Converte automaticamente mysql:// (padrão Aiven/TiDB/Railway) para mysql+pymysql://
    if env_url.startswith("mysql://"):
        env_url = "mysql+pymysql://" + env_url[len("mysql://") :]

    # Detecta necessidade de SSL (ex: ?ssl-mode=REQUIRED do Aiven ou ?ssl=true do TiDB Cloud)
    needs_ssl = os.getenv("DB_SSL_REQUIRED", "false").lower() in ("1", "true", "yes")
    if "ssl-mode=" in env_url or "ssl_mode=" in env_url or "ssl=true" in env_url:
        needs_ssl = True
        env_url = re.sub(r"([?&])(ssl-mode|ssl_mode|ssl)=[^&]*&?", r"\1", env_url).rstrip("?&")

    return env_url, needs_ssl


DATABASE_URL, _DB_NEEDS_SSL = _resolve_database_url()

_connect_args: dict = {}
if DATABASE_URL.startswith("mysql"):
    _connect_args["connect_timeout"] = 10
    if _DB_NEEDS_SSL:
        import ssl

        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        _connect_args["ssl"] = ssl_ctx

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# MODELOS SQLALCHEMY MULTITENANT
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
    datetime_occurrence_creation = Column(DateTime, default=_utcnow)


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
    status_user = Column(Enum("active", "inactive"), nullable=False, default="active")
    last_access_datetime = Column(DateTime, nullable=True)
    datetime_user_creation = Column(DateTime, default=_utcnow)


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
    ph_map_point = Column(Float, nullable=False, default=7.2)
    turbidity_map_point = Column(Float, nullable=False, default=20.0)
    contaminant_map_point = Column(Float, nullable=False, default=0.6)
    volume_map_point = Column(Float, nullable=False, default=2800.0)
    risk_map_point = Column(String(50), nullable=False, default="low")
    datetime_map_point_creation = Column(DateTime, default=_utcnow)
    datetime_map_point_update = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class MapMeasurementHistoryModel(Base):
    __tablename__ = "Map_Measurement_History"
    __table_args__ = (
        Index("idx_mmh_tenant_recorded", "tenant_id", "recorded_at"),
    )

    id_measurement = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    code_map_point = Column(String(10), nullable=False, index=True)
    name_map_point = Column(String(255), nullable=False)
    ph = Column(Float, nullable=False)
    turbidity = Column(Float, nullable=False)
    contaminant = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=2800.0)
    risk = Column(String(50), nullable=False, default="low")
    recorded_at = Column(DateTime, default=_utcnow, index=True)


class HistoryEventModel(Base):
    __tablename__ = "History_Event"
    __table_args__ = (
        Index("idx_history_tenant_dt", "tenant_id", "datetime_history"),
    )

    id_history = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    event_type = Column(String(50), nullable=False, index=True)
    event_label = Column(String(100), nullable=False)
    event_point = Column(String(255), nullable=False)
    event_description = Column(Text, nullable=False)
    event_severity = Column(String(50), nullable=False, default="normal")
    id_reference = Column(Integer, nullable=True)
    reference_type = Column(String(50), nullable=True)
    created_by = Column(String(255), nullable=True)
    datetime_history = Column(DateTime, default=_utcnow, index=True)


class AIDailyAnalysisModel(Base):
    __tablename__ = "AI_Daily_Analysis"
    __table_args__ = (
        UniqueConstraint("tenant_id", "analysis_date", name="uq_ai_daily_tenant_date"),
    )

    id_analysis = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    analysis_date = Column(Date, index=True, nullable=False)
    analysis_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class AlertModel(Base):
    __tablename__ = "Alert"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code_alert", name="uq_alert_tenant_code"),
        Index("idx_alert_tenant_viewed", "tenant_id", "is_viewed"),
    )

    id_alert = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    code_alert = Column(String(20), index=True, nullable=False)
    point_name = Column(String(255), nullable=False)
    severity = Column(String(50), nullable=False, default="critical")
    status = Column(String(50), nullable=False, default="active")
    message = Column(Text, nullable=False)
    params_json = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    responsible = Column(String(255), nullable=False, default="Responsável Local")
    id_occurrence = Column(Integer, nullable=True)
    code_occurrence = Column(String(20), nullable=True)
    is_viewed = Column(Integer, default=0)
    datetime_alert = Column(DateTime, default=_utcnow, index=True)


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
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ==========================================
# MODELOS DO CICLO HÍDRICO E LICENCIAMENTO
# ==========================================
class WaterSellerModel(Base):
    __tablename__ = "Water_Seller"

    id_seller = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    cnpj_seller = Column(String(18), nullable=True)
    name_seller = Column(String(255), nullable=False)
    license_number_seller = Column(String(100), nullable=True)


class PropertyModel(Base):
    __tablename__ = "Property"

    id_property = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    property_address = Column(String(255), nullable=False)
    property_city = Column(String(100), nullable=False)


class EnvironmentalRegulatorModel(Base):
    __tablename__ = "Environmental_Regulator"

    id_regulator = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    name_regulator = Column(String(255), nullable=False)
    jurisdiction_regulator = Column(String(255), nullable=False)


class MeasurementModel(Base):
    __tablename__ = "Measurement"

    id_measurement = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    datetime_measurement = Column(DateTime, default=_utcnow)
    ph_measurement = Column(Float, nullable=False, default=7.0)
    o2_dissolved_measurement = Column(Float, nullable=False, default=6.0)
    turbidity_measurement = Column(Float, nullable=False, default=20.0)
    conductivity_measurement = Column(Float, nullable=False, default=350.0)
    bod_measurement = Column(Float, nullable=False, default=15.0)
    cod_measurement = Column(Float, nullable=False, default=45.0)
    nitrogen_phosphorus_measurement = Column(Float, nullable=False, default=8.0)


class WaterBatchModel(Base):
    __tablename__ = "Water_Batch"

    id_batch = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    id_seller = Column(Integer, ForeignKey("Water_Seller.id_seller"), nullable=True)
    id_property = Column(Integer, ForeignKey("Property.id_property"), nullable=True)
    datetime_batch_creation = Column(DateTime, default=_utcnow)


class AreaOfDisposalModel(Base):
    __tablename__ = "Area_Of_Disposal"

    id_disposal_area = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    id_property = Column(Integer, ForeignKey("Property.id_property"), nullable=True)
    x_coordinate = Column(Float, nullable=False, default=50.0)
    y_coordinate = Column(Float, nullable=False, default=50.0)
    is_validated_for_disposal = Column(Boolean, nullable=False, default=False)
    license_number_disposal = Column(String(100), nullable=True)
    id_regulator = Column(Integer, ForeignKey("Environmental_Regulator.id_regulator"), nullable=True)


class WaterAdmissionModel(Base):
    __tablename__ = "Water_Admission"

    id_admission = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    id_batch = Column(Integer, ForeignKey("Water_Batch.id_batch"), nullable=True)
    volume_admitted = Column(Float, nullable=False, default=0.0)
    id_measurement = Column(Integer, ForeignKey("Measurement.id_measurement"), nullable=True)


class WaterStorageModel(Base):
    __tablename__ = "Water_Storage"

    id_storage = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    volume_stored = Column(Float, nullable=False, default=0.0)
    id_measurement = Column(Integer, ForeignKey("Measurement.id_measurement"), nullable=True)
    id_property = Column(Integer, ForeignKey("Property.id_property"), nullable=True)


class WaterDisposalModel(Base):
    __tablename__ = "Water_Disposal"

    id_disposal = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tenant_id = Column(String(128), index=True, nullable=False)
    id_disposal_area = Column(Integer, ForeignKey("Area_Of_Disposal.id_disposal_area"), nullable=True)
    volume_disposed = Column(Float, nullable=False, default=0.0)
    id_measurement = Column(Integer, ForeignKey("Measurement.id_measurement"), nullable=True)


def _migrate_multitenancy_schema(conn) -> None:
    """
    Executa migração idempotente consultando INFORMATION_SCHEMA em lote (2 queries no total em vez de 38).
    """
    tenant_tables = [
        "Occurrence",
        "App_User",
        "Map_Point",
        "Map_Measurement_History",
        "History_Event",
        "AI_Daily_Analysis",
        "Alert",
        "Water_Seller",
        "Property",
        "Environmental_Regulator",
        "Measurement",
        "Water_Batch",
        "Area_Of_Disposal",
        "Water_Admission",
        "Water_Storage",
        "Water_Disposal",
    ]

    cols_stmt = text(
        "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN :tables "
        "AND COLUMN_NAME IN ('tenant_id', 'volume_map_point')"
    ).bindparams(bindparam("tables", expanding=True))
    existing_cols = {(r[0], r[1]) for r in conn.execute(cols_stmt, {"tables": tenant_tables}).fetchall()}

    if ("Map_Point", "volume_map_point") not in existing_cols:
        try:
            conn.execute(text("ALTER TABLE `Map_Point` ADD COLUMN `volume_map_point` FLOAT NOT NULL DEFAULT 2800.0"))
            conn.commit()
        except Exception:
            pass

    for tbl in tenant_tables:
        safe_tbl = _validate_sql_identifier(tbl)
        if (safe_tbl, "tenant_id") not in existing_cols:
            conn.execute(
                DDL(f"ALTER TABLE `{safe_tbl}` ADD COLUMN `tenant_id` VARCHAR(128) NOT NULL DEFAULT '__legacy__'")
            )
            conn.commit()
            logger.info(f"[Multitenancy Migration] Coluna tenant_id adicionada em {safe_tbl}.")

    stats_stmt = text(
        "SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME FROM INFORMATION_SCHEMA.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN :tables"
    ).bindparams(bindparam("tables", expanding=True))
    stat_rows = conn.execute(stats_stmt, {"tables": tenant_tables}).fetchall()

    indexed_tenant_tables = {r[0] for r in stat_rows if r[3] == "tenant_id"}
    for tbl in tenant_tables:
        safe_tbl = _validate_sql_identifier(tbl)
        if safe_tbl not in indexed_tenant_tables:
            try:
                conn.execute(DDL(f"CREATE INDEX `idx_{safe_tbl}_tenant_id` ON `{safe_tbl}` (`tenant_id`)"))
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

    unique_indexes_by_table = {}
    for tbl_name, idx_name, non_unique, col_name in stat_rows:
        if non_unique == 0 and idx_name != "PRIMARY":
            unique_indexes_by_table.setdefault(tbl_name, {}).setdefault(idx_name, set()).add(col_name)

    for tbl, col_name, uq_name in composite_uniques:
        safe_tbl = _validate_sql_identifier(tbl)
        safe_col = _validate_sql_identifier(col_name)
        safe_uq = _validate_sql_identifier(uq_name)
        indexes_by_name = unique_indexes_by_table.get(safe_tbl, {})
        for idx_name, cols in indexes_by_name.items():
            if safe_col in cols and "tenant_id" not in cols:
                try:
                    safe_idx = _validate_sql_identifier(str(idx_name))
                    conn.execute(DDL(f"ALTER TABLE `{safe_tbl}` DROP INDEX `{safe_idx}`"))
                    conn.commit()
                except Exception as drop_err:
                    logger.warning(f"[Multitenancy Migration] Aviso ao remover índice {idx_name} de {safe_tbl}: {drop_err}")

        has_composite = any(cols == {"tenant_id", safe_col} for cols in indexes_by_name.values())
        if not has_composite:
            try:
                conn.execute(
                    DDL(f"ALTER TABLE `{safe_tbl}` ADD CONSTRAINT `{safe_uq}` UNIQUE (`tenant_id`, `{safe_col}`)")
                )
                conn.commit()
            except Exception as uq_err:
                logger.warning(f"[Multitenancy Migration] Aviso ao criar constraint {safe_uq} em {safe_tbl}: {uq_err}")


def init_db() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        if engine.dialect.name == "mysql":
            with engine.connect() as conn:
                try:
                    _migrate_multitenancy_schema(conn)
                except Exception as mt_err:
                    logger.warning(f"[Multitenancy Migration] Aviso na migração automática: {mt_err}")
    except Exception as exc:
        logger.warning(f"[Database] Banco de dados indisponível na inicialização: {exc}")
