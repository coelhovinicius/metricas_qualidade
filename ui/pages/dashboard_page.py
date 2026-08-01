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
from ui.theme import PALETA_BUGS_TEMPO, PALETA_COLORIDA, PALETA_GRAFICOS, PALETA_STATUS, cor_discreta_coluna_board

TIPOS_GRAFICO_PADRAO = ["Barras", "Barras Horizontais", "Pizza", "Rosca", "Linha", "Área", "Treemap", "Pareto", "Radar (Preenchido)"]


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
        "coluna_board": "Coluna do Board (Kanban)",
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
    """Cicla pela paleta colorida (30 tons), uma cor por posição/categoria (não por valor)."""
    return [PALETA_COLORIDA[indice % len(PALETA_COLORIDA)] for indice in range(quantidade)]


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


def _plotar(
    df: pd.DataFrame,
    tipo: str,
    x: str,
    y: str,
    chave: str,
    cor: Optional[str] = None,
    ordem_categorias: Optional[dict[str, list[str]]] = None,
) -> None:
    """
    `ordem_categorias` (opcional): dict eixo/coluna -> lista com a ordem
    desejada das categorias (ex.: {"Coluna do Board": analytics.ORDEM_COLUNAS_BOARD}),
    repassado direto pro `category_orders` do Plotly Express - sem isso, a
    ordem das categorias segue a ordem das linhas do dataframe recebido, o
    que nem sempre é suficiente quando a mesma coluna aparece espalhada (ex.:
    cruzada com Projeto) e precisa de uma ordem única e consistente em todo
    o gráfico (barras, cor/legenda e empilhamento).
    """
    cor_discreta = None
    if cor and cor in df.columns:
        valores_cor = set(df[cor].unique())
        if cor == "__status_bruto__" and valores_cor <= set(PALETA_STATUS):
            cor_discreta = PALETA_STATUS
        elif cor == "Categoria" and valores_cor <= set(PALETA_BUGS_TEMPO):
            cor_discreta = PALETA_BUGS_TEMPO
        elif cor == "Coluna do Board":
            # Paleta dedicada (conjunto de máximo contraste, ver `ui/theme.py`)
            # em vez da paleta padrão de 8 cores - com até 19 colunas oficiais +
            # eventuais colunas com nome próprio, 8 cores ciclando faziam a 9ª
            # coluna repetir a cor da 1ª.
            cor_discreta = cor_discreta_coluna_board(valores_cor)

    # Sem uma segunda dimensão de cor (`cor`), mas o eixo de categoria É a
    # Coluna do Board (caso da "Distribuição por Coluna do Board", uma
    # dimensão só): usa a mesma paleta dedicada acima, por valor, em vez de
    # `_cores_por_posicao`/do ciclo padrão de 8 cores.
    cor_coluna_board_sem_dimensao = (
        cor is None and x == "Coluna do Board" and x in df.columns
    )
    if cor_coluna_board_sem_dimensao:
        cor_discreta = cor_discreta_coluna_board(set(df[x]))

    def _cores_para_barras(eixo_categoria: str) -> list[str]:
        if cor_coluna_board_sem_dimensao:
            return [cor_discreta[str(valor)] for valor in df[eixo_categoria]]
        return _cores_por_posicao(len(df))

    if tipo == "Barras":
        fig = px.bar(df, x=x, y=y, color=cor, color_discrete_sequence=PALETA_COLORIDA,
                      color_discrete_map=cor_discreta, text_auto=True, category_orders=ordem_categorias)
        if cor is None:
            # Sem uma segunda dimensão pra agrupar/empilhar: colore cada barra por
            # posição (categoria), sem criar legenda nova - é a mesma série, só
            # com uma cor por categoria em vez de uma cor única pra todo o gráfico.
            fig.update_traces(marker_color=_cores_para_barras(x))
    elif tipo == "Barras Horizontais":
        fig = px.bar(df, x=y, y=x, color=cor, orientation="h", color_discrete_sequence=PALETA_COLORIDA,
                      color_discrete_map=cor_discreta, text_auto=True, category_orders=ordem_categorias)
        if cor is None:
            fig.update_traces(marker_color=_cores_para_barras(x))
    elif tipo == "Pizza":
        # px.pie só aplica `color_discrete_map` quando `color` é passado de
        # verdade (com `color=None`, ignora o mapa e cicla a paleta padrão por
        # posição) - por isso, quando não há uma segunda dimensão mas o eixo É
        # a Coluna do Board, usa a própria coluna de nomes (`x`) como `color`.
        cor_pizza = cor or (x if cor_coluna_board_sem_dimensao else None)
        fig = px.pie(df, names=x, values=y, color=cor_pizza, color_discrete_sequence=PALETA_COLORIDA,
                      color_discrete_map=cor_discreta, category_orders=ordem_categorias)
    elif tipo == "Rosca":
        cor_pizza = cor or (x if cor_coluna_board_sem_dimensao else None)
        fig = px.pie(df, names=x, values=y, color=cor_pizza, color_discrete_sequence=PALETA_COLORIDA,
                      color_discrete_map=cor_discreta, hole=0.45, category_orders=ordem_categorias)
    elif tipo == "Área":
        fig = px.area(df, x=x, y=y, color=cor, color_discrete_sequence=PALETA_COLORIDA,
                       color_discrete_map=cor_discreta, category_orders=ordem_categorias)
    elif tipo == "Treemap":
        # Com uma segunda dimensão (cor/grupo) escolhida, o Treemap vira
        # hierárquico de verdade (Categoria > Grupo) em vez de um nível só -
        # é o caso em que "gráfico além de dois eixos" faz sentido de forma
        # nativa, sem inventar um tipo de gráfico novo.
        #
        # `px.treemap` não aceita `category_orders` (só `px.bar`/`px.pie`/
        # `px.area`/`px.line` aceitam) - passar esse argumento aqui derruba a
        # página com "TypeError: treemap() got an unexpected keyword argument
        # 'category_orders'". Não faz falta pro Treemap mesmo: a posição dos
        # retângulos é decidida pelo algoritmo de preenchimento por área
        # (tamanho = valor), não por uma ordem de categorias como num eixo de
        # barras - não existe "ordem" pra impor aqui.
        caminho = [x, cor] if cor else [x]
        cor_discreta_treemap = cor_discreta
        if cor_discreta_treemap is None and (cor or x) == "Coluna do Board":
            cor_discreta_treemap = cor_discreta_coluna_board(set(df[cor or x]))
        fig = px.treemap(df, path=caminho, values=y, color=cor or x, color_discrete_sequence=PALETA_COLORIDA,
                          color_discrete_map=cor_discreta_treemap)
    elif tipo == "Pareto":
        fig = _construir_grafico_pareto(df, x, y)
    elif tipo == "Radar (Preenchido)":
        # Gráfico de radar/teia PREENCHIDO (filled radar chart): cada série vira
        # um polígono fechado com a área sombreada, no estilo clássico de
        # comparação "uma forma colorida por série" (ex.: Severidade em cada
        # eixo, uma forma por Projeto/Responsável). Pra sobrepor mais de uma
        # série - o que dá o efeito de formas coloridas se cruzando - use
        # "Agrupar por" no construtor personalizado. Não faz sentido pra séries
        # temporais (Semana) nem pra 2 categorias só (vira só uma linha reta) -
        # por isso não é oferecido nesses gráficos.
        fig = px.line_polar(df, r=y, theta=x, color=cor, line_close=True,
                             color_discrete_sequence=PALETA_COLORIDA, color_discrete_map=cor_discreta,
                             category_orders=ordem_categorias)
        fig.update_traces(
            fill="toself",
            opacity=0.85,
            mode="lines+markers",
            marker=dict(size=6, line=dict(color="#FFFFFF", width=1)),
            line=dict(width=2.5),
        )
        fig.update_layout(
            polar=dict(
                bgcolor="rgba(0,0,0,0)",
                radialaxis=dict(
                    visible=True,
                    gridcolor="#E4E0D6",
                    linecolor="#C9C4B8",
                    tickfont=dict(size=11, color="#6B6558"),
                ),
                angularaxis=dict(
                    gridcolor="#E4E0D6",
                    linecolor="#C9C4B8",
                    tickfont=dict(size=12),
                ),
            )
        )
    else:  # Linha
        fig = px.line(df, x=x, y=y, color=cor, color_discrete_sequence=PALETA_COLORIDA,
                       color_discrete_map=cor_discreta, markers=True, category_orders=ordem_categorias)

    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        legend_title_text="",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        polar_bgcolor="rgba(0,0,0,0)",
        font_family="Poppins, sans-serif",
    )
    st.plotly_chart(fig, use_container_width=True, key=f"chart_{chave}")

    if tipo == "Radar (Preenchido)" and cor is None:
        st.caption(
            "💡 Pra sobrepor várias formas coloridas no mesmo radar (comparar Projetos, "
            "Responsáveis, etc. lado a lado), use o **construtor de gráfico personalizado** "
            "mais abaixo e escolha uma coluna em \"Agrupar por\"."
        )


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
        st.markdown("**Distribuição de Status**" if not status_binario else "**Passou vs. Não Passou**")
        if not status_binario:
            st.caption(
                f"Valores exatamente como vêm do campo **{mapeamento.status}** (Status/State) de cada "
                "work item - **não tem nenhuma relação com a Coluna do Board** (Kanban), que é outro "
                "campo, mapeado e mostrado separadamente mais abaixo. Se times/Area Paths diferentes "
                "usam templates de processo diferentes no Azure DevOps, cada um pode ter seu próprio "
                "vocabulário de Status (ex.: um time usa só New/Active/Closed, outro usa nomes próprios "
                "como UAT/QA/Deploy) - com vários Area Paths selecionados ao mesmo tempo, é esperado ver "
                "esses vocabulários diferentes juntos neste gráfico. Para ver qual Area Path usa qual "
                "valor, confira o gráfico **Area Path × Status** logo abaixo."
            )
        col_tipo, _col_espaco = st.columns([1, 3])
        with col_tipo:
            tipo_status = _selecionar_tipo_grafico("status_geral", ["Pizza", "Rosca", "Barras", "Barras Horizontais", "Treemap", "Radar (Preenchido)"])
        if status_binario:
            resumo_status = df_filtrado["__status_normalizado__"].value_counts().reset_index()
            resumo_status.columns = ["Status", "Quantidade"]
        else:
            resumo_status = analytics.distribuicao_status_bruto(df_filtrado, mapeamento)
        _plotar(resumo_status, tipo_status, x="Status", y="Quantidade", chave="status_geral")
        st.divider()

    # ------------------------------------------------- Area Path × Status
    if not status_binario:
        df_area_x_status = analytics.distribuicao_area_path_x_status(df_filtrado, mapeamento)
        if df_area_x_status is not None and not df_area_x_status.empty:
            st.markdown("**Area Path × Status**")
            st.caption(
                "Discrimina, para cada Area Path/Projeto, quantos work items estão em cada valor de "
                "Status - útil para confirmar que valores como UAT/QA/Deploy (quando aparecem) vêm de "
                "um Area Path/time específico com vocabulário de Status próprio, e não de uma mistura "
                "com a Coluna do Board."
            )
            col_area_status, _col_espaco_area_status = st.columns([1, 3])
            with col_area_status:
                tipo_area_status = _selecionar_tipo_grafico("area_path_status", ["Barras", "Barras Horizontais", "Treemap"])
            _plotar(df_area_x_status, tipo_area_status, x="Projeto", y="Quantidade", chave="area_path_status", cor="Status")
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
        st.markdown("**Planejamento vs. Testes Efetivados**")
        col_tipo, _col_espaco = st.columns([1, 3])
        with col_tipo:
            tipo_planejamento = _selecionar_tipo_grafico("planejamento", ["Barras", "Pizza", "Rosca"])
        _plotar(df_planejamento, tipo_planejamento, x="Categoria", y="Quantidade", chave="planejamento")
        st.divider()

    # ------------------------------------------------------ Testes por projeto
    df_projeto = analytics.testes_por_projeto(df_filtrado, mapeamento)
    if df_projeto is not None:
        st.markdown("**Testes por Projeto**")
        col_tipo, _col_espaco = st.columns([1, 3])
        with col_tipo:
            tipo_projeto = _selecionar_tipo_grafico("testes_projeto")
        _plotar(df_projeto, tipo_projeto, x="Projeto", y="Quantidade de Testes", chave="testes_projeto")
        st.divider()

    # ------------------------------------------------- Ranking de bugs
    df_bugs = analytics.ranking_bugs_por_projeto(df_filtrado, mapeamento)
    if df_bugs is not None and not df_bugs.empty:
        st.markdown("**Ranking de Bugs por Projeto**")
        col_tipo, _col_espaco = st.columns([1, 3])
        with col_tipo:
            tipo_bugs = _selecionar_tipo_grafico("bugs_projeto")
        _plotar(df_bugs, tipo_bugs, x="Projeto", y="Quantidade de Bugs", chave="bugs_projeto")
        st.divider()

    # ------------------------------------------------- Distribuição por Tipo de Teste
    if mapeamento.tipo_teste and mapeamento.tipo_teste in df_filtrado.columns:
        tipos_teste_disponiveis = sorted(
            df_filtrado[mapeamento.tipo_teste].dropna().astype(str).unique().tolist()
        )
        # Pré-seleção sugerida: tipos que são contêineres organizacionais do
        # Azure DevOps (agrupam vários Test Cases dentro), não um item de
        # teste individual - contar "1 Test Plan" ao lado de "1 Test Case" na
        # mesma distribuição não é uma comparação de volume válida. O usuário
        # pode ajustar livremente no multiselect abaixo.
        _PALAVRAS_TIPO_CONTAINER = ("test plan", "test suite")
        padrao_tipos_excluidos = [
            valor
            for valor in tipos_teste_disponiveis
            if any(palavra in valor.lower() for palavra in _PALAVRAS_TIPO_CONTAINER)
        ]

        st.markdown("**Distribuição por Tipo de Teste**")
        st.caption(
            "Por padrão, exclui tipos que são contêineres organizacionais (ex.: Test Plan, "
            "Test Suite) — eles agrupam vários Test Cases e não representam um item de teste "
            "individual, então não fazem sentido na mesma régua de contagem."
        )
        tipos_excluidos_selecionados = st.multiselect(
            "Tipos a excluir desta distribuição",
            options=tipos_teste_disponiveis,
            default=padrao_tipos_excluidos,
            key="tipo_teste_excluidos",
            help=(
                "Itens desses tipos não entram na contagem deste gráfico específico — "
                "continuam contando normalmente nos outros indicadores do painel."
            ),
        )
        df_tipo_teste = analytics.distribuicao_tipo_teste(
            df_filtrado, mapeamento, tipos_excluidos=set(tipos_excluidos_selecionados)
        )
        if df_tipo_teste is not None and not df_tipo_teste.empty:
            col_tipo, _col_espaco = st.columns([1, 3])
            with col_tipo:
                tipo_tt = _selecionar_tipo_grafico("tipo_teste", ["Treemap", "Barras", "Pizza", "Rosca", "Barras Horizontais", "Pareto", "Radar (Preenchido)"])
            _plotar(df_tipo_teste, tipo_tt, x="Tipo de Teste", y="Quantidade", chave="tipo_teste")
        else:
            st.info("Nenhum tipo restante depois da exclusão acima — ajuste a lista para ver o gráfico.")
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
    colunas_board_disponiveis: list[str] = []
    padrao_colunas_externas: list[str] = []
    if mapeamento.coluna_board and mapeamento.coluna_board in df_filtrado.columns:
        colunas_board_disponiveis = sorted(
            df_filtrado[mapeamento.coluna_board].dropna().astype(str).unique().tolist(),
            key=analytics.ordem_coluna_board,
        )
        # Pré-seleção: TUDO que não for, exatamente, "Pronto para QA" e/ou
        # "Teste QA" - únicas colunas que representam trabalho realmente sob
        # responsabilidade da QA; qualquer outra (Backlog, Dev, Code Review,
        # UAT, CAB, Produção, "Não atribuído(a)", coluna com nome próprio de
        # algum time, etc.) conta como fora do controle da QA por padrão. O
        # usuário pode ajustar livremente no multiselect abaixo. Os valores
        # em `colunas_board_disponiveis` já vêm canonizados (ver
        # `canonizar_coluna_board`/`preparar_dados`), então a comparação é
        # direta com a grafia oficial - sem precisar normalizar de novo aqui.
        _COLUNAS_RESPONSABILIDADE_QA = {"Pronto para QA", "Teste QA"}
        padrao_colunas_externas = [
            valor for valor in colunas_board_disponiveis if valor not in _COLUNAS_RESPONSABILIDADE_QA
        ]

    colunas_externas_selecionadas = st.session_state.get(
        "bugs_tempo_colunas_externas", padrao_colunas_externas
    )
    df_bugs_tempo = analytics.bugs_abertos_vs_solucionados(
        df_filtrado, mapeamento, colunas_aguardando_externo=set(colunas_externas_selecionadas)
    )
    if df_bugs_tempo is not None and not df_bugs_tempo.empty:
        st.markdown("**Bugs Abertos vs. Solucionados**")
        st.caption(
            "Acumulado por semana de criação. 'Finalizado' reflete a situação atual "
            "(o arquivo não traz data de resolução), então mostra quantos dos bugs "
            "criados até cada semana já estão numa situação terminal hoje."
        )
        if colunas_board_disponiveis:
            st.multiselect(
                "Colunas do board fora do controle da QA (aguardando validação externa)",
                options=colunas_board_disponiveis,
                default=padrao_colunas_externas,
                key="bugs_tempo_colunas_externas",
                help=(
                    "Por padrão vem marcado tudo que não for exatamente 'Pronto para QA' e/ou "
                    "'Teste QA' - as únicas colunas que representam trabalho sob "
                    "responsabilidade da QA. Itens que a QA já resolveu, mas que estão parados "
                    "numa dessas colunas marcadas (ex.: 'Pronto para UAT', aguardando o time de "
                    "Produto/Negócio/UX validar) entram na categoria 'Aguardando Validação "
                    "Externa' em vez de contar como trabalho ainda em andamento da QA."
                ),
            )
        col_tipo, _col_espaco = st.columns([1, 3])
        with col_tipo:
            tipo_bugs_tempo = _selecionar_tipo_grafico("bugs_tempo", ["Área", "Linha", "Barras"])
        colunas_valor = [coluna for coluna in df_bugs_tempo.columns if coluna not in ("Semana", "Bugs Criados (acumulado)")]
        df_bugs_tempo_longo = df_bugs_tempo.melt(
            id_vars="Semana",
            value_vars=colunas_valor,
            var_name="Categoria",
            value_name="Quantidade",
        )
        _plotar(df_bugs_tempo_longo, tipo_bugs_tempo, x="Semana", y="Quantidade",
                chave="bugs_tempo", cor="Categoria")
        st.divider()

    # ------------------------------------------------- Distribuição de severidade
    df_severidade = analytics.distribuicao_severidade(df_filtrado, mapeamento)
    if df_severidade is not None and not df_severidade.empty:
        st.markdown("**Distribuição por Severidade/Prioridade**")
        _plotar(df_severidade, "Pizza", x="Severidade", y="Quantidade", chave="severidade")
        st.divider()

    # ------------------------------------------------- Distribuição por Coluna do Board
    df_coluna_board_completo = analytics.distribuicao_coluna_board(df_filtrado, mapeamento)
    if df_coluna_board_completo is not None and not df_coluna_board_completo.empty:
        st.markdown("**Distribuição por Coluna do Board (Kanban)**")
        st.caption(
            "Coluna do board **exatamente como veio do Azure DevOps** para cada item (campo "
            "`System.BoardColumn`), sem lista fixa nem filtro do app — se o board do time tem "
            "19 colunas próprias (Backlog, Em Refinamento de Negócios, ..., Finalizado), essas "
            "19 aparecem aqui. Nomes batem com a lista oficial abaixo ignorando acento e "
            "maiúscula/minúscula (ex.: 'pronto para qa' e 'Pronto Para QA' contam juntos); "
            "colunas com nome próprio de algum time específico aparecem do mesmo jeito, só "
            "ficam ordenadas depois das reconhecidas. As barras seguem a ordem real do fluxo "
            "(Backlog → Finalizado), não a quantidade — assim dá pra ver o funil/gargalo. "
            "Tipos de work item que não aparecem em nenhum board (ex.: Test Case, que vive em "
            "Test Plans/Test Suites) herdam a coluna do item pai vinculado, quando existir esse "
            "vínculo. Itens sem pai vinculado, ou cujo pai também não está em nenhuma coluna, "
            "ficam sem Coluna do Board — esses itens **não entram neste gráfico nem no "
            "cruzamento Area Path × Coluna do Board logo abaixo** (ver detalhamento por tipo no "
            "expansor abaixo)."
        )
        with st.expander("Lista oficial de colunas usada para ordenar (não limita quais colunas aparecem)"):
            st.write(", ".join(analytics.ORDEM_COLUNAS_BOARD))

        df_detalhe_nao_atribuido = analytics.detalhamento_nao_atribuido_coluna_board(df_filtrado, mapeamento)
        if df_detalhe_nao_atribuido is not None and not df_detalhe_nao_atribuido.empty:
            with st.expander(
                f"Por que {int(df_detalhe_nao_atribuido['Quantidade'].sum()):,}".replace(",", ".")
                + ' item(ns) sem Coluna do Board não aparece(m) nos gráficos abaixo (ver por tipo)'
            ):
                st.caption(
                    "Quebra, por Tipo de Work Item, dos itens sem Coluna do Board - excluídos "
                    "dos dois gráficos abaixo. Ajuda a diferenciar as duas causas possíveis: "
                    "**(a)** o tipo simplesmente nunca aparece em nenhum board no Azure DevOps "
                    "(ex.: Test Case, que vive em Test Plans/Test Suites) e não tem um item pai "
                    "vinculado pra herdar a coluna dele — nesse caso é o esperado, não é bug; "
                    "**(b)** o tipo normalmente aparece no board (ex.: Bug, User Story, Task) mas "
                    "mesmo assim veio sem coluna direto da API do Azure DevOps — o que costuma "
                    "acontecer quando o Area Path do item não está associado a nenhum Time, ou o "
                    "Time responsável não tem uma coluna mapeada pro State atual do item nas "
                    "configurações do board dele (isso é configuração do lado do Azure DevOps, "
                    "não algo que o app calcula)."
                )
                st.dataframe(df_detalhe_nao_atribuido, use_container_width=True, hide_index=True)

        df_para_graficos_coluna_board = analytics.excluir_nao_atribuido_coluna_board(df_filtrado, mapeamento)
        df_coluna_board = analytics.distribuicao_coluna_board(df_para_graficos_coluna_board, mapeamento)

        col_board, _col_espaco_board = st.columns([1, 3])
        with col_board:
            tipo_board = _selecionar_tipo_grafico(
                "coluna_board", ["Barras", "Barras Horizontais", "Pizza", "Rosca", "Treemap"]
            )
        if df_coluna_board is not None and not df_coluna_board.empty:
            _plotar(
                df_coluna_board, tipo_board, x="Coluna do Board", y="Quantidade", chave="coluna_board",
                ordem_categorias={"Coluna do Board": analytics.ORDEM_COLUNAS_BOARD},
            )
        else:
            st.info('Nenhum item com Coluna do Board (fora de "Não atribuído(a)") para os filtros atuais.')
        st.divider()

        # --------------------------------------------- Area Path × Coluna do Board
        df_area_x_board = analytics.distribuicao_area_path_x_coluna_board(
            df_para_graficos_coluna_board, mapeamento
        )
        if df_area_x_board is not None and not df_area_x_board.empty:
            st.markdown("**Area Path × Coluna do Board**")
            st.caption(
                "Cruza Projeto/Area Path com a coluna do board — mostra quantos itens de cada "
                "Area Path estão parados em cada coluna, na ordem real do fluxo (Backlog → "
                "Finalizado), em vez de só o total geral por coluna. Ajuda a enxergar onde "
                "exatamente está o gargalo: por exemplo, um Area Path específico acumulando "
                'muito item numa coluna só. Também não inclui itens "Não atribuído(a)" (ver '
                "detalhamento acima)."
            )
            col_area_board, _col_espaco_area_board = st.columns([1, 3])
            with col_area_board:
                tipo_area_board = _selecionar_tipo_grafico(
                    "area_path_coluna_board", ["Barras", "Barras Horizontais", "Treemap"]
                )
            _plotar(
                df_area_x_board, tipo_area_board, x="Projeto", y="Quantidade",
                chave="area_path_coluna_board", cor="Coluna do Board",
                ordem_categorias={"Coluna do Board": analytics.ORDEM_COLUNAS_BOARD},
            )
            st.divider()

    # ------------------------------------------------- Volume de Testes por Responsável
    if mapeamento.responsavel and mapeamento.responsavel in df_filtrado.columns:
        st.markdown("**Volume de Testes por Responsável**")
        projeto_disponivel_responsavel = bool(mapeamento.projeto and mapeamento.projeto in df_filtrado.columns)
        col_agrupar, col_tipo_resp, _col_espaco = st.columns([1.4, 1, 2])
        with col_agrupar:
            agrupar_por_projeto = st.checkbox(
                "Agrupar por Projeto",
                value=projeto_disponivel_responsavel,
                key="volume_responsavel_agrupar_projeto",
                disabled=not projeto_disponivel_responsavel,
                help=(
                    "Divide a barra de cada Responsável pelos Projetos em que atuou, em vez de "
                    "mostrar só o total."
                ),
            )
        with col_tipo_resp:
            tipo_volume_responsavel = _selecionar_tipo_grafico(
                "volume_responsavel", ["Barras", "Barras Horizontais", "Treemap", "Pizza", "Rosca"]
            )
        df_volume_responsavel = analytics.volume_por_responsavel(
            df_filtrado,
            mapeamento,
            agrupar_por_projeto=agrupar_por_projeto and projeto_disponivel_responsavel,
        )
        if df_volume_responsavel is not None and not df_volume_responsavel.empty:
            _plotar(
                df_volume_responsavel, tipo_volume_responsavel, x="Responsável", y="Quantidade",
                chave="volume_responsavel",
                cor="Projeto" if "Projeto" in df_volume_responsavel.columns else None,
            )
        else:
            st.info("Sem dados suficientes de Responsável para montar este gráfico.")
        st.divider()

    # ------------------------------------------------- Volume por Responsável ao longo do tempo
    df_volume_tempo, volume_tempo_truncado = analytics.volume_responsavel_por_semana(df_filtrado, mapeamento)
    if df_volume_tempo is not None and not df_volume_tempo.empty:
        st.markdown("**Volume por Responsável ao Longo do Tempo**")
        st.caption(
            "Acumulado por semana (não por dia) - o volume individual por dia costuma ser baixo, "
            "o que deixaria a linha muito irregular e dominada pelo dia da semana, escondendo o "
            "padrão real de ritmo de cada pessoa. Mostra a soma de todos os Projetos que estiverem "
            "marcados no filtro **Projeto** da barra lateral — para ver a tendência de um Projeto "
            "específico, marque só ele lá."
        )
        col_tipo_volume_tempo, _col_espaco = st.columns([1, 3])
        with col_tipo_volume_tempo:
            tipo_volume_tempo = _selecionar_tipo_grafico("volume_responsavel_tempo", ["Linha", "Área", "Barras"])
        _plotar(
            df_volume_tempo, tipo_volume_tempo, x="Semana", y="Quantidade",
            chave="volume_responsavel_tempo", cor="Responsável",
        )
        if volume_tempo_truncado:
            st.caption(
                "Mostrando só as 8 pessoas com mais registros no período (mais que isso deixaria "
                "o gráfico ilegível, com muitas linhas/cores se cruzando)."
            )
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
        "personalizados e qualquer outra coluna do arquivo importado. Cada coluna só pode "
        "ser usada em uma dimensão por vez (não é possível repetir a mesma coluna no eixo X, "
        "no agrupamento e na métrica)."
    )

    colunas_disponiveis = _colunas_disponiveis_para_grafico(df, mapeamento)
    rotulos = list(colunas_disponiveis.keys())

    colunas_numericas_reais = df.select_dtypes(include="number").columns.tolist()
    rotulos_numericos = [
        rotulo for rotulo, coluna in colunas_disponiveis.items() if coluna in colunas_numericas_reais
    ]

    OPCAO_SEM_GRUPO = "— nenhum —"

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        rotulo_x = st.selectbox("Eixo / Categoria (X)", rotulos, key="grafico_custom_x")
    coluna_x = colunas_disponiveis[rotulo_x]

    with col2:
        # O agrupamento (2ª dimensão / cor) nunca pode repetir a coluna do X -
        # por isso ela já sai fora das opções aqui, em vez de deixar o usuário
        # escolher e só avisar depois.
        rotulos_grupo_disponiveis = [r for r in rotulos if colunas_disponiveis[r] != coluna_x]
        rotulo_grupo = st.selectbox(
            "Agrupar por (opcional)",
            [OPCAO_SEM_GRUPO] + rotulos_grupo_disponiveis,
            key="grafico_custom_grupo",
            help="Adiciona uma segunda dimensão ao gráfico (cor/série/empilhamento). "
                 "Útil para comparações como 'Projeto por Status'.",
        )
    coluna_grupo = colunas_disponiveis.get(rotulo_grupo) if rotulo_grupo != OPCAO_SEM_GRUPO else None

    with col3:
        modo_metrica = st.selectbox(
            "Métrica", ["Contagem de registros", "Soma de coluna numérica"], key="grafico_custom_modo"
        )
    with col4:
        # A coluna numérica também não pode repetir nem o X nem o agrupamento -
        # mesma lógica: filtra as opções em vez de só validar depois.
        colunas_ja_usadas = {coluna_x, coluna_grupo} - {None}
        rotulos_numericos_disponiveis = [
            r for r in rotulos_numericos if colunas_disponiveis[r] not in colunas_ja_usadas
        ]
        rotulo_metrica = None
        if modo_metrica == "Soma de coluna numérica":
            if rotulos_numericos_disponiveis:
                rotulo_metrica = st.selectbox("Coluna numérica", rotulos_numericos_disponiveis, key="grafico_custom_metrica")
            else:
                st.selectbox("Coluna numérica", ["— nenhuma coluna numérica disponível —"], disabled=True)
        else:
            st.selectbox("Coluna numérica", ["— não se aplica —"], disabled=True)
    with col5:
        tipo_grafico_custom = st.selectbox("Tipo de gráfico", TIPOS_GRAFICO_PADRAO, key="grafico_custom_tipo")
        if coluna_grupo and tipo_grafico_custom == "Pareto":
            st.caption("⚠️ Pareto ignora o agrupamento (usa só Categoria x Métrica).")

    gerar = action_button("Gerar gráfico", key="btn_gerar_grafico_customizado")

    if gerar:
        with loading_overlay("Carregando, aguarde..."):
            coluna_metrica = colunas_disponiveis.get(rotulo_metrica) if rotulo_metrica else None
            modo = "soma" if modo_metrica == "Soma de coluna numérica" and coluna_metrica else "contagem"

            # Guardamos apenas a CONFIGURAÇÃO escolhida (colunas + tipo de gráfico),
            # não os dados já calculados. Assim, sempre que a página recarregar -
            # inclusive depois de mudar Período/Tipos de Teste/Status e confirmar -
            # o gráfico é recalculado a partir do dataframe já filtrado no momento,
            # em vez de continuar exibindo dados antigos.
            st.session_state["grafico_customizado_params"] = {
                "coluna_x": coluna_x,
                "coluna_grupo": coluna_grupo,
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
                coluna_grupo=parametros_salvos.get("coluna_grupo"),
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
                    cor="Grupo" if parametros_salvos.get("coluna_grupo") else None,
                )
