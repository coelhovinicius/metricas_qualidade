"""Painel administrativo: solicitações de criação de conta (visível só para o admin)."""

from __future__ import annotations

import base64
from typing import Optional

import streamlit as st

from auth.auth_manager import AuthManager
from core.config_app import (
    CHAVE_CODIGO_VISAO_ADMIN_SOBRE_APP,
    CHAVE_FLUXOGRAMA_COMPLETO_BASE64,
    CHAVE_FLUXOGRAMA_COMPLETO_HASH,
    CHAVE_FLUXOGRAMA_PUBLICO_BASE64,
    CHAVE_FLUXOGRAMA_PUBLICO_HASH,
    CHAVE_GUIA_PDF_BASE64,
    CHAVE_GUIA_PDF_HASH,
    definir_configuracao,
    obter_configuracao,
    obter_configuracao_com_data,
)
from core.fuso_horario import formatar_data_hora_brasil
from core.gerador_fluxograma import (
    gerar_bytes_completo as gerar_fluxograma_completo_bytes,
    gerar_bytes_publico as gerar_fluxograma_publico_bytes,
    hash_conteudo_completo as hash_fluxograma_completo,
    hash_conteudo_publico as hash_fluxograma_publico,
)
from core.gerador_guia_pdf import gerar_pdf_bytes, hash_conteudo_atual
from core.google_drive_client import GoogleDriveError, email_conta_servico
from core.google_drive_client import testar_conexao as testar_conexao_drive
from core.logs_sistema import (
    ROTULOS_TIPO_LOG,
    TIPO_ERRO,
    TIPO_LOGIN,
    TIPO_PAINEL,
    limpar_logs_antigos,
    listar_logs,
    registrar_log,
)
from core.glpi_client import GlpiError
from core.glpi_client import testar_conexao as testar_conexao_glpi
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
from core.usuarios_autorizados_glpi import (
    adicionar_usuario_autorizado,
    listar_usuarios_autorizados,
    remover_usuario_autorizado,
)
from ui.components import action_button, finish_action, loading_overlay, render_header

# Rótulo (em português, pronto pra exibir) de cada mudança de status possível
# numa solicitação de conta - usado só pra montar a mensagem do log de
# auditoria em `_confirmar_acao` (ver `core/logs_sistema.py`).
_ROTULOS_ACAO_LOG = {
    STATUS_CRIADA: "marcou como criada",
    STATUS_REJEITADA: "rejeitou",
    STATUS_REVOGADA: "revogou o acesso de",
    STATUS_PENDENTE: "moveu de volta para pendentes",
}

# Usuário (login, não o nome de exibição) tratado como administrador. Hoje só
# você tem esse acesso - se quiser dar acesso ao painel pra outro usuário
# cadastrado (nos Secrets ou em auth/users.yaml, ver auth/auth_manager.py) no
# futuro, é só trocar por uma lista/tupla aqui.
USUARIO_ADMIN = "admin"

# E-mails que nunca mostram o botão de revogar na seção "Já criadas" - a
# tabela de solicitações não guarda o usuário de login associado, então não
# tem como detectar sozinho "esse card é o do admin logado agora". Preencha
# aqui com o(s) seu(s) próprio(s) e-mail(s) (o mesmo usado ao preencher o
# formulário de solicitação de conta), pra nunca aparecer a opção de revogar
# o seu próprio acesso sem querer. Comparação é case-insensitive.
EMAILS_PROTEGIDOS_DE_REVOGACAO: set[str] = {
    # "seu-email@empresa.com",
}


def usuario_e_admin(username: Optional[str]) -> bool:
    return username == USUARIO_ADMIN


def _email_protegido_de_revogacao(email: str) -> bool:
    protegidos = {e.strip().lower() for e in EMAILS_PROTEGIDOS_DE_REVOGACAO if e.strip()}
    return email.strip().lower() in protegidos


