"""
Componentes de interface reutilizáveis:

    - `render_header`: cabeçalho com a logo Refuturiza;
    - `loading_overlay`: context manager que escurece a tela e bloqueia
      interação enquanto uma operação pesada está em andamento, exibindo
      "Carregando, aguarde...";
    - `action_button`: botão que se desabilita sozinho após o primeiro clique
      para evitar múltiplas requisições disparadas por cliques repetidos;
    - `kpi_card`: cartão estilizado para indicadores numéricos.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import streamlit as st

ASSETS_DIR = Path(__file__).parent.parent / "assets"


def _imagem_para_base64(caminho: Path) -> str:
    return base64.b64encode(caminho.read_bytes()).decode("utf-8")


def render_header(titulo: str, subtitulo: str = "") -> None:
    logo_path = ASSETS_DIR / "logo_refuturiza.png"
    if logo_path.exists():
        logo_b64 = _imagem_para_base64(logo_path)
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="Refuturiza" />'
    else:
        logo_html = ""

    st.markdown(
        f"""
        <div class="refu-header">
            {logo_html}
            <div class="refu-header-texto">
                <div class="refu-header-titulo">{titulo}</div>
                <div class="refu-header-subtitulo">{subtitulo}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def loading_overlay(mensagem: str = "Carregando, aguarde...") -> Generator[None, None, None]:
    """
    Exibe um overlay que escurece toda a tela e bloqueia cliques enquanto o
    bloco `with` está em execução. Some automaticamente ao final (sucesso
    ou exceção).
    """
    placeholder = st.empty()
    placeholder.markdown(
        f"""
        <div class="loading-overlay">
            <div class="loading-spinner"></div>
            <div>{mensagem}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        yield
    finally:
        placeholder.empty()


def action_button(
    label: str,
    key: str,
    type: str = "primary",
    help: Optional[str] = None,
    use_container_width: bool = False,
) -> bool:
    """
    Botão com proteção contra múltiplos cliques/requisições simultâneas.

    Enquanto uma ação disparada por este botão está em processamento
    (`finish_action` ainda não foi chamado), o botão permanece desabilitado
    em qualquer nova execução do script, mesmo que o usuário clique de novo.
    """
    flag_key = f"__processing__{key}"
    st.session_state.setdefault(flag_key, False)

    clicado = st.button(
        label,
        key=key,
        type=type,
        help=help,
        disabled=st.session_state[flag_key],
        use_container_width=use_container_width,
    )

    if clicado:
        st.session_state[flag_key] = True

    return clicado


def finish_action(key: str) -> None:
    """Libera o botão `key` para poder ser clicado novamente."""
    st.session_state[f"__processing__{key}"] = False


def kpi_card(label: str, valor: str, delta: Optional[str] = None, delta_positivo: bool = True) -> str:
    delta_html = ""
    if delta:
        classe = "positivo" if delta_positivo else "negativo"
        delta_html = f'<div class="kpi-delta {classe}">{delta}</div>'
    return f"""
        <div class="kpi-card">
            <div class="kpi-label">{label}</div>
            <div class="kpi-valor">{valor}</div>
            {delta_html}
        </div>
    """


def render_kpi_row(cartoes: list[tuple[str, str, Optional[str], bool]]) -> None:
    """Renderiza uma linha de cartões KPI. Cada item: (label, valor, delta, delta_positivo)."""
    colunas = st.columns(len(cartoes))
    for coluna, (label, valor, delta, delta_positivo) in zip(colunas, cartoes):
        with coluna:
            st.markdown(kpi_card(label, valor, delta, delta_positivo), unsafe_allow_html=True)