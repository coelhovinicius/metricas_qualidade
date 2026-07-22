"""Inicialização centralizada das chaves de `st.session_state` usadas na aplicação."""

from __future__ import annotations

import streamlit as st

CHAVES_PADRAO = {
    "pagina_atual": "upload",
    "dataframe_bruto": None,
    "resultado_carga": None,
    "mapeamento_colunas": None,
    "mapeamento_confirmado": False,
    "df_status_preparado": None,
}


def inicializar_sessao() -> None:
    for chave, valor_padrao in CHAVES_PADRAO.items():
        if chave not in st.session_state:
            st.session_state[chave] = valor_padrao


def resetar_dados_importados() -> None:
    """Limpa os dados de um arquivo importado anteriormente (ex: ao importar um novo)."""
    st.session_state["dataframe_bruto"] = None
    st.session_state["resultado_carga"] = None
    st.session_state["mapeamento_colunas"] = None
    st.session_state["mapeamento_confirmado"] = False
    st.session_state["df_status_preparado"] = None
    # Limpa também o período filtrado de uma importação anterior - sem isso,
    # um intervalo de datas confirmado para o arquivo antigo poderia ficar
    # fora do range do arquivo novo (e o widget de data quebraria), além de
    # não deixar o período padrão (último mês) ser recalculado na nova carga.
    st.session_state.pop("filtro_data_inicio", None)
    st.session_state.pop("filtro_data_fim", None)
