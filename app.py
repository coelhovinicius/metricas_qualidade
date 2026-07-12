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
from pathlib import Path

import streamlit as st

from auth.auth_manager import AuthManager
from ui.pages.dashboard_page import render_dashboard_page
from ui.pages.login_page import render_login_page
from ui.pages.upload_page import render_upload_page
from ui.theme import injetar_css_global
from utils.session import inicializar_sessao

ASSETS_DIR = Path(__file__).parent / "assets"


def _configurar_pagina() -> None:
    icone_path = ASSETS_DIR / "simbolo_refuturiza.png"
    st.set_page_config(
        page_title="Refuturiza · Indicadores de Qualidade",
        page_icon=str(icone_path) if icone_path.exists() else "📊",
        layout="wide",
        initial_sidebar_state="expanded",
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
    pagina_selecionada = st.sidebar.radio(
        "Navegação",
        options=list(paginas.keys()),
        format_func=lambda chave: paginas[chave],
        index=list(paginas.keys()).index(st.session_state.get("pagina_atual", "upload")),
        label_visibility="collapsed",
    )
    st.session_state["pagina_atual"] = pagina_selecionada


def main() -> None:
    _configurar_pagina()
    injetar_css_global()
    inicializar_sessao()

    auth_manager = AuthManager()

    if not AuthManager.is_authenticated():
        render_login_page(auth_manager)
        return

    _renderizar_sidebar_navegacao(auth_manager)

    if st.session_state["pagina_atual"] == "upload":
        render_upload_page()
    else:
        render_dashboard_page()

    # O botão "Sair" é renderizado por último, depois de qualquer filtro que a
    # página atual (ex.: dashboard) tenha adicionado à sidebar.
    st.sidebar.divider()
    auth_manager.logout()


if __name__ == "__main__":
    main()
