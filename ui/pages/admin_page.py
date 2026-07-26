"""Painel administrativo: solicitações de criação de conta (visível só para o admin)."""

from __future__ import annotations

from typing import Optional

import streamlit as st

from core.solicitacoes_conta import (
    STATUS_CRIADA,
    STATUS_PENDENTE,
    STATUS_REJEITADA,
    STATUS_REVOGADA,
    SolicitacaoConta,
    atualizar_status,
    listar_solicitacoes,
    testar_conexao,
)
from core.turso_client import TursoError
from ui.components import render_header

# Usuário (login, não o nome de exibição) tratado como administrador. Hoje só
# você tem esse acesso - se quiser dar acesso ao painel pra outro usuário do
# auth/users.yaml no futuro, é só trocar por uma lista/tupla aqui.
USUARIO_ADMIN = "admin"

# E-mails que nunca mostram o botão de revogar na seção "Já criadas" - a
# tabela de solicitações não guarda o usuário de login associado, então não
# tem como detectar sozinho "esse card é o do admin logado agora". Preencha
# aqui com o(s) seu(s) próprio(s) e-mail(s) (o mesmo usado ao preencher o
# formulário de solicitação de conta), pra nunca aparecer a opção de revogar
# o seu próprio acesso sem querer. Comparação é case-insensitive.
EMAILS_PROTEGIDOS_DE_REVOGACAO: set[str] = {
    # "seu-email@refuturiza.com",
}


def usuario_e_admin(username: Optional[str]) -> bool:
    return username == USUARIO_ADMIN


def _email_protegido_de_revogacao(email: str) -> bool:
    protegidos = {e.strip().lower() for e in EMAILS_PROTEGIDOS_DE_REVOGACAO if e.strip()}
    return email.strip().lower() in protegidos


def render_admin_page() -> None:
    render_header(
        titulo="Painel Administrativo",
        subtitulo="Solicitações de criação de conta recebidas pela tela de login.",
    )

    with st.expander("Diagnóstico da conexão com o banco de dados (Turso)"):
        if st.button("Testar conexão", key="btn_testar_conexao_turso"):
            try:
                testar_conexao()
            except TursoError as erro:
                st.error(str(erro))
            else:
                st.success("Conexão com o banco de dados funcionando normalmente.")

    try:
        pendentes = listar_solicitacoes(status=STATUS_PENDENTE)
        criadas = listar_solicitacoes(status=STATUS_CRIADA)
        rejeitadas = listar_solicitacoes(status=STATUS_REJEITADA)
        revogadas = listar_solicitacoes(status=STATUS_REVOGADA)
    except TursoError as erro:
        st.error(str(erro))
        return

    st.markdown(f"### Pendentes ({len(pendentes)})")
    st.caption(
        "Ao criar a conta manualmente em `auth/users.yaml` (gerando o hash da senha com "
        "`scripts/gerar_hash_senha.py`, como já é feito hoje), marque a solicitação como "
        "criada para tirá-la da lista de pendentes."
    )
    if not pendentes:
        st.info("Nenhuma solicitação pendente no momento.")
    for solicitacao in pendentes:
        _renderizar_cartao_solicitacao(solicitacao, mostrar_acoes_pendente=True)

    with st.expander(f"Já criadas ({len(criadas)})"):
        if criadas:
            st.caption(
                "Revogar aqui só atualiza o status neste painel (controle/auditoria) - "
                "lembre de também remover o acesso de verdade em `auth/users.yaml` (apagando "
                "o usuário ou trocando a senha), já que a criação/remoção de conta continua "
                "manual, fora deste app."
            )
        else:
            st.caption("Nenhuma ainda.")
        for solicitacao in criadas:
            _renderizar_cartao_solicitacao(solicitacao, mostrar_revogar=True)

    with st.expander(f"Revogadas ({len(revogadas)})"):
        if not revogadas:
            st.caption("Nenhuma ainda.")
        for solicitacao in revogadas:
            _renderizar_cartao_solicitacao(solicitacao, mostrar_reverter=True)

    with st.expander(f"Rejeitadas ({len(rejeitadas)})"):
        if not rejeitadas:
            st.caption("Nenhuma ainda.")
        for solicitacao in rejeitadas:
            _renderizar_cartao_solicitacao(solicitacao)


