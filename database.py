from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# URL de conexao com as credenciais do seu docker-compose.yml
DATABASE_URL = "mysql+pymysql://user:password@localhost:3306/water_management?charset=utf8mb4"


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verifica se a conexao ainda esta ativa antes de usar
    pool_recycle=3600
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
    
