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
    excluir_solicitacao,
    listar_solicitacoes,
    testar_conexao,
)
from core.turso_client import TursoError
from ui.components import action_button, finish_action, loading_overlay, render_header

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
        if action_button("Testar conexão", key="btn_testar_conexao_turso"):
            with loading_overlay("Testando conexão, aguarde..."):
                try:
                    testar_conexao()
                except TursoError as erro:
                    erro_teste = erro
                else:
                    erro_teste = None
            finish_action("btn_testar_conexao_turso")
            if erro_teste:
                st.error(str(erro_teste))
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
        if revogadas:
            st.caption(
                "\"Reverter revogação\" manda de volta para \"Pendentes\" (não direto para "
                "\"Já criadas\") - assim você reconfirma que a conta foi mesmo recriada em "
                "`auth/users.yaml` antes de marcar como criada de novo. \"Excluir\" apaga o "
                "registro desta solicitação de vez, sem afetar o acesso real de ninguém. Use "
                "as caixas de seleção pra excluir várias de uma vez, em vez de uma por uma."
            )
        else:
            st.caption("Nenhuma ainda.")
        _controles_selecao_em_massa("revogadas", revogadas)
        for solicitacao in revogadas:
            _renderizar_cartao_solicitacao(
                solicitacao, mostrar_reverter=True, mostrar_excluir=True, mostrar_selecao=True,
            )
        _botao_excluir_selecionadas("revogadas", revogadas)

    with st.expander(f"Rejeitadas ({len(rejeitadas)})"):
        if rejeitadas:
            st.caption(
                "\"Recuperar\" manda de volta para \"Pendentes\", caso a rejeição tenha sido "
                "engano. \"Excluir\" apaga o registro desta solicitação de vez. Use as caixas "
                "de seleção pra excluir várias de uma vez, em vez de uma por uma."
            )
        else:
            st.caption("Nenhuma ainda.")
        _controles_selecao_em_massa("rejeitadas", rejeitadas)
        for solicitacao in rejeitadas:
            _renderizar_cartao_solicitacao(
                solicitacao, mostrar_recuperar=True, mostrar_excluir=True, mostrar_selecao=True,
            )
        _botao_excluir_selecionadas("rejeitadas", rejeitadas)


def _chave_selecao(id_solicitacao: int) -> str:
    return f"sel_excluir_{id_solicitacao}"


def _controles_selecao_em_massa(prefixo_estado: str, lista: list[SolicitacaoConta]) -> None:
    """
    Desenha o checkbox "Selecionar todas" - precisa ser chamado ANTES do loop
    que desenha os cartões da lista (que desenham os checkboxes individuais),
    pra que o valor calculado aqui já valha pra eles no mesmo rerun (o
    Streamlit lê o valor atual de `st.session_state` na hora de desenhar cada
    checkbox - escrever a chave antes do widget existir "pré-marca" ele).

    Só reage quando o PRÓPRIO checkbox "Selecionar todas" é clicado (compara
    com o valor da vez anterior, guardado em `_selecionar_todas_anterior_*`) -
    assim, marcar/desmarcar itens individualmente não briga com isso; só
    clicar em "Selecionar todas" de novo (pra marcar ou desmarcar todo mundo)
    é que sobrescreve as caixinhas de cada item.
    """
    if not lista:
        return
    chave_todas = f"selecionar_todas_{prefixo_estado}"
    chave_anterior = f"_selecionar_todas_anterior_{prefixo_estado}"
    valor_todas = st.checkbox(f"Selecionar todas ({len(lista)})", key=chave_todas)
    if valor_todas != st.session_state.get(chave_anterior, False):
        for solicitacao in lista:
            st.session_state[_chave_selecao(solicitacao.id)] = valor_todas
        st.session_state[chave_anterior] = valor_todas


