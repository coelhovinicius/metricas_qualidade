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
    "azure_area_paths_selecionados": [],  # list[str] - [] = nenhum escolhido (campo opcional, multiescolha)
    "azure_queries_disponiveis": [],  # list[ItemQuery]
    "azure_query_selecionada_id": None,
    # ---- Memória do último valor realmente usado em cada passo ----
    # Ao contrário das chaves acima (que representam o passo "em andamento"
    # e são limpas por resetar_selecao_azure_devops quando um passo anterior
    # muda), estas guardam o último valor de verdade escolhido pelo usuário
    # nesta sessão do navegador e NUNCA são limpas por resetar_selecao_azure_devops.
    # Servem só para a tela de importação conseguir se auto-recuperar (ver
    # upload_page.py) caso a cascata de seleção seja perdida por algum motivo
    # externo (ex.: navegação entre páginas), sem obrigar o usuário a refazer
    # manualmente todos os passos.
    "azure_ultima_organizacao_usada": None,
    "azure_ultimo_projeto_usado": None,
    "azure_ultimos_area_paths_usados": [],
    "azure_ultima_query_usada": None,
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
    # Os widgets de data (`st.date_input`) guardam o próprio valor em
    # session_state via `key=` assim que são renderizados uma vez - sem
    # limpar essas chaves aqui também, o widget continuaria mostrando o
    # intervalo do arquivo antigo (e fora dos limites min/max do arquivo
    # novo) até o usuário mexer nele manualmente.
    st.session_state.pop("input_data_inicio", None)
    st.session_state.pop("input_data_fim", None)
    # Lista de campos personalizados montada durante a confirmação do
    # mapeamento anterior (ver upload_page.py) - some sentido pra um arquivo
    # novo, que pode nem ter as mesmas colunas.
    st.session_state.pop("campos_personalizados_temp", None)
    # Mensagem de erro de uma carga anterior (upload manual ou Azure DevOps)
    # não deve sobreviver a um novo processamento.
    st.session_state.pop("erro_carga", None)


_CHAVES_RELATORIO_DASHBOARD_PARA_LIMPAR = (
    # Filtros da barra lateral do dashboard (Projeto / Tipos de Teste / Status)
    "filtro_projeto",
    "filtro_tipo_teste",
    "filtro_status",
    # Configurações específicas de alguns gráficos do dashboard
    "tipo_teste_excluidos",
    "bugs_tempo_colunas_externas",
    "volume_responsavel_agrupar_projeto",
    # Construtor de gráfico personalizado
    "grafico_custom_x",
    "grafico_custom_grupo",
    "grafico_custom_modo",
    "grafico_custom_metrica",
    "grafico_custom_tipo",
    "grafico_customizado_params",
)
_PREFIXO_CHAVES_TIPO_GRAFICO = "tipo_grafico_"


def resetar_para_nova_analise() -> None:
    """
    Limpa os dados importados e todos os relatórios/filtros/gráficos
    derivados deles, para permitir um novo processamento do zero sem
    precisar dar F5 na página (o que perderia a sessão de login).

    De propósito, NÃO mexe em:
      - chaves de autenticação (o usuário continua logado);
      - chaves de "memória" da busca automática no Azure DevOps
        (`azure_ultima_organizacao_usada`, `azure_ultimo_projeto_usado`,
        etc.) nem no PAT em memória - assim quem usa a busca automática não
        precisa refazer a cascata de organização/projeto/query de novo só
        pra começar uma nova análise;
      - a preferência de origem de importação (`origem_importacao_persistida`).
    """
    resetar_dados_importados()
    for chave in _CHAVES_RELATORIO_DASHBOARD_PARA_LIMPAR:
        st.session_state.pop(chave, None)
    for chave in list(st.session_state.keys()):
        if chave.startswith(_PREFIXO_CHAVES_TIPO_GRAFICO):
            st.session_state.pop(chave, None)
    st.session_state["pagina_atual"] = "upload"


def resetar_selecao_azure_devops(manter_organizacao: bool = False) -> None:
    """
    Limpa a cascata de seleção da busca automática no Azure DevOps (projeto,
    area path e query), usada sempre que um passo anterior muda (ex.: troca
    de organização ou de projeto invalida o que já tinha sido carregado nos
    passos seguintes). O PAT nunca é limpo por aqui - só no logout. As chaves
    de memória "azure_ultimo(a)_*_usado(a)" também nunca são limpas por esta
    função de propósito - são o que permite a tela de importação se
    auto-recuperar depois (ver upload_page.py).
    """
    if not manter_organizacao:
        st.session_state["azure_organizacao_carregada"] = None
    st.session_state["azure_projetos_disponiveis"] = []
    st.session_state["azure_projeto_selecionado"] = None
    st.session_state["azure_area_paths_disponiveis"] = []
    st.session_state["azure_area_paths_selecionados"] = []
    st.session_state["azure_queries_disponiveis"] = []
    st.session_state["azure_query_selecionada_id"] = None
