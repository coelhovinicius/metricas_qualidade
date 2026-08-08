"""
Refuturiza · Painel de Indicadores de Qualidade de Testes
============================================================

Aplicação Streamlit para importar arquivos de execução de testes (CSV/TXT)
e gerar indicadores e gráficos interativos de qualidade.

Estrutura do projeto:
    app.py                    -> ponto de entrada / roteamento de páginas
    auth/                      -> autenticação (login multiusuário + sessão persistida)
    core/                      -> regras de negócio (carga de arquivo, mapeamento, indicadores)
    ui/                        -> camada de apresentação (tema, componentes, páginas)
    utils/                     -> utilitários gerais (session_state)
    assets/                    -> logotipos e imagens
    scripts/                   -> utilitários de linha de comando (gerar hash de senha)

Para rodar:
    streamlit run app.py
"""

from __future__ import annotations

import base64
import traceback
from pathlib import Path

import streamlit as st

from auth.auth_manager import AuthManager
from core.logs_sistema import TIPO_ERRO, registrar_log
from ui.components import action_button, finish_action, loading_overlay
from ui.pages.admin_page import render_admin_page, usuario_e_admin
from ui.pages.dashboard_page import render_dashboard_page
from ui.pages.login_page import render_login_page
from ui.pages.upload_page import render_upload_page
from ui.theme import injetar_css_global
from utils.session import inicializar_sessao, resetar_para_nova_analise

ASSETS_DIR = Path(__file__).parent / "assets"


