"""Página de importação do arquivo CSV/TXT (ou busca automática no Azure DevOps) e confirmação do mapeamento de colunas."""

from __future__ import annotations

import time

import streamlit as st

from core.azure_devops_client import AzureDevOpsError, buscar_work_items_da_query, configuracao_disponivel
from core.column_mapper import MapeamentoColunas, detectar_mapeamento
from core.data_loader import DataLoadError, ResultadoCarga, carregar_arquivo
from ui.components import action_button, finish_action, loading_overlay, render_header
from utils.session import resetar_dados_importados

CAMPOS_MAPEAVEIS = [
    ("projeto", "Projeto"),
    ("status", "Status"),
    ("data_planejada", "Data Planejada"),
    ("data_execucao", "Data de Execução"),
    ("data_criacao", "Data de Criação"),
    ("tipo_teste", "Tipos de Teste"),
    ("responsavel", "Responsável / Executor"),
    ("caso_teste", "Caso de Teste / ID"),
    ("severidade", "Severidade / Prioridade"),
]

CHAVE_CAMPOS_PERSONALIZADOS = "campos_personalizados_temp"

OPCAO_ORIGEM_MANUAL = "Enviar arquivo (.csv/.txt)"
OPCAO_ORIGEM_AZURE = "Buscar automaticamente do Azure DevOps"


def _opcao_coluna(colunas: list[str], atual: str | None) -> list[str]:
    return ["— não mapeado —"] + colunas


def render_upload_page() -> None:
    render_header(
        titulo="Importar dados de testes",
        subtitulo="Envie um arquivo .csv/.txt ou busque automaticamente do Azure DevOps.",
    )

    origem = st.radio(
        "Como deseja importar os dados?",
        options=[OPCAO_ORIGEM_MANUAL, OPCAO_ORIGEM_AZURE],
        key="origem_importacao",
        horizontal=True,
    )

    if origem == OPCAO_ORIGEM_MANUAL:
        _renderizar_importacao_manual()
    else:
        _renderizar_importacao_azure_devops()

    if st.session_state.get("erro_carga"):
        st.error(st.session_state["erro_carga"])

    resultado = st.session_state.get("resultado_carga")
    if resultado is not None:
        _renderizar_confirmacao_mapeamento(resultado)


def _renderizar_importacao_manual() -> None:
    arquivo_enviado = st.file_uploader(
        "Arquivo de testes (.csv ou .txt) — limite 20MB",
        type=["csv", "txt"],
        accept_multiple_files=False,
        key="uploader_arquivo_testes",
    )

    col_botao, col_msg = st.columns([1, 3])
    with col_botao:
        processar = action_button(
            "Processar arquivo",
            key="btn_processar_arquivo",
            use_container_width=True,
            help="Lê o arquivo e detecta automaticamente as colunas relevantes.",
        )

    if processar:
        if arquivo_enviado is None:
            st.warning("Selecione um arquivo antes de clicar em Processar.")
            finish_action("btn_processar_arquivo")
        else:
            with loading_overlay("Carregando, aguarde..."):
                try:
                    resetar_dados_importados()
                    st.session_state[CHAVE_CAMPOS_PERSONALIZADOS] = []
                    resultado = carregar_arquivo(arquivo_enviado, arquivo_enviado.name)
                    mapeamento = detectar_mapeamento(resultado.dataframe)

                    st.session_state["resultado_carga"] = resultado
                    st.session_state["dataframe_bruto"] = resultado.dataframe
                    st.session_state["mapeamento_colunas"] = mapeamento
                    st.session_state["mapeamento_confirmado"] = False

                    time.sleep(0.3)
                except DataLoadError as erro:
                    st.session_state["erro_carga"] = str(erro)
                else:
                    st.session_state["erro_carga"] = None
            finish_action("btn_processar_arquivo")
            st.rerun()


def _renderizar_importacao_azure_devops() -> None:
    if not configuracao_disponivel():
        st.warning(
            "A busca automática ainda não está configurada. Adicione a seção "
            "`[azure_devops]` (organization, project, query_id, pat) nos "
            "**Secrets** do Streamlit para habilitar esta opção. Enquanto isso, "
            "use a importação manual do arquivo."
        )
        return

    st.caption(
        "Busca os work items da mesma query salva usada hoje para o export manual, "
        "direto da API do Azure DevOps — sem precisar baixar e subir o CSV."
    )

    processar = action_button(
        "Baixar relatório atualizado",
        key="btn_baixar_azure_devops",
        help="Busca os dados mais recentes da query configurada no Azure DevOps.",
    )

    if processar:
        with loading_overlay("Buscando dados no Azure DevOps, aguarde..."):
            try:
                resetar_dados_importados()
                st.session_state[CHAVE_CAMPOS_PERSONALIZADOS] = []
                dataframe = buscar_work_items_da_query()

                if dataframe.empty:
                    raise AzureDevOpsError(
                        "A query configurada não retornou nenhum work item. Confira o "
                        "query_id em [azure_devops] nos Secrets."
                    )

                resultado = ResultadoCarga(
                    dataframe=dataframe,
                    encoding_detectado="—",
                    delimitador_detectado="—",
                    nome_arquivo="Azure DevOps (consulta automática)",
                    total_linhas=dataframe.shape[0],
                    total_colunas=dataframe.shape[1],
                )
                mapeamento = detectar_mapeamento(dataframe)

                st.session_state["resultado_carga"] = resultado
                st.session_state["dataframe_bruto"] = dataframe
                st.session_state["mapeamento_colunas"] = mapeamento
                st.session_state["mapeamento_confirmado"] = False

                time.sleep(0.3)
            except AzureDevOpsError as erro:
                st.session_state["erro_carga"] = str(erro)
            else:
                st.session_state["erro_carga"] = None
        finish_action("btn_baixar_azure_devops")
        st.rerun()


