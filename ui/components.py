"""
Componentes de interface reutilizáveis:

    - `render_header`: cabeçalho com a logo Refuturiza;
    - `loading_overlay`: context manager que escurece a tela e bloqueia
      interação enquanto uma operação pesada está em andamento, exibindo
      "Carregando, aguarde...";
    - `action_button`: botão que se desabilita sozinho após o primeiro clique
      para evitar múltiplas requisições disparadas por cliques repetidos;
    - `kpi_card`: cartão estilizado para indicadores numéricos.
    - `rolar_para_topo`: rola a janela pro topo (ver `app.py`).
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import streamlit as st
import streamlit.components.v1 as components

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


def rolar_para_topo() -> None:
    """
    Rola a janela pro topo - usada em `app.py` sempre que a TELA muda de
    verdade (login <-> app autenticado, ou troca de página no menu lateral:
    Importar Dados/Indicadores/Administração), pra quem chegou rolado pra
    baixo numa tela (ex.: até o fim do dashboard) não continuar rolado pra
    baixo na tela seguinte, que é outro conteúdo.

    `st.markdown(..., unsafe_allow_html=True)` NÃO executa `<script>` (o
    Streamlit sanitiza) - só `st.components.v1.html(...)` roda de verdade,
    porque desenha um iframe de componente próprio; o script roda DENTRO
    desse iframe, então precisa mirar `window.top` (a janela de verdade do
    navegador) pra rolar a página real - mesma técnica já usada em
    `auth/auth_manager.py` (`_forcar_logout_ao_fechar_navegador`) e em
    `ui/pages/login_page.py` (`_focar_campo_usuario`).

    Chama `scrollTo` mais de uma vez (na hora + alguns atrasos pequenos) de
    propósito: o próprio Streamlit tenta, sozinho, PRESERVAR a posição de
    rolagem entre reruns (pra não perder o lugar ao interagir com um
    filtro/widget) - se essa restauração dele rodar DEPOIS da nossa chamada
    única, ela cancelava o efeito e a tela voltava a aparecer rolada pra
    baixo. Repetir por ~1s garante que rolar pro topo seja sempre a ÚLTIMA
    palavra, não importa a ordem em que os dois rodem.
    """
    components.html(
        """
        <script>
        (function() {
            function rolarTopo() {
                window.top.scrollTo({top: 0, left: 0, behavior: "auto"});
            }
            rolarTopo();
            [50, 150, 300, 600, 1000].forEach(function(atraso) {
                setTimeout(rolarTopo, atraso);
            });
        })();
        </script>
        """,
        height=0,
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