def _configurar_pagina() -> None:
    icone_path = ASSETS_DIR / "simbolo_refuturiza.png"
    st.set_page_config(
        page_title="Refuturiza · Indicadores de Qualidade",
        page_icon=str(icone_path) if icone_path.exists() else "📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )


def _renderizar_sidebar_navegacao(auth_manager: AuthManager) -> None:
    simbolo_path = ASSETS_DIR / "simbolo_refuturiza.png"
    if simbolo_path.exists():
        simbolo_b64 = base64.b64encode(simbolo_path.read_bytes()).decode("utf-8")
        st.sidebar.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                <img src="data:image/png;base64,{simbolo_b64}" style="height:34px;" />
                <span style="font-weight:700;font-size:1.05rem;">Refuturiza QA</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    nome_usuario = auth_manager.current_user_name() or "Usuário"
    st.sidebar.caption(f"Sessão de **{nome_usuario}**")
    st.sidebar.divider()

    paginas = {"upload": "📥 Importar Dados", "dashboard": "📊 Indicadores"}
    if usuario_e_admin(auth_manager.current_username()):
        paginas["admin"] = "⚙️ Administração"

    pagina_atual = st.session_state.get("pagina_atual", "upload")
    if pagina_atual not in paginas:
        # Ex.: usuário estava em "admin" e o app recarregou como outro
        # usuário sem esse acesso - volta pra página padrão em vez de deixar
        # a navegação "presa" numa página que não existe mais pra ele.
        pagina_atual = "upload"
        st.session_state["pagina_atual"] = pagina_atual

    # Botões de verdade (um por página), em vez do `st.sidebar.radio` de
    # antes - pedido explícito: os pontinhos de rádio deram lugar a botões
    # clicáveis, largura total, empilhados na barra lateral. O botão da
    # página atual fica destacado (`type="primary"`, mesma cor de marca dos
    # outros botões de destaque do app); os demais ficam no estilo padrão
    # (contorno). Clicar num botão que já é a página atual não faz nada -
    # sem re-render/piscar desnecessário.
    for chave_pagina, rotulo_pagina in paginas.items():
        eh_pagina_atual = chave_pagina == pagina_atual
        clicou = st.sidebar.button(
            rotulo_pagina,
            key=f"nav_botao_{chave_pagina}",
            use_container_width=True,
            type="primary" if eh_pagina_atual else "secondary",
        )
        if clicou and not eh_pagina_atual:
            st.session_state["pagina_atual"] = chave_pagina
            st.rerun()


@st.dialog("Nova Análise")
def _confirmar_nova_analise() -> None:
    st.warning(
        "⚠️ Isso limpa o arquivo importado e todos os indicadores/gráficos/filtros "
        "gerados a partir dele - inclusive o gráfico personalizado que você montou, se "
        "algum. Você volta para a página **Importar Dados** para processar um arquivo "
        "novo. Sua sessão continua logada, e a organização/projeto/query do Azure DevOps "
        "já carregados (se você usa a busca automática) não são afetados."
    )

    chave_confirmar = "confirma_nova_analise"
    col_confirmar, col_cancelar = st.columns(2)
    with col_confirmar:
        confirmar = action_button(
            "Sim, começar nova análise", key=chave_confirmar, use_container_width=True,
        )
    with col_cancelar:
        cancelar = st.button(
            "Cancelar", key="cancela_nova_analise", use_container_width=True,
        )

    if confirmar:
        with loading_overlay("Limpando dados, aguarde..."):
            resetar_para_nova_analise()
        finish_action(chave_confirmar)
        st.rerun()
    if cancelar:
        st.rerun()


def _renderizar_botao_nova_analise() -> None:
    # Só aparece depois que já existe algum arquivo processado - antes disso
    # não há "análise" nenhuma pra limpar, e o botão só ocuparia espaço.
    if st.session_state.get("dataframe_bruto") is None:
        return
    st.sidebar.divider()
    if st.sidebar.button(
        "🔄 Nova Análise",
        key="btn_abrir_nova_analise",
        use_container_width=True,
        help="Limpa o arquivo importado e os relatórios gerados, para processar um novo arquivo sem precisar dar F5.",
    ):
        _confirmar_nova_analise()


def main() -> None:
    _configurar_pagina()
    injetar_css_global()
    inicializar_sessao()

    auth_manager = AuthManager()

    if not AuthManager.is_authenticated():
        render_login_page(auth_manager)
        return

    _renderizar_sidebar_navegacao(auth_manager)
    _renderizar_botao_nova_analise()

    pagina_atual = st.session_state["pagina_atual"]
    try:
        if pagina_atual == "upload":
            render_upload_page()
        elif pagina_atual == "admin" and usuario_e_admin(auth_manager.current_username()):
            render_admin_page()
        else:
            render_dashboard_page()
    except Exception as exc:
        # Rede de segurança: qualquer exceção não tratada que escape de uma
        # página vai parar aqui, em vez de estourar a tela de erro padrão do
        # Streamlit (que expõe detalhe técnico pro usuário e não fica
        # guardada em lugar nenhum pra consulta depois). `st.rerun()`/
        # `st.stop()`, usados em várias páginas, NÃO caem neste `except` -
        # as duas levantam uma exceção de controle (`RerunException`/
        # `StopException`) que herda de `BaseException`, não de `Exception`,
        # de propósito (é assim que o próprio Streamlit é feito) - por isso
        # capturar só `Exception` aqui é seguro e não quebra navegação nem
        # os fluxos normais de "recarregar a página" espalhados pelo app.
        registrar_log(
            TIPO_ERRO, auth_manager.current_username(),
            f"Erro não tratado na página '{pagina_atual}': {exc}",
            detalhes=traceback.format_exc(),
        )
        st.error(
            "😕 Ocorreu um erro inesperado nesta página. O detalhe técnico foi registrado "
            "no log do sistema" + (
                " (Administração → Logs do Sistema → Erros Técnicos)."
                if usuario_e_admin(auth_manager.current_username())
                else " para o administrador consultar."
            )
        )

    # O botão "Sair" é renderizado por último, depois de qualquer filtro que a
    # página atual (ex.: dashboard) tenha adicionado à sidebar.
    st.sidebar.divider()
    auth_manager.logout()


if __name__ == "__main__":
    main()
