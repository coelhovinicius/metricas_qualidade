"""Tela de login exibida enquanto o usuário não está autenticado."""

from __future__ import annotations

import streamlit as st

from auth.auth_manager import AuthManager
from ui.components import render_header


def render_login_page(auth_manager: AuthManager) -> None:
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])

    with col_meio:
        render_header(
            titulo="Dashboard QA",
            subtitulo="Painel de Indicadores de Qualidade",
        )

        nome, status_autenticacao, username = auth_manager.render_login_form()

        if status_autenticacao is False:
            st.error("Usuário ou senha incorretos. Tente novamente, ou entre em contato com o administrador do sistema.")
        elif status_autenticacao is None:
            st.info("Informe suas credenciais para acessar o painel.")

        st.caption(
            "Caso não tenha uma conta, entre em contato com o administrador do sistema."
        )
