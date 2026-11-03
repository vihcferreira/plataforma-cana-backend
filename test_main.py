import base64
import datetime as dt
import json
import time
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import auth_tenant
import schemas
from database import AIDailyAnalysisModel, Base
from routers import alertas, app_user, historico, ia_groq, mapa, ocorrencias, tarefas
from services import telemetry_service


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate_test_rsa_cert():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "firebase-test-ca")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=10))
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return private_key, cert_pem


def _sign_firebase_jwt(
    private_key,
    uid: str,
    email: str = "user@teste.com",
    kid: str = "test-kid-1",
    aud: str = auth_tenant.FIREBASE_PROJECT_ID,
    iss: str = f"https://securetoken.google.com/{auth_tenant.FIREBASE_PROJECT_ID}",
    exp_offset: int = 3600,
) -> str:
    now = int(time.time())
    header = {"alg": "RS256", "kid": kid, "typ": "JWT"}
    payload = {
        "aud": aud,
        "iss": iss,
        "sub": uid,
        "user_id": uid,
        "email": email,
        "iat": now - 5,
        "exp": now + exp_offset,
    }
    h_b64 = _b64url_encode(json.dumps(header).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


class TestMultitenancyIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.priv_key, cls.cert_pem = _generate_test_rsa_cert()
        cls.other_priv_key, _ = _generate_test_rsa_cert()

        cls.test_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.test_engine)
        Base.metadata.create_all(bind=cls.test_engine)

        cls.certs_patcher = patch.object(
            auth_tenant,
            "_get_google_public_certs",
            return_value={"test-kid-1": cls.cert_pem},
        )
        cls.certs_patcher.start()

        tok_a = _sign_firebase_jwt(cls.priv_key, uid="uid_tenant_alpha_001", email="alpha@usina.com")
        tok_b = _sign_firebase_jwt(cls.priv_key, uid="uid_tenant_beta_002", email="beta@usina.com")

        cls.ctx_a = auth_tenant.get_current_tenant_context(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok_a)
        )
        cls.ctx_b = auth_tenant.get_current_tenant_context(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok_b)
        )

    @classmethod
    def tearDownClass(cls):
        cls.certs_patcher.stop()

    def setUp(self):
        self.db = self.TestingSessionLocal()

    def tearDown(self):
        self.db.close()

    def test_01_bloqueia_credenciais_ausentes_ou_forjadas(self):
        with self.assertRaises(HTTPException) as ctx_missing:
            auth_tenant.get_current_tenant_context(None)
        self.assertEqual(ctx_missing.exception.status_code, 401)

        forged = _sign_firebase_jwt(self.other_priv_key, uid="uid_tenant_alpha_001")
        with self.assertRaises(HTTPException) as ctx_forged:
            auth_tenant.get_current_tenant_context(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged)
            )
        self.assertEqual(ctx_forged.exception.status_code, 401)

        expired = _sign_firebase_jwt(self.priv_key, uid="uid_tenant_alpha_001", exp_offset=-300)
        with self.assertRaises(HTTPException) as ctx_exp:
            auth_tenant.get_current_tenant_context(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired)
            )
        self.assertEqual(ctx_exp.exception.status_code, 401)

        wrong_aud = _sign_firebase_jwt(self.priv_key, uid="uid_tenant_alpha_001", aud="outro-projeto")
        with self.assertRaises(HTTPException) as ctx_aud:
            auth_tenant.get_current_tenant_context(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=wrong_aud)
            )
        self.assertEqual(ctx_aud.exception.status_code, 401)

    def test_02_isolamento_completo_pontos_do_mapa_e_historico_medicoes(self):
        pt_a = mapa.criar_mapa(
            schemas.MapCriar(
                code_map_point="P1",
                name_map_point="Ponto P1 - Usina Alpha",
                pos_x_map_point=25.0,
                pos_y_map_point=35.0,
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        pt_b = mapa.criar_mapa(
            schemas.MapCriar(
                code_map_point="P1",
                name_map_point="Ponto P1 - Usina Beta",
                pos_x_map_point=60.0,
                pos_y_map_point=70.0,
            ),
            tenant_id=self.ctx_b.tenant_id,
            db=self.db,
        )
        self.assertNotEqual(pt_a.id_map_point, pt_b.id_map_point)

        list_a = mapa.listar_mapa(tenant_id=self.ctx_a.tenant_id, db=self.db)
        list_b = mapa.listar_mapa(tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual([p.name_map_point for p in list_a], ["Ponto P1 - Usina Alpha"])
        self.assertEqual([p.name_map_point for p in list_b], ["Ponto P1 - Usina Beta"])

        with self.assertRaises(HTTPException) as err_get:
            mapa.buscar_mapa(pt_a.id_map_point, tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual(err_get.exception.status_code, 404)

        with self.assertRaises(HTTPException) as err_del:
            mapa.excluir_mapa(pt_a.id_map_point, tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual(err_del.exception.status_code, 404)

        hist_a = mapa.listar_historico_medicoes(tenant_id=self.ctx_a.tenant_id, db=self.db)
        self.assertEqual(len(hist_a), 1)
        self.assertEqual(hist_a[0].name_map_point, "Ponto P1 - Usina Alpha")

    def test_03_isolamento_ocorrencias_equipe_alertas_historico_telemetria_e_ia(self):
        # 1. Ocorrências
        occ_a = ocorrencias.criar_ocorrencia(
            schemas.OcorrenciaCriar(
                title_occurrence="Vazamento Canal Alpha",
                location_occurrence="Ponto P1 - Usina Alpha",
                responsible_occurrence="Eng. Alpha",
                metrics_occurrence="PH: 5.1",
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        self.assertEqual(ocorrencias.listar_ocorrencias(tenant_id=self.ctx_b.tenant_id, db=self.db), [])
        with self.assertRaises(HTTPException):
            ocorrencias.buscar_ocorrencia(occ_a.id_occurrence, tenant_id=self.ctx_b.tenant_id, db=self.db)

        # 2. Usuários de Equipe
        usr_a = app_user.criar_usuario(
            schemas.UserCriar(
                name_user="Operador Alpha",
                email_user="operador@usina.com",
                responsible_point_user="Ponto P1 - Usina Alpha",
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        usr_b = app_user.criar_usuario(
            schemas.UserCriar(
                name_user="Operador Beta",
                email_user="operador@usina.com",
                responsible_point_user="Ponto P1 - Usina Beta",
            ),
            tenant_id=self.ctx_b.tenant_id,
            db=self.db,
        )
        self.assertNotEqual(usr_a.id_user, usr_b.id_user)
        with self.assertRaises(HTTPException):
            app_user.excluir_usuario(usr_a.id_user, tenant_id=self.ctx_b.tenant_id, db=self.db)

        # 3. Alertas & Configurações
        alertas.criar_alerta(
            schemas.AlertCriar(
                point_name="Ponto P1 - Usina Alpha",
                message="Alerta exclusivo Alpha",
                recommendation="Conter descarte",
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        self.assertEqual(alertas.contagem_nao_lidos(tenant_id=self.ctx_a.tenant_id, db=self.db)["unread_count"], 1)
        self.assertEqual(alertas.contagem_nao_lidos(tenant_id=self.ctx_b.tenant_id, db=self.db)["unread_count"], 0)
        alertas.marcar_alertas_como_lidos(tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual(alertas.contagem_nao_lidos(tenant_id=self.ctx_a.tenant_id, db=self.db)["unread_count"], 1)

        alertas.atualizar_config_gerais(
            {"unit": "vale-verde-sul", "frequency": "60", "timezone": "America/Manaus"},
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        self.assertEqual(alertas.obter_config_gerais(tenant_id=self.ctx_a.tenant_id, db=self.db)["unit"], "vale-verde-sul")
        self.assertEqual(alertas.obter_config_gerais(tenant_id=self.ctx_b.tenant_id, db=self.db)["unit"], "vale-verde-norte")

        # 4. Histórico
        ev_a = historico.criar_evento_historico(
            schemas.HistoryEventCriar(
                event_type="medicao",
                event_label="Coleta Manual",
                event_point="Ponto P1 - Usina Alpha",
                event_description="Medição manual registrada",
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        self.assertEqual(historico.listar_historico(tipo=None, busca=None, dias=None, tenant_id=self.ctx_b.tenant_id, db=self.db), [])
        with self.assertRaises(HTTPException):
            historico.excluir_evento_historico(ev_a.id_history, tenant_id=self.ctx_b.tenant_id, db=self.db)

        # 5. Telemetria por Tenant
        telemetry_service.definir_status_telemetria(False, tenant_id=self.ctx_a.tenant_id, db=self.db)
        self.assertFalse(telemetry_service.obter_status_telemetria(tenant_id=self.ctx_a.tenant_id, db=self.db)["active"])
        self.assertTrue(telemetry_service.obter_status_telemetria(tenant_id=self.ctx_b.tenant_id, db=self.db)["active"])

        # 6. Cache da IA Diária por Tenant
        with patch.object(
            ia_groq,
            "call_groq_chat",
            side_effect=lambda msgs, temperature=0.2: {
                "analysis_text": "Análise Alpha" if "Usina Alpha" in str(msgs) else "Análise Beta"
            },
        ):
            res_ia_a = ia_groq.executar_e_persistir_analise_diaria(self.db, tenant_id=self.ctx_a.tenant_id)
            res_ia_b = ia_groq.executar_e_persistir_analise_diaria(self.db, tenant_id=self.ctx_b.tenant_id)
            self.assertEqual(res_ia_a["analysis_text"], "Análise Alpha")
            self.assertEqual(res_ia_b["analysis_text"], "Análise Beta")
            self.assertEqual(self.db.query(AIDailyAnalysisModel).count(), 2)

    def test_04_isolamento_tarefas_por_tenant(self):
        t_a = tarefas.criar_tarefa(
            schemas.TarefaCriar(titulo="Revisar sensores Alpha", descricao="Inspeção"),
            tenant_id=self.ctx_a.tenant_id,
        )
        self.assertEqual(len(tarefas.listar_tarefas(concluida=None, busca=None, tenant_id=self.ctx_a.tenant_id)), 1)
        self.assertEqual(tarefas.listar_tarefas(concluida=None, busca=None, tenant_id=self.ctx_b.tenant_id), [])
        with self.assertRaises(HTTPException):
            tarefas.buscar_tarefa(t_a["id"], tenant_id=self.ctx_b.tenant_id)


if __name__ == "__main__":
    unittest.main()
