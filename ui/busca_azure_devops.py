"""
UI reutilizável de busca direta no Azure DevOps (Organização -> Projeto ->
Area Path(s) opcional -> Query salva -> Baixar), compartilhada entre:

    - `ui/pages/upload_page.py` - a busca "geral" do app, que alimenta
      `st.session_state["dataframe_bruto"]` (usado pelo Dashboard, PDF, etc);
    - `ui/pages/scrum_page.py` - uma busca PRÓPRIA, independente, que
      alimenta só a página Scrum & Sprints (pedido explícito: mesmo que o
      arquivo/busca geral do app misture work items de vários projetos/Area
      Paths, a Scrum Master precisa conseguir escolher Organização/Projeto/
      Area Path específicos só para essa página, sem depender - nem afetar -
      o que está carregado no resto do app).

A independência entre as duas é garantida pelo parâmetro `namespace`: TODA
chave de `st.session_state` usada aqui (seleção em cascata, PAT, erro,
memória do último valor usado) é prefixada com `f"{namespace}_..."`, então
duas chamadas desta função com `namespace` diferente (ex.: "azure" e
"scrum_azure") nunca leem/escrevem a mesma chave - trocar o Projeto na busca
do Scrum & Sprints não mexe em nada da busca usada em Importar Dados, e
vice-versa. Quem usa o resultado da busca (o dataframe já buscado e, se
algum Area Path foi escolhido, já filtrado por eles) decide o que fazer com
ele através do callback `ao_concluir_busca` - normalmente, gravar em algum
par de chaves de `session_state` próprio (`dataframe_bruto`/`mapeamento_colunas`
no caso da busca geral; `scrum_dataframe_bruto`/`scrum_mapeamento_colunas` no
caso do Scrum & Sprints) e, opcionalmente, mapear as colunas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd
import streamlit as st

from auth.auth_manager import AuthManager
from core.azure_devops_client import (
    AzureDevOpsError,
    buscar_work_items_da_query,
    listar_area_paths,
    listar_projetos,
    listar_queries,
    montar_link_criacao_query,
    obter_identidade_autenticada,
)
from core.column_mapper import normalizar_texto
from core.logs_sistema import TIPO_ERRO, TIPO_PAINEL, registrar_log
from ui.components import action_button, finish_action, loading_overlay

# Organizações sugeridas no dropdown (apenas o rótulo aparece pronto - nada é
# carregado da API até o usuário clicar em "Carregar organização"). Se sua
# empresa usa mais de uma organização no Azure DevOps, adicione aqui.
ORGANIZACOES_SUGERIDAS = ["refuturiza"]

# Apelidos conhecidos: o "dono do PAT" (nome de exibição devolvido pelo
# próprio Azure DevOps) nem sempre bate, letra por letra, com o "name"
# cadastrado pra esse mesmo usuário no login deste app (`auth/users.yaml`) -
# pode ter sido cadastrado como apelido, nome incompleto, etc. Sem esse mapa,
# a pessoa aparecia com a bandeira de "possível anomalia" usando o PRÓPRIO
# PAT, logada na PRÓPRIA conta - um falso positivo.
#
# A chave é o `username` de LOGIN deste app (`AuthManager.current_username()`,
# não o nome de exibição); o valor é o conjunto de nomes que o Azure DevOps
# pode devolver como dono do PAT e que correspondem, de fato, à mesma pessoa
# desse login. Só entra aqui como reforço do nome já cadastrado no login -
# continua funcionando normalmente pra qualquer usuário/nome que não esteja
# nesta lista.
APELIDOS_DONO_PAT_POR_USUARIO_APP: dict[str, set[str]] = {
    "admin": {"Vinícius Bemfica"},
}


@dataclass
class ResultadoBuscaAzureDevOps:
    dataframe: pd.DataFrame
    organizacao: str
    projeto: str
    area_paths_filtro: list[str]


def resetar_selecao_azure_devops_namespaced(namespace: str, manter_organizacao: bool = False) -> None:
    """
    Versão namespaced de `utils.session.resetar_selecao_azure_devops` - limpa
    a cascata de seleção (projeto, area path, query) de UMA instância desta
    UI (identificada por `namespace`), sem afetar nenhuma outra instância
    (ex.: limpar a seleção do Scrum & Sprints não mexe na seleção usada em
    Importar Dados). O PAT nunca é limpo por aqui - só no logout. As chaves
    de memória "{namespace}_ultimo(a)_*_usado(a)" também nunca são limpas por
    esta função de propósito - são o que permite esta UI se auto-recuperar
    (ver `renderizar_busca_azure_devops`, abaixo).
    """
    if not manter_organizacao:
        st.session_state[f"{namespace}_organizacao_carregada"] = None
    st.session_state[f"{namespace}_projetos_disponiveis"] = []
    st.session_state[f"{namespace}_projeto_selecionado"] = None
    st.session_state[f"{namespace}_area_paths_disponiveis"] = []
    st.session_state[f"{namespace}_area_paths_selecionados"] = []
    st.session_state[f"{namespace}_queries_disponiveis"] = []
    st.session_state[f"{namespace}_query_selecionada_id"] = None


def renderizar_busca_azure_devops(
    *,
    namespace: str,
    ao_concluir_busca: Callable[[ResultadoBuscaAzureDevOps], None],
    ao_iniciar_busca: Callable[[], None] | None = None,
    pat_inicial: str = "",
    rotulo_botao_baixar: str = "Baixar relatório atualizado",
    contexto_log: str = "",
) -> None:
    """
    Desenha a cascata completa (PAT -> Organização -> Projeto -> Area
    Path(s) opcional -> Query salva -> Baixar) e, quando o usuário clica em
    baixar com sucesso, chama `ao_concluir_busca(resultado)` com o dataframe
    já buscado (e já filtrado pelos Area Paths escolhidos, se algum foi).

    `ao_iniciar_busca`, se informado, roda ANTES da tentativa de busca em si
    (assim que o usuário clica no botão) - existe só para o caso de
    `ui/pages/upload_page.py`, que precisa limpar os dados importados
    anteriormente (`resetar_dados_importados()`) nesse momento, reproduzindo
    o comportamento que já existia ali antes desta função ser extraída
    (inclusive quando a busca nova falha - comportamento pré-existente,
    preservado de propósito aqui, não uma escolha desta função). A busca
    independente do Scrum & Sprints não usa este parâmetro: como ela nunca
    mexe no `dataframe_bruto` geral do app, não há nada seu para limpar antes
    de tentar - só grava algo nas próprias chaves quando a busca dá certo.

    `namespace` isola completamente o estado desta instância de qualquer
    outra (ver docstring do módulo) - use um valor diferente por tela que
    chamar esta função (ex.: "azure" para Importar Dados, "scrum_azure" para
    Scrum & Sprints).

    `pat_inicial` pré-preenche o campo de PAT (conveniência - ex.: reaproveitar
    o PAT já colado em outra tela desta mesma sessão do navegador) sem ligar
    os dois de verdade: a partir do primeiro render, o PAT desta instância
    vive na sua própria chave (`{namespace}_pat_persistido`) e muda
    independente da instância de onde veio o valor inicial.

    `contexto_log`, se informado, é acrescentado à mensagem de auditoria
    registrada em Administração -> Logs do Sistema (ex.: "via Scrum &
    Sprints"), para distinguir de onde veio cada busca.

    Não levanta exceção - qualquer erro de comunicação com o Azure DevOps
    vira uma mensagem amigável (`st.error`) desenhada pela própria função.
    """

    def _chave(sufixo: str) -> str:
        return f"{namespace}_{sufixo}"

    erro_carga = st.session_state.get(_chave("erro_carga"))
    if erro_carga:
        st.error(erro_carga)

    col_esquerda, col_direita = st.columns(2, gap="large")

    # ---------------------------------------------------- Linha 1, coluna esquerda: PAT
    with col_esquerda:
        st.text_input(
            "Seu Personal Access Token (PAT) do Azure DevOps",
            type="password",
            value=st.session_state.get(_chave("pat_persistido"), pat_inicial),
            key=_chave("pat"),
            placeholder="Cole aqui o seu PAT pessoal",
            help=(
                "Cada usuário usa o próprio PAT — ele nunca é salvo em disco nem nos Secrets "
                "do Streamlit, fica só na memória desta sessão do navegador e some ao sair. "
                "Gere um token em dev.azure.com → foto de perfil → Personal Access Tokens → "
                "New Token, com escopo 'Work Items (Read)'."
            ),
        )
    pat = st.session_state.get(_chave("pat"), "")
    st.session_state[_chave("pat_persistido")] = pat

    if not pat:
        with col_direita:
            st.caption("👈 Informe o seu PAT ao lado para liberar a Organização.")
        return

    # ---------------------------------------------------- Linha 1, coluna direita: Organização
    with col_direita:
        organizacao_escolhida = st.selectbox(
            "Organização",
            options=ORGANIZACOES_SUGERIDAS,
            key=_chave("organizacao_input"),
            help="Nada é carregado da API até você clicar em \"Carregar organização\".",
        )
        with st.container(key=_chave("btn_carregar_organizacao_container")):
            carregar_org = st.button(
                "Carregar organização",
                key=_chave("btn_carregar_organizacao"),
                use_container_width=True,
            )

    if carregar_org:
        with loading_overlay("Carregando projetos da organização, aguarde..."):
            try:
                resetar_selecao_azure_devops_namespaced(namespace)
                projetos = listar_projetos(organizacao_escolhida, pat)
                st.session_state[_chave("organizacao_carregada")] = organizacao_escolhida
                st.session_state[_chave("ultima_organizacao_usada")] = organizacao_escolhida
                st.session_state[_chave("projetos_disponiveis")] = projetos
                st.session_state[_chave("erro_carga")] = None
            except AzureDevOpsError as erro:
                st.session_state[_chave("organizacao_carregada")] = None
                st.session_state[_chave("erro_carga")] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao carregar organização '{organizacao_escolhida}' do Azure DevOps"
                    f"{f' ({contexto_log})' if contexto_log else ''}: {erro}",
                )
        st.rerun()

    organizacao_carregada = st.session_state.get(_chave("organizacao_carregada"))
    if not organizacao_carregada:
        # Auto-recuperação: a organização já tinha sido carregada antes nesta
        # mesma sessão do navegador, mas esse passo foi perdido por algum
        # motivo (ex.: alguma navegação em outra parte do app limpou o
        # estado) - recarrega automaticamente pra não obrigar o usuário a
        # clicar em "Carregar organização" de novo só porque foi em outro menu.
        ultima_organizacao = st.session_state.get(_chave("ultima_organizacao_usada"))
        if ultima_organizacao:
            with loading_overlay("Restaurando organização usada anteriormente, aguarde..."):
                try:
                    projetos = listar_projetos(ultima_organizacao, pat)
                    st.session_state[_chave("organizacao_carregada")] = ultima_organizacao
                    st.session_state[_chave("projetos_disponiveis")] = projetos
                except AzureDevOpsError:
                    return
            st.rerun()
        return

    # ---------------------------------------------------- Linha 2, coluna esquerda: Projeto
    projetos_disponiveis = st.session_state.get(_chave("projetos_disponiveis"), [])
    opcoes_projeto = ["---"] + [projeto.nome for projeto in projetos_disponiveis]

    projeto_atual = st.session_state.get(_chave("projeto_selecionado"))

    limpou_manualmente = st.session_state.pop(_chave("projeto_limpo_manualmente"), False)
    if not projeto_atual and not limpou_manualmente:
        ultimo_projeto = st.session_state.get(_chave("ultimo_projeto_usado"))
        if ultimo_projeto and ultimo_projeto in opcoes_projeto:
            with loading_overlay("Restaurando projeto usado anteriormente, aguarde..."):
                try:
                    area_paths = listar_area_paths(organizacao_carregada, ultimo_projeto, pat)
                    queries = listar_queries(organizacao_carregada, ultimo_projeto, pat)
                    st.session_state[_chave("projeto_selecionado")] = ultimo_projeto
                    st.session_state[_chave("area_paths_disponiveis")] = area_paths
                    ultimos_area_paths = st.session_state.get(_chave("ultimos_area_paths_usados"), [])
                    st.session_state[_chave("area_paths_selecionados")] = [
                        area_path for area_path in ultimos_area_paths if area_path in area_paths
                    ]
                    st.session_state[_chave("queries_disponiveis")] = queries
                    mapa_queries_restauro = {item.caminho: item.id for item in queries}
                    ultima_query = st.session_state.get(_chave("ultima_query_usada"))
                    st.session_state[_chave("query_selecionada_id")] = mapa_queries_restauro.get(ultima_query)
                except AzureDevOpsError:
                    pass
            st.rerun()

    indice_projeto = opcoes_projeto.index(projeto_atual) if projeto_atual in opcoes_projeto else 0

    with col_esquerda:
        projeto_escolhido = st.selectbox(
            "Projeto",
            options=opcoes_projeto,
            index=indice_projeto,
            key=_chave("projeto_input"),
        )

    if projeto_escolhido != "---" and projeto_escolhido != projeto_atual:
        # Escolher um projeto novo já dispara sozinho o carregamento do
        # próximo passo (Area Path + Queries) — não precisa de botão de
        # confirmação separado.
        with loading_overlay("Carregando informações do projeto, aguarde..."):
            try:
                area_paths = listar_area_paths(organizacao_carregada, projeto_escolhido, pat)
                queries = listar_queries(organizacao_carregada, projeto_escolhido, pat)
                st.session_state[_chave("projeto_selecionado")] = projeto_escolhido
                st.session_state[_chave("ultimo_projeto_usado")] = projeto_escolhido
                st.session_state[_chave("area_paths_disponiveis")] = area_paths
                st.session_state[_chave("area_paths_selecionados")] = []
                st.session_state[_chave("queries_disponiveis")] = queries
                st.session_state[_chave("query_selecionada_id")] = None
                st.session_state[_chave("erro_carga")] = None
            except AzureDevOpsError as erro:
                st.session_state[_chave("erro_carga")] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao carregar o projeto '{projeto_escolhido}' do Azure DevOps"
                    f"{f' ({contexto_log})' if contexto_log else ''}: {erro}",
                )
        st.rerun()
    elif projeto_escolhido == "---" and projeto_atual is not None:
        resetar_selecao_azure_devops_namespaced(namespace, manter_organizacao=True)
        st.session_state[_chave("projeto_limpo_manualmente")] = True
        st.rerun()

    projeto_selecionado = st.session_state.get(_chave("projeto_selecionado"))
    if not projeto_selecionado:
        with col_direita:
            st.caption("👈 Escolha um Projeto ao lado para liberar Area Path(s).")
        return

    # ------------------------------------------- Linha 2, coluna direita: Area Path(s) (opcional)
    area_paths_disponiveis = st.session_state.get(_chave("area_paths_disponiveis"), [])
    area_paths_atuais = [
        area_path
        for area_path in st.session_state.get(_chave("area_paths_selecionados"), [])
        if area_path in area_paths_disponiveis
    ]

    with col_direita:
        area_paths_escolhidos = st.multiselect(
            "Area Path(s) do Board no Projeto (opcional)",
            options=area_paths_disponiveis,
            default=area_paths_atuais,
            key=_chave(f"area_path_input__{projeto_selecionado}"),
            help="Selecione um ou mais Area Paths para trazer work items de vários times/módulos de uma vez.",
        )
        st.caption(
            "Campo opcional. Se você escolher um ou mais Area Paths aqui, o app filtra os work "
            "items trazidos pela query para manter só os que estão dentro de algum deles (e dos "
            "seus sub-caminhos). Se deixar em branco, nenhum filtro extra de Area Path é aplicado "
            "— vale o que a própria query já retorna."
        )
    st.session_state[_chave("area_paths_selecionados")] = area_paths_escolhidos
    if area_paths_escolhidos:
        st.session_state[_chave("ultimos_area_paths_usados")] = area_paths_escolhidos

    # ---------------------------------------------- Linha 3, coluna esquerda: Query existente
    queries_disponiveis = st.session_state.get(_chave("queries_disponiveis"), [])
    mapa_queries = {item.caminho: item.id for item in queries_disponiveis}
    opcoes_query = ["---"] + list(mapa_queries.keys())

    query_id_atual = st.session_state.get(_chave("query_selecionada_id"))
    caminho_atual = next(
        (caminho for caminho, id_query in mapa_queries.items() if id_query == query_id_atual),
        "---",
    ) if query_id_atual else "---"
    indice_query = opcoes_query.index(caminho_atual) if caminho_atual in opcoes_query else 0

    with col_esquerda:
        query_escolhida_caminho = st.selectbox(
            "Query salva no Azure DevOps",
            options=opcoes_query,
            index=indice_query,
            key=_chave(f"query_input__{projeto_selecionado}"),
        )
        col_atualizar, col_link = st.columns(2)
        with col_atualizar:
            atualizar_queries = st.button(
                "🔄 Atualizar lista",
                key=_chave("btn_atualizar_queries"),
                use_container_width=True,
                help="Busca a lista de queries de novo — use depois de criar uma query nova no Azure DevOps.",
            )
        with col_link:
            link_criacao = montar_link_criacao_query(organizacao_carregada, projeto_selecionado)
            st.link_button(
                "Criar nova query ↗",
                link_criacao,
                use_container_width=True,
                help=(
                    "Abre a tela nativa do Azure DevOps para você montar uma query nova "
                    f"em {organizacao_carregada}/{projeto_selecionado}. Depois de salvar lá, "
                    "clique em 'Atualizar lista' ao lado para recarregar."
                ),
            )

    if atualizar_queries:
        with loading_overlay("Atualizando lista de queries, aguarde..."):
            try:
                st.session_state[_chave("queries_disponiveis")] = listar_queries(
                    organizacao_carregada, projeto_selecionado, pat
                )
                st.session_state[_chave("erro_carga")] = None
            except AzureDevOpsError as erro:
                st.session_state[_chave("erro_carga")] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao atualizar a lista de queries do projeto '{projeto_selecionado}'"
                    f"{f' ({contexto_log})' if contexto_log else ''}: {erro}",
                )
        st.rerun()

    st.session_state[_chave("query_selecionada_id")] = (
        mapa_queries[query_escolhida_caminho] if query_escolhida_caminho != "---" else None
    )
    if query_escolhida_caminho != "---":
        st.session_state[_chave("ultima_query_usada")] = query_escolhida_caminho

    if not queries_disponiveis:
        with col_esquerda:
            st.info(
                "Nenhuma query encontrada neste projeto ainda. Confira se o projeto certo está "
                "selecionado acima e se a query está salva em **Shared Queries** (ou em **My "
                "Queries** do mesmo usuário dono do PAT) — depois use **Atualizar lista**. Ou "
                "use o botão **Criar nova query** para criar uma diretamente no Azure DevOps."
            )

    # ------------------------------------- Abaixo das duas colunas: Baixar
    query_id = st.session_state.get(_chave("query_selecionada_id"))
    if not query_id:
        st.caption("👆 Selecione uma query salva acima para liberar o download.")
        return

    processar = action_button(
        rotulo_botao_baixar,
        key=_chave("btn_baixar"),
        help="Busca os dados mais recentes da query escolhida no Azure DevOps.",
    )

    if processar:
        with loading_overlay("Buscando dados no Azure DevOps, aguarde..."):
            try:
                if ao_iniciar_busca is not None:
                    ao_iniciar_busca()
                dataframe = buscar_work_items_da_query(
                    organizacao_carregada, projeto_selecionado, query_id, pat
                )

                area_paths_filtro = st.session_state.get(_chave("area_paths_selecionados")) or []
                if area_paths_filtro and "Area Path" in dataframe.columns:
                    valores_area_path = dataframe["Area Path"].astype(str)
                    dataframe = dataframe[
                        valores_area_path.apply(
                            lambda valor: any(valor.startswith(area_path) for area_path in area_paths_filtro)
                        )
                    ]

                if dataframe.empty:
                    raise AzureDevOpsError(
                        "A query escolhida (após o filtro de Area Path(s), se algum foi "
                        "escolhido) não retornou nenhum work item."
                    )
            except AzureDevOpsError as erro:
                st.session_state[_chave("erro_carga")] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao baixar relatório do Azure DevOps (projeto '{projeto_selecionado}')"
                    f"{f' ({contexto_log})' if contexto_log else ''}: {erro}",
                )
            else:
                st.session_state[_chave("erro_carga")] = None

                # Registra QUEM usou o PAT do Azure DevOps pra buscar os dados
                # - mesmo raciocínio de auditoria/rastreabilidade de
                # `ui/pages/upload_page.py` (ver comentário original: duas
                # identidades na mensagem - usuário logado neste app e dono
                # de verdade do PAT, segundo o próprio Azure DevOps -, com um
                # 🚩 quando as duas não batem).
                identidade_pat = obter_identidade_autenticada(organizacao_carregada, pat)
                nome_usuario_app = AuthManager.current_user_name() or AuthManager.current_username()
                apelidos_usuario_logado = APELIDOS_DONO_PAT_POR_USUARIO_APP.get(
                    AuthManager.current_username(), set()
                )
                nomes_aceitos_para_usuario_logado = {nome_usuario_app, *apelidos_usuario_logado}
                possivel_anomalia = (
                    identidade_pat is not None
                    and normalizar_texto(identidade_pat)
                    not in {normalizar_texto(nome) for nome in nomes_aceitos_para_usuario_logado}
                )
                prefixo = "🚩 POSSÍVEL ANOMALIA (PAT de outra pessoa?) · " if possivel_anomalia else ""

                registrar_log(
                    TIPO_PAINEL, AuthManager.current_username(),
                    f"{prefixo}Baixou relatório do Azure DevOps via PAT próprio"
                    f"{f' ({contexto_log})' if contexto_log else ''} · "
                    f"Usuário logado no app: {nome_usuario_app} · "
                    f"Dono do PAT (Azure DevOps): {identidade_pat or 'não identificado'} · "
                    f"Projeto: '{projeto_selecionado}' · {len(dataframe)} itens",
                )

                ao_concluir_busca(
                    ResultadoBuscaAzureDevOps(
                        dataframe=dataframe,
                        organizacao=organizacao_carregada,
                        projeto=projeto_selecionado,
                        area_paths_filtro=area_paths_filtro,
                    )
                )
        finish_action(_chave("btn_baixar"))
        st.rerun()
