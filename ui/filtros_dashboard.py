"""
Filtros de barra lateral (Período / Projeto / Sprint / Tipos de Teste /
Status) compartilhados entre páginas que exploram o mesmo arquivo importado
(Dashboard e Scrum/Sprints, ver `ui/pages/dashboard_page.py` e
`ui/pages/scrum_page.py`).

Extraído de `ui/pages/dashboard_page.py` quando a página de Scrum/Sprints foi
criada - as duas páginas usam exatamente os mesmos widgets (mesmas `key`),
então o filtro escolhido numa página continua aplicado ao trocar pra outra
(cada rerun do Streamlit só executa a página atual, então não há conflito de
`key` entre elas - só uma roda por vez).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import analytics
from core.column_mapper import MapeamentoColunas
from core.fuso_horario import agora_brasilia


def aplicar_filtros_sidebar(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> pd.DataFrame:
    df_filtrado = df

    # ---- Período: fica entre a navegação (radio) e a seção de Filtros ----
    coluna_data = mapeamento.coluna_data_principal(df)
    if coluna_data and coluna_data in df.columns:
        datas_validas = pd.to_datetime(df[coluna_data], errors="coerce").dropna()
        if not datas_validas.empty:
            data_min = datas_validas.min().date()
            data_max = datas_validas.max().date()

            # Período padrão na primeira visualização (antes de qualquer
            # "Confirmar intervalo" do usuário): do dia atual - a data em que
            # o arquivo está sendo consultado/importado - até um mês antes,
            # sempre dentro dos limites reais do arquivo importado.
            fim_padrao = min(max(agora_brasilia().date(), data_min), data_max)
            inicio_padrao = max(data_min, (pd.Timestamp(fim_padrao) - pd.DateOffset(months=1)).date())

            st.sidebar.markdown("### Período")
            col_de, col_ate = st.sidebar.columns(2)
            entrada_inicio = col_de.date_input(
                "De", value=st.session_state.get("filtro_data_inicio", inicio_padrao),
                min_value=data_min, max_value=data_max, key="input_data_inicio",
                format="DD/MM/YYYY",
            )
            entrada_fim = col_ate.date_input(
                "Até", value=st.session_state.get("filtro_data_fim", fim_padrao),
                min_value=data_min, max_value=data_max, key="input_data_fim",
                format="DD/MM/YYYY",
            )
            if st.sidebar.button("Confirmar intervalo", use_container_width=True, type="primary", key="btn_confirmar_intervalo"):
                st.session_state["filtro_data_inicio"] = entrada_inicio
                st.session_state["filtro_data_fim"] = entrada_fim

            inicio_aplicado = st.session_state.get("filtro_data_inicio", inicio_padrao)
            fim_aplicado = st.session_state.get("filtro_data_fim", fim_padrao)
            df_filtrado = analytics.filtrar_por_intervalo_datas(df_filtrado, coluna_data, inicio_aplicado, fim_aplicado)

    # ---- Filtros (Projeto / Sprint / Tipos de Teste / Status) ----
    st.sidebar.markdown("### Filtros")

    if mapeamento.projeto and mapeamento.projeto in df.columns:
        projetos = sorted(df[mapeamento.projeto].dropna().astype(str).unique().tolist())
        selecionados = st.sidebar.multiselect("Projeto", projetos, default=projetos, key="filtro_projeto")
        if selecionados:
            df_filtrado = df_filtrado[df_filtrado[mapeamento.projeto].astype(str).isin(selecionados)]

    if mapeamento.sprint and mapeamento.sprint in df.columns:
        sprints = sorted(df_filtrado[mapeamento.sprint].dropna().astype(str).unique().tolist())
        sprints_selecionados = st.sidebar.multiselect("Sprint", sprints, default=sprints, key="filtro_sprint")
        if sprints_selecionados:
            df_filtrado = df_filtrado[df_filtrado[mapeamento.sprint].astype(str).isin(sprints_selecionados)]

    if mapeamento.tipo_teste and mapeamento.tipo_teste in df.columns:
        tipos = sorted(df_filtrado[mapeamento.tipo_teste].dropna().astype(str).unique().tolist())
        tipos_selecionados = st.sidebar.multiselect("Tipos de Teste", tipos, default=tipos, key="filtro_tipo_teste")
        if tipos_selecionados:
            df_filtrado = df_filtrado[df_filtrado[mapeamento.tipo_teste].astype(str).isin(tipos_selecionados)]

    if mapeamento.status and mapeamento.status in df.columns:
        status_disponiveis = sorted(df_filtrado[mapeamento.status].dropna().astype(str).unique().tolist())
        status_selecionados = st.sidebar.multiselect("Status", status_disponiveis, default=status_disponiveis, key="filtro_status")
        if status_selecionados:
            df_filtrado = df_filtrado[df_filtrado[mapeamento.status].astype(str).isin(status_selecionados)]

    return df_filtrado