def _renderizar_secao_acesso_conteudo_admin_sobre_app() -> None:
    """
    Controla o "código de acesso" que libera, dentro da página "Sobre o App",
    o conteúdo que descreve os fluxos exclusivos de Administração (a trilha
    "quem administra" do fluxograma completo, e a seção "Administração") -
    ver `ui/pages/sobre_page.py::_usuario_tem_visao_admin`. Por padrão, esse
    conteúdo fica escondido para qualquer pessoa que não seja o admin; só
    quem digitar o código certo (repassado por você, por fora do app, pra
    quem você quiser) consegue desbloquear, e só na própria sessão do
    navegador dela - o desbloqueio não fica "ligado" pra sempre nem afeta
    outras pessoas.

    De propósito, NÃO é uma senha de autenticação de verdade (não tem
    usuário associado, não expira, é a mesma pra quem quer que a pessoa
    admin decida compartilhar) - é só um seletor de conteúdo informativo,
    guardado como configuração comum no Turso (mesma tabela de
    `core/config_app.py` usada pelo Guia do Usuário em PDF).
    """
    st.caption(
        "Por padrão, a seção \"Administração\" e a trilha \"quem administra\" do fluxograma, "
        "dentro de \"Sobre o App\", ficam escondidas para quem não é você. Defina um código "
        "aqui e repasse (por fora do app, só para quem você quiser) - a pessoa digita esse "
        "código na tela dela para desbloquear esse conteúdo."
    )

    try:
        codigo_atual = obter_configuracao(CHAVE_CODIGO_VISAO_ADMIN_SOBRE_APP)
    except TursoError as erro:
        st.error(str(erro))
        codigo_atual = None

    if codigo_atual:
        st.success(f"Código atual: `{codigo_atual}`")
    else:
        st.info("Nenhum código definido ainda - ninguém além de você enxerga esse conteúdo.")

    novo_codigo = st.text_input(
        "Novo código (deixe em branco e salve para desativar o desbloqueio para todo mundo)",
        key="input_codigo_visao_admin_sobre_app",
        placeholder="ex.: qa2026",
    )
    if action_button("💾 Salvar código", key="btn_salvar_codigo_visao_admin"):
        with loading_overlay("Salvando, aguarde..."):
            try:
                definir_configuracao(CHAVE_CODIGO_VISAO_ADMIN_SOBRE_APP, novo_codigo.strip())
            except TursoError as erro:
                erro_salvar: Optional[TursoError] = erro
            else:
                erro_salvar = None
                registrar_log(
                    TIPO_PAINEL, AuthManager.current_username(),
                    "Alterou o código de acesso ao conteúdo administrativo de \"Sobre o App\"",
                )
        finish_action("btn_salvar_codigo_visao_admin")
        if erro_salvar:
            st.error(str(erro_salvar))
        else:
            st.success("Código salvo.")
            st.rerun()


def render_admin_page() -> None:
    render_header(
        titulo="Administração",
        subtitulo="Solicitações de acesso e logs do sistema — visível só para o administrador.",
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

    with st.expander("🔒 Código de acesso ao conteúdo administrativo de \"Sobre o App\""):
        _renderizar_secao_acesso_conteudo_admin_sobre_app()

    # Quatro áreas dentro do mesmo menu "Administração", em abas em vez de uma
    # embaixo da outra na mesma rolagem - "Solicitações de Acesso" (criação/
    # revogação de conta), "Logs do Sistema" (auditoria/erros/acessos),
    # "Google Drive" (configuração da conta de serviço/pasta usada na busca
    # automática de arquivo, ver ui/pages/upload_page.py) e "Guia do Usuário"
    # (regerar o PDF de "Sobre o App" sem precisar de terminal/VSCode, ver
    # `_renderizar_secao_guia_pdf`) são assuntos distintos no dia a dia,
    # mesmo as duas primeiras usando o mesmo banco (Turso).
    aba_solicitacoes, aba_logs, aba_drive, aba_glpi, aba_guia = st.tabs(
        [
            "📋 Solicitações de Acesso", "🗒️ Logs do Sistema", "📁 Google Drive",
            "🔗 Integração GLPI", "📘 Guia do Usuário",
        ]
    )

    with aba_solicitacoes:
        _renderizar_secao_solicitacoes()

    with aba_logs:
        _renderizar_secao_logs()

    with aba_drive:
        _renderizar_secao_google_drive()

    with aba_glpi:
        _renderizar_secao_integracao_glpi()

    with aba_guia:
        _renderizar_secao_guia_pdf()
        st.divider()
        _renderizar_secao_fluxograma()


def _renderizar_secao_solicitacoes() -> None:
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
        "Ao criar a conta manualmente — gerando o hash da senha com "
        "`scripts/gerar_hash_senha.py` e adicionando o usuário em `[auth.credentials.usernames.*]` "
        "nos Secrets do Streamlit (local e/ou do Streamlit Community Cloud; `auth/users.yaml` "
        "local só entra como fallback de desenvolvimento, nunca deve ser commitado) — marque a "
        "solicitação como criada para tirá-la da lista de pendentes."
    )
    if not pendentes:
        st.info("Nenhuma solicitação pendente no momento.")
    for solicitacao in pendentes:
        _renderizar_cartao_solicitacao(solicitacao, mostrar_acoes_pendente=True)

    # "Já criadas" / "Revogadas" / "Rejeitadas" lado a lado em duas colunas
    # (em vez de empilhadas uma embaixo da outra) - preenche esquerda, direita,
    # esquerda, igual à ordem em que já apareciam antes. "Pendentes" acima
    # continua de largura total, fora dessa grade, por ser a seção mais
    # urgente/acionável da página. As colunas são criadas uma vez só e
    # reaproveitadas nos três `with` abaixo - cada bloco novo escrito na mesma
    # coluna empilha por baixo do anterior dela, sem afetar a outra coluna.
    col_esquerda, col_direita = st.columns(2, gap="medium")

    with col_esquerda:
        with st.expander(f"Já criadas ({len(criadas)})"):
            if criadas:
                st.caption(
                    "Revogar aqui só atualiza o status neste painel (controle/auditoria) - "
                    "lembre de também remover o acesso de verdade (apagando o usuário ou trocando "
                    "a senha) nos Secrets do Streamlit — ou em `auth/users.yaml`, se essa conta "
                    "ainda estiver só no arquivo local —, já que a criação/remoção de conta "
                    "continua manual, fora deste app."
                )
            else:
                st.caption("Nenhuma ainda.")
            for solicitacao in criadas:
                _renderizar_cartao_solicitacao(solicitacao, mostrar_revogar=True)

    with col_direita:
        with st.expander(f"Revogadas ({len(revogadas)})"):
            if revogadas:
                st.caption(
                    "\"Reverter revogação\" manda de volta para \"Pendentes\" (não direto para "
                    "\"Já criadas\") - assim você reconfirma que a conta foi mesmo recriada nos "
                    "Secrets (ou em `auth/users.yaml` local) antes de marcar como criada de novo. "
                    "\"Excluir\" apaga o registro desta solicitação de vez, sem afetar o acesso "
                    "real de ninguém. Use as caixas de seleção pra excluir várias de uma vez, em "
                    "vez de uma por uma."
                )
            else:
                st.caption("Nenhuma ainda.")
            _controles_selecao_em_massa("revogadas", revogadas)
            for solicitacao in revogadas:
                _renderizar_cartao_solicitacao(
                    solicitacao, mostrar_reverter=True, mostrar_excluir=True, mostrar_selecao=True,
                )
            _botao_excluir_selecionadas("revogadas", revogadas)

    with col_esquerda:
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


