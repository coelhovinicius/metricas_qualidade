"""
Cliente para buscar work items diretamente do Azure DevOps (REST API), como
alternativa a exportar/importar o CSV manualmente.

Arquitetura de credenciais (v2 - PAT por usuário, nunca em Secrets):
    O Personal Access Token (PAT) NUNCA fica em `st.secrets`/`secrets.toml` -
    cada usuário cola o seu próprio PAT em um campo de senha na tela de
    importação (ver `ui/pages/upload_page.py`). O PAT fica só em
    `st.session_state` (memória do processo daquela sessão do navegador,
    nunca gravado em disco/banco), some ao fazer logout/fechar a aba, e cada
    requisição à API do Azure DevOps é feita com o PAT de quem está logado -
    o que dá rastreabilidade real: o log de acesso do Azure DevOps mostra o
    usuário dono do PAT usado, não uma conta de serviço compartilhada.

Organização / Projeto / Area Path / Query também não são mais fixos em
`secrets.toml`: são escolhidos dentro do app, em cascata (organização ->
projeto -> area path opcional -> query existente), cada passo consultando a
API do Azure DevOps com o PAT informado. A criação de queries novas continua
acontecendo na própria interface do Azure DevOps (ver `montar_link_criacao_query`),
não dentro deste app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests

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
    "System.BoardColumn": "Board Column",
    # Iteration Path é o nome que o Azure DevOps dá ao campo de Sprint - a
    # mesma lógica de hierarquia ("Projeto\Sprint 24") já tratada para o
    # Area Path também se aplica aqui (ver `column_mapper.simplificar_valor_projeto`,
    # reaproveitado em `_montar_dataframe` para esta coluna).
    "System.IterationPath": "Sprint",
}

# Campos auxiliares, buscados na API mas que não viram coluna própria no
# arquivo final - usados só internamente (ver `_completar_board_column_via_item_pai`).
_CAMPO_PARENT = "System.Parent"
_CAMPO_BOARD_COLUMN = "System.BoardColumn"

# Campos ocultos do Azure DevOps que controlam a ordem vertical dos itens
# dentro de cada Coluna do Board/backlog - "Stack Rank" nos processos Agile/
# Basic/CMMI, "Backlog Priority" no processo Scrum (o nome depende de qual
# processo a organização usa; só um dos dois costuma vir preenchido, nunca os
# dois ao mesmo tempo). Quanto MENOR o valor, mais ACIMA o item fica no board
# - contraintuitivo, mas é assim que o próprio Azure DevOps funciona. Não
# aparecem no formulário do work item por padrão, então normalmente não vêm
# em export manual/CSV - só são buscados aqui, pela API.
_CAMPO_STACK_RANK = "Microsoft.VSTS.Common.StackRank"
_CAMPO_BACKLOG_PRIORITY = "Microsoft.VSTS.Common.BacklogPriority"
COLUNA_PRIORIDADE_BOARD = "Prioridade (posição no board)"


class AzureDevOpsError(Exception):
    """Erro amigável de configuração/comunicação com a API do Azure DevOps."""


@dataclass
class Projeto:
    id: str
    nome: str


@dataclass
class ItemQuery:
    id: str
    nome: str
    caminho: str  # ex.: "Shared Queries/QA/Bugs em aberto"


def _autenticacao(pat: str) -> tuple[str, str]:
    # A API do Azure DevOps aceita o PAT como "senha" em Basic Auth, com usuário vazio.
    return ("", pat)


def _tratar_erro_http(resposta: requests.Response) -> None:
    if resposta.status_code == 401:
        raise AzureDevOpsError(
            "O Azure DevOps recusou a autenticação (401) - o seu PAT está inválido, "
            "expirado ou sem permissão de leitura em Work Items. Gere um novo Personal "
            "Access Token (escopo mínimo: Work Items · Read) e cole novamente no campo "
            "de PAT."
        )
    if resposta.status_code == 403:
        raise AzureDevOpsError(
            "Seu PAT não tem permissão para acessar este recurso (403). Confira se o "
            "token tem o escopo 'Work Items (Read)' e se sua conta tem acesso a este "
            "projeto no Azure DevOps."
        )
    if resposta.status_code == 404:
        raise AzureDevOpsError(
            "Organização, projeto, area path ou query não encontrados (404). Confira os "
            "valores escolhidos - ou, se acabou de criar a query no Azure DevOps, recarregue "
            "a lista de queries."
        )
    if not resposta.ok:
        raise AzureDevOpsError(
            f"O Azure DevOps retornou um erro inesperado ({resposta.status_code}): "
            f"{resposta.text[:300]}"
        )


_MARCADORES_PAGINA_DE_LOGIN = (
    "sign in",
    "idsrv",
    "login.microsoftonline",
    "login.live.com",
)


def _decodificar_json(resposta: requests.Response) -> dict:
    """
    Faz `resposta.json()` de forma segura, convertendo uma falha de decodificação
    num `AzureDevOpsError` (com uma mensagem que ajuda a diagnosticar o motivo)
    em vez de deixar o `JSONDecodeError` cru estourar - esse erro cru não é
    pego pelos `except AzureDevOpsError` espalhados pela interface, então
    derrubava a página inteira do Streamlit em vez de mostrar um aviso.

    HTTP "OK" (2xx, às vezes especificamente 203) com corpo que não é JSON
    válido geralmente significa que a resposta não veio da API de verdade, e
    sim de uma camada na frente dela. Dois casos são tratados separadamente:

    1) A própria tela de login do Azure DevOps/Microsoft (título "Sign In",
       domínio de login da Microsoft, etc.) - na prática, o caso mais comum
       de longe: o PAT está errado, expirado, foi colado com espaço/quebra de
       linha a mais, ou o nome da Organização não existe. O Azure DevOps não
       devolve um 401 limpo nesse caso - devolve "sucesso" (às vezes HTTP 203)
       com essa página de login no lugar dos dados.
    2) Qualquer outra página HTML não reconhecida - aí sim entra a hipótese
       de uma política de Conditional Access/restrição de IP no Azure AD da
       organização, que bloqueia o servidor onde este app está rodando
       (diferente da rede de onde foi testado localmente).
    """
    try:
        return resposta.json()
    except ValueError as exc:
        trecho = resposta.text[:300].strip()
        trecho_lower = trecho.lower()
        eh_html = "<html" in trecho_lower or "<!doctype html" in trecho_lower

        if eh_html and any(marcador in trecho_lower for marcador in _MARCADORES_PAGINA_DE_LOGIN):
            raise AzureDevOpsError(
                "O Azure DevOps não aceitou a requisição e devolveu a própria tela de login "
                "em vez dos dados - normalmente isso quer dizer que o PAT está errado, "
                "expirado, foi colado com algum espaço/quebra de linha a mais, ou que o nome "
                "da Organização não existe ou está digitado diferente do que aparece em "
                "dev.azure.com. Confira esses dois pontos: gere um novo Personal Access Token "
                "(escopo mínimo: Work Items · Read) em dev.azure.com → foto de perfil → "
                "Personal Access Tokens, e confira o nome exato da organização."
            ) from exc

        pista = ""
        if eh_html:
            pista = (
                " O Azure DevOps devolveu uma página HTML em vez de dados - isso costuma "
                "acontecer quando a organização tem uma política de Conditional Access ou "
                "restrição de IP no Azure AD que bloqueia o servidor onde este app está "
                "rodando (diferente da rede de onde você testou localmente). Vale confirmar "
                "com quem administra o Azure AD/Azure DevOps da organização se existe essa "
                "restrição, e se o endereço de onde o app roda pode ser liberado."
            )
        raise AzureDevOpsError(
            f"O Azure DevOps respondeu (HTTP {resposta.status_code}), mas o conteúdo não é "
            f"um JSON válido.{pista} Início da resposta recebida: \"{trecho}\""
        ) from exc


def _get(url: str, pat: str) -> dict:
    try:
        resposta = requests.get(url, auth=_autenticacao(pat), timeout=TIMEOUT_SEGUNDOS)
    except requests.RequestException as exc:
        raise AzureDevOpsError(f"Não foi possível conectar ao Azure DevOps: {exc}") from exc
    _tratar_erro_http(resposta)
    return _decodificar_json(resposta)


def listar_projetos(organization: str, pat: str) -> list[Projeto]:
    """Lista os Team Projects visíveis para o PAT informado, dentro da organização escolhida."""
    if not organization or not pat:
        raise AzureDevOpsError("Informe a organização e o PAT antes de carregar os projetos.")
    url = f"https://dev.azure.com/{organization}/_apis/projects?api-version={API_VERSION}&$top=1000"
    corpo = _get(url, pat)
    projetos = [Projeto(id=item["id"], nome=item["name"]) for item in corpo.get("value", [])]
    return sorted(projetos, key=lambda projeto: projeto.nome.lower())


def listar_area_paths(organization: str, project: str, pat: str) -> list[str]:
    """
    Lista os Area Paths (achatados em string, ex.: 'Produto\\Time A\\Sub-time') do
    projeto escolhido, na mesma notação usada no export manual em CSV.
    """
    url = (
        f"https://dev.azure.com/{organization}/{project}/_apis/wit/classificationnodes/areas"
        f"?api-version={API_VERSION}&$depth=20"
    )
    raiz = _get(url, pat)

    caminhos: list[str] = []

    def _percorrer(no: dict, caminho_atual: str) -> None:
        nome = no.get("name", "")
        caminho = f"{caminho_atual}\\{nome}" if caminho_atual else nome
        caminhos.append(caminho)
        for filho in no.get("children", []) or []:
            _percorrer(filho, caminho)

    _percorrer(raiz, "")
    return caminhos


def listar_queries(organization: str, project: str, pat: str) -> list[ItemQuery]:
    """
    Lista as queries salvas (pastas 'Shared Queries' e 'My Queries') do projeto,
    achatando a árvore de pastas em uma lista única com o caminho completo.

    A API só expande a árvore até o `$depth` pedido (aqui, 2 níveis) - uma pasta
    que tenha filhos além disso volta com `hasChildren: true` mas `children`
    vazio/ausente. Pra não perder queries guardadas em subpastas mais fundas
    (ex.: "Shared Queries/QA/Sprint 23/Minha query"), qualquer pasta nessa
    situação é expandida com uma chamada extra à API (`.../_apis/wit/queries/{id}`),
    recursivamente.
    """
    raiz = _get(
        f"https://dev.azure.com/{organization}/{project}/_apis/wit/queries"
        f"?$depth=2&api-version={API_VERSION}",
        pat,
    )

    itens: list[ItemQuery] = []

    def _expandir_pasta_nao_carregada(no: dict) -> list[dict]:
        corpo = _get(
            f"https://dev.azure.com/{organization}/{project}/_apis/wit/queries/{no['id']}"
            f"?$depth=2&api-version={API_VERSION}",
            pat,
        )
        return corpo.get("children", []) or []

    def _percorrer(no: dict, profundidade: int = 0) -> None:
        if profundidade > 8:
            # Trava de segurança contra uma estrutura de pastas anormalmente
            # profunda (evita recursão/chamadas infinitas em caso de dado
            # inesperado da API) - Azure DevOps não costuma passar disso.
            return
        if no.get("isFolder"):
            filhos = no.get("children") or []
            if not filhos and no.get("hasChildren") and no.get("id"):
                filhos = _expandir_pasta_nao_carregada(no)
            for filho in filhos:
                _percorrer(filho, profundidade + 1)
        else:
            caminho = (no.get("path") or no.get("name", "")).lstrip("/")
            itens.append(ItemQuery(id=no["id"], nome=no["name"], caminho=caminho))

    for filho in raiz.get("value", []):
        _percorrer(filho)

    return itens


def montar_link_criacao_query(organization: str, project: str) -> str:
    """
    Link direto para a tela nativa de criação de query do Azure DevOps, já
    apontando para a organização/projeto escolhidos. O Azure DevOps não
    documenta parâmetros de URL para pré-preencher Area Path/filtros, então
    esse é o "melhor esforço": o usuário abre a tela certa e monta a query lá,
    com os filtros da própria interface do Azure DevOps.
    """
    return f"https://dev.azure.com/{organization}/{project}/_queries/create/"


def _buscar_ids_da_query(organization: str, project: str, query_id: str, pat: str) -> list[int]:
    url = (
        f"https://dev.azure.com/{organization}/{project}"
        f"/_apis/wit/wiql/{query_id}?api-version={API_VERSION}"
    )
    corpo = _get(url, pat)

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


def _buscar_campos_em_lotes(
    organization: str, ids: list[int], pat: str, campos: Optional[list[str]] = None
) -> list[dict]:
    url = f"https://dev.azure.com/{organization}/_apis/wit/workitemsbatch?api-version={API_VERSION}"
    # Por padrão busca todos os campos "de coluna" + o campo auxiliar do item
    # pai (usado por `_completar_board_column_via_item_pai`) + os dois campos
    # de prioridade por posição no board (só um deles vem preenchido,
    # dependendo do processo do Azure DevOps - ver `_montar_dataframe`) - mas
    # aceita uma lista de campos menor/diferente pra buscas mais enxutas (ex.:
    # buscar só a Coluna do Board de um lote de itens pai, sem os outros campos).
    campos = (
        campos
        if campos is not None
        else list(CAMPOS_API_PARA_COLUNA.keys()) + [_CAMPO_PARENT, _CAMPO_STACK_RANK, _CAMPO_BACKLOG_PRIORITY]
    )
    resultados: list[dict] = []

    for inicio in range(0, len(ids), TAMANHO_LOTE):
        lote = ids[inicio : inicio + TAMANHO_LOTE]
        try:
            resposta = requests.post(
                url,
                auth=_autenticacao(pat),
                json={"ids": lote, "fields": campos},
                timeout=TIMEOUT_SEGUNDOS,
            )
        except requests.RequestException as exc:
            raise AzureDevOpsError(f"Falha ao buscar work items do Azure DevOps: {exc}") from exc

        _tratar_erro_http(resposta)
        resultados.extend(_decodificar_json(resposta).get("value", []))

    return resultados


def _completar_board_column_via_item_pai(
    organization: str, itens_api: list[dict], pat: str
) -> list[dict]:
    """
    Preenche a Coluna do Board de itens que não têm board próprio no Azure
    DevOps (o caso mais comum: Test Case, que vive dentro de Test Plans/Test
    Suites, não no board) usando a coluna do item "pai" vinculado (ex.: o
    Bug/User Story ao qual aquele Test Case está associado como filho) quando
    esse vínculo existir e o pai estiver, ele sim, numa coluna do board.

    Sobe só UM nível (o pai direto, via `System.Parent`) - não percorre a
    árvore inteira. Cobre o caso real de longe mais comum (Test Case ligado
    direto ao User Story/Bug que ele valida); itens sem pai vinculado, ou
    cujo pai também não tem coluna de board, continuam sem coluna - não tem
    de onde mais puxar essa informação.

    Antes de fazer qualquer chamada extra à API, reaproveita a Coluna do
    Board dos itens pai que já vieram na mesma busca (comum quando a query
    já traz Bugs/User Stories junto dos Test Cases filhos deles) - só busca
    na API os pais que faltam.
    """
    coluna_por_id_pai: dict[int, Optional[str]] = {
        item["id"]: item.get("fields", {}).get(_CAMPO_BOARD_COLUMN)
        for item in itens_api
        if item.get("fields", {}).get(_CAMPO_BOARD_COLUMN)
    }

    pendentes: dict[int, list[dict]] = {}
    for item in itens_api:
        campos = item.get("fields", {})
        if campos.get(_CAMPO_BOARD_COLUMN):
            continue
        parent_id = campos.get(_CAMPO_PARENT)
        if parent_id:
            pendentes.setdefault(int(parent_id), []).append(item)

    if not pendentes:
        return itens_api

    ids_pais_faltando = [id_pai for id_pai in pendentes if id_pai not in coluna_por_id_pai]
    if ids_pais_faltando:
        itens_pais = _buscar_campos_em_lotes(
            organization, ids_pais_faltando, pat, campos=[_CAMPO_BOARD_COLUMN]
        )
        for item_pai in itens_pais:
            coluna_por_id_pai[item_pai["id"]] = item_pai.get("fields", {}).get(_CAMPO_BOARD_COLUMN)

    for parent_id, itens_filhos in pendentes.items():
        coluna_do_pai = coluna_por_id_pai.get(parent_id)
        if not coluna_do_pai:
            continue
        for item in itens_filhos:
            item["fields"][_CAMPO_BOARD_COLUMN] = coluna_do_pai

    return itens_api


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

        # Junta Stack Rank / Backlog Priority numa única coluna: só um dos
        # dois vem preenchido por item (depende do processo do Azure DevOps
        # da organização), então não há conflito em preferir o Stack Rank
        # quando, por algum motivo raro, os dois vierem preenchidos.
        linha[COLUNA_PRIORIDADE_BOARD] = campos.get(_CAMPO_STACK_RANK)
        if linha[COLUNA_PRIORIDADE_BOARD] is None:
            linha[COLUNA_PRIORIDADE_BOARD] = campos.get(_CAMPO_BACKLOG_PRIORITY)

        linhas.append(linha)

    colunas_ordenadas = list(CAMPOS_API_PARA_COLUNA.values()) + [COLUNA_PRIORIDADE_BOARD]
    df = pd.DataFrame(linhas, columns=colunas_ordenadas)

    # Mesma limpeza de texto do core/data_loader.py: remove espaços extras
    # preservando valores vazios como nulo de verdade (nunca a string "nan").
    colunas_texto = df.select_dtypes(include="object").columns
    for coluna in colunas_texto:
        df[coluna] = df[coluna].apply(lambda valor: valor if pd.isna(valor) else str(valor).strip())

    return df


def buscar_work_items_da_query(
    organization: str, project: str, query_id: str, pat: str
) -> pd.DataFrame:
    """
    Busca todos os work items da query escolhida, e devolve um DataFrame com
    as mesmas colunas do export manual em CSV.

    Levanta `AzureDevOpsError` (mensagem amigável, pronta pra exibir na
    interface) em caso de parâmetro ausente/inválido ou falha de comunicação
    com a API.
    """
    if not all([organization, project, query_id, pat]):
        raise AzureDevOpsError(
            "Organização, projeto, query e PAT são obrigatórios para buscar os dados."
        )

    ids = _buscar_ids_da_query(organization, project, query_id, pat)
    if not ids:
        return pd.DataFrame(columns=list(CAMPOS_API_PARA_COLUNA.values()))

    itens_api = _buscar_campos_em_lotes(organization, ids, pat)
    itens_api = _completar_board_column_via_item_pai(organization, itens_api, pat)
    return _montar_dataframe(itens_api)
