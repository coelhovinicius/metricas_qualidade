"""Painel administrativo: solicitações de criação de conta (visível só para o admin)."""

from __future__ import annotations

from typing import Optional

import streamlit as st

from core.solicitacoes_conta import (
    STATUS_CRIADA,
    STATUS_PENDENTE,
    STATUS_REJEITADA,
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


def usuario_e_admin(username: Optional[str]) -> bool:
    return username == USUARIO_ADMIN


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
        _renderizar_cartao_solicitacao(solicitacao)

    with st.expander(f"Já criadas ({len(criadas)})"):
        if not criadas:
            st.caption("Nenhuma ainda.")
        for solicitacao in criadas:
            _renderizar_cartao_solicitacao(solicitacao, somente_leitura=True)

    with st.expander(f"Rejeitadas ({len(rejeitadas)})"):
        if not rejeitadas:
            st.caption("Nenhuma ainda.")
        for solicitacao in rejeitadas:
            _renderizar_cartao_solicitacao(solicitacao, somente_leitura=True)


def _renderizar_cartao_solicitacao(solicitacao: SolicitacaoConta, somente_leitura: bool = False) -> None:
    with st.container(border=True):
        col_info, col_acoes = st.columns([3, 1])
        with col_info:
            st.markdown(f"**{solicitacao.nome}** · {solicitacao.email}")
            st.caption(f"Recebida em {solicitacao.criado_em} (UTC)")
            if solicitacao.justificativa:
                st.write(solicitacao.justificativa)
        if not somente_leitura:
            with col_acoes:
                if st.button("✅ Marcar como criada", key=f"criar_{solicitacao.id}", use_container_width=True):
                    atualizar_status(solicitacao.id, STATUS_CRIADA)
                    st.rerun()
                if st.button("❌ Rejeitar", key=f"rejeitar_{solicitacao.id}", use_container_width=True):
                    atualizar_status(solicitacao.id, STATUS_REJEITADA)
                    st.rerun()
