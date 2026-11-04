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
from routers import alertas, app_user, ciclo_hidrico, historico, ia_groq, mapa, ocorrencias, tarefas
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

    def test_05_isolamento_e_fluxo_completo_ciclo_hidrico(self):
        # 1. Cadastros base para Tenant Alpha (Property, Water_Seller, Environmental_Regulator)
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

        # Isolamento entre tenants nos cadastros base
        self.assertEqual(ciclo_hidrico.listar_propriedades(tenant_id=self.ctx_b.tenant_id, db=self.db), [])
        self.assertEqual(ciclo_hidrico.listar_fornecedores(tenant_id=self.ctx_b.tenant_id, db=self.db), [])
        self.assertEqual(ciclo_hidrico.listar_reguladores(tenant_id=self.ctx_b.tenant_id, db=self.db), [])
        with self.assertRaises(HTTPException) as err_prop_b:
            ciclo_hidrico.excluir_propriedade(prop_a.id_property, tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual(err_prop_b.exception.status_code, 404)

        # 2. Áreas de Descarte (Area_Of_Disposal): uma homologada e outra não homologada
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
        self.assertEqual(len(ciclo_hidrico.listar_areas_descarte(tenant_id=self.ctx_a.tenant_id, db=self.db)), 2)
        self.assertEqual(ciclo_hidrico.listar_areas_descarte(tenant_id=self.ctx_b.tenant_id, db=self.db), [])

        # 3. Laudos Físico-Químicos (Measurement) avaliados com IA + CONAMA 430
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

        # 4. Lote Hídrico (Water_Batch), Admissão (Water_Admission) e Armazenamento (Water_Storage)
        lote_a = ciclo_hidrico.criar_lote(
            schemas.WaterBatchCriar(id_seller=seller_a.id_seller, id_property=prop_a.id_property),
            tenant_id=self.ctx_a.tenant_id,
            db=self.db,
        )
        adm_a = ciclo_hidrico.criar_admissao(
            schemas.WaterAdmissionCriar(
                id_batch=lote_a["id_batch"],
                volume_admitted=5000.0,
                id_measurement=laudo_limpo["id_measurement"],
            ),
            ctx=self.ctx_a,
            db=self.db,
        )
        self.assertEqual(adm_a["volume_admitted"], 5000.0)

        sto_a = ciclo_hidrico.criar_armazenamento(
            schemas.WaterStorageCriar(
                id_property=prop_a.id_property,
                volume_stored=3200.0,
                id_measurement=laudo_limpo["id_measurement"],
            ),
            ctx=self.ctx_a,
            db=self.db,
        )
        self.assertEqual(sto_a["volume_stored"], 3200.0)

        # 5. Descarte regular (área homologada + laudo conforme) -> NÃO gera alerta nem ocorrência
        alerts_before = len(alertas.listar_alertas(severidade=None, tenant_id=self.ctx_a.tenant_id, db=self.db))
        occs_before = len(ocorrencias.listar_ocorrencias(tenant_id=self.ctx_a.tenant_id, db=self.db))

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
        self.assertIsNone(desc_ok["generated_occurrence_code"])
        self.assertEqual(
            len(alertas.listar_alertas(severidade=None, tenant_id=self.ctx_a.tenant_id, db=self.db)),
            alerts_before,
        )

        # 6. Descarte irregular (área não homologada + laudo poluído) -> GERA Alert + Occurrence + History_Event
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
        self.assertEqual(
            len(alertas.listar_alertas(severidade=None, tenant_id=self.ctx_a.tenant_id, db=self.db)),
            alerts_before + 1,
        )
        self.assertEqual(len(ocorrencias.listar_ocorrencias(tenant_id=self.ctx_a.tenant_id, db=self.db)), occs_before + 1)

        # 7. Resumo consolidado do Ciclo Hídrico e isolamento total contra Tenant Beta
        resumo_a = ciclo_hidrico.obter_resumo_ciclo(tenant_id=self.ctx_a.tenant_id, db=self.db)
        self.assertEqual(resumo_a["total_admitted_m3"], 5000.0)
        self.assertEqual(resumo_a["total_stored_m3"], 3200.0)
        self.assertEqual(resumo_a["total_disposed_m3"], 2000.0)
        self.assertEqual(resumo_a["net_balance_m3"], 3000.0)
        self.assertEqual(resumo_a["areas_count"], 2)
        self.assertEqual(resumo_a["validated_areas_count"], 1)
        self.assertEqual(resumo_a["measurements_count"], 2)
        self.assertEqual(resumo_a["conama_compliance_pct"], 50.0)

        resumo_b = ciclo_hidrico.obter_resumo_ciclo(tenant_id=self.ctx_b.tenant_id, db=self.db)
        self.assertEqual(resumo_b["total_admitted_m3"], 0.0)
        self.assertEqual(resumo_b["measurements_count"], 0)
        self.assertEqual(resumo_b["areas_count"], 0)

        # Bloqueio de referência cruzada entre tenants (Tenant Beta tentando usar lote/área de Alpha)
        with self.assertRaises(HTTPException) as err_cross:
            ciclo_hidrico.criar_descarte(
                schemas.WaterDisposalCriar(
                    id_disposal_area=area_ok["id_disposal_area"],
                    volume_disposed=100.0,
                ),
                ctx=self.ctx_b,
                db=self.db,
            )
        self.assertEqual(err_cross.exception.status_code, 404)

        # 8. Seed de demonstração popula as 9 tabelas isoladamente para Tenant Beta sem afetar Alpha
        seed_b = ciclo_hidrico.popular_dados_exemplo(ctx=self.ctx_b, db=self.db)
        self.assertTrue(seed_b["success"])
        self.assertEqual(seed_b["summary"]["properties_count"], 2)
        self.assertEqual(seed_b["summary"]["sellers_count"], 2)
        self.assertEqual(seed_b["summary"]["regulators_count"], 2)
        self.assertEqual(seed_b["summary"]["batches_count"], 2)
        self.assertEqual(seed_b["summary"]["areas_count"], 2)
        self.assertEqual(seed_b["summary"]["measurements_count"], 3)
        self.assertEqual(seed_b["summary"]["admissions_count"], 1)
        self.assertEqual(seed_b["summary"]["storages_count"], 1)
        self.assertEqual(seed_b["summary"]["disposals_count"], 1)
        self.assertEqual(
            ciclo_hidrico.obter_resumo_ciclo(tenant_id=self.ctx_a.tenant_id, db=self.db)["properties_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
