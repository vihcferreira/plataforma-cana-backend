from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Dict
from auth_tenant import get_current_tenant
from schemas import TarefaCriar, TarefaAtualizar, TarefaResposta
import httpx
import random
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tarefas"])

# ==========================================
# BANCO DE DADOS EM MEMÓRIA ISOLADO POR TENANT
# ==========================================
banco_tarefas_por_tenant: Dict[str, Dict[int, dict]] = {}
contadores_por_tenant: Dict[str, int] = {}


def _obter_banco_do_tenant(tenant_id: str) -> Dict[int, dict]:
    if tenant_id not in banco_tarefas_por_tenant:
        banco_tarefas_por_tenant[tenant_id] = {}
        contadores_por_tenant[tenant_id] = 0
    return banco_tarefas_por_tenant[tenant_id]


# ==========================================
# FUNÇÕES DE INTEGRAÇÃO (SERVIÇOS EXTERNOS)
# ==========================================
def buscar_endereco_por_cep(cep: str):
    try:
        resposta = httpx.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=3.0)
        if resposta.status_code == 200 and "erro" not in resposta.json():
            dados = resposta.json()
            return f"{dados['logradouro']}, {dados['bairro']} - {dados['localidade']}/{dados['uf']}"
    except Exception:
        pass
    return "Endereço não encontrado"


def ia_prever_esforco(descricao: Optional[str]):
    dias = random.randint(1, 5) if descricao else 1
    return f"Previsão da IA: {dias} dia(s) para conclusão."


def notificar_conclusao_email(titulo: str):
    logger.info(f"📧 [E-MAIL ENVIADO] A tarefa '{titulo}' foi marcada como concluída!")


# ==========================================
# ROTAS DE TAREFAS (ISOLADAS POR TENANT)
# ==========================================
@router.get("/", response_model=List[TarefaResposta])
def listar_tarefas(
    concluida: Optional[bool] = Query(None),
    busca: Optional[str] = Query(None),
    tenant_id: str = Depends(get_current_tenant),
):
    banco = _obter_banco_do_tenant(tenant_id)
    tarefas = list(banco.values())
    if concluida is not None:
        tarefas = [t for t in tarefas if t["concluida"] == concluida]
    if busca:
        tarefas = [t for t in tarefas if busca.lower() in t["titulo"].lower()]
    return tarefas


@router.get("/{tarefa_id}", response_model=TarefaResposta)
def buscar_tarefa(
    tarefa_id: int,
    tenant_id: str = Depends(get_current_tenant),
):
    banco = _obter_banco_do_tenant(tenant_id)
    if tarefa_id not in banco:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return banco[tarefa_id]


@router.post("/", response_model=TarefaResposta, status_code=status.HTTP_201_CREATED)
def criar_tarefa(
    dados: TarefaCriar,
    tenant_id: str = Depends(get_current_tenant),
):
    banco = _obter_banco_do_tenant(tenant_id)
    contadores_por_tenant[tenant_id] += 1
    novo_id = contadores_por_tenant[tenant_id]

    endereco = buscar_endereco_por_cep(dados.cep) if dados.cep else None
    previsao = ia_prever_esforco(dados.descricao)

    descricao_completa = f"{dados.descricao or ''} | {previsao}"
    if endereco:
        descricao_completa += f" | Local: {endereco}"

    nova_tarefa = {
        "id": novo_id,
        "titulo": dados.titulo,
        "descricao": descricao_completa,
        "concluida": dados.concluida,
    }
    banco[novo_id] = nova_tarefa
    logger.info(f"Tarefa {novo_id} criada para tenant {tenant_id[:8]}.")
    return nova_tarefa


@router.put("/{tarefa_id}", response_model=TarefaResposta)
def atualizar_tarefa(
    tarefa_id: int,
    dados: TarefaAtualizar,
    tenant_id: str = Depends(get_current_tenant),
):
    banco = _obter_banco_do_tenant(tenant_id)
    if tarefa_id not in banco:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")

    tarefa = banco[tarefa_id]
    foi_concluida_agora = (dados.concluida is True) and (tarefa["concluida"] is False)

    dados_dict = dados.model_dump(exclude_unset=True)
    for campo, valor in dados_dict.items():
        tarefa[campo] = valor

    if foi_concluida_agora:
        notificar_conclusao_email(tarefa["titulo"])

    return tarefa


@router.delete("/{tarefa_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_tarefa(
    tarefa_id: int,
    tenant_id: str = Depends(get_current_tenant),
):
    banco = _obter_banco_do_tenant(tenant_id)
    if tarefa_id not in banco:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    del banco[tarefa_id]
    return None
