"""Página de importação do arquivo CSV/TXT (ou busca automática no Azure DevOps) e confirmação do mapeamento de colunas."""

from __future__ import annotations

import time

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
from core.column_mapper import MapeamentoColunas, detectar_mapeamento, normalizar_texto
from core.data_loader import DataLoadError, ResultadoCarga, carregar_arquivo
from core.logs_sistema import TIPO_ERRO, TIPO_PAINEL, registrar_log
from ui.components import action_button, finish_action, loading_overlay, render_header
from utils.session import resetar_dados_importados, resetar_selecao_azure_devops

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
    "admin": {
        "Vinícius Bemfica",
        "Vinícius Coelho Bemfica",
        "Vinicius Bemfica",
        "Vinicius Coelho Bemfica",
        "Vinícius Benfica",
        "Vinícius Coelho Benfica",
        "Vinicius Benfica",
        "Vinicius Coelho Benfica",
        "Vinicius Coelho",
        "Vinícius Coelho",
        "vinicius.refuturiza"
    }
}

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
    ("prioridade_board", "Prioridade (posição no board) - Stack Rank/Backlog Priority"),
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

    # O Streamlit "esquece" o valor de um widget sempre que ele deixa de ser
    # renderizado por pelo menos uma execução do script (ex.: o usuário foi
    # pra outra página do menu, onde este `st.radio` não é chamado) - ao
    # voltar, o widget nasce de novo do zero e cairia sempre na 1ª opção
    # ("Enviar arquivo"), escondendo todo o passo a passo do Azure DevOps já
    # configurado antes. Por isso o valor escolhido é espelhado numa chave
    # "solta" (não presa a nenhum widget, então nunca é esquecida) e usada
    # como valor inicial (`index=`) sempre que o widget nascer de novo.
    opcoes_origem = [OPCAO_ORIGEM_MANUAL, OPCAO_ORIGEM_AZURE]
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

    # Layout em duas colunas fixas, preenchidas em zigue-zague conforme cada
    # passo libera o próximo (linha 1 → PAT / Organização, linha 2 → Projeto
    # / Area Path(s), linha 3 → Query / Baixar relatório) - em vez de tudo
    # empilhado numa coluna só, esticando a tela toda na horizontal. As duas
    # colunas são criadas uma vez só aqui e reaproveitadas nos blocos `with`
    # abaixo (mesma técnica já usada no menu Administração) - cada passo só
    # aparece de verdade quando o anterior já foi cumprido; antes disso, o
    # lado correspondente mostra só uma dica do que falta.
    col_esquerda, col_direita = st.columns(2, gap="large")

    # ---------------------------------------------------- Linha 1, coluna esquerda: PAT
    with col_esquerda:
        # Mesmo cuidado do `origem_importacao` acima: o campo de PAT também é
        # um widget, e o Streamlit esquece o valor de um widget que não é
        # renderizado por pelo menos uma execução do script (ex.: o usuário
        # foi pra outra página do menu). Sem isso, o usuário seria obrigado a
        # colar o PAT de novo toda vez que voltasse à tela de importação
        # depois de navegar por outro menu - mesmo o PAT continua só em
        # memória desta sessão do navegador (nunca em disco), exatamente
        # como já era.
        st.text_input(
            "Seu Personal Access Token (PAT) do Azure DevOps",
            type="password",
            value=st.session_state.get("azure_pat_persistido", ""),
            key="azure_pat",
            placeholder="Cole aqui o seu PAT pessoal",
            help=(
                "Cada usuário usa o próprio PAT — ele nunca é salvo em disco nem nos Secrets "
                "do Streamlit, fica só na memória desta sessão do navegador e some ao sair. "
                "Gere um token em dev.azure.com → foto de perfil → Personal Access Tokens → "
                "New Token, com escopo 'Work Items (Read)'."
            ),
        )
    pat = st.session_state.get("azure_pat", "")
    st.session_state["azure_pat_persistido"] = pat

    if not pat:
        with col_direita:
            st.caption("👈 Informe o seu PAT ao lado para liberar a Organização.")
        return

    # ---------------------------------------------------- Linha 1, coluna direita: Organização
    with col_direita:
        organizacao_escolhida = st.selectbox(
            "Organização",
            options=ORGANIZACOES_SUGERIDAS,
            key="azure_organizacao_input",
            help="Nada é carregado da API até você clicar em \"Carregar organização\".",
        )
        # `key=` no container vira a classe CSS `st-key-ado_btn_carregar_organizacao`
        # (recurso nativo do Streamlit) - é o que ui/theme.py usa pra pintar só
        # este botão de azul, sem afetar os outros botões da página.
        with st.container(key="ado_btn_carregar_organizacao"):
            carregar_org = st.button(
                "Carregar organização",
                key="btn_carregar_organizacao_azure",
                use_container_width=True,
            )

    if carregar_org:
        with loading_overlay("Carregando projetos da organização, aguarde..."):
            try:
                resetar_selecao_azure_devops()
                projetos = listar_projetos(organizacao_escolhida, pat)
                st.session_state["azure_organizacao_carregada"] = organizacao_escolhida
                st.session_state["azure_ultima_organizacao_usada"] = organizacao_escolhida
                st.session_state["azure_projetos_disponiveis"] = projetos
                st.session_state["erro_carga"] = None
            except AzureDevOpsError as erro:
                st.session_state["azure_organizacao_carregada"] = None
                st.session_state["erro_carga"] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao carregar organização '{organizacao_escolhida}' do Azure DevOps: {erro}",
                )
        st.rerun()

    organizacao_carregada = st.session_state.get("azure_organizacao_carregada")
    if not organizacao_carregada:
        # Auto-recuperação: a organização já tinha sido carregada antes nesta
        # mesma sessão do navegador, mas esse passo foi perdido por algum
        # motivo (ex.: alguma navegação em outra parte do app limpou o
        # estado) - recarrega automaticamente pra não obrigar o usuário a
        # clicar em "Carregar organização" de novo só porque foi em outro menu.
        ultima_organizacao = st.session_state.get("azure_ultima_organizacao_usada")
        if ultima_organizacao:
            with loading_overlay("Restaurando organização usada anteriormente, aguarde..."):
                try:
                    projetos = listar_projetos(ultima_organizacao, pat)
                    st.session_state["azure_organizacao_carregada"] = ultima_organizacao
                    st.session_state["azure_projetos_disponiveis"] = projetos
                except AzureDevOpsError:
                    return
            st.rerun()
        return

    # ---------------------------------------------------- Linha 2, coluna esquerda: Projeto
    projetos_disponiveis = st.session_state.get("azure_projetos_disponiveis", [])
    opcoes_projeto = ["---"] + [projeto.nome for projeto in projetos_disponiveis]

    projeto_atual = st.session_state.get("azure_projeto_selecionado")

    # Auto-recuperação: se nenhum projeto está selecionado agora mas o
    # usuário já tinha escolhido um antes nesta mesma sessão do navegador (e
    # não foi ele mesmo que limpou a seleção de propósito agora, escolhendo
    # "---"), restaura automaticamente esse projeto e o que vinha depois dele
    # (Area Path e Query). Assim, voltar a esta tela depois de gerar os
    # gráficos e navegar por outros menus sempre mostra a configuração de
    # verdade em uso — e a partir daí o usuário pode trocar qualquer campo
    # livremente, em tempo real, sem precisar refazer os passos manualmente.
    limpou_manualmente = st.session_state.pop("azure_projeto_limpo_manualmente", False)
    if not projeto_atual and not limpou_manualmente:
        ultimo_projeto = st.session_state.get("azure_ultimo_projeto_usado")
        if ultimo_projeto and ultimo_projeto in opcoes_projeto:
            with loading_overlay("Restaurando projeto usado anteriormente, aguarde..."):
                try:
                    area_paths = listar_area_paths(organizacao_carregada, ultimo_projeto, pat)
                    queries = listar_queries(organizacao_carregada, ultimo_projeto, pat)
                    st.session_state["azure_projeto_selecionado"] = ultimo_projeto
                    st.session_state["azure_area_paths_disponiveis"] = area_paths
                    ultimos_area_paths = st.session_state.get("azure_ultimos_area_paths_usados", [])
                    st.session_state["azure_area_paths_selecionados"] = [
                        area_path for area_path in ultimos_area_paths if area_path in area_paths
                    ]
                    st.session_state["azure_queries_disponiveis"] = queries
                    mapa_queries_restauro = {item.caminho: item.id for item in queries}
                    ultima_query = st.session_state.get("azure_ultima_query_usada")
                    st.session_state["azure_query_selecionada_id"] = mapa_queries_restauro.get(ultima_query)
                except AzureDevOpsError:
                    pass
            st.rerun()

    indice_projeto = opcoes_projeto.index(projeto_atual) if projeto_atual in opcoes_projeto else 0

    with col_esquerda:
        projeto_escolhido = st.selectbox(
            "Projeto",
            options=opcoes_projeto,
            index=indice_projeto,
            key="azure_projeto_input",
        )

    if projeto_escolhido != "---" and projeto_escolhido != projeto_atual:
        # Escolher um projeto novo já dispara sozinho o carregamento do
        # próximo passo (Area Path + Queries) — não precisa de botão de
        # confirmação separado.
        with loading_overlay("Carregando informações do projeto, aguarde..."):
            try:
                area_paths = listar_area_paths(organizacao_carregada, projeto_escolhido, pat)
                queries = listar_queries(organizacao_carregada, projeto_escolhido, pat)
                st.session_state["azure_projeto_selecionado"] = projeto_escolhido
                st.session_state["azure_ultimo_projeto_usado"] = projeto_escolhido
                st.session_state["azure_area_paths_disponiveis"] = area_paths
                st.session_state["azure_area_paths_selecionados"] = []
                st.session_state["azure_queries_disponiveis"] = queries
                st.session_state["azure_query_selecionada_id"] = None
                st.session_state["erro_carga"] = None
            except AzureDevOpsError as erro:
                st.session_state["erro_carga"] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao carregar o projeto '{projeto_escolhido}' do Azure DevOps: {erro}",
                )
        st.rerun()
    elif projeto_escolhido == "---" and projeto_atual is not None:
        resetar_selecao_azure_devops(manter_organizacao=True)
        st.session_state["azure_projeto_limpo_manualmente"] = True
        st.rerun()

    projeto_selecionado = st.session_state.get("azure_projeto_selecionado")
    if not projeto_selecionado:
        with col_direita:
            st.caption("👈 Escolha um Projeto ao lado para liberar Area Path(s).")
        return

    # ------------------------------------------- Linha 2, coluna direita: Area Path(s) (opcional)
    area_paths_disponiveis = st.session_state.get("azure_area_paths_disponiveis", [])
    area_paths_atuais = [
        area_path
        for area_path in st.session_state.get("azure_area_paths_selecionados", [])
        if area_path in area_paths_disponiveis
    ]

    with col_direita:
        area_paths_escolhidos = st.multiselect(
            "Area Path(s) do Board no Projeto (opcional)",
            options=area_paths_disponiveis,
            default=area_paths_atuais,
            # A chave inclui o projeto atual de propósito: o Streamlit, quando um
            # widget já tinha valores selecionados, às vezes mantém esses valores
            # na tela mesmo depois de trocar as opções (aqui, ao trocar de
            # projeto) - forçar uma chave nova junto com a troca de projeto faz o
            # Streamlit tratar como um widget realmente novo, evitando seleção
            # "fantasma" do projeto anterior.
            key=f"azure_area_path_input__{projeto_selecionado}",
            help="Selecione um ou mais Area Paths para trazer work items de vários times/módulos de uma vez.",
        )
        st.caption(
            "Campo opcional. Se você escolher um ou mais Area Paths aqui, o app filtra os work "
            "items trazidos pela query para manter só os que estão dentro de algum deles (e dos "
            "seus sub-caminhos). Se deixar em branco, nenhum filtro extra de Area Path é aplicado "
            "— vale o que a própria query já retorna."
        )
    st.session_state["azure_area_paths_selecionados"] = area_paths_escolhidos
    if area_paths_escolhidos:
        st.session_state["azure_ultimos_area_paths_usados"] = area_paths_escolhidos

    # ---------------------------------------------- Linha 3, coluna esquerda: Query existente
    queries_disponiveis = st.session_state.get("azure_queries_disponiveis", [])
    mapa_queries = {item.caminho: item.id for item in queries_disponiveis}
    opcoes_query = ["---"] + list(mapa_queries.keys())

    # Mesmo raciocínio do Projeto/Area Path acima: sem calcular o `index=` a
    # partir do que já estava selecionado (`azure_query_selecionada_id`), esse
    # combobox nasceria sempre em "---" ao ser recriado (ex.: depois de
    # navegar por outro menu) - e, pior, a linha abaixo que espelha o valor
    # escolhido de volta pro session_state acabaria apagando a query que já
    # estava selecionada, mesmo sem o usuário ter tocado no campo.
    query_id_atual = st.session_state.get("azure_query_selecionada_id")
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
            key=f"azure_query_input__{projeto_selecionado}",  # mesmo motivo do Area Path acima
        )
        # Botões um do lado do outro, numa sub-divisão só dentro desta
        # coluna (coluna já é metade da tela - 3 colunas lado a lado aqui
        # ficaria apertado demais).
        col_atualizar, col_link = st.columns(2)
        with col_atualizar:
            atualizar_queries = st.button(
                "🔄 Atualizar lista",
                key="btn_atualizar_queries_azure",
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
                st.session_state["azure_queries_disponiveis"] = listar_queries(
                    organizacao_carregada, projeto_selecionado, pat
                )
                st.session_state["erro_carga"] = None
            except AzureDevOpsError as erro:
                st.session_state["erro_carga"] = str(erro)
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao atualizar a lista de queries do projeto '{projeto_selecionado}': {erro}",
                )
        st.rerun()

    st.session_state["azure_query_selecionada_id"] = (
        mapa_queries[query_escolhida_caminho] if query_escolhida_caminho != "---" else None
    )
    if query_escolhida_caminho != "---":
        st.session_state["azure_ultima_query_usada"] = query_escolhida_caminho

    if not queries_disponiveis:
        with col_esquerda:
            st.info(
                "Nenhuma query encontrada neste projeto ainda. Confira se o projeto certo está "
                "selecionado acima e se a query está salva em **Shared Queries** (ou em **My "
                "Queries** do mesmo usuário dono do PAT) — depois use **Atualizar lista**. Ou "
                "use o botão **Criar nova query** para criar uma diretamente no Azure DevOps."
            )

    # ------------------------------------- Abaixo das duas colunas: Baixar relatório
    # Fora do zigue-zague de propósito (não fica "grudado" numa das duas
    # colunas): como a coluna direita (Area Path(s), com o campo + legenda)
    # costuma ficar mais alta que a esquerda nessa altura do fluxo, colocar
    # este botão dentro de uma das colunas fazia ele nascer desalinhado,
    # meio solto no meio da tela - de largura total, abaixo de tudo, ele
    # sempre fica no mesmo lugar, sem depender da altura de nenhuma coluna.
    query_id = st.session_state.get("azure_query_selecionada_id")
    if not query_id:
        st.caption("👆 Selecione uma query salva acima para liberar o download.")
        return

    processar = action_button(
        "Baixar relatório atualizado",
        key="btn_baixar_azure_devops",
        help="Busca os dados mais recentes da query escolhida no Azure DevOps.",
    )

    if processar:
        with loading_overlay("Buscando dados no Azure DevOps, aguarde..."):
            try:
                resetar_dados_importados()
                st.session_state[CHAVE_CAMPOS_PERSONALIZADOS] = []
                dataframe = buscar_work_items_da_query(
                    organizacao_carregada, projeto_selecionado, query_id, pat
                )

                area_paths_filtro = st.session_state.get("azure_area_paths_selecionados") or []
                if area_paths_filtro and "Area Path" in dataframe.columns:
                    # Mantém a linha se o Area Path do item começar com QUALQUER um dos
                    # Area Paths escolhidos (ou for um sub-caminho de algum deles) - é a
                    # mesma lógica de "OR entre os selecionados" do multiselect de Projeto/
                    # Tipos de Teste/Status no dashboard.
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

                resultado = ResultadoCarga(
                    dataframe=dataframe,
                    encoding_detectado="—",
                    delimitador_detectado="—",
                    nome_arquivo=f"Azure DevOps · {projeto_selecionado} (consulta automática)",
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
                registrar_log(
                    TIPO_ERRO, AuthManager.current_username(),
                    f"Falha ao baixar relatório do Azure DevOps (projeto '{projeto_selecionado}'): {erro}",
                )
            else:
                st.session_state["erro_carga"] = None
                # Registra QUEM usou o PAT do Azure DevOps pra buscar os
                # dados - com DUAS identidades na mensagem, pra ficar
                # identificável de relance na tela de Logs do Sistema
                # (Administração → Logs do Sistema → Ações no Painel):
                #   1) o usuário LOGADO neste app (nome de exibição, não só
                #      o username de login);
                #   2) o dono de verdade do PAT usado, consultado na hora
                #      direto na API do Azure DevOps ("Connection Data") -
                #      é o nome que aparece no PRÓPRIO log de acesso do
                #      Azure DevOps também, então é o que de fato importa
                #      pra auditoria/rastreabilidade. Só não vem preenchido
                #      se essa chamada extra falhar por algum motivo (PAT
                #      revogado entre a busca e este ponto, instabilidade da
                #      API etc.) - nesse caso mostra "não identificado" em
                #      vez de deixar a mensagem incompleta sem explicação.
                identidade_pat = obter_identidade_autenticada(organizacao_carregada, pat)
                nome_usuario_app = AuthManager.current_user_name() or AuthManager.current_username()

                # Sinalizador visual de possível anomalia (pedido explícito:
                # "bater o olho" na tela de logs) - quando o dono de verdade
                # do PAT (segundo o próprio Azure DevOps) NÃO é a mesma
                # pessoa logada neste app no momento, prefixa a mensagem com
                # 🚩. Não prova nada sozinho (pode ser legítimo - alguém
                # emprestou o token de propósito), mas chama atenção pra
                # conferir. Comparação ignora acento/maiúscula (mesmo nome
                # escrito de um jeito ligeiramente diferente no app x no
                # Azure DevOps não deve disparar alarme falso) e só acontece
                # quando o dono do PAT foi identificado de verdade - sem
                # isso não dá pra concluir nada, então não marca como
                # anomalia só por falha técnica da consulta. Além do nome
                # cadastrado no login, também aceita qualquer apelido
                # conhecido pra esse mesmo login (ver
                # `APELIDOS_DONO_PAT_POR_USUARIO_APP`, acima) - cobre o caso
                # de o nome de exibição no Azure DevOps não bater 100% com o
                # nome cadastrado no login deste app, mesmo sendo a mesma
                # pessoa.
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
                    f"{prefixo}Baixou relatório do Azure DevOps via PAT próprio · "
                    f"Usuário logado no app: {nome_usuario_app} · "
                    f"Dono do PAT (Azure DevOps): {identidade_pat or 'não identificado'} · "
                    f"Projeto: '{projeto_selecionado}' · {len(dataframe)} itens",
                )
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
