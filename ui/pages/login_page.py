"""Tela de login exibida enquanto o usuário não está autenticado."""

from __future__ import annotations

import re

import streamlit as st

from auth.auth_manager import AuthManager
from core.solicitacoes_conta import existe_solicitacao_pendente_com_email, registrar_solicitacao
from core.turso_client import TursoError
from ui.components import action_button, finish_action, loading_overlay, render_header

CHAVE_SOLICITACAO_ENVIADA = "solicitacao_conta_enviada"

# Validação simples de formato de e-mail: exige um "@" e, depois dele, um "."
# seguido de pelo menos um caractere (ex.: "nome@empresa.com") - não tenta
# validar o e-mail de forma completa/RFC-perfeita (isso é praticamente
# impossível sem enviar um e-mail de confirmação de verdade), só pegar o caso
# óbvio de alguém digitar algo sem "@" ou sem domínio.
PADRAO_EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def render_login_page(auth_manager: AuthManager) -> None:
    # `key=` neste container vira a classe CSS `st-key-refu_tela_login`
    # (recurso nativo do Streamlit, já usado em outros lugares deste app) -
    # usada em ui/theme.py só pra ENCOLHER os espaçamentos verticais desta
    # tela especificamente (sem afetar o resto do app), pra dar pra ver o
    # botão "Solicitar acesso" inteiro sem precisar de tela cheia (F11).
    with st.container(key="refu_tela_login"):
        col_esq, col_meio, col_dir = st.columns([1, 1.3, 1])

        with col_meio:
            render_header(
                titulo="Dashboard QA",
                subtitulo="Painel de Indicadores de Qualidade",
            )

            # Ordem: campos de usuário/senha -> botão "Entrar" (ambos
            # renderizados juntos pela lib de autenticação, dentro do mesmo
            # st.form) -> texto de contato + botão "Solicitar acesso", por
            # último.
            nome, status_autenticacao, username = auth_manager.render_login_form()

            if status_autenticacao is False:
                st.error("Usuário ou senha incorretos. Tente novamente, ou entre em contato com o administrador do sistema.")
            elif status_autenticacao is None:
                st.info("Informe suas credenciais para acessar o painel.")

            st.caption(
                "Caso não tenha uma conta, entre em contato com o administrador do sistema."
            )
            _renderizar_botao_solicitacao_conta()


def _renderizar_botao_solicitacao_conta() -> None:
    """
    Botão "Solicitar acesso" (laranja, largura total) que abre um modal
    (`st.dialog`) com o formulário - em vez do antigo link de texto que
    expandia um `st.popover` embaixo dele. O popover, quando o formulário
    tinha 3 campos + texto explicativo, ficava mais alto que a área visível
    da janela sem precisar de F11, e como ele "empurrava" o layout da página
    (em vez de flutuar por cima), dava a impressão de que os campos de
    Usuário/Senha tinham sumido. Um `st.dialog` é um overlay de verdade,
    centralizado na tela, independente do fluxo do restante da página -
    resolve os dois problemas de uma vez.

    `key=` no container vira a classe CSS `st-key-refu_btn_solicitar_acesso`
    (recurso nativo do Streamlit) - usada em ui/theme.py pra pintar este
    botão de laranja com fonte branca, igual ao "Entrar".
    """
    with st.container(key="refu_btn_solicitar_acesso"):
        if st.button("Solicitar acesso", key="btn_abrir_solicitacao_acesso", use_container_width=True):
            _dialogo_solicitar_acesso()

    if st.session_state.get(CHAVE_SOLICITACAO_ENVIADA):
        st.success(
            "Solicitação registrada! O administrador vai analisar no painel dele e "
            "criar sua conta em breve."
        )
        st.session_state[CHAVE_SOLICITACAO_ENVIADA] = False


@st.dialog("Solicitar criação de conta")
def _dialogo_solicitar_acesso() -> None:
    st.caption(
        "Preencha os dados abaixo. Sua solicitação fica registrada só no painel "
        "administrativo — hoje, o administrador é a única pessoa com acesso a ela."
    )
    nome = st.text_input("Nome completo", key="solicitacao_nome")
    email = st.text_input("E-mail", key="solicitacao_email")
    justificativa = st.text_area(
        "Motivo do acesso",
        key="solicitacao_justificativa",
        placeholder="Ex.: faço parte do time de QA do projeto X",
    )

    col_confirmar, col_cancelar = st.columns(2)
    with col_confirmar:
        # `action_button`, não `st.button`: some sozinho durante o envio, e o
        # `loading_overlay` logo abaixo bloqueia a tela inteira (inclusive
        # este modal) enquanto a solicitação é gravada no banco.
        confirmar = action_button(
            "Confirmar", key="btn_confirmar_solicitacao_acesso",
            use_container_width=True, type="primary",
        )
    with col_cancelar:
        cancelar = st.button(
            "Cancelar", key="btn_cancelar_solicitacao_acesso",
            use_container_width=True,
        )

    if cancelar:
        st.rerun()

    if confirmar:
        if not nome.strip() or not email.strip() or not justificativa.strip():
            # Precisa liberar o botão aqui também - sem isso, "Confirmar" fica
            # desabilitado pra sempre depois do primeiro clique com campo
            # vazio, porque `finish_action` só era chamado nos ramos de
            # sucesso/erro do envio, nunca neste aviso de validação. Nome,
            # e-mail e motivo do acesso agora são todos obrigatórios.
            finish_action("btn_confirmar_solicitacao_acesso")
            st.warning("Preencha o nome completo, o e-mail e o motivo do acesso.")
        elif not PADRAO_EMAIL_VALIDO.match(email.strip()):
            # Mesma lição do bug anterior: qualquer ramo que termina o clique
            # em "Confirmar" sem passar pelo envio de verdade também precisa
            # liberar o botão aqui, senão ele fica travado (desabilitado) pra
            # sempre depois do primeiro e-mail inválido.
            finish_action("btn_confirmar_solicitacao_acesso")
            st.warning("Informe um e-mail válido, no formato nome@dominio.com.")
        else:
            try:
                with loading_overlay("Enviando solicitação, aguarde..."):
                    # Evita que a mesma pessoa (ou alguém testando o
                    # formulário) mande várias solicitações pendentes com o
                    # mesmo e-mail, poluindo a lista de "Pendentes" do painel
                    # administrativo - só bloqueia enquanto já existir uma
                    # PENDENTE com esse e-mail; se a anterior já foi
                    # rejeitada, uma nova tentativa é permitida normalmente.
                    ja_pendente = existe_solicitacao_pendente_com_email(email.strip())
                    if not ja_pendente:
                        registrar_solicitacao(nome.strip(), email.strip(), justificativa.strip())
            except TursoError as erro:
                finish_action("btn_confirmar_solicitacao_acesso")
                st.error(str(erro))
            else:
                # Precisa liberar o botão aqui também - esse ramo não passa
                # necessariamente por um `st.rerun()` (o caso "já pendente"
                # mantém o modal aberto pra mostrar o aviso), então, sem essa
                # chamada, o "Confirmar" ficaria travado igual aos bugs
                # anteriores.
                finish_action("btn_confirmar_solicitacao_acesso")
                if ja_pendente:
                    st.warning(
                        "Já existe uma solicitação pendente com esse e-mail. "
                        "Aguarde a análise do administrador antes de enviar outra."
                    )
                else:
                    st.session_state[CHAVE_SOLICITACAO_ENVIADA] = True
                    st.rerun()
