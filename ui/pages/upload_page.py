"""Página de importação do arquivo CSV/TXT (ou busca automática no Azure DevOps) e confirmação do mapeamento de colunas."""

from __future__ import annotations

import io
import time

import streamlit as st

from auth.auth_manager import AuthManager
from core.column_mapper import MapeamentoColunas, detectar_mapeamento
from core.config_app import chave_pasta_raiz_google_drive, definir_configuracao, obter_configuracao
from core.data_loader import DataLoadError, ResultadoCarga, carregar_arquivo
from core.google_drive_client import (
    GoogleDriveError,
    baixar_arquivo_csv,
    email_conta_servico,
    extrair_id_pasta_do_link,
    listar_pastas_e_arquivos_csv,
    testar_conexao as testar_conexao_drive,
)
from core.logs_sistema import TIPO_ERRO, TIPO_PAINEL, registrar_log
from ui.busca_azure_devops import ResultadoBuscaAzureDevOps, renderizar_busca_azure_devops
from ui.components import action_button, finish_action, loading_overlay, render_header
from utils.session import resetar_dados_importados, resetar_selecao_google_drive

CAMPOS_MAPEAVEIS = [
    ("projeto", "Projeto"),
    ("status", "Status"),
    ("data_planejada", "Data Planejada"),
    ("data_execucao", "Data de Execução"),
    ("data_criacao", "Data de Criação"),
    ("tipo_teste", "Tipos de Teste"),
    ("responsavel", "Responsável / Executor"),
    ("criado_por", "Criado por (reserva p/ quando Responsável estiver vazio)"),
    ("caso_teste", "Caso de Teste / ID"),
    ("severidade", "Severidade / Prioridade"),
    ("coluna_board", "Coluna do Board (Kanban)"),
    ("sprint", "Sprint"),
    ("story_points", "Story Points (Velocity por esforço, em Sprints)"),
    ("prioridade_board", "Prioridade (posição no board) - Stack Rank/Backlog Priority"),
]

CHAVE_CAMPOS_PERSONALIZADOS = "campos_personalizados_temp"

OPCAO_ORIGEM_MANUAL = "Enviar arquivo (.csv/.txt)"
OPCAO_ORIGEM_AZURE = "Buscar Query no Azure DevOps"
OPCAO_ORIGEM_DRIVE = "Buscar arquivo no Google Drive"


def _opcao_coluna(colunas: list[str], atual: str | None) -> list[str]:
    return ["— não mapeado —"] + colunas


def render_upload_page() -> None:
    render_header(
        titulo="Importar dados de testes",
        subtitulo="Envie um arquivo .csv/.txt, busque uma query do Azure DevOps, ou puxe um arquivo já salvo no Google Drive.",
    )

    # O Streamlit "esquece" o valor de um widget sempre que ele deixa de ser
    # renderizado por pelo menos uma execução do script (ex.: o usuário foi
    # pra outra página do menu, onde este `st.radio` não é chamado) - ao
    # voltar, o widget nasce de novo do zero e cairia sempre na 1ª opção
    # ("Enviar arquivo"), escondendo todo o passo a passo já configurado
    # antes (Azure DevOps ou Google Drive). Por isso o valor escolhido é
    # espelhado numa chave "solta" (não presa a nenhum widget, então nunca é
    # esquecida) e usada como valor inicial (`index=`) sempre que o widget
    # nascer de novo.
    opcoes_origem = [OPCAO_ORIGEM_MANUAL, OPCAO_ORIGEM_AZURE, OPCAO_ORIGEM_DRIVE]
    origem_persistida = st.session_state.get("origem_importacao_persistida", OPCAO_ORIGEM_MANUAL)
    indice_origem = opcoes_origem.index(origem_persistida) if origem_persistida in opcoes_origem else 0

    origem = st.radio(
        "Como deseja importar os dados?",
        options=opcoes_origem,
        index=indice_origem,
        key="origem_importacao",
        horizontal=True,
    )
    st.session_state["origem_importacao_persistida"] = origem

    if origem == OPCAO_ORIGEM_MANUAL:
        _renderizar_importacao_manual()
    elif origem == OPCAO_ORIGEM_AZURE:
        _renderizar_importacao_azure_devops()
    else:
        _renderizar_importacao_google_drive()

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
                    registrar_log(
                        TIPO_ERRO, AuthManager.current_username(),
                        f"Falha ao processar arquivo '{arquivo_enviado.name}': {erro}",
                    )
                else:
                    st.session_state["erro_carga"] = None
            finish_action("btn_processar_arquivo")
            st.rerun()