def _renderizar_secao_logs() -> None:
    """
    Aba "Logs do Sistema": três sub-abas (uma por categoria, ver
    `core/logs_sistema.py`) com as entradas mais recentes de cada uma. A
    tabela de logs é criada sozinha no banco na primeira vez que é preciso
    (mesma lógica que já existe pra solicitações de conta) - não exige
    nenhuma configuração além dos Secrets do Turso que o resto do painel já
    usa.
    """
    st.caption(
        "Histórico técnico/de auditoria do app. **Ações no Painel** registra o que cada "
        "administrador faz nas solicitações de conta (marcar como criada, revogar, "
        "rejeitar, excluir...) - hoje só dava pra ver o status atual de cada uma, sem saber "
        "quando/quem mudou o quê. **Erros Técnicos** guarda falhas capturadas durante o uso "
        "do app (ex.: falha ao buscar do Azure DevOps, erro inesperado em alguma página) - "
        "útil pra diagnosticar problemas sem depender só da mensagem amigável que aparece "
        "pra quem estava usando. **Login/Acessos** registra toda tentativa de entrar no "
        "app, com sucesso ou não."
    )

    aba_painel, aba_erro, aba_login = st.tabs([
        f"🗂️ {ROTULOS_TIPO_LOG[TIPO_PAINEL]}",
        f"⚠️ {ROTULOS_TIPO_LOG[TIPO_ERRO]}",
        f"🔑 {ROTULOS_TIPO_LOG[TIPO_LOGIN]}",
    ])
    with aba_painel:
        _renderizar_aba_log(TIPO_PAINEL)
    with aba_erro:
        _renderizar_aba_log(TIPO_ERRO, mostrar_detalhes_padrao=True)
    with aba_login:
        _renderizar_aba_log(TIPO_LOGIN)


