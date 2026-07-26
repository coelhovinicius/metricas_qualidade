"""Tela de login exibida enquanto o usuário não está autenticado."""

from __future__ import annotations

import streamlit as st

from auth.auth_manager import AuthManager
from core.solicitacoes_conta import registrar_solicitacao
from core.turso_client import TursoError
from ui.components import render_header

CHAVE_SOLICITACAO_ENVIADA = "solicitacao_conta_enviada"


def render_login_page(auth_manager: AuthManager) -> None:
    col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])

    with col_meio:
        render_header(
            titulo="Dashboard QA",
            subtitulo="Painel de Indicadores de Qualidade",
        )

        # Ordem: campos de usuário/senha -> botão "Entrar" (ambos renderizados
        # juntos pela lib de autenticação, dentro do mesmo st.form) -> texto de
        # contato com o link de solicitação de conta, por último.
        nome, status_autenticacao, username = auth_manager.render_login_form()

        if status_autenticacao is False:
            st.error("Usuário ou senha incorretos. Tente novamente, ou entre em contato com o administrador do sistema.")
        elif status_autenticacao is None:
            st.info("Informe suas credenciais para acessar o painel.")

        st.caption(
            "Caso não tenha uma conta, entre em contato com o administrador do sistema."
        )
        _renderizar_link_solicitacao_conta()


def _renderizar_link_solicitacao_conta() -> None:
    # `key=` no container vira a classe CSS `st-key-refu_link_solicitar_acesso`
    # (recurso nativo do Streamlit) - é o que ui/theme.py usa pra fazer o botão
    # do popover abaixo parecer um link de texto ("clique aqui") em vez de um
    # botão comum, sem depender de nenhum truque de marcador/CSS frágil.
    with st.container(key="refu_link_solicitar_acesso"):
        with st.popover("Clique aqui para solicitar acesso"):
            if st.session_state.get(CHAVE_SOLICITACAO_ENVIADA):
                st.success(
                    "Solicitação registrada! O administrador vai analisar no painel dele e "
                    "criar sua conta em breve."
                )
                if st.button("Enviar outra solicitação", key="btn_nova_solicitacao_conta"):
                    st.session_state[CHAVE_SOLICITACAO_ENVIADA] = False
                    st.rerun()
                return

            st.markdown("**Solicitar criação de conta**")
            st.caption(
                "Preencha os dados abaixo. Sua solicitação fica registrada só no painel "
                "administrativo — hoje, o administrador é a única pessoa com acesso a ela."
            )
            with st.form("form_solicitacao_conta", clear_on_submit=False):
                nome = st.text_input("Nome completo", key="solicitacao_nome")
                email = st.text_input("E-mail", key="solicitacao_email")
                justificativa = st.text_area(
                    "Motivo do acesso (opcional)",
                    key="solicitacao_justificativa",
                    placeholder="Ex.: faço parte do time de QA do projeto X",
                )
                enviar = st.form_submit_button("Enviar solicitação")

            if enviar:
                if not nome.strip() or not email.strip():
                    st.warning("Preencha ao menos o nome completo e o e-mail.")
                else:
                    try:
                        registrar_solicitacao(nome.strip(), email.strip(), justificativa.strip())
                    except TursoError as erro:
                        st.error(str(erro))
                    else:
                        st.session_state[CHAVE_SOLICITACAO_ENVIADA] = True
                        st.rerun()
