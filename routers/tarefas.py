from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Optional, Dict
from schemas import TarefaCriar, TarefaAtualizar, TarefaResposta
import httpx
import random
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tarefas"])

# ==========================================
# BANCO DE DADOS EM MEMÓRIA
# ==========================================
banco_tarefas: Dict[int, dict] = {
    1: {"id": 1, "titulo": "Definir contratos da API", "descricao": "Alinhar schemas", "concluida": True},
}
contador_id: int = 1

# ==========================================
# FUNÇÕES DE INTEGRAÇÃO (SERVIÇOS EXTERNOS)
# ==========================================
def buscar_endereco_por_cep(cep: str):
    try:
        resposta = httpx.get(f"https://viacep.com.br/ws/{cep}/json/")
        if resposta.status_code == 200 and "erro" not in resposta.json():
            dados = resposta.json()
            return f"{dados['logradouro']}, {dados['bairro']} - {dados['localidade']}/{dados['uf']}"
    except Exception:
        pass
    return "Endereço não encontrado"

def ia_prever_esforco(descricao: str):
    dias = random.randint(1, 5) if descricao else 1
    return f"Previsão da IA: {dias} dia(s) para conclusão."

def notificar_conclusao_email(titulo: str):
    logger.info(f"📧 [E-MAIL ENVIADO] A tarefa '{titulo}' foi marcada como concluída!")

# ==========================================
# ROTAS DE TAREFAS
# ==========================================
@router.get("/", response_model=List[TarefaResposta])
def listar_tarefas(concluida: Optional[bool] = Query(None), busca: Optional[str] = Query(None)):
    tarefas = list(banco_tarefas.values())
    if concluida is not None:
        tarefas = [t for t in tarefas if t["concluida"] == concluida]
    if busca:
        tarefas = [t for t in tarefas if busca.lower() in t["titulo"].lower()]
    return tarefas

@router.get("/{tarefa_id}", response_model=TarefaResposta)
def buscar_tarefa(tarefa_id: int):
    if tarefa_id not in banco_tarefas:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return banco_tarefas[tarefa_id]

@router.post("/", response_model=TarefaResposta, status_code=status.HTTP_201_CREATED)
def criar_tarefa(dados: TarefaCriar):
    global contador_id
    contador_id += 1
    
    endereco = buscar_endereco_por_cep(dados.cep) if dados.cep else None
    previsao = ia_prever_esforco(dados.descricao)
    
    descricao_completa = f"{dados.descricao} | {previsao}"
    if endereco:
        descricao_completa += f" | Local: {endereco}"

    nova_tarefa = {
        "id": contador_id,
        "titulo": dados.titulo,
        "descricao": descricao_completa,
        "concluida": dados.concluida
    }
    banco_tarefas[contador_id] = nova_tarefa
    logger.info(f"Tarefa {contador_id} criada. Integrada com ViaCEP.")
    return nova_tarefa

@router.put("/{tarefa_id}", response_model=TarefaResposta)
def atualizar_tarefa(tarefa_id: int, dados: TarefaAtualizar):
    if tarefa_id not in banco_tarefas:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    
    tarefa = banco_tarefas[tarefa_id]
    foi_concluida_agora = (dados.concluida is True) and (tarefa["concluida"] is False)
    
    dados_dict = dados.model_dump(exclude_unset=True)
    for campo, valor in dados_dict.items():
        tarefa[campo] = valor
        
    if foi_concluida_agora:
        notificar_conclusao_email(tarefa["titulo"])

    return tarefa

@router.delete("/{tarefa_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_tarefa(tarefa_id: int):
    if tarefa_id not in banco_tarefas:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    del banco_tarefas[tarefa_id]
    APIRouter, HTTPException, status, Query
from typing import List, Optional, Dict
from schemas import TarefaCriar, TarefaAtualizar, TarefaResposta
import httpx
import random
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tarefas"])

# ==========================================
# BANCO DE DADOS EM MEMÓRIA
# ==========================================
banco_tarefas: Dict[int, dict] = {
    1: {"id": 1, "titulo": "Definir contratos da API", "descricao": "Alinhar schemas", "concluida": True},
}
contador_id: int = 1

# ==========================================
# FUNÇÕES DE INTEGRAÇÃO (SERVIÇOS EXTERNOS)
# ==========================================
def buscar_endereco_por_cep(cep: str):
    try:
        resposta = httpx.get(f"https://viacep.com.br/ws/{cep}/json/")
        if resposta.status_code == 200 and "erro" not in resposta.json():
            dados = resposta.json()
            return f"{dados['logradouro']}, {dados['bairro']} - {dados['localidade']}/{dados['uf']}"
    except Exception:
        pass
    return "Endereço não encontrado"

def ia_prever_esforco(descricao: str):
    dias = random.randint(1, 5) if descricao else 1
    return f"Previsão da IA: {dias} dia(s) para conclusão."

def notificar_conclusao_email(titulo: str):
    logger.info(f"📧 [E-MAIL ENVIADO] A tarefa '{titulo}' foi marcada como concluída!")

# ==========================================
# ROTAS DE TAREFAS
# ==========================================
@router.get("/", response_model=List[TarefaResposta])
def listar_tarefas(concluida: Optional[bool] = Query(None), busca: Optional[str] = Query(None)):
    tarefas = list(banco_tarefas.values())
    if concluida is not None:
        tarefas = [t for t in tarefas if t["concluida"] == concluida]
    if busca:
        tarefas = [t for t in tarefas if busca.lower() in t["titulo"].lower()]
    return tarefas

@router.get("/{tarefa_id}", response_model=TarefaResposta)
def buscar_tarefa(tarefa_id: int):
    if tarefa_id not in banco_tarefas:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return banco_tarefas[tarefa_id]

@router.post("/", response_model=TarefaResposta, status_code=status.HTTP_201_CREATED)
def criar_tarefa(dados: TarefaCriar):
    global contador_id
    contador_id += 1
    
    endereco = buscar_endereco_por_cep(dados.cep) if dados.cep else None
    previsao = ia_prever_esforco(dados.descricao)
    
    descricao_completa = f"{dados.descricao} | {previsao}"
    if endereco:
        descricao_completa += f" | Local: {endereco}"

    nova_tarefa = {
        "id": contador_id,
        "titulo": dados.titulo,
        "descricao": descricao_completa,
        "concluida": dados.concluida
    }
    banco_tarefas[contador_id] = nova_tarefa
    logger.info(f"Tarefa {contador_id} criada. Integrada com ViaCEP.")
    return nova_tarefa

@router.put("/{tarefa_id}", response_model=TarefaResposta)
def atualizar_tarefa(tarefa_id: int, dados: TarefaAtualizar):
    if tarefa_id not in banco_tarefas:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    
    tarefa = banco_tarefas[tarefa_id]
    foi_concluida_agora = (dados.concluida is True) and (tarefa["concluida"] is False)
    
    dados_dict = dados.model_dump(exclude_unset=True)
    for campo, valor in dados_dict.items():
        tarefa[campo] = valor
        
    if foi_concluida_agora:
        notificar_conclusao_email(tarefa["titulo"])

    return tarefa

@router.delete("/{tarefa_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_tarefa(tarefa_id: int):
    if tarefa_id not in banco_tarefas:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    del banco_tarefas[tarefa_id]
    return None