def _renderizar_aba_log(tipo: str, mostrar_detalhes_padrao: bool = False) -> None:
    """
    Desenha uma aba de log: seletor de quantas entradas mostrar, o toggle
    "Ver com detalhes", botão de atualizar, a lista em si (tabela compacta,
    ou um cartão expansível por entrada com o texto INTEIRO, sem cortar,
    quando "Ver com detalhes" está marcado) e, por último, a limpeza de
    entradas antigas.

    `mostrar_detalhes_padrao`: só controla o valor INICIAL do toggle - em
    "Erros Técnicos" já começa marcado, porque o campo `detalhes` costuma
    trazer um traceback longo, que polui a tabela compacta; nas outras abas
    começa desmarcado, mas a pessoa pode ligar o toggle a qualquer momento -
    por exemplo, pra ler sem cortes uma mensagem longa em "Ações no Painel"
    (como as de download via PAT do Azure DevOps, que têm bastante texto).
    """
    col_limite, col_detalhes, col_atualizar = st.columns([2.2, 1.4, 1])
    with col_limite:
        limite = st.select_slider(
            "Quantas entradas mais recentes mostrar",
            options=[50, 100, 200, 500],
            value=100,
            key=f"logs_limite_{tipo}",
        )
    with col_detalhes:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        mostrar_detalhes = st.checkbox(
            "Ver com detalhes",
            value=mostrar_detalhes_padrao,
            key=f"logs_detalhes_{tipo}",
            help=(
                "Mostra cada entrada em um cartão separado, com o texto completo da "
                "mensagem (sem cortar) - útil quando a tabela compacta corta o texto "
                "da coluna Mensagem."
            ),
        )
    with col_atualizar:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Atualizar", key=f"logs_atualizar_{tipo}", use_container_width=True):
            st.rerun()

    try:
        logs = listar_logs(tipo=tipo, limite=limite)
    except TursoError as erro:
        st.error(str(erro))
        return

    if not logs:
        st.caption("Nenhum registro ainda.")
    else:
        st.caption(f"Mostrando {len(logs)} entrada(s) mais recente(s) (mais nova primeiro).")

        if mostrar_detalhes:
            for log in logs:
                with st.expander(f"{formatar_data_hora_brasil(log.criado_em)} · {log.mensagem}"):
                    st.caption(f"Usuário: {log.usuario or '—'}")
                    if log.detalhes:
                        st.code(log.detalhes, language="text")
        else:
            # `column_config` força "Mensagem" a ficar bem mais larga que
            # "Data/Hora"/"Usuário" (que são sempre curtas) - sem isso, a
            # tabela dividia a largura em 3 partes quase iguais e cortava o
            # texto da mensagem sem dar nenhum jeito de ler o resto (nem
            # scroll horizontal aparecia, porque a soma das colunas ainda
            # cabia na largura do container). Com "Mensagem" bem mais larga
            # que o espaço visível, a própria grade do Streamlit passa a
            # mostrar uma barra de rolagem horizontal - e a coluna, sendo
            # mais larga, mostra bem mais texto de cada vez mesmo sem rolar.
            st.dataframe(
                [
                    {
                        "Data/Hora": formatar_data_hora_brasil(log.criado_em),
                        "Usuário": log.usuario or "—",
                        "Mensagem": log.mensagem,
                    }
                    for log in logs
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Data/Hora": st.column_config.TextColumn(width="small"),
                    "Usuário": st.column_config.TextColumn(width="small"),
                    "Mensagem": st.column_config.TextColumn(width="large"),
                },
            )
            st.caption(
                "💡 Mensagem cortada? Arraste a barra de rolagem horizontal "
                "logo abaixo da tabela (ou marque \"Ver com detalhes\" acima "
                "pra ver cada entrada sem nenhum corte)."
            )

    with st.expander("Limpar entradas antigas"):
        dias = st.number_input(
            "Apagar entradas desta categoria com mais de quantos dias?",
            min_value=1, value=90, step=1, key=f"logs_dias_limpar_{tipo}",
        )
        if st.button("🗑️ Limpar entradas antigas", key=f"logs_limpar_{tipo}"):
            with loading_overlay("Limpando logs antigos, aguarde..."):
                try:
                    apagados = limpar_logs_antigos(int(dias), tipo=tipo)
                except TursoError as erro:
                    st.error(str(erro))
                else:
                    st.success(f"{apagados} entrada(s) apagada(s).")
                    st.rerun()


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
        nomes = ", ".join(f"{s.nome} ({s.email})" for s in selecionadas)
        registrar_log(
            TIPO_PAINEL, AuthManager.current_username(),
            f"Excluiu em massa {len(selecionadas)} solicitação(ões): {nomes}",
        )
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
                mensagem_log = f"Excluiu a solicitação de {solicitacao.nome} ({solicitacao.email})"
            else:
                atualizar_status(solicitacao.id, novo_status)
                rotulo_acao = _ROTULOS_ACAO_LOG.get(novo_status, f"mudou o status para '{novo_status}' de")
                mensagem_log = (
                    f"{rotulo_acao[0].upper()}{rotulo_acao[1:]} a solicitação de "
                    f"{solicitacao.nome} ({solicitacao.email})"
                )
        registrar_log(TIPO_PAINEL, AuthManager.current_username(), mensagem_log)
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
            st.caption(f"Recebida em {formatar_data_hora_brasil(solicitacao.criado_em)}")
            if solicitacao.justificativa:
                st.write(solicitacao.justificativa)
        if mostrar_acoes_pendente:
            with col_acoes:
                if st.button("✅ Marcar como criada", key=f"criar_{solicitacao.id}", use_container_width=True):
                    _confirmar_acao(
                        solicitacao, "Sim, marcar como criada",
                        "Confirma que a conta desta pessoa já foi criada de verdade nos "
                        "Secrets do Streamlit (ou em `auth/users.yaml` local)? Isso só "
                        "atualiza o status aqui no painel - não cria a conta sozinho.",
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
                        "desabilitar o usuário nos Secrets do Streamlit (ou em "
                        "`auth/users.yaml` local, se essa conta ainda estiver só lá).",
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
                            "removeu o usuário dos Secrets (ou de `auth/users.yaml` local), "
                            "lembre de recriá-lo antes de marcar como criada de novo.",
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


def _renderizar_secao_google_drive() -> None:
    """
    Diagnóstico da conta de serviço usada na busca de arquivo no Google
    Drive (ver `ui/pages/upload_page.py` → opção "Buscar arquivo no Google
    Drive"): mostra se a credencial está configurada (e o e-mail dela, pra
    referência), e permite testar a conexão com a API do Google.

    De propósito, NÃO existe mais aqui uma "pasta raiz" única/global pra
    configurar - cada usuário logado escolhe e guarda a PRÓPRIA pasta,
    direto na tela de Importar Dados (ver `core/config_app.py` →
    `chave_pasta_raiz_google_drive`). Isso evita que todo mundo dependa do
    administrador pra trocar de pasta, e evita que uma pessoa enxergue a
    pasta compartilhada por outra sem querer - aqui em Administração fica
    só o que é de fato administrativo: a CREDENCIAL da conta de serviço em
    si (que segue nos Secrets do Streamlit / arquivo local, nunca colada
    pela tela do app) e um jeito rápido de confirmar que ela está
    funcionando.
    """
    st.caption(
        "Diagnóstico da conta de serviço usada pela busca de arquivo no Google Drive (tela "
        "Importar Dados). Cada usuário configura a própria pasta diretamente por lá - aqui só "
        "dá pra conferir se a credencial da conta de serviço está funcionando."
    )

    email_servico = email_conta_servico()
    if not email_servico:
        st.warning(
            "Nenhuma conta de serviço do Google Drive configurada ainda. Configure a seção "
            "[google_drive] nos Secrets do Streamlit (produção) ou o arquivo "
            "core/google_drive_credentials.json (local) - veja o guia de configuração entregue "
            "junto com este recurso."
        )
        return

    # Duas colunas lado a lado (empilha sozinho em uma coluna só no celular -
    # comportamento nativo do `st.columns` do Streamlit, mesmo usado no
    # emparelhamento de gráficos do dashboard, ver `_FilaGraficos` em
    # `ui/pages/dashboard_page.py`): à esquerda o status da credencial já
    # configurada, à direita a ação de testar a conexão. Só existem esses
    # dois blocos aqui (não uma lista que se repete pra formar um "zigue-
    # zague" de várias linhas de verdade), mas separar em duas colunas ainda
    # evita um bloco fininho empilhado ocupando a largura toda da tela à toa.
    col_status, col_teste = st.columns(2, gap="large")
    with col_status:
        st.success(f"Conta de serviço configurada: `{email_servico}`")
        st.caption(
            "É esse o e-mail que cada usuário precisa compartilhar (permissão de Leitor) com a "
            "própria pasta do Drive, na tela Importar Dados → \"Buscar arquivo no Google Drive\"."
        )
    with col_teste:
        if action_button("Testar conexão", key="btn_testar_conexao_drive"):
            with loading_overlay("Testando conexão, aguarde..."):
                try:
                    testar_conexao_drive()
                except GoogleDriveError as erro:
                    erro_teste = erro
                else:
                    erro_teste = None
            finish_action("btn_testar_conexao_drive")
            if erro_teste:
                st.error(str(erro_teste))
            else:
                st.success("Credencial da conta de serviço válida - a API do Google Drive respondeu normalmente.")


def _renderizar_secao_integracao_glpi() -> None:
    """
    Aba "🔗 Integração GLPI": gerencia quem, além de você (admin), pode
    acessar a área "Integração GLPI x Azure DevOps" do menu lateral (ver
    `core/usuarios_autorizados_glpi.py` e `ui/pages/integracao_glpi_page.py`),
    e um diagnóstico rápido da conexão com a API do GLPI (mesmo padrão já
    usado para Turso/Google Drive acima).
    """
    with st.expander("Diagnóstico da conexão com o GLPI"):
        st.caption(
            "Confere se a seção [glpi] (url_base, app_token, user_token) está configurada nos "
            "Secrets e se a API REST do GLPI está respondendo."
        )
        if action_button("Testar conexão", key="btn_testar_conexao_glpi"):
            with loading_overlay("Testando conexão, aguarde..."):
                try:
                    testar_conexao_glpi()
                except GlpiError as erro:
                    erro_teste: Optional[GlpiError] = erro
                else:
                    erro_teste = None
            finish_action("btn_testar_conexao_glpi")
            if erro_teste:
                st.error(str(erro_teste))
            else:
                st.success("Conexão com o GLPI funcionando normalmente.")

    st.markdown("#### Usuários autorizados (além de você)")
    st.caption(
        "Digite o **username de login** deste app (o mesmo usado para entrar - não é e-mail "
        "nem nome de exibição) de cada pessoa que deve enxergar \"🔗 Integração GLPI\" no menu "
        "lateral dela. Você (admin) sempre tem acesso, esteja ou não nesta lista."
    )

    col_input, col_botao = st.columns([3, 1])
    with col_input:
        novo_username = st.text_input(
            "Username de login para autorizar",
            key="input_novo_usuario_autorizado_glpi",
            placeholder="ex.: joao.silva",
            label_visibility="collapsed",
        )
    with col_botao:
        adicionar = action_button(
            "➕ Adicionar", key="btn_adicionar_usuario_autorizado_glpi", use_container_width=True,
        )

    if adicionar:
        username_limpo = novo_username.strip()
        if not username_limpo:
            st.warning("Digite um username antes de adicionar.")
            finish_action("btn_adicionar_usuario_autorizado_glpi")
        else:
            with loading_overlay("Salvando, aguarde..."):
                try:
                    adicionar_usuario_autorizado(username_limpo, AuthManager.current_username())
                except TursoError as erro:
                    erro_salvar: Optional[TursoError] = erro
                else:
                    erro_salvar = None
                    registrar_log(
                        TIPO_PAINEL, AuthManager.current_username(),
                        f"Autorizou '{username_limpo}' a acessar a Integração GLPI",
                    )
            finish_action("btn_adicionar_usuario_autorizado_glpi")
            if erro_salvar:
                st.error(str(erro_salvar))
            else:
                st.success(f"'{username_limpo}' autorizado.")
                st.rerun()

    try:
        autorizados = listar_usuarios_autorizados()
    except TursoError as erro:
        st.error(str(erro))
        return

    if not autorizados:
        st.caption("Nenhum usuário extra autorizado ainda - só você (admin) tem acesso a esta área.")
        return

    for usuario in autorizados:
        with st.container(border=True):
            col_info, col_remover = st.columns([3, 1])
            with col_info:
                st.markdown(f"**{usuario.username}**")
                rodape = f"Autorizado em {formatar_data_hora_brasil(usuario.criado_em)}"
                if usuario.adicionado_por:
                    rodape += f" por {usuario.adicionado_por}"
                st.caption(rodape)
            with col_remover:
                if st.button(
                    "🗑️ Remover", key=f"remover_autorizado_glpi_{usuario.id}", use_container_width=True,
                ):
                    with loading_overlay("Removendo, aguarde..."):
                        remover_usuario_autorizado(usuario.id)
                        registrar_log(
                            TIPO_PAINEL, AuthManager.current_username(),
                            f"Removeu a autorização de '{usuario.username}' na Integração GLPI",
                        )
                    st.rerun()


def _renderizar_secao_guia_pdf() -> None:
    """
    Aba "📘 Guia do Usuário": recria o PDF "Guia Completo do Usuário" (ver
    `core/gerador_guia_pdf.py`) direto pelo navegador, com um clique - sem
    precisar abrir terminal nem VSCode. O resultado é gravado no banco de
    dados (Turso, mesma tabela genérica de `core/config_app.py`) - é de lá
    que a tela "Sobre o App" busca o PDF na hora de oferecer o download pra
    qualquer usuário (ver `ui/pages/sobre_page.py::_obter_bytes_guia_pdf`).
    Gravar no banco (e não só num arquivo em disco) é o que garante que o
    PDF sobrevive a reinícios/redeploys no Streamlit Community Cloud, cujo
    disco é temporário - clicar aqui uma vez basta; não depende de rodar
    `scripts/gerar_guia_usuario_pdf.py` (esse script continua existindo só
    como atalho pra quem quiser conferir o arquivo localmente).

    De propósito, NÃO regenera sozinho (ver decisão do usuário: prefere um
    botão manual) - em vez disso, mostra um aviso claro de "há alteração de
    conteúdo pendente" comparando um HASH do código atual de
    `_montar_story` (ver `core/gerador_guia_pdf.py::hash_conteudo_atual`)
    com o hash salvo junto da última versão gerada. Só compara hashes (não
    os PDFs em si) porque dois PDFs do MESMO conteúdo nunca são idênticos
    byte a byte entre si - o reportlab embute a data/hora de criação em cada
    geração.

    As EXPLICAÇÕES e o FLUXOGRAMA do resto de "Sobre o App" não precisam de
    nenhum botão/aviso parecido - são texto/HTML dentro do próprio código
    Python, então já aparecem sempre atualizados sozinhos a cada
    carregamento da página. Só este PDF (conteúdo estático, servido pronto)
    precisa ser recriado manualmente de vez em quando.
    """
    st.caption(
        "Recria o PDF \"Guia Completo do Usuário\" (o mesmo oferecido para download em "
        "\"Sobre o App\") com o conteúdo mais atual, sem precisar rodar nada fora do "
        "navegador."
    )
    st.caption(
        "💡 As explicações e o fluxograma do restante de \"Sobre o App\" não precisam de nada "
        "aqui - já são código, então aparecem sempre atualizados sozinhos a cada "
        "carregamento da página."
    )

    try:
        atual = obter_configuracao_com_data(CHAVE_GUIA_PDF_BASE64)
        hash_salvo = obter_configuracao(CHAVE_GUIA_PDF_HASH)
    except TursoError as erro:
        st.error(str(erro))
        atual = None
        hash_salvo = None

    hash_agora = hash_conteudo_atual()

    if not atual:
        st.info(
            "Nenhuma versão gerada pelo app ainda - \"Sobre o App\" está servindo o PDF padrão "
            "incluído no repositório. Clique no botão abaixo para gerar a primeira versão."
        )
    else:
        _, atualizado_em = atual
        data_formatada = formatar_data_hora_brasil(atualizado_em)
        if hash_salvo == hash_agora:
            st.success(
                f"✅ Atualizado - sem alterações pendentes. Última geração: {data_formatada}."
            )
        else:
            st.warning(
                f"⚠️ Há alterações no conteúdo do guia (no código) que ainda não foram enviadas "
                f"para o PDF - a última geração foi em {data_formatada}, com uma versão anterior "
                f"do conteúdo. Clique no botão abaixo para atualizar o que os usuários recebem."
            )

    if action_button("🔄 Gerar/Atualizar PDF agora", key="btn_gerar_guia_pdf"):
        with loading_overlay("Gerando o PDF, aguarde..."):
            try:
                pdf_bytes = gerar_pdf_bytes()
                definir_configuracao(CHAVE_GUIA_PDF_BASE64, base64.b64encode(pdf_bytes).decode("ascii"))
                definir_configuracao(CHAVE_GUIA_PDF_HASH, hash_agora)
            except Exception as erro:  # reportlab e TursoError não compartilham uma base comum
                erro_geracao: Optional[Exception] = erro
            else:
                erro_geracao = None
                registrar_log(
                    TIPO_PAINEL, AuthManager.current_username(),
                    "Gerou/atualizou o PDF do Guia Completo do Usuário",
                )
        finish_action("btn_gerar_guia_pdf")
        if erro_geracao:
            st.error(f"Não foi possível gerar/salvar o PDF: {erro_geracao}")
        else:
            st.success(
                "PDF gerado e salvo com sucesso - já disponível para download em \"Sobre o App\" "
                "para qualquer usuário, imediatamente (não precisa recarregar nem esperar nada)."
            )
            st.download_button(
                "⬇️ Baixar esta versão para manter o assets/ do repositório em dia (opcional)",
                data=pdf_bytes,
                file_name="Guia_do_Usuario_QA.pdf",
                mime="application/pdf",
                key="btn_baixar_guia_pdf_recem_gerado",
            )
            st.caption(
                "💡 Esse download é BYTE A BYTE igual ao que acabou de ser salvo no banco de "
                "dados (o que os usuários já estão recebendo) - baixe, substitua o arquivo em "
                "`assets/Guia_do_Usuario_QA.pdf` no seu repositório local, e faça `git add` + "
                "`git commit` + `git push`. Isso é só para manter o arquivo do repositório "
                "arrumado/igual ao que está no ar (ex.: caso o banco de dados algum dia seja "
                "resetado, o repositório já tem a versão certa como reserva) - os usuários já "
                "estão recebendo a versão certa mesmo sem você fazer esse passo."
            )


def _renderizar_secao_fluxograma() -> None:
    """
    Segundo bloco da mesma aba "📘 Guia do Usuário": recria as duas imagens
    do "Fluxograma completo do app" (retângulos + setas, ver
    `core/gerador_fluxograma.py`) direto pelo navegador - sem precisar de
    terminal, VSCode, nem ter o Graphviz instalado na sua própria máquina
    (só o ambiente do app precisa dele - já incluído em `requirements.txt`/
    `packages.txt`). Mesmíssimo padrão de `_renderizar_secao_guia_pdf` acima
    (grava no Turso para sobreviver a reinícios/redeploys, indicador de
    "alteração pendente" por hash do conteúdo, um clique regenera tudo) -
    aplicado às DUAS versões da imagem de uma vez só (a completa e a
    trancada), já que as duas vêm do mesmo desenho de trilhas e mudam juntas
    na prática.
    """
    st.markdown("**🗺️ Fluxograma completo do app (imagem)**")
    st.caption(
        "Recria as duas versões da imagem do fluxograma (retângulos + setas) mostrada em "
        "\"Sobre o App\" - a completa (duas trilhas) e a trancada (para quem não desbloqueou o "
        "conteúdo administrativo)."
    )
    st.caption(
        "💡 Só a IMAGEM precisa desse botão. Os cartões de texto do resto de \"Sobre o App\" "
        "(inclusive os da própria seção \"Fluxograma completo do app\") já são código Python - "
        "aparecem sempre atualizados sozinhos, sem precisar gerar nada."
    )

    try:
        atual_completo = obter_configuracao_com_data(CHAVE_FLUXOGRAMA_COMPLETO_BASE64)
        hash_salvo_completo = obter_configuracao(CHAVE_FLUXOGRAMA_COMPLETO_HASH)
        hash_salvo_publico = obter_configuracao(CHAVE_FLUXOGRAMA_PUBLICO_HASH)
    except TursoError as erro:
        st.error(str(erro))
        atual_completo = None
        hash_salvo_completo = None
        hash_salvo_publico = None

    hash_agora_completo = hash_fluxograma_completo()
    hash_agora_publico = hash_fluxograma_publico()
    sem_alteracao_pendente = (
        hash_salvo_completo == hash_agora_completo and hash_salvo_publico == hash_agora_publico
    )

    if not atual_completo:
        st.info(
            "Nenhuma versão gerada pelo app ainda - \"Sobre o App\" está servindo as imagens "
            "padrão incluídas no repositório. Clique no botão abaixo para gerar pelo Turso."
        )
    elif sem_alteracao_pendente:
        _, atualizado_em = atual_completo
        st.success(
            f"✅ Atualizado - sem alterações pendentes. Última geração: "
            f"{formatar_data_hora_brasil(atualizado_em)}."
        )
    else:
        _, atualizado_em = atual_completo
        st.warning(
            f"⚠️ Há alterações no desenho do fluxograma (no código, ver "
            f"`core/gerador_fluxograma.py`) que ainda não foram enviadas para a imagem - a "
            f"última geração foi em {formatar_data_hora_brasil(atualizado_em)}, com uma versão "
            f"anterior do conteúdo. Clique no botão abaixo para atualizar o que os usuários veem."
        )

    if action_button("🔄 Gerar/Atualizar fluxograma agora", key="btn_gerar_fluxograma"):
        with loading_overlay("Gerando o fluxograma, aguarde..."):
            try:
                bytes_completo = gerar_fluxograma_completo_bytes()
                bytes_publico = gerar_fluxograma_publico_bytes()
                definir_configuracao(
                    CHAVE_FLUXOGRAMA_COMPLETO_BASE64, base64.b64encode(bytes_completo).decode("ascii")
                )
                definir_configuracao(CHAVE_FLUXOGRAMA_COMPLETO_HASH, hash_agora_completo)
                definir_configuracao(
                    CHAVE_FLUXOGRAMA_PUBLICO_BASE64, base64.b64encode(bytes_publico).decode("ascii")
                )
                definir_configuracao(CHAVE_FLUXOGRAMA_PUBLICO_HASH, hash_agora_publico)
            except Exception as erro:  # graphviz e TursoError não compartilham uma base comum
                erro_geracao: Optional[Exception] = erro
            else:
                erro_geracao = None
                registrar_log(
                    TIPO_PAINEL, AuthManager.current_username(),
                    "Gerou/atualizou as imagens do Fluxograma completo do app",
                )
        finish_action("btn_gerar_fluxograma")
        if erro_geracao:
            st.error(f"Não foi possível gerar/salvar o fluxograma: {erro_geracao}")
        else:
            st.success(
                "Fluxograma gerado e salvo com sucesso - já disponível em \"Sobre o App\" para "
                "qualquer usuário, imediatamente (não precisa recarregar nem esperar nada)."
            )
            col_completo, col_publico = st.columns(2)
            with col_completo:
                st.image(bytes_completo, caption="Versão completa", use_container_width=True)
                st.download_button(
                    "⬇️ Baixar (manter assets/ em dia)",
                    data=bytes_completo,
                    file_name="fluxograma_completo.png",
                    mime="image/png",
                    key="btn_baixar_fluxograma_completo_recem_gerado",
                )
            with col_publico:
                st.image(bytes_publico, caption="Versão trancada (sem desbloqueio)", use_container_width=True)
                st.download_button(
                    "⬇️ Baixar (manter assets/ em dia)",
                    data=bytes_publico,
                    file_name="fluxograma_publico.png",
                    mime="image/png",
                    key="btn_baixar_fluxograma_publico_recem_gerado",
                )
            st.caption(
                "💡 Esses downloads são BYTE A BYTE iguais ao que acabou de ser salvo no banco de "
                "dados - baixe os dois, substitua os arquivos em `assets/fluxograma_completo.png` "
                "e `assets/fluxograma_publico.png` no seu repositório local, e faça `git add` + "
                "`git commit` + `git push`. Isso é só para manter o repositório arrumado/igual ao "
                "que está no ar - os usuários já estão recebendo a versão certa mesmo sem você "
                "fazer esse passo."
            )