def _renderizar_importacao_azure_devops() -> None:
    st.caption(
        "Busca work items direto da API do Azure DevOps, sem precisar baixar e subir o "
        "CSV manualmente. Escolha a organização, o projeto e (se quiser) um ou mais Area "
        "Paths, depois selecione uma query já existente para trazer os dados."
    )

    def _ao_iniciar() -> None:
        # Mesmo comportamento de sempre: limpa os dados importados
        # anteriormente assim que o usuário clica em "Baixar relatório        # atualizado", antes mesmo de saber se a busca nova vai dar certo -
        # ver docstring de `ao_iniciar_busca` em `ui/busca_azure_devops.py`.
        resetar_dados_importados()
        st.session_state[CHAVE_CAMPOS_PERSONALIZADOS] = []

    def _ao_concluir(resultado: ResultadoBuscaAzureDevOps) -> None:
        resultado_carga = ResultadoCarga(
            dataframe=resultado.dataframe,
            encoding_detectado="—",
            delimitador_detectado="—",
            nome_arquivo=f"Azure DevOps · {resultado.projeto} (consulta automática)",
            total_linhas=resultado.dataframe.shape[0],
            total_colunas=resultado.dataframe.shape[1],
        )
        mapeamento = detectar_mapeamento(resultado.dataframe)

        st.session_state["resultado_carga"] = resultado_carga
        st.session_state["dataframe_bruto"] = resultado.dataframe
        st.session_state["mapeamento_colunas"] = mapeamento
        st.session_state["mapeamento_confirmado"] = False
        time.sleep(0.3)

    renderizar_busca_azure_devops(
        namespace="azure",
        ao_concluir_busca=_ao_concluir,
        ao_iniciar_busca=_ao_iniciar,
        contexto_log="via Importar Dados",
    )