def _botao_excluir_selecionadas(prefixo_estado: str, lista: list[SolicitacaoConta]) -> None:
    """
    Chamado DEPOIS do loop que desenha os cartões (os checkboxes individuais
    já foram desenhados nesse rerun, então `st.session_state` já reflete o
    que está marcado agora). Só aparece quando há pelo menos uma selecionada.
    """
    if not lista:
        return
    selecionadas = [s for s in lista if st.session_state.get(_chave_selecao(s.id), False)]
    if selecionadas:
        if st.button(
            f"🗑️ Excluir selecionadas ({len(selecionadas)})",
            key=f"excluir_selecionadas_{prefixo_estado}",
            type="primary",
        ):
            _confirmar_exclusao_em_massa(selecionadas)


@st.dialog("Confirmar exclusão em massa")
def _confirmar_exclusao_em_massa(selecionadas: list[SolicitacaoConta]) -> None:
    """Mesma lógica de `_confirmar_acao`, mas apaga várias solicitações de uma vez."""
    plural = len(selecionadas) != 1
    st.warning(
        f"⚠️ Isso apaga de vez o registro d{'as' if plural else 'a'} "
        f"{len(selecionadas)} solicitaç{'ões' if plural else 'ão'} selecionada"
        f"{'s' if plural else ''} - não dá para desfazer. Não afeta o acesso real de "
        "ninguém, só o histórico aqui no painel."
    )
    for solicitacao in selecionadas:
        st.caption(f"**{solicitacao.nome}** · {solicitacao.email}")

    chave_confirmar = "confirma_exclusao_em_massa"
    col_confirmar, col_cancelar = st.columns(2)
    with col_confirmar:
        confirmar = action_button(
            "Sim, excluir selecionadas", key=chave_confirmar,
            use_container_width=True, type="primary",
        )
    with col_cancelar:
        cancelar = st.button(
            "Cancelar", key="cancela_exclusao_em_massa", use_container_width=True,
        )

    if confirmar:
        with loading_overlay(f"Excluindo {len(selecionadas)} solicitações, aguarde..."):
            for solicitacao in selecionadas:
                excluir_solicitacao(solicitacao.id)
                st.session_state.pop(_chave_selecao(solicitacao.id), None)
        finish_action(chave_confirmar)
        st.rerun()
    if cancelar:
        st.rerun()


@st.dialog("Confirmar ação")
def _confirmar_acao(
    solicitacao: SolicitacaoConta,
    texto_botao: str,
    mensagem_aviso: str,
    novo_status: Optional[str] = None,
    excluir: bool = False,
) -> None:
    """
    Modal de confirmação genérico, reaproveitado por TODAS as ações que
    alteram alguma coisa (criar, rejeitar, revogar, reverter revogação,
    recuperar, excluir) - nenhuma delas aplica a mudança direto no clique do
    botão da lista; todas passam por aqui primeiro, com um aviso específico
    do que vai acontecer. `excluir=True` apaga o registro de vez (usa
    `excluir_solicitacao`); caso contrário, muda o status para
    `novo_status` (usa `atualizar_status`).
    """
    st.warning(mensagem_aviso)
    st.caption(f"**{solicitacao.nome}** · {solicitacao.email}")

    sufixo_chave = "excluir" if excluir else novo_status
    chave_confirmar = f"confirma_{sufixo_chave}_{solicitacao.id}"

    col_confirmar, col_cancelar = st.columns(2)
    with col_confirmar:
        # `action_button` (não `st.button`) - some sozinho evita clique duplo
        # disparando duas requisições ao banco enquanto a primeira ainda está
        # em andamento; o `loading_overlay` logo abaixo é quem efetivamente
        # bloqueia a tela inteira (inclusive este modal) enquanto a chamada
        # ao Turso está em andamento.
        confirmar = action_button(
            texto_botao, key=chave_confirmar,
            use_container_width=True, type="primary",
        )
    with col_cancelar:
        cancelar = st.button(
            "Cancelar", key=f"cancela_{sufixo_chave}_{solicitacao.id}",
            use_container_width=True,
        )

    if confirmar:
        with loading_overlay("Aplicando alteração, aguarde..."):
            if excluir:
                excluir_solicitacao(solicitacao.id)
            else:
                atualizar_status(solicitacao.id, novo_status)
        finish_action(chave_confirmar)
        st.rerun()
    if cancelar:
        st.rerun()


