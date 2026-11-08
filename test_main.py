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
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import auth_tenant
from database import AIDailyAnalysisModel, Base, get_db
from main import app
from routers import alertas, app_user, ciclo_hidrico, historico, ia_groq, mapa, ocorrencias
import schemas
from services import incident_service, telemetry_service, tenant_settings_service, water_quality_service


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


class TestPlataformaCanaBackend(unittest.TestCase):
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

        cls.tok_a = _sign_firebase_jwt(cls.priv_key, uid="uid_tenant_alpha_001", email="alpha@usina.com")
        cls.tok_b = _sign_firebase_jwt(cls.priv_key, uid="uid_tenant_beta_002", email="beta@usina.com")

        cls.ctx_a = auth_tenant.get_current_tenant_context(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=cls.tok_a)
        )
        cls.ctx_b = auth_tenant.get_current_tenant_context(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=cls.tok_b)
        )

    @classmethod
    def tearDownClass(cls):
        cls.certs_patcher.stop()
        cls.test_engine.dispose()

    def setUp(self):
        tenant_settings_service.clear_settings_cache()
        self.db = self.TestingSessionLocal()

    def tearDown(self):
        self.db.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            self.db.execute(table.delete())
        self.db.commit()
        self.db.close()
        tenant_settings_service.clear_settings_cache()

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

    def test_02_isolamento_completo_pontos_do_mapa_recalculo_risco_e_historico(self):
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
        self.assertEqual(pt_a.risk_map_point, "low")

        # Atualiza métricas para faixa crítica sem enviar risk_map_point -> recalcula automaticamente
        pt_a_upd = mapa.atualizar_mapa(
            pt_a.id_map_point,
            schemas.MapAtualizar(ph_map_point=9.4, turbidity_map_point=70.0),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        self.assertEqual(pt_a_upd.risk_map_point, "critical")

        list_a = mapa.listar_mapa(tenant_id=self.ctx_a.tenant_id, db=self.db)
        list_b = mapa.listar_mapa(tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual([p.name_map_point for p in list_a], ["Ponto P1 - Usina Alpha"])
        self.assertEqual([p.name_map_point for p in list_b], ["Ponto P1 - Usina Beta"])

        with self.assertRaises(HTTPException) as err_del:
            mapa.excluir_mapa(pt_a.id_map_point, tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual(err_del.exception.status_code, 404)

        hist_a = mapa.listar_historico_medicoes(tenant_id=self.ctx_a.tenant_id, db=self.db)
        self.assertEqual(len(hist_a), 2)
        self.assertEqual(hist_a[-1].risk, "critical")

    def test_03_isolamento_ocorrencias_equipe_alertas_historico_telemetria_e_ia(self):
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
            ocorrencias.excluir_ocorrencia(occ_a.id_occurrence, tenant_id=self.ctx_b.tenant_id, db=self.db)

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

        # Gera incidente crítico via serviço centralizado para Alpha
        incident_service.registrar_incidente_critico(
            db=self.db,
            tenant_id=self.ctx_a.tenant_id,
            occurrence_title="Crítico Alpha",
            location_label="P1 - Alpha",
            point_name="Ponto P1 - Usina Alpha",
            responsible="Operador Alpha",
            metrics_summary="PH: 9.4 | TUR: 70 NTU",
            alert_message="Alerta exclusivo Alpha",
            params_chips=["pH: 9.4", "Turbidez: 70 NTU"],
            recommendation="Conter descarte",
            history_label="Alerta Crítico",
            history_description_prefix="Violação detectada.",
        )
        self.db.commit()

        self.assertEqual(alertas.contagem_nao_lidos(tenant_id=self.ctx_a.tenant_id, db=self.db)["unread_count"], 1)
        self.assertEqual(alertas.contagem_nao_lidos(tenant_id=self.ctx_b.tenant_id, db=self.db)["unread_count"], 0)
        alertas.marcar_alertas_como_lidos(tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual(alertas.contagem_nao_lidos(tenant_id=self.ctx_a.tenant_id, db=self.db)["unread_count"], 1)

        alertas.atualizar_config_gerais(
            schemas.GeneralSettingsUpdate(unit="vale-verde-sul", frequency="60", timezone="America/Manaus"),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        self.assertEqual(alertas.obter_config_gerais(tenant_id=self.ctx_a.tenant_id, db=self.db)["unit"], "vale-verde-sul")
        self.assertEqual(alertas.obter_config_gerais(tenant_id=self.ctx_b.tenant_id, db=self.db)["unit"], "vale-verde-norte")

        self.assertEqual(
            historico.listar_historico(tipo=None, busca=None, dias=None, tenant_id=self.ctx_b.tenant_id, db=self.db),
            [],
        )

        telemetry_service.definir_status_telemetria(False, tenant_id=self.ctx_a.tenant_id, db=self.db)
        self.assertFalse(telemetry_service.obter_status_telemetria(tenant_id=self.ctx_a.tenant_id, db=self.db)["active"])
        self.assertTrue(telemetry_service.obter_status_telemetria(tenant_id=self.ctx_b.tenant_id, db=self.db)["active"])

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

    def test_04_regras_risco_e_telemetria_processamento_ponto(self):
        self.assertEqual(water_quality_service.calculate_point_risk(7.2, 22.0, 2800.0, 0.6), "low")
        self.assertEqual(water_quality_service.calculate_point_risk(9.4, 22.0, 2800.0, 0.6), "medium")
        self.assertEqual(water_quality_service.calculate_point_risk(8.8, 45.0, 2800.0, 0.6), "medium")
        self.assertEqual(water_quality_service.calculate_point_risk(9.4, 70.0, 2800.0, 0.6), "critical")

        pt = mapa.criar_mapa(
            schemas.MapCriar(
                code_map_point="T1",
                name_map_point="Ponto Telemetria",
                pos_x_map_point=40.0,
                pos_y_map_point=50.0,
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        telemetry_service._processar_ponto_do_tenant(self.db, self.ctx_a.tenant_id, pt)
        self.db.commit()
        self.assertIn(pt.risk_map_point, ("low", "medium", "critical"))

    def test_05_isolamento_e_fluxo_completo_ciclo_hidrico(self):
        prop_a = ciclo_hidrico.criar_propriedade(
            schemas.PropertyCriar(property_address="Usina Alpha - Setor 01", property_city="Ribeirão Preto - SP"),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        seller_a = ciclo_hidrico.criar_fornecedor(
            schemas.WaterSellerCriar(
                cnpj_seller="12.345.678/0001-99",
                name_seller="Captação Rio Pardo Alpha",
                license_number_seller="OUT-DAEE-2026-01",
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        reg_a = ciclo_hidrico.criar_regulador(
            schemas.EnvironmentalRegulatorCriar(
                name_regulator="CETESB",
                jurisdiction_regulator="Estadual - SP",
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )

        self.assertEqual(ciclo_hidrico.listar_propriedades(tenant_id=self.ctx_b.tenant_id, db=self.db), [])
        with self.assertRaises(HTTPException) as err_prop_b:
            ciclo_hidrico.excluir_propriedade(prop_a.id_property, tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual(err_prop_b.exception.status_code, 404)

        area_ok = ciclo_hidrico.criar_area_descarte(
            schemas.AreaOfDisposalCriar(
                id_property=prop_a.id_property,
                x_coordinate=35.0,
                y_coordinate=45.0,
                is_validated_for_disposal=True,
                license_number_disposal="LO-CETESB-1001",
                id_regulator=reg_a.id_regulator,
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        area_pendente = ciclo_hidrico.criar_area_descarte(
            schemas.AreaOfDisposalCriar(
                id_property=prop_a.id_property,
                x_coordinate=72.0,
                y_coordinate=64.0,
                is_validated_for_disposal=False,
                license_number_disposal="LO-PENDENTE-999",
                id_regulator=reg_a.id_regulator,
            ),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )

        laudo_limpo = ciclo_hidrico.criar_medicao_laboratorial(
            schemas.MeasurementCriar(
                ph_measurement=7.2,
                o2_dissolved_measurement=6.8,
                turbidity_measurement=14.0,
                conductivity_measurement=310.0,
                bod_measurement=12.0,
                cod_measurement=38.0,
                nitrogen_phosphorus_measurement=5.5,
            ),
            ctx=self.ctx_a,
            db=self.db,
        )
        self.assertTrue(laudo_limpo["conama_compliant"])
        self.assertEqual(laudo_limpo["ml_status"], "Própria")

        laudo_poluido = ciclo_hidrico.criar_medicao_laboratorial(
            schemas.MeasurementCriar(
                ph_measurement=4.3,
                o2_dissolved_measurement=1.8,
                turbidity_measurement=95.0,
                conductivity_measurement=1150.0,
                bod_measurement=140.0,
                cod_measurement=380.0,
                nitrogen_phosphorus_measurement=42.0,
            ),
            ctx=self.ctx_a,
            db=self.db,
        )
        self.assertFalse(laudo_poluido["conama_compliant"])
        self.assertIn("Poluída", laudo_poluido["ml_status"])

        lote_a = ciclo_hidrico.criar_lote(
            schemas.WaterBatchCriar(id_seller=seller_a.id_seller, id_property=prop_a.id_property),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        ciclo_hidrico.criar_admissao(
            schemas.WaterAdmissionCriar(
                id_batch=lote_a["id_batch"],
                volume_admitted=5000.0,
                id_measurement=laudo_limpo["id_measurement"],
            ),
            ctx=self.ctx_a,
            db=self.db,
        )
        ciclo_hidrico.criar_armazenamento(
            schemas.WaterStorageCriar(
                id_property=prop_a.id_property,
                volume_stored=3200.0,
                id_measurement=laudo_limpo["id_measurement"],
            ),
            ctx=self.ctx_a,
            db=self.db,
        )

        desc_ok = ciclo_hidrico.criar_descarte(
            schemas.WaterDisposalCriar(
                id_disposal_area=area_ok["id_disposal_area"],
                volume_disposed=1200.0,
                id_measurement=laudo_limpo["id_measurement"],
            ),
            ctx=self.ctx_a,
            db=self.db,
        )
        self.assertIsNone(desc_ok["generated_alert_code"])

        desc_irreg = ciclo_hidrico.criar_descarte(
            schemas.WaterDisposalCriar(
                id_disposal_area=area_pendente["id_disposal_area"],
                volume_disposed=800.0,
                id_measurement=laudo_poluido["id_measurement"],
            ),
            ctx=self.ctx_a,
            db=self.db,
        )
        self.assertIsNotNone(desc_irreg["generated_alert_code"])
        self.assertIsNotNone(desc_irreg["generated_occurrence_code"])

        resumo_a = ciclo_hidrico.obter_resumo_ciclo(tenant_id=self.ctx_a.tenant_id, db=self.db)
        self.assertEqual(resumo_a["total_admitted_m3"], 5000.0)
        self.assertEqual(resumo_a["total_stored_m3"], 3200.0)
        self.assertEqual(resumo_a["total_disposed_m3"], 2000.0)
        self.assertEqual(resumo_a["net_balance_m3"], 3000.0)
        self.assertEqual(resumo_a["conama_compliance_pct"], 50.0)

        seed_b = ciclo_hidrico.popular_dados_exemplo(ctx=self.ctx_b, db=self.db)
        self.assertTrue(seed_b["success"])
        self.assertEqual(seed_b["summary"]["properties_count"], 2)
        self.assertEqual(
            ciclo_hidrico.obter_resumo_ciclo(tenant_id=self.ctx_a.tenant_id, db=self.db)["properties_count"],
            1,
        )

    def test_06_integracao_http_fastapi_testclient(self):
        def _override_get_db():
            yield self.db

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with patch("main.init_db"):
                client = TestClient(app)
                unauth = client.get("/mapa/")
                self.assertEqual(unauth.status_code, 401)

                headers = {"Authorization": f"Bearer {self.tok_a}"}
                created = client.post(
                    "/mapa/",
                    headers=headers,
                    json={
                        "code_map_point": "HTTP1",
                        "name_map_point": "Ponto HTTP",
                        "pos_x_map_point": 30.0,
                        "pos_y_map_point": 40.0,
                    },
                )
                self.assertEqual(created.status_code, 201)
                self.assertEqual(created.json()["code_map_point"], "HTTP1")

                resumo = client.get("/ciclo-hidrico/resumo", headers=headers)
                self.assertEqual(resumo.status_code, 200)
                self.assertEqual(resumo.json()["total_admitted_m3"], 0.0)

                # Confirma que rotas mortas foram removidas (404)
                self.assertEqual(client.get("/tarefas/", headers=headers).status_code, 404)
                self.assertEqual(client.get("/me", headers=headers).status_code, 404)
                self.assertEqual(client.get("/dashboard/metricas", headers=headers).status_code, 404)
        finally:
            app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