def _renderizar_importacao_google_drive() -> None:
    st.caption(
        "Explora uma pasta do SEU Google Drive (não uma pasta compartilhada de outra pessoa), "
        "pra você escolher um arquivo .csv que já tenha exportado de uma query do Azure DevOps "
        "e deixado lá (ou numa subpasta)."
    )
    st.caption(
        "💡 Não usa Google Drive (ou prefere não configurar nada agora)? Escolha "
        f"**\"{OPCAO_ORIGEM_MANUAL}\"** logo acima - dá pra subir o arquivo .csv direto do seu "
        "computador, sem precisar compartilhar nenhuma pasta com ninguém."
    )

    email_servico = email_conta_servico()
    if not email_servico:
        st.warning(
            "A conta de serviço do Google Drive ainda não foi configurada neste app. Peça para "
            "o administrador configurar em Administração → Google Drive."
        )
        return

    # Cada usuário logado guarda a PRÓPRIA pasta raiz, numa chave separada
    # por username (ver core/config_app.py) - de propósito, não existe mais
    # uma pasta única/global configurada pelo administrador: cada pessoa
    # compartilha a pasta que ela mesma escolher com a conta de serviço, e
    # configura esse link aqui, sem depender de ninguém pra trocar depois.
    # Isso também significa que ninguém enxerga, por aqui, a pasta
    # configurada por outra pessoa - só a sua própria.
    username = AuthManager.current_username()
    chave_pasta = chave_pasta_raiz_google_drive(username)
    pasta_raiz_id = obter_configuracao(chave_pasta)

    with st.expander(
        "⚙️ Configurar/trocar a minha pasta do Google Drive", expanded=not pasta_raiz_id
    ):
        st.caption(
            "1️⃣ No Google Drive, compartilhe a pasta que você quer usar (botão direito na "
            "pasta → **Compartilhar** → cole o e-mail abaixo → permissão de **Leitor**):"
        )
        st.code(email_servico, language=None)
        st.caption("2️⃣ Copie o link dessa pasta (botão direito → **Copiar link**) e cole abaixo:")
        link_ou_id_digitado = st.text_input(
            "Link ou ID da minha pasta",
            key="drive_input_minha_pasta_raiz",
            placeholder="https://drive.google.com/drive/folders/XXXXXXXXXXXXXXXXXXXX",
        )
        if action_button("Salvar minha pasta", key="btn_salvar_minha_pasta_drive"):
            # Reseta os dois avisos persistidos (ver session_state abaixo) a
            # cada novo clique - só um dos três ramos abaixo (vazio / sem
            # mudança / mudança de verdade) decide o valor final de cada um,
            # pra nunca sobrar um aviso "preso" de um clique anterior.
            st.session_state["aviso_pasta_ja_configurada_drive"] = False
            st.session_state["erro_minha_pasta_raiz_drive"] = None
            if not link_ou_id_digitado.strip():
                st.warning("Cole o link ou o ID da pasta antes de salvar.")
            else:
                novo_id = extrair_id_pasta_do_link(link_ou_id_digitado)
                if novo_id == pasta_raiz_id:
                    # Mesmo ID que já estava salvo - não é uma inclusão nem uma
                    # alteração de verdade (ex.: usuário clicou "Salvar" de novo
                    # sem ter mudado o link colado). Pedido explícito: só tratar
                    # como "salvo"/gerar log de auditoria quando algo realmente
                    # muda - aqui não escreve no banco, não reseta a navegação
                    # já em cache, e não registra log nenhum, só avisa (depois
                    # do rerun, ver abaixo) que já era essa a pasta configurada.
                    st.session_state["aviso_pasta_ja_configurada_drive"] = True
                else:
                    with loading_overlay("Confirmando acesso à pasta antes de salvar, aguarde..."):
                        try:
                            # Confirma que a conta de serviço realmente enxerga essa
                            # pasta ANTES de salvar - evita configurar um ID errado
                            # (ou uma pasta ainda não compartilhada) sem nenhum
                            # aviso, o que só apareceria na hora de navegar.
                            testar_conexao_drive(novo_id)
                        except GoogleDriveError as erro:
                            st.session_state["erro_minha_pasta_raiz_drive"] = str(erro)
                        else:
                            definir_configuracao(chave_pasta, novo_id)
                            resetar_selecao_google_drive()
                            registrar_log(
                                TIPO_PAINEL, username,
                                f"Configurou a própria pasta do Google Drive para o ID '{novo_id}'",
                            )
            finish_action("btn_salvar_minha_pasta_drive")
            st.rerun()

        if st.session_state.get("erro_minha_pasta_raiz_drive"):
            st.error(
                "Não foi possível confirmar acesso a essa pasta, então ela NÃO foi salva: "
                + st.session_state["erro_minha_pasta_raiz_drive"]
            )
        elif st.session_state.get("aviso_pasta_ja_configurada_drive"):
            st.info("Essa já é a pasta configurada - nada para salvar.")

    if not pasta_raiz_id:
        st.info("Configure a sua pasta acima para liberar a navegação de arquivos.")
        return

    # A pilha de navegação (pasta raiz -> subpasta -> subpasta...) é
    # reiniciada automaticamente se a pasta raiz configurada por este
    # usuário mudou desde a última vez (ex.: ele trocou pra outra pasta) -
    # sem isso, quem já tinha navegado numa subpasta da pasta raiz ANTIGA
    # continuaria "preso" lá, sem nenhuma pista de que a raiz mudou.
    pilha = st.session_state.get("drive_pilha_pastas") or []
    if not pilha or pilha[0]["id"] != pasta_raiz_id:
        resetar_selecao_google_drive()
        pilha = [{"id": pasta_raiz_id, "nome": "📁 Minha pasta"}]
        st.session_state["drive_pilha_pastas"] = pilha

    pasta_atual = pilha[-1]

    st.markdown(f"**Local atual:** {' / '.join(item['nome'] for item in pilha)}")

    col_voltar, col_atualizar, _col_espaco = st.columns([1, 1.4, 2])
    with col_voltar:
        if len(pilha) > 1 and st.button("⬅️ Voltar", key="drive_btn_voltar", use_container_width=True):
            pilha.pop()
            st.session_state["drive_pilha_pastas"] = pilha
            st.session_state["drive_conteudo_cache"] = None
            st.rerun()
    with col_atualizar:
        # Cobre o cenário descrito no pedido original: a pasta do Drive pode
        # ganhar/perder arquivos a qualquer momento por fora do app - este
        # botão força reconsultar a pasta atual em vez de confiar só no que
        # já estava em cache desde a última navegação.
        if st.button("🔄 Atualizar lista desta pasta", key="drive_btn_atualizar", use_container_width=True):
            st.session_state["drive_conteudo_cache"] = None

    conteudo = st.session_state.get("drive_conteudo_cache")
    if conteudo is None:
        with loading_overlay("Consultando a pasta no Google Drive, aguarde..."):
            try:
                conteudo = listar_pastas_e_arquivos_csv(pasta_atual["id"])
                st.session_state["drive_conteudo_cache"] = conteudo
                st.session_state["erro_carga"] = None
            except GoogleDriveError as erro:
                st.session_state["erro_carga"] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao consultar pasta do Google Drive ('{pasta_atual['nome']}'): {erro}",
                )
                return

    if conteudo.subpastas:
        col_sub, col_entrar = st.columns([3, 1])
        with col_sub:
            subpasta_escolhida_nome = st.selectbox(
                "Subpastas nesta pasta",
                [item["nome"] for item in conteudo.subpastas],
                key="drive_subpasta_escolhida",
            )
        with col_entrar:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Entrar →", key="drive_btn_entrar", use_container_width=True):
                subpasta_escolhida = next(
                    item for item in conteudo.subpastas if item["nome"] == subpasta_escolhida_nome
                )
                pilha.append(subpasta_escolhida)
                st.session_state["drive_pilha_pastas"] = pilha
                st.session_state["drive_conteudo_cache"] = None
                st.rerun()
    else:
        st.caption("Esta pasta não tem subpastas.")

    st.divider()

    if not conteudo.arquivos_csv:
        st.info("Nenhum arquivo .csv encontrado nesta pasta.")
        return

    arquivo_escolhido_nome = st.selectbox(
        "Arquivo .csv nesta pasta",
        [item["nome"] for item in conteudo.arquivos_csv],
        key="drive_arquivo_escolhido",
    )

    importar = action_button(
        "Importar arquivo selecionado",
        key="btn_importar_drive",
        help="Baixa o arquivo escolhido do Google Drive e processa igual a um envio manual.",
    )

    if importar:
        arquivo = next(
            item for item in conteudo.arquivos_csv if item["nome"] == arquivo_escolhido_nome
        )
        with loading_overlay("Baixando e processando o arquivo, aguarde..."):
            try:
                resetar_dados_importados()
                st.session_state[CHAVE_CAMPOS_PERSONALIZADOS] = []
                conteudo_bytes = baixar_arquivo_csv(arquivo["id"])
                resultado = carregar_arquivo(io.BytesIO(conteudo_bytes), arquivo["nome"])
                mapeamento = detectar_mapeamento(resultado.dataframe)

                st.session_state["resultado_carga"] = resultado
                st.session_state["dataframe_bruto"] = resultado.dataframe
                st.session_state["mapeamento_colunas"] = mapeamento
                st.session_state["mapeamento_confirmado"] = False

                time.sleep(0.3)
            except (GoogleDriveError, DataLoadError) as erro:
                st.session_state["erro_carga"] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao importar '{arquivo['nome']}' do Google Drive: {erro}",
                )
            else:
                st.session_state["erro_carga"] = None
                caminho_pasta = " / ".join(item["nome"] for item in pilha)
                registrar_log(
                    TIPO_PAINEL, AuthManager.current_username(),
                    f"Importou arquivo '{arquivo['nome']}' do Google Drive · "
                    f"Pasta: {caminho_pasta} · {len(resultado.dataframe)} linhas",
                )
        finish_action("btn_importar_drive")
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