def _renderizar_cartao_solicitacao(
    solicitacao: SolicitacaoConta,
    mostrar_acoes_pendente: bool = False,
    mostrar_revogar: bool = False,
    mostrar_reverter: bool = False,
    mostrar_recuperar: bool = False,
    mostrar_excluir: bool = False,
    mostrar_selecao: bool = False,
) -> None:
    with st.container(border=True):
        # `mostrar_selecao` só vem True em Revogadas/Rejeitadas (as duas
        # seções com exclusão em massa) - Pendentes e Já criadas continuam
        # sem a caixinha, já que não têm um botão de exclusão em massa.
        if mostrar_selecao:
            col_sel, col_info, col_acoes = st.columns([0.4, 2.6, 1])
            with col_sel:
                st.checkbox(
                    "Selecionar", key=_chave_selecao(solicitacao.id),
                    label_visibility="collapsed",
                )
        else:
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
                        solicitacao, "Sim, marcar como criada",
                        "Confirma que a conta desta pessoa já foi criada de verdade em "
                        "`auth/users.yaml`? Isso só atualiza o status aqui no painel - "
                        "não cria a conta sozinho.",
                        novo_status=STATUS_CRIADA,
                    )
                if st.button("❌ Rejeitar", key=f"rejeitar_{solicitacao.id}", use_container_width=True):
                    _confirmar_acao(
                        solicitacao, "Sim, rejeitar",
                        "Confirma que quer rejeitar esta solicitação? A pessoa continua "
                        "sem acesso ao painel, e a solicitação vai para \"Rejeitadas\".",
                        novo_status=STATUS_REJEITADA,
                    )
        elif mostrar_revogar:
            with col_acoes:
                if _email_protegido_de_revogacao(solicitacao.email):
                    st.caption("🛡️ Protegida")
                elif st.button("🚫 Revogar acesso", key=f"revogar_{solicitacao.id}", use_container_width=True):
                    _confirmar_acao(
                        solicitacao, "Sim, revogar acesso",
                        "⚠️ Isso marca o acesso desta pessoa como revogado aqui no painel. "
                        "NÃO desliga a conta de verdade sozinho - lembre de também remover/"
                        "desabilitar o usuário em `auth/users.yaml`.",
                        novo_status=STATUS_REVOGADA,
                    )
        else:
            with col_acoes:
                if mostrar_reverter:
                    if st.button("↩️ Reverter revogação", key=f"reverter_{solicitacao.id}", use_container_width=True):
                        _confirmar_acao(
                            solicitacao, "Sim, reverter revogação",
                            "Confirma que quer mover esta solicitação de volta para "
                            "\"Pendentes\"? Isso NÃO recria a conta sozinho - se você já "
                            "removeu o usuário de `auth/users.yaml`, lembre de recriá-lo "
                            "antes de marcar como criada de novo.",
                            novo_status=STATUS_PENDENTE,
                        )
                if mostrar_recuperar:
                    if st.button("♻️ Recuperar", key=f"recuperar_{solicitacao.id}", use_container_width=True):
                        _confirmar_acao(
                            solicitacao, "Sim, recuperar",
                            "Confirma que quer mover esta solicitação de volta para "
                            "\"Pendentes\"? Ela volta a aparecer na lista de solicitações "
                            "aguardando criação de conta.",
                            novo_status=STATUS_PENDENTE,
                        )
                if mostrar_excluir:
                    if st.button("🗑️ Excluir", key=f"excluir_{solicitacao.id}", use_container_width=True):
                        _confirmar_acao(
                            solicitacao, "Sim, excluir",
                            "⚠️ Isso apaga o registro desta solicitação de vez - não dá "
                            "para desfazer. Não afeta o acesso real de ninguém, só o "
                            "histórico aqui no painel.",
                            excluir=True,
                        )
