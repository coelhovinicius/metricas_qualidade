"""
Modal de "novidades" mostrado logo após o login, avisando sobre as
alterações/melhorias/implementações feitas desde a última grande leva de
mudanças (ver `VERSAO_NOVIDADES_ATUAL` abaixo) - com opção de marcar "não
mostrar mais essas novidades" (persistida por usuário, ver
`core/config_app.py::chave_novidades_vista`) e atalhos para a documentação:
o guia específico do papel de quem está logado (Convidado ou Administrador)
e o "Guia Completo do Usuário" em PDF, que vale para os dois papéis (mesmo
PDF oferecido na página "Sobre o App" - ver `core/gerador_guia_pdf.py::
obter_bytes_pdf_atual`).

Segue o mesmo padrão de modal já usado em `app.py` (`_confirmar_nova_
análise`, decorado com `@st.dialog`) - chamado uma vez por sessão de
navegador, logo após a autenticação, antes de desenhar a barra lateral/
página atual (ver `renderizar_modal_novidades_se_necessario`, chamada em
`app.py::main`).

Quando houver uma nova leva de novidades para anunciar no futuro: atualize
`ITENS_NOVIDADES` abaixo E troque `VERSAO_NOVIDADES_ATUAL` por um valor
novo - trocar a versão é o que faz o modal voltar a aparecer até pra quem já
tinha marcado "não mostrar mais" da leva anterior (afinal, é conteúdo novo
que essa pessoa ainda não viu).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import streamlit as st

from auth.auth_manager import AuthManager
from core.config_app import chave_novidades_vista, definir_configuracao, obter_configuracao
from core.gerador_guia_pdf import obter_bytes_pdf_atual
from ui.pages.admin_page import usuario_e_admin

# ui/novidades.py -> ui -> raiz do projeto (onde os dois guias .md vivem)
_RAIZ_PROJETO = Path(__file__).resolve().parent.parent
_CAMINHO_GUIA_CONVIDADO = _RAIZ_PROJETO / "GUIA_CONVIDADO.md"
_CAMINHO_GUIA_ADMIN = _RAIZ_PROJETO / "GUIA_ADMIN.md"

# Identificador da leva de novidades atual - ver docstring do módulo, acima,
# sobre quando (e por que) trocar este valor.
VERSAO_NOVIDADES_ATUAL = "2026-08-scrum-sprints-story-points"

# (título, descrição) de cada novidade, da mais recente para a mais antiga -
# cobre tudo que foi entregue desde antes do trabalho de Scrum/Sprint
# começar (o seletor de tipo de gráfico) até a busca própria por Organização/
# Projeto/Area Path na página Scrum & Sprints.
ITENS_NOVIDADES: list[tuple[str, str]] = [
    (
        "☁️ Busca direta no Azure DevOps, só para Scrum & Sprints",
        "Novo expansor \"Fonte de dados desta página\" deixa escolher Organização, Projeto e "
        "Area Path(s) e buscar os dados direto da API do Azure DevOps - de forma isolada do "
        "resto do app, mesmo que o arquivo já importado misture vários projetos/áreas.",
    ),
    (
        "📈 Velocity clássica do Scrum, por Story Points",
        "Novo KPI e novo gráfico \"Velocity por Story Points (Sprint)\", ao lado do já existente "
        "\"Itens Concluídos por Sprint\" - com aviso automático quando poucos itens têm Story "
        "Points preenchido, pra não passar uma impressão errada. O guia de como montar a query "
        "no Azure DevOps também foi atualizado, orientando a incluir essa coluna.",
    ),
    (
        "🏃 Nova página Scrum & Sprints",
        "Área própria no menu, com indicadores de fluxo e ritmo de entrega - WIP total e idade "
        "média, itens criados/concluídos por período, carga de trabalho em aberto por "
        "responsável e mais - disponível para qualquer pessoa logada.",
    ),
    (
        "🎯 Escopo ajustável dos indicadores de Scrum",
        "Um expansor na própria página deixa incluir ou excluir tipos de item (ex.: Test Case, "
        "Test Plan) do cálculo dos indicadores, sem afetar o resto do app.",
    ),
    (
        "🧹 Fim das \"categorias fantasmas\" nos gráficos por Coluna do Board",
        "Os eixos dos gráficos por Coluna do Board (Dashboard e Scrum & Sprints) agora mostram "
        "só as colunas que realmente existem nos seus dados, sem barras/rótulos vazios sobrando.",
    ),
    (
        "📊 Seletor de tipo de gráfico no Dashboard",
        "Praticamente todo gráfico do painel agora deixa escolher o tipo de visualização mais "
        "adequado pra cada indicador (barras, linha, pizza, rosca, treemap, funil, radar e mais).",
    ),
]

# Guarda, PARA QUE USUÁRIO (nome de login), já foi decidido se o modal
# começa aberto nesta sessão do navegador - comparar contra o nome de
# usuário (em vez de só um `True`/`False`) evita que, num mesmo navegador/
# aba, uma pessoa que faça logout e outra que faça login em seguida "herde"
# o estado de quem saiu (streamlit-authenticator não limpa o
# `st.session_state` inteiro no logout, só as próprias chaves de sessão).
_CHAVE_SESSAO_USUARIO_AVALIADO = "novidades_usuario_avaliado_nesta_sessao"

# Controla se o modal está "aberto" agora - precisa ser reavaliada (e, se
# `True`, a função decorada com `@st.dialog` precisa ser chamada de novo) a
# CADA execução do script, não só na primeira vez - ver a docstring de
# `renderizar_modal_novidades_se_necessario`, abaixo, para o motivo.
_CHAVE_SESSAO_MODAL_ABERTO = "novidades_modal_aberto"


def _usuario_ja_dispensou_permanentemente(nome_usuario: str) -> bool:
    """
    True se este usuário já marcou "não mostrar mais essas novidades" para a
    leva ATUAL (`VERSAO_NOVIDADES_ATUAL`) em algum login anterior. Qualquer
    falha ao falar com o banco (Turso fora do ar, não configurado) é
    silenciosa aqui, caindo para "não dispensou" - o pior caso é o modal
    aparecer de novo, não travar o login por causa disso.
    """
    try:
        versao_vista = obter_configuracao(chave_novidades_vista(nome_usuario))
    except Exception:
        return False
    return versao_vista == VERSAO_NOVIDADES_ATUAL


def _persistir_dispensa_permanente(nome_usuario: str) -> None:
    try:
        definir_configuracao(chave_novidades_vista(nome_usuario), VERSAO_NOVIDADES_ATUAL)
    except Exception:
        pass  # ver comentário em _usuario_ja_dispensou_permanentemente, acima


def _bytes_guia_md(caminho: Path) -> Optional[bytes]:
    if not caminho.exists():
        return None
    return caminho.read_bytes()


@st.dialog("🎉 Novidades do Painel de Qualidade")
def _modal_novidades(nome_usuario: str, eh_admin: bool) -> None:
    st.caption(
        "Um resumo do que mudou no painel desde a última leva de novidades - dá pra fechar e "
        "continuar de onde parou a qualquer momento."
    )

    for titulo, descricao in ITENS_NOVIDADES:
        st.markdown(f"**{titulo}**")
        st.caption(descricao)

    st.divider()
    st.markdown("**📚 Quer saber mais?**")
    st.caption(
        "O guia abaixo, à esquerda, é o específico para o seu papel; o da direita é o Guia "
        "Completo (o mesmo conteúdo para qualquer pessoa)."
    )
    col_guia_papel, col_guia_comum = st.columns(2)

    with col_guia_papel:
        if eh_admin:
            bytes_guia_papel = _bytes_guia_md(_CAMINHO_GUIA_ADMIN)
            st.download_button(
                "⬇️ Guia do Administrador",
                data=bytes_guia_papel or b"",
                file_name="GUIA_ADMIN.md",
                mime="text/markdown",
                disabled=bytes_guia_papel is None,
                use_container_width=True,
                key="novidades_baixar_guia_admin",
            )
        else:
            bytes_guia_papel = _bytes_guia_md(_CAMINHO_GUIA_CONVIDADO)
            st.download_button(
                "⬇️ Guia do Convidado",
                data=bytes_guia_papel or b"",
                file_name="GUIA_CONVIDADO.md",
                mime="text/markdown",
                disabled=bytes_guia_papel is None,
                use_container_width=True,
                key="novidades_baixar_guia_convidado",
            )

    with col_guia_comum:
        bytes_pdf = obter_bytes_pdf_atual()
        st.download_button(
            "⬇️ Guia Completo (PDF)",
            data=bytes_pdf or b"",
            file_name="Guia_do_Usuario_QA.pdf",
            mime="application/pdf",
            disabled=bytes_pdf is None,
            use_container_width=True,
            key="novidades_baixar_guia_pdf",
        )

    st.divider()
    nao_mostrar_mais = st.checkbox(
        "Não mostrar mais essas novidades",
        key="novidades_checkbox_nao_mostrar",
    )
    if st.button("Fechar", key="novidades_botao_fechar", use_container_width=True, type="primary"):
        if nao_mostrar_mais:
            _persistir_dispensa_permanente(nome_usuario)
        st.session_state[_CHAVE_SESSAO_MODAL_ABERTO] = False
        st.rerun()


def renderizar_modal_novidades_se_necessario(auth_manager: AuthManager) -> None:
    """
    Chamada uma vez por execução de `main()` (ver `app.py`), logo após
    confirmar que a pessoa está autenticada. Decide se o modal de novidades
    deve estar aberto AGORA e, se sim, (re)abre o `@st.dialog`
    correspondente.

    Importante sobre `st.dialog`: ele só continua "aberto" enquanto a
    função decorada for chamada de novo a CADA execução do script (o
    Streamlit reexecuta o app inteiro a cada interação, e um diálogo que
    não for chamado de novo numa dessas execuções fecha sozinho) - por
    isso este código chama `_modal_novidades(...)` toda vez que
    `_CHAVE_SESSAO_MODAL_ABERTO` for `True`, não só na primeira vez. A
    decisão de ABRIR (ou não) só acontece uma vez por usuário, por sessão
    do navegador - controlada por `_CHAVE_SESSAO_USUARIO_AVALIADO` - e leva
    em conta se essa pessoa já marcou "não mostrar mais" para esta mesma
    leva de novidades (`VERSAO_NOVIDADES_ATUAL`) em outro login.
    """
    nome_usuario = auth_manager.current_username()
    if not nome_usuario:
        return

    if st.session_state.get(_CHAVE_SESSAO_USUARIO_AVALIADO) != nome_usuario:
        # Primeira vez que este usuário é avaliado nesta sessão do
        # navegador - decide, uma vez só, se o modal deve começar aberto.
        st.session_state[_CHAVE_SESSAO_USUARIO_AVALIADO] = nome_usuario
        st.session_state[_CHAVE_SESSAO_MODAL_ABERTO] = not _usuario_ja_dispensou_permanentemente(
            nome_usuario
        )

    if not st.session_state.get(_CHAVE_SESSAO_MODAL_ABERTO):
        return

    eh_admin = usuario_e_admin(nome_usuario)
    _modal_novidades(nome_usuario, eh_admin)
