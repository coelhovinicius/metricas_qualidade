"""
Cliente para buscar work items diretamente do Azure DevOps (REST API), como
alternativa a exportar/importar o CSV manualmente.

Reaproveita a MESMA query salva já usada hoje para a exportação manual - o
resultado sai com exatamente as mesmas colunas do CSV exportado (ID, Work
Item Type, Title, Assigned To, State, Tags, Created Date, Severity, Area
Path), então o restante do pipeline (`core.column_mapper` / `core.analytics`)
não precisa de nenhum ajuste: os dois caminhos (upload manual e busca
automática) convergem pro mesmo dataframe/mapeamento.

Configuração (nunca no código - sempre em `st.secrets`):

    [azure_devops]
    organization = "sua-organizacao"
    project = "SeuProjeto"
    query_id = "id-da-query-salva"
    pat = "seu-personal-access-token"

Localmente isso vai em `.streamlit/secrets.toml` (arquivo que NÃO deve ser
versionado no Git - conferir se já está no .gitignore). Em produção, na
seção "Secrets" da plataforma onde o app está publicado (o mesmo lugar onde
já fica configurado o `[auth] cookie_key`, ver `auth/auth_manager.py`).

Como descobrir organization / project / query_id: são as três partes que
aparecem na URL da query salva no navegador, no formato
    https://dev.azure.com/{organization}/{project}/_queries/query/{query_id}/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests
import streamlit as st

API_VERSION = "7.1"
TAMANHO_LOTE = 200  # limite de IDs por chamada da API de workitemsbatch
TIMEOUT_SEGUNDOS = 30

# Campos buscados na API do Azure DevOps, mapeados para os mesmos nomes de
# coluna do export manual em CSV - é o que permite reaproveitar 100% do
# `column_mapper`/`analytics` sem nenhum tratamento especial pra essa origem.
CAMPOS_API_PARA_COLUNA = {
    "System.Id": "ID",
    "System.WorkItemType": "Work Item Type",
    "System.Title": "Title",
    "System.AssignedTo": "Assigned To",
    "System.State": "State",
    "System.Tags": "Tags",
    "System.CreatedDate": "Created Date",
    "Microsoft.VSTS.Common.Severity": "Severity",
    "System.AreaPath": "Area Path",
}


class AzureDevOpsError(Exception):
    """Erro amigável de configuração/comunicação com a API do Azure DevOps."""


@dataclass
class ConfiguracaoAzureDevOps:
    organization: str
    project: str
    query_id: str
    pat: str


def configuracao_disponivel() -> bool:
    """True quando os 4 campos obrigatórios de [azure_devops] estão presentes em st.secrets."""
    try:
        config = st.secrets.get("azure_devops")
    except Exception:
        # st.secrets pode levantar exceção quando não existe secrets.toml
        # configurado - mesmo comportamento já tratado em auth_manager.py.
        return False
    if not config:
        return False
    campos_obrigatorios = ("organization", "project", "query_id", "pat")
    return all(config.get(campo) for campo in campos_obrigatorios)


def _carregar_configuracao() -> ConfiguracaoAzureDevOps:
    if not configuracao_disponivel():
        raise AzureDevOpsError(
            "As credenciais do Azure DevOps não estão configuradas. Adicione a seção "
            "[azure_devops] (organization, project, query_id, pat) nos Secrets do "
            "Streamlit antes de usar a busca automática."
        )
    config = st.secrets["azure_devops"]
    return ConfiguracaoAzureDevOps(
        organization=config["organization"],
        project=config["project"],
        query_id=config["query_id"],
        pat=config["pat"],
    )


def _autenticacao(config: ConfiguracaoAzureDevOps) -> tuple[str, str]:
    # A API do Azure DevOps aceita o PAT como "senha" em Basic Auth, com usuário vazio.
    return ("", config.pat)


def _tratar_erro_http(resposta: requests.Response) -> None:
    if resposta.status_code == 401:
        raise AzureDevOpsError(
            "O Azure DevOps recusou a autenticação (401) - o PAT configurado está "
            "inválido, expirado ou sem permissão de leitura em Work Items. Gere um "
            "novo Personal Access Token e atualize o secrets.toml."
        )
    if resposta.status_code == 404:
        raise AzureDevOpsError(
            "Organização, projeto ou query não encontrados (404). Confira os valores "
            "de organization/project/query_id em [azure_devops] nos Secrets."
        )
    if not resposta.ok:
        raise AzureDevOpsError(
            f"O Azure DevOps retornou um erro inesperado ({resposta.status_code}): "
            f"{resposta.text[:300]}"
        )


def _buscar_ids_da_query(config: ConfiguracaoAzureDevOps) -> list[int]:
    url = (
        f"https://dev.azure.com/{config.organization}/{config.project}"
        f"/_apis/wit/wiql/{config.query_id}?api-version={API_VERSION}"
    )
    try:
        resposta = requests.get(url, auth=_autenticacao(config), timeout=TIMEOUT_SEGUNDOS)
    except requests.RequestException as exc:
        raise AzureDevOpsError(f"Não foi possível conectar ao Azure DevOps: {exc}") from exc

    _tratar_erro_http(resposta)
    corpo = resposta.json()

    # Query "flat" (lista simples) -> "workItems"; query com hierarquia
    # (ex.: árvore de Test Plan/Suite/Case) -> "workItemRelations".
    itens = corpo.get("workItems") or corpo.get("workItemRelations") or []
    ids = []
    for item in itens:
        if "id" in item:
            ids.append(item["id"])
        elif item.get("target", {}).get("id"):
            ids.append(item["target"]["id"])
    return ids


def _buscar_campos_em_lotes(config: ConfiguracaoAzureDevOps, ids: list[int]) -> list[dict]:
    url = f"https://dev.azure.com/{config.organization}/_apis/wit/workitemsbatch?api-version={API_VERSION}"
    campos = list(CAMPOS_API_PARA_COLUNA.keys())
    resultados: list[dict] = []

    for inicio in range(0, len(ids), TAMANHO_LOTE):
        lote = ids[inicio : inicio + TAMANHO_LOTE]
        try:
            resposta = requests.post(
                url,
                auth=_autenticacao(config),
                json={"ids": lote, "fields": campos},
                timeout=TIMEOUT_SEGUNDOS,
            )
        except requests.RequestException as exc:
            raise AzureDevOpsError(f"Falha ao buscar work items do Azure DevOps: {exc}") from exc

        _tratar_erro_http(resposta)
        resultados.extend(resposta.json().get("value", []))

    return resultados


def _formatar_pessoa(valor: Optional[dict]) -> Optional[str]:
    """
    Converte o objeto de identidade da API ({"displayName": ..., "uniqueName": ...})
    no mesmo formato "Nome <email>" usado no export manual do Azure DevOps -
    assim `extrair_nome_de_email` (core/column_mapper.py) funciona igual nas duas origens.
    """
    if not valor:
        return None
    nome = valor.get("displayName")
    email = valor.get("uniqueName") or valor.get("mailAddress")
    if nome and email:
        return f"{nome} <{email}>"
    return nome or email


def _formatar_data(valor: Optional[str]) -> Optional[str]:
    """Converte o timestamp ISO 8601 da API pro mesmo formato dd/mm/aaaa hh:mm:ss do export manual."""
    if not valor:
        return None
    data = pd.to_datetime(valor, errors="coerce", utc=True)
    if pd.isna(data):
        return valor
    return data.strftime("%d/%m/%Y %H:%M:%S")


def _montar_dataframe(itens_api: list[dict]) -> pd.DataFrame:
    linhas = []
    for item in itens_api:
        campos = item.get("fields", {})
        linha = {}
        for campo_api, coluna in CAMPOS_API_PARA_COLUNA.items():
            valor = campos.get(campo_api)
            if campo_api == "System.AssignedTo":
                valor = _formatar_pessoa(valor)
            elif campo_api == "System.CreatedDate":
                valor = _formatar_data(valor)
            linha[coluna] = valor
        linhas.append(linha)

    colunas_ordenadas = list(CAMPOS_API_PARA_COLUNA.values())
    df = pd.DataFrame(linhas, columns=colunas_ordenadas)

    # Mesma limpeza de texto do core/data_loader.py: remove espaços extras
    # preservando valores vazios como nulo de verdade (nunca a string "nan").
    colunas_texto = df.select_dtypes(include="object").columns
    for coluna in colunas_texto:
        df[coluna] = df[coluna].apply(lambda valor: valor if pd.isna(valor) else str(valor).strip())

    return df


def buscar_work_items_da_query() -> pd.DataFrame:
    """
    Busca todos os work items da query salva configurada em `st.secrets`, e
    devolve um DataFrame com as mesmas colunas do export manual em CSV.

    Levanta `AzureDevOpsError` (mensagem amigável, pronta pra exibir na
    interface) em caso de configuração ausente/inválida ou falha de
    comunicação com a API.
    """
    config = _carregar_configuracao()
    ids = _buscar_ids_da_query(config)
    if not ids:
        return pd.DataFrame(columns=list(CAMPOS_API_PARA_COLUNA.values()))

    itens_api = _buscar_campos_em_lotes(config, ids)
    return _montar_dataframe(itens_api)
