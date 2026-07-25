"""Página de dashboard: indicadores calculados e gráficos interativos/customizáveis."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import analytics
from core.column_mapper import MapeamentoColunas
from ui.components import action_button, finish_action, loading_overlay, render_header, render_kpi_row
from ui.theme import PALETA_GRAFICOS, PALETA_STATUS

TIPOS_GRAFICO_PADRAO = ["Barras", "Barras Horizontais", "Pizza", "Rosca", "Linha", "Área", "Treemap", "Pareto"]


def _colunas_disponiveis_para_grafico(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> dict[str, str]:
    """Monta {rótulo amigável: nome real da coluna} combinando campos mapeados, personalizados e colunas brutas."""
    disponiveis: dict[str, str] = {}

    rotulos_fixos = {
        "projeto": "Projeto",
        "status": "Status",
        "data_planejada": "Data Planejada",
        "data_execucao": "Data de Execução",
        "data_criacao": "Data de Criação",
        "tipo_teste": "Tipos de Teste",
        "responsavel": "Responsável / Executor",
        "caso_teste": "Caso de Teste / ID",
        "severidade": "Severidade / Prioridade",
    }
    for campo, rotulo in rotulos_fixos.items():
        coluna = getattr(mapeamento, campo)
        if coluna and coluna in df.columns:
            disponiveis[rotulo] = coluna

    for rotulo, coluna in mapeamento.campos_personalizados.items():
        if coluna in df.columns:
            disponiveis[rotulo] = coluna

    for coluna in df.columns:
        if coluna.startswith("__"):
            continue
        if coluna not in disponiveis.values():
            disponiveis[coluna] = coluna

    return disponiveis


def _aplicar_filtros_sidebar(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> pd.DataFrame:
    df_filtrado = df

    # ---- Período: fica entre a navegação (radio) e a seção de Filtros ----
    coluna_data = mapeamento.coluna_data_principal()
    if coluna_data and coluna_data in df.columns:
        datas_validas = pd.to_datetime(df[coluna_data], errors="coerce").dropna()
        if not datas_validas.empty:
            data_min = datas_validas.min().date()
            data_max = datas_validas.max().date()

            # Período padrão na primeira visualização (antes de qualquer
            # "Confirmar intervalo" do usuário): do dia atual - a data em que
            # o arquivo está sendo consultado/importado - até um mês antes,
            # sempre dentro dos limites reais do arquivo importado.
            fim_padrao = min(max(datetime.now().date(), data_min), data_max)
            inicio_padrao = max(data_min, (pd.Timestamp(fim_padrao) - pd.DateOffset(months=1)).date())

            st.sidebar.markdown("### Período")
            col_de, col_ate = st.sidebar.columns(2)
            entrada_inicio = col_de.date_input(
                "De", value=st.session_state.get("filtro_data_inicio", inicio_padrao),
                min_value=data_min, max_value=data_max, key="input_data_inicio",
            )
            entrada_fim = col_ate.date_input(
                "Até", value=st.session_state.get("filtro_data_fim", fim_padrao),
                min_value=data_min, max_value=data_max, key="input_data_fim",
            )
            if st.sidebar.button("Confirmar intervalo", use_container_width=True, type="primary", key="btn_confirmar_intervalo"):
                st.session_state["filtro_data_inicio"] = entrada_inicio
                st.session_state["filtro_data_fim"] = entrada_fim

            inicio_aplicado = st.session_state.get("filtro_data_inicio", inicio_padrao)
            fim_aplicado = st.session_state.get("filtro_data_fim", fim_padrao)
            df_filtrado = analytics.filtrar_por_intervalo_datas(df_filtrado, coluna_data, inicio_aplicado, fim_aplicado)

    # ---- Filtros (Projeto / Tipos de Teste / Status) ----
    st.sidebar.markdown("### Filtros")

    if mapeamento.projeto and mapeamento.projeto in df.columns:
        projetos = sorted(df[mapeamento.projeto].dropna().astype(str).unique().tolist())
        selecionados = st.sidebar.multiselect("Projeto", projetos, default=projetos)
        if selecionados:
            df_filtrado = df_filtrado[df_filtrado[mapeamento.projeto].astype(str).isin(selecionados)]

    if mapeamento.tipo_teste and mapeamento.tipo_teste in df.columns:
        tipos = sorted(df_filtrado[mapeamento.tipo_teste].dropna().astype(str).unique().tolist())
        tipos_selecionados = st.sidebar.multiselect("Tipos de Teste", tipos, default=tipos)
        if tipos_selecionados:
            df_filtrado = df_filtrado[df_filtrado[mapeamento.tipo_teste].astype(str).isin(tipos_selecionados)]

    if mapeamento.status and mapeamento.status in df.columns:
        status_disponiveis = sorted(df_filtrado[mapeamento.status].dropna().astype(str).unique().tolist())
        status_selecionados = st.sidebar.multiselect("Status", status_disponiveis, default=status_disponiveis)
        if status_selecionados:
            df_filtrado = df_filtrado[df_filtrado[mapeamento.status].astype(str).isin(status_selecionados)]

    return df_filtrado


def _selecionar_tipo_grafico(chave: str, opcoes: list[str] = None) -> str:
    opcoes = opcoes or TIPOS_GRAFICO_PADRAO
    return st.selectbox("Tipo de gráfico", opcoes, key=f"tipo_grafico_{chave}")


def _cores_por_posicao(quantidade: int) -> list[str]:
    """Cicla pela paleta de gráficos, uma cor por posição/categoria (não por valor)."""
    return [PALETA_GRAFICOS[indice % len(PALETA_GRAFICOS)] for indice in range(quantidade)]


def _construir_grafico_pareto(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    """
    Gráfico de Pareto: barras com o valor de cada categoria (mantendo a ordem
    em que os dados já chegam - todas as funções de indicador já entregam em
    ordem decrescente) + linha de percentual acumulado num eixo secundário
    (0-100%), com uma referência pontilhada em 80% (o "80/20" da análise de
    Pareto). É a exceção deliberada à regra de "nunca dois eixos Y": aqui o
    segundo eixo é sempre um percentual acumulado 0-100%, uma convenção
    padrão desse tipo de gráfico, não duas métricas arbitrárias em escalas
    diferentes.
    """
    dados = df.reset_index(drop=True)
    total = dados[y].sum()
    percentual_acumulado = (dados[y].cumsum() / total * 100) if total else dados[y].cumsum().astype(float)

    fig = go.Figure()
    fig.add_bar(
        x=dados[x], y=dados[y], name=y,
        marker_color=_cores_por_posicao(len(dados)),
        text=dados[y], textposition="outside",
    )
    fig.add_scatter(
        x=dados[x], y=percentual_acumulado, name="% acumulado",
        mode="lines+markers", yaxis="y2",
        line=dict(color=PALETA_GRAFICOS[7], width=2),
        marker=dict(size=6, color=PALETA_GRAFICOS[7]),
    )
    fig.update_layout(
        yaxis=dict(title=y),
        yaxis2=dict(title="% acumulado", overlaying="y", side="right", range=[0, 105], ticksuffix="%"),
        shapes=[
            dict(
                type="line", xref="paper", x0=0, x1=1, yref="y2", y0=80, y1=80,
                line=dict(color="#8C8C8C", width=1, dash="dot"),
            )
        ],
    )
    return fig


def _plotar(df: pd.DataFrame, tipo: str, x: str, y: str, chave: str, cor: Optional[str] = None) -> None:
    cor_discreta = PALETA_STATUS if cor == "__status_bruto__" and set(df[cor].unique()) <= set(PALETA_STATUS) else None

    if tipo == "Barras":
        fig = px.bar(df, x=x, y=y, color=cor, color_discrete_sequence=PALETA_GRAFICOS,
                      color_discrete_map=cor_discreta, text_auto=True)
        if cor is None:
            # Sem uma segunda dimensão pra agrupar/empilhar: colore cada barra por
            # posição (categoria), sem criar legenda nova - é a mesma série, só
            # com uma cor por categoria em vez de uma cor única pra todo o gráfico.
            fig.update_traces(marker_color=_cores_por_posicao(len(df)))
    elif tipo == "Barras Horizontais":
        fig = px.bar(df, x=y, y=x, color=cor, orientation="h", color_discrete_sequence=PALETA_GRAFICOS,
                      color_discrete_map=cor_discreta, text_auto=True)
        if cor is None:
            fig.update_traces(marker_color=_cores_por_posicao(len(df)))
    elif tipo == "Pizza":
        fig = px.pie(df, names=x, values=y, color=cor, color_discrete_sequence=PALETA_GRAFICOS,
                      color_discrete_map=cor_discreta)
    elif tipo == "Rosca":
        fig = px.pie(df, names=x, values=y, color=cor, color_discrete_sequence=PALETA_GRAFICOS,
                      color_discrete_map=cor_discreta, hole=0.45)
    elif tipo == "Área":
        fig = px.area(df, x=x, y=y, color=cor, color_discrete_sequence=PALETA_GRAFICOS,
                       color_discrete_map=cor_discreta)
    elif tipo == "Treemap":
        fig = px.treemap(df, path=[x], values=y, color=x, color_discrete_sequence=PALETA_GRAFICOS)
    elif tipo == "Pareto":
        fig = _construir_grafico_pareto(df, x, y)
    else:  # Linha
        fig = px.line(df, x=x, y=y, color=cor, color_discrete_sequence=PALETA_GRAFICOS,
                       color_discrete_map=cor_discreta, markers=True)

    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        legend_title_text="",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_family="Poppins, sans-serif",
    )
    st.plotly_chart(fig, use_container_width=True, key=f"chart_{chave}")


def render_dashboard_page() -> None:
    render_header(
        titulo="Indicadores de Qualidade dos Testes",
        subtitulo="Explore, filtre e customize a visualização dos resultados importados.",
    )

    df_bruto = st.session_state.get("dataframe_bruto")
    mapeamento: Optional[MapeamentoColunas] = st.session_state.get("mapeamento_colunas")

    if df_bruto is None or mapeamento is None or not st.session_state.get("mapeamento_confirmado"):
        st.info(
            "Nenhum arquivo processado ainda. Vá até a página **Importar Dados** no menu lateral, "
            "envie um arquivo e confirme o mapeamento de colunas."
        )
        return

    df = analytics.preparar_dados(df_bruto, mapeamento)
    df_filtrado = _aplicar_filtros_sidebar(df, mapeamento)

    if df_filtrado.empty:
        st.warning("Nenhum registro corresponde aos filtros selecionados.")
        return

    status_binario = analytics.status_e_binario(df_filtrado)

    # ---------------------------------------------------------------- KPIs
    if status_binario:
        indicadores = analytics.calcular_indicadores_gerais(df_filtrado)
        taxa_texto = f"{indicadores.taxa_sucesso}%" if indicadores.taxa_sucesso is not None else "—"
        render_kpi_row([
            ("Volumetria de Testes", f"{indicadores.total_registros:,}".replace(",", "."), None, True),
            ("Passaram", f"{indicadores.total_passou:,}".replace(",", "."), None, True),
            ("Não Passaram", f"{indicadores.total_falhou:,}".replace(",", "."), None, False),
            ("Taxa de Sucesso", taxa_texto, None, True),
        ])
    else:
        total = len(df_filtrado)
        distribuicao = analytics.distribuicao_status_bruto(df_filtrado, mapeamento)
        status_top = distribuicao.iloc[0]["Status"] if distribuicao is not None and not distribuicao.empty else "—"
        qtd_top = int(distribuicao.iloc[0]["Quantidade"]) if distribuicao is not None and not distribuicao.empty else 0
        qtd_status_distintos = distribuicao["Status"].nunique() if distribuicao is not None else 0
        render_kpi_row([
            ("Volumetria de Testes", f"{total:,}".replace(",", "."), None, True),
            ("Status Mais Frequente", str(status_top), f"{qtd_top} registros", True),
            ("Status Distintos", str(qtd_status_distintos), None, True),
        ])

    st.markdown("<br>", unsafe_allow_html=True)

    # ---------------------------------------------------- Status geral
    if mapeamento.status:
        col_grafico, col_config = st.columns([3, 1])
        with col_config:
            st.markdown("**Distribuição de Status**" if not status_binario else "**Passou vs. Não Passou**")
            tipo_status = _selecionar_tipo_grafico("status_geral", ["Pizza", "Rosca", "Barras", "Barras Horizontais", "Treemap"])
        with col_grafico:
            if status_binario:
                resumo_status = df_filtrado["__status_normalizado__"].value_counts().reset_index()
                resumo_status.columns = ["Status", "Quantidade"]
            else:
                resumo_status = analytics.distribuicao_status_bruto(df_filtrado, mapeamento)
            _plotar(resumo_status, tipo_status, x="Status", y="Quantidade", chave="status_geral")
        st.divider()

    # ------------------------------------------------- Backlog aberto (idade)
    indicadores_backlog = analytics.calcular_backlog_aberto(df_filtrado, mapeamento)
    if indicadores_backlog is not None and indicadores_backlog.total_abertos > 0:
        st.markdown("**Backlog Aberto — Tempo Parado**")
        st.caption(
            "Itens que ainda não chegaram a um estado terminal (ex.: Finalizado/Closed/Done), "
            "e há quanto tempo estão parados desde a data de referência do item."
        )
        idade_media_texto = (
            f"{indicadores_backlog.idade_media_dias:.0f} dias"
            if indicadores_backlog.idade_media_dias is not None
            else "—"
        )
        render_kpi_row([
            ("Itens em Aberto", f"{indicadores_backlog.total_abertos:,}".replace(",", "."), None, True),
            ("Idade Média", idade_media_texto, None, False),
            ("Parados há +90 dias", f"{indicadores_backlog.mais_90_dias:,}".replace(",", "."), None, False),
            ("Parados há +365 dias", f"{indicadores_backlog.mais_365_dias:,}".replace(",", "."), None, False),
        ])
        df_mais_antigos = analytics.ranking_itens_mais_antigos_abertos(df_filtrado, mapeamento)
        if df_mais_antigos is not None and not df_mais_antigos.empty:
            with st.expander("Ver os itens em aberto há mais tempo"):
                st.dataframe(df_mais_antigos, use_container_width=True)
        st.divider()

    # ------------------------------------------ Planejamento vs Efetivado
    df_planejamento = analytics.planejamento_vs_efetivado(df_filtrado, mapeamento)
    if df_planejamento is not None:
        col_grafico, col_config = st.columns([3, 1])
        with col_config:
            st.markdown("**Planejamento vs. Testes Efetivados**")
            tipo_planejamento = _selecionar_tipo_grafico("planejamento", ["Barras", "Pizza", "Rosca"])
        with col_grafico:
            _plotar(df_planejamento, tipo_planejamento, x="Categoria", y="Quantidade", chave="planejamento")
        st.divider()

    # ------------------------------------------------------ Testes por projeto
    df_projeto = analytics.testes_por_projeto(df_filtrado, mapeamento)
    if df_projeto is not None:
        col_grafico, col_config = st.columns([3, 1])
        with col_config:
            st.markdown("**Testes por Projeto**")
            tipo_projeto = _selecionar_tipo_grafico("testes_projeto")
        with col_grafico:
            _plotar(df_projeto, tipo_projeto, x="Projeto", y="Quantidade de Testes", chave="testes_projeto")
        st.divider()

    # ------------------------------------------------- Ranking de bugs
    df_bugs = analytics.ranking_bugs_por_projeto(df_filtrado, mapeamento)
    if df_bugs is not None and not df_bugs.empty:
        col_grafico, col_config = st.columns([3, 1])
        with col_config:
            st.markdown("**Ranking de Bugs por Projeto**")
            tipo_bugs = _selecionar_tipo_grafico("bugs_projeto")
        with col_grafico:
            _plotar(df_bugs, tipo_bugs, x="Projeto", y="Quantidade de Bugs", chave="bugs_projeto")
        st.divider()

    # ------------------------------------------------- Distribuição por Tipo de Teste
    df_tipo_teste = analytics.distribuicao_tipo_teste(df_filtrado, mapeamento)
    if df_tipo_teste is not None and not df_tipo_teste.empty:
        col_grafico, col_config = st.columns([3, 1])
        with col_config:
            st.markdown("**Distribuição por Tipo de Teste**")
            tipo_tt = _selecionar_tipo_grafico("tipo_teste", ["Barras", "Pizza", "Rosca", "Treemap", "Barras Horizontais", "Pareto"])
        with col_grafico:
            _plotar(df_tipo_teste, tipo_tt, x="Tipo de Teste", y="Quantidade", chave="tipo_teste")
        st.divider()

    # ------------------------------------------------- Taxa de sucesso por projeto
    df_taxa_projeto = analytics.taxa_sucesso_por_projeto(df_filtrado, mapeamento)
    if df_taxa_projeto is not None and not df_taxa_projeto.empty:
        st.markdown("**Taxa de Sucesso por Projeto**")
        _plotar(df_taxa_projeto, "Barras", x="Projeto", y="Taxa de Sucesso (%)", chave="taxa_projeto")
        st.divider()

    # ------------------------------------------------- Tendência temporal
    df_tendencia = analytics.tendencia_temporal(df_filtrado, mapeamento)
    if df_tendencia is not None:
        st.markdown("**Tendência ao Longo do Tempo**")
        _plotar(df_tendencia, "Linha", x="Semana", y="Quantidade", chave="tendencia",
                cor="Status" if "Status" in df_tendencia.columns else None)
        st.divider()

    # ------------------------------------------------- Bugs abertos vs. solucionados
    df_bugs_tempo = analytics.bugs_abertos_vs_solucionados(df_filtrado, mapeamento)
    if df_bugs_tempo is not None and not df_bugs_tempo.empty:
        col_grafico, col_config = st.columns([3, 1])
        with col_config:
            st.markdown("**Bugs Abertos vs. Solucionados**")
            st.caption(
                "Acumulado por semana de criação. 'Solucionados' reflete a situação "
                "atual (o arquivo não traz data de resolução), então mostra quantos "
                "dos bugs abertos até cada semana já estão resolvidos hoje."
            )
            tipo_bugs_tempo = _selecionar_tipo_grafico("bugs_tempo", ["Área", "Linha", "Barras"])
        with col_grafico:
            df_bugs_tempo_longo = df_bugs_tempo.melt(
                id_vars="Semana",
                value_vars=["Ainda Abertos (situação atual)", "Já Solucionados (situação atual)"],
                var_name="Categoria",
                value_name="Quantidade",
            )
            _plotar(df_bugs_tempo_longo, tipo_bugs_tempo, x="Semana", y="Quantidade",
                    chave="bugs_tempo", cor="Categoria")
        st.divider()

    # ------------------------------------------------- Ranking de responsáveis
    df_responsaveis = analytics.ranking_responsaveis(df_filtrado, mapeamento)
    if df_responsaveis is not None and not df_responsaveis.empty:
        st.markdown("**Testes por Responsável**")
        _plotar(df_responsaveis, "Barras", x="Responsável", y="Testes Executados", chave="responsaveis")
        st.divider()

    # ------------------------------------------------- Distribuição de severidade
    df_severidade = analytics.distribuicao_severidade(df_filtrado, mapeamento)
    if df_severidade is not None and not df_severidade.empty:
        st.markdown("**Distribuição por Severidade/Prioridade**")
        _plotar(df_severidade, "Pizza", x="Severidade", y="Quantidade", chave="severidade")
        st.divider()

    # ------------------------------------------------- Construtor de gráfico personalizado
    _renderizar_construtor_grafico_personalizado(df_filtrado, mapeamento)

    # ------------------------------------------------------------- Tabela
    with st.expander("Ver dados detalhados (filtrados)"):
        colunas_ocultar = [c for c in df_filtrado.columns if c.startswith("__")]
        st.dataframe(df_filtrado.drop(columns=colunas_ocultar), use_container_width=True)
        st.download_button(
            "Exportar dados filtrados (CSV)",
            data=df_filtrado.drop(columns=colunas_ocultar).to_csv(index=False).encode("utf-8-sig"),
            file_name="indicadores_qa_filtrado.csv",
            mime="text/csv",
        )


def _renderizar_construtor_grafico_personalizado(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> None:
    st.markdown("### Monte seu gráfico personalizado")
    st.caption(
        "Escolha quais colunas devem compor o gráfico — inclui campos já mapeados, campos "
        "personalizados e qualquer outra coluna do arquivo importado."
    )

    colunas_disponiveis = _colunas_disponiveis_para_grafico(df, mapeamento)
    rotulos = list(colunas_disponiveis.keys())

    colunas_numericas_reais = df.select_dtypes(include="number").columns.tolist()
    rotulos_numericos = [
        rotulo for rotulo, coluna in colunas_disponiveis.items() if coluna in colunas_numericas_reais
    ]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        rotulo_x = st.selectbox("Eixo / Categoria (X)", rotulos, key="grafico_custom_x")
    with col2:
        modo_metrica = st.selectbox(
            "Métrica", ["Contagem de registros", "Soma de coluna numérica"], key="grafico_custom_modo"
        )
    with col3:
        rotulo_metrica = None
        if modo_metrica == "Soma de coluna numérica":
            if rotulos_numericos:
                rotulo_metrica = st.selectbox("Coluna numérica", rotulos_numericos, key="grafico_custom_metrica")
            else:
                st.selectbox("Coluna numérica", ["— nenhuma coluna numérica disponível —"], disabled=True)
        else:
            st.selectbox("Coluna numérica", ["— não se aplica —"], disabled=True)
    with col4:
        tipo_grafico_custom = st.selectbox("Tipo de gráfico", TIPOS_GRAFICO_PADRAO, key="grafico_custom_tipo")

    gerar = action_button("Gerar gráfico", key="btn_gerar_grafico_customizado")

    if gerar:
        with loading_overlay("Carregando, aguarde..."):
            coluna_x = colunas_disponiveis[rotulo_x]
            coluna_metrica = colunas_disponiveis.get(rotulo_metrica) if rotulo_metrica else None
            modo = "soma" if modo_metrica == "Soma de coluna numérica" and coluna_metrica else "contagem"

            # Guardamos apenas a CONFIGURAÇÃO escolhida (colunas + tipo de gráfico),
            # não os dados já calculados. Assim, sempre que a página recarregar -
            # inclusive depois de mudar Período/Tipos de Teste/Status e confirmar -
            # o gráfico é recalculado a partir do dataframe já filtrado no momento,
            # em vez de continuar exibindo dados antigos.
            st.session_state["grafico_customizado_params"] = {
                "coluna_x": coluna_x,
                "coluna_metrica": coluna_metrica,
                "modo": modo,
                "tipo_grafico": tipo_grafico_custom,
                "rotulo_x": rotulo_x,
            }
        finish_action("btn_gerar_grafico_customizado")
        st.rerun()

    parametros_salvos = st.session_state.get("grafico_customizado_params")
    if parametros_salvos is not None:
        if parametros_salvos["coluna_x"] not in df.columns:
            st.warning(
                f"A coluna **{parametros_salvos['rotulo_x']}** usada neste gráfico não está mais "
                "disponível para os dados atuais. Gere o gráfico novamente."
            )
        else:
            dados_grafico = analytics.construir_grafico_personalizado(
                df,
                parametros_salvos["coluna_x"],
                parametros_salvos["coluna_metrica"],
                parametros_salvos["modo"],
            )
            if dados_grafico.empty:
                st.info("Nenhum dado disponível para os filtros/período selecionados atualmente.")
            else:
                _plotar(
                    dados_grafico,
                    parametros_salvos["tipo_grafico"],
                    x="Categoria",
                    y="Valor",
                    chave="grafico_customizado",
                )