def _renderizar_confirmacao_mapeamento(resultado) -> None:
    df = resultado.dataframe
    st.success(
        f"Arquivo **{resultado.nome_arquivo}** carregado com sucesso · "
        f"{resultado.total_linhas} linhas · {resultado.total_colunas} colunas · "
        f"encoding detectado: `{resultado.encoding_detectado}` · "
        f"delimitador detectado: `{repr(resultado.delimitador_detectado)}`"
    )

    with st.expander("Prévia dos dados importados", expanded=False):
        st.dataframe(df.head(20), use_container_width=True)

    st.markdown("#### Confirme o mapeamento automático de colunas")
    st.caption(
        "A aplicação tentou identificar sozinha qual coluna representa cada informação. "
        "Ajuste manualmente qualquer campo que não tenha sido detectado corretamente. "
        "Campos deixados como **— não mapeado —** são ignorados na geração dos gráficos."
    )

    mapeamento_atual: MapeamentoColunas = st.session_state["mapeamento_colunas"]
    colunas_disponiveis = list(df.columns)

    with st.container():
        st.markdown('<div class="mapeamento-caixa">', unsafe_allow_html=True)
        colunas_layout = st.columns(2)
        novo_mapeamento_kwargs = {}

        for indice, (campo_key, campo_label) in enumerate(CAMPOS_MAPEAVEIS):
            coluna_layout = colunas_layout[indice % 2]
            valor_sugerido = getattr(mapeamento_atual, campo_key)
            opcoes = _opcao_coluna(colunas_disponiveis, valor_sugerido)
            indice_padrao = opcoes.index(valor_sugerido) if valor_sugerido in opcoes else 0

            with coluna_layout:
                selecionado = st.selectbox(
                    campo_label,
                    options=opcoes,
                    index=indice_padrao,
                    key=f"select_mapeamento_{campo_key}",
                )
            novo_mapeamento_kwargs[campo_key] = None if selecionado == "— não mapeado —" else selecionado
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("##### Campos personalizados (opcional)")
    st.caption(
        "Relacione colunas do arquivo que não se encaixam nos campos fixos acima a um "
        "rótulo livre. Esses campos ficam disponíveis no construtor de gráfico personalizado."
    )
    _renderizar_campos_personalizados(colunas_disponiveis)

    confirmar = action_button(
        "Confirmar mapeamento e gerar indicadores",
        key="btn_confirmar_mapeamento",
        use_container_width=False,
    )

    if confirmar:
        with loading_overlay("Carregando, aguarde..."):
            campos_personalizados = {
                item["label"].strip(): item["coluna"]
                for item in st.session_state.get(CHAVE_CAMPOS_PERSONALIZADOS, [])
                if item.get("label", "").strip() and item.get("coluna") not in (None, "— não mapeado —")
            }
            mapeamento_final = MapeamentoColunas(
                **novo_mapeamento_kwargs, campos_personalizados=campos_personalizados
            )
            st.session_state["mapeamento_colunas"] = mapeamento_final
            st.session_state["mapeamento_confirmado"] = True
            st.session_state["pagina_atual"] = "dashboard"
            time.sleep(0.2)
        finish_action("btn_confirmar_mapeamento")
        st.rerun()


def _renderizar_campos_personalizados(colunas_disponiveis: list[str]) -> None:
    if CHAVE_CAMPOS_PERSONALIZADOS not in st.session_state:
        st.session_state[CHAVE_CAMPOS_PERSONALIZADOS] = []

    itens = st.session_state[CHAVE_CAMPOS_PERSONALIZADOS]
    opcoes_coluna = ["— não mapeado —"] + colunas_disponiveis

    indices_para_remover = []
    for indice, item in enumerate(itens):
        col_label, col_coluna, col_remover = st.columns([2, 2, 1])
        with col_label:
            item["label"] = st.text_input(
                "Nome do campo",
                value=item.get("label", ""),
                key=f"campo_personalizado_label_{indice}",
                placeholder="Ex.: Sprint, Cliente, Ambiente...",
            )
        with col_coluna:
            valor_atual = item.get("coluna") or "— não mapeado —"
            indice_padrao = opcoes_coluna.index(valor_atual) if valor_atual in opcoes_coluna else 0
            selecionado = st.selectbox(
                "Coluna do arquivo",
                options=opcoes_coluna,
                index=indice_padrao,
                key=f"campo_personalizado_coluna_{indice}",
            )
            item["coluna"] = None if selecionado == "— não mapeado —" else selecionado
        with col_remover:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Remover", key=f"remover_campo_personalizado_{indice}"):
                indices_para_remover.append(indice)

    if indices_para_remover:
        st.session_state[CHAVE_CAMPOS_PERSONALIZADOS] = [
            item for i, item in enumerate(itens) if i not in indices_para_remover
        ]
        st.rerun()

    if st.button("+ Adicionar campo personalizado", key="btn_adicionar_campo_personalizado"):
        st.session_state[CHAVE_CAMPOS_PERSONALIZADOS].append({"label": "", "coluna": None})
        st.rerun()
