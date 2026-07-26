"""Inicialização centralizada das chaves de `st.session_state` usadas na aplicação."""

from __future__ import annotations

import streamlit as st

CHAVES_PADRAO = {
    "pagina_atual": "upload",
    "dataframe_bruto": None,
    "resultado_carga": None,
    "mapeamento_colunas": None,
    "mapeamento_confirmado": False,
    "df_status_preparado": None,
    # ---- Seleção em cascata da busca automática no Azure DevOps ----
    # O PAT nunca é persistido em disco/secrets - fica só aqui, em memória,
    # durante a sessão do navegador (ver core/azure_devops_client.py).
    "azure_pat": "",
    "azure_organizacao_carregada": None,  # organização já confirmada (após clicar "Carregar")
    "azure_projetos_disponiveis": [],  # list[Projeto] retornada pela API
    "azure_projeto_selecionado": None,  # nome do projeto escolhido
    "azure_area_paths_disponiveis": [],  # list[str]
    "azure_area_path_selecionado": None,  # "" = nenhum escolhido (campo opcional)
    "azure_queries_disponiveis": [],  # list[ItemQuery]
    "azure_query_selecionada_id": None,
}


def inicializar_sessao() -> None:
    for chave, valor_padrao in CHAVES_PADRAO.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor_padrao


def resetar_dados_importados() -> None:
    """Limpa os dados de um arquivo importado anteriormente (ex: ao importar um novo)."""
    st.session_state["dataframe_bruto"] = None
    st.session_state["resultado_carga"] = None
    st.session_state["mapeamento_colunas"] = None
    st.session_state["mapeamento_confirmado"] = False
    st.session_state["df_status_preparado"] = None
    # Limpa também o período filtrado de uma importação anterior - sem isso,
    # um intervalo de datas confirmado para o arquivo antigo poderia ficar
    # fora do range do arquivo novo (e o widget de data quebraria), além de
    # não deixar o período padrão (último mês) ser recalculado na nova carga.
    st.session_state.pop("filtro_data_inicio", None)
    st.session_state.pop("filtro_data_fim", None)


def resetar_selecao_azure_devops(manter_organizacao: bool = False) -> None:
    """
    Limpa a cascata de seleção da busca automática no Azure DevOps (projeto,
    area path e query), usada sempre que um passo anterior muda (ex.: troca
    de organização ou de projeto invalida o que já tinha sido carregado nos
    passos seguintes). O PAT nunca é limpo por aqui - só no logout.
    """
    if not manter_organizacao:
        st.session_state["azure_organizacao_carregada"] = None
    st.session_state["azure_projetos_disponiveis"] = []
    st.session_state["azure_projeto_selecionado"] = None
    st.session_state["azure_area_paths_disponiveis"] = []
    st.session_state["azure_area_path_selecionado"] = None
    st.session_state["azure_queries_disponiveis"] = []
    st.session_state["azure_query_selecionada_id"] = None