@st.dialog("Confirmar ação")
def _confirmar_acao(
    solicitacao: SolicitacaoConta,
    novo_status: str,
    texto_botao: str,
    mensagem_aviso: str,
) -> None:
    """
    Modal de confirmação genérico, reaproveitado pelas 4 ações que mudam
    status (criar, rejeitar, revogar, reverter revogação) - nenhuma delas
    aplica a mudança direto no clique do botão da lista; todas passam por
    aqui primeiro, com um aviso específico do que vai acontecer.
    """
    st.warning(mensagem_aviso)
    st.caption(f"**{solicitacao.nome}** · {solicitacao.email}")

    col_confirmar, col_cancelar = st.columns(2)
    with col_confirmar:
        if st.button(
            texto_botao, key=f"confirma_{novo_status}_{solicitacao.id}",
            use_container_width=True, type="primary",
        ):
            atualizar_status(solicitacao.id, novo_status)
            st.rerun()
    with col_cancelar:
        if st.button(
            "Cancelar", key=f"cancela_{novo_status}_{solicitacao.id}",
            use_container_width=True,
        ):
            st.rerun()


def _renderizar_cartao_solicitacao(
    solicitacao: SolicitacaoConta,
    mostrar_acoes_pendente: bool = False,
    mostrar_revogar: bool = False,
    mostrar_reverter: bool = False,
) -> None:
    with st.container(border=True):
        col_info, col_acoes = st.columns([3, 1])
        with col_info:
            st.markdown(f"**{solicitacao.nome}** · {solicitacao.email}")
            st.caption(f"Recebida em {solicitacao.criado_em} (UTC)")
            if solicitacao.justificativa:
                st.write(solicitacao.justificativa)
        if mostrar_acoes_pendente:
            with col_acoes:
                if st.button("✅ Marcar como criada", key=f"criar_{solicitacao.id}", use_container_width=True):
                    _confirmar_acao(
                        solicitacao, STATUS_CRIADA, "Sim, marcar como criada",
                        "Confirma que a conta desta pessoa já foi criada de verdade em "
                        "`auth/users.yaml`? Isso só atualiza o status aqui no painel - "
                        "não cria a conta sozinho.",
                    )
                if st.button("❌ Rejeitar", key=f"rejeitar_{solicitacao.id}", use_container_width=True):
                    _confirmar_acao(
                        solicitacao, STATUS_REJEITADA, "Sim, rejeitar",
                        "Confirma que quer rejeitar esta solicitação? A pessoa continua "
                        "sem acesso ao painel, e a solicitação vai para \"Rejeitadas\".",
                    )
        elif mostrar_revogar:
            with col_acoes:
                if _email_protegido_de_revogacao(solicitacao.email):
                    st.caption("🛡️ Protegida")
                elif st.button("🚫 Revogar acesso", key=f"revogar_{solicitacao.id}", use_container_width=True):
                    _confirmar_acao(
                        solicitacao, STATUS_REVOGADA, "Sim, revogar acesso",
                        "⚠️ Isso marca o acesso desta pessoa como revogado aqui no painel. "
                        "NÃO desliga a conta de verdade sozinho - lembre de também remover/"
                        "desabilitar o usuário em `auth/users.yaml`.",
                    )
        elif mostrar_reverter:
            with col_acoes:
                if st.button("↩️ Reverter revogação", key=f"reverter_{solicitacao.id}", use_container_width=True):
                    _confirmar_acao(
                        solicitacao, STATUS_CRIADA, "Sim, reverter revogação",
                        "Confirma que quer mover esta solicitação de volta para \"Já "
                        "criadas\"? Isso NÃO recria a conta sozinho - se você já removeu "
                        "o usuário de `auth/users.yaml`, lembre de recriá-lo também.",
                    )
