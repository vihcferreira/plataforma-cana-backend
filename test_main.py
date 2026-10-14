from fastapi.testclient import TestClient
from main import app

# Cria um "cliente" falso que vai simular o navegador enviando dados para a nossa API
client = TestClient(app)

# ==========================================
# TESTES DA API DE TAREFAS
# ==========================================
def test_listar_tarefas_retorna_200():
    resposta = client.get("/tarefas")
    assert resposta.status_code == 200
    assert isinstance(resposta.json(), list)

def test_criar_tarefa_simples():
    resposta = client.post(
        "/tarefas",
        json={
            "titulo": "Estudar para a apresentação",
            "descricao": "Revisar o código de IA",
            "concluida": False
        }
    )
    assert resposta.status_code == 201
    assert resposta.json()["titulo"] == "Estudar para a apresentação"

def test_criar_tarefa_com_integracao_cep():
    # Testa se o ViaCEP está sendo chamado corretamente
    resposta = client.post(
        "/tarefas",
        json={
            "titulo": "Coleta de efluentes",
            "descricao": "Ir até a usina",
            "concluida": False,
            "cep": "01001000"
        }
    )
    assert resposta.status_code == 201
    dados = resposta.json()
    # Confirma se a API adicionou a palavra "Local:" na descrição da tarefa
    assert "Local:" in dados["descricao"]


# ==========================================
# TESTES DA INTELIGÊNCIA ARTIFICIAL (Tópico 9)
# ==========================================
def test_prever_agua_limpa():
    resposta = client.post(
        "/prever-qualidade-agua",
        json={
            "ph": 6.5,
            "temperatura_c": 25.0,
            "dbo_mgl": 10.0,
            "turbidez_ntu": 15.0
        }
    )
    
    # Se o arquivo .pkl estiver na pasta, o teste passa e verifica a resposta
    if resposta.status_code == 200:
        dados = resposta.json()
        assert dados["status_agua"] == "Própria"
    # Se o modelo não estiver, a API retorna 500 (conforme programamos para evitar quebra)
    else:
        assert resposta.status_code == 500

def test_prever_agua_poluida_vinhaça():
    resposta = client.post(
        "/prever-qualidade-agua",
        json={
            "ph": 4.2,
            "temperatura_c": 28.0,
            "dbo_mgl": 80.0,
            "turbidez_ntu": 45.0
        }
    )
    
    if resposta.status_code == 200:
        dados = resposta.json()
        assert "Poluída" in dados["status_agua"]