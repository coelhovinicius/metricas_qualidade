"""Página de dashboard: indicadores calculados e gráficos interativos/customizáveis."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import analytics
from core.column_mapper import MapeamentoColunas
from core.fuso_horario import agora_brasilia
from ui.components import action_button, finish_action, loading_overlay, render_header, render_kpi_row
from ui.theme import (
    BACKGROUND_COLOR,
    PALETA_BUGS_TEMPO,
    PALETA_COLORIDA,
    PALETA_GRAFICOS,
    PALETA_STATUS,
    PRIMARY_COLOR,
    cor_discreta_coluna_board,
    cor_discreta_criticidade,
    cor_discreta_severidade_prioridade,
)

TIPOS_GRAFICO_PADRAO = ["Barras", "Barras Horizontais", "Pizza", "Rosca", "Linha", "Área", "Treemap", "Pareto", "Radar (Preenchido)"]

# ui/pages/dashboard_page.py -> ui/pages -> ui -> raiz do projeto -> assets/
_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


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

    # ---- Filtros (Projeto / Tipos de Teste / Status) ----
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


def _construir_grafico_mapa_calor(
    df: pd.DataFrame, x: str, y: str, cor: Optional[str], ordem_categorias: Optional[dict[str, list[str]]]
) -> go.Figure:
    """
    Mapa de calor (heatmap): duas dimensões categóricas nos eixos (`x` e
    `cor` - aqui `cor` funciona como o eixo Y do mapa, não como "uma cor por
    categoria") e a magnitude (`y`, normalmente "Quantidade") como
    intensidade de cor de cada célula, numa única escala SEQUENCIAL (branco
    -> laranja da marca). Cor sequencial (um matiz só, do claro ao escuro)
    é a escolha certa pra magnitude - nunca uma paleta categórica aqui, que
    faria a cor "competir" com a própria intensidade que o mapa de calor
    existe pra mostrar.

    Resolve a ilegibilidade que barras agrupadas/empilhadas têm quando uma
    das duas dimensões tem muitas categorias (ex.: até 19 Colunas do Board,
    ou uma lista longa de Responsáveis) - um grid de células substitui um
    emaranhado de barras coloridas.

    Requer as três colunas (`x`, `cor`, `y`) presentes em `df` - só é
    oferecido como opção de "Tipo de gráfico" nas seções que já cruzam duas
    dimensões (Area Path × Coluna do Board, Responsável × Severidade).
    """
    tabela = df.pivot_table(index=cor, columns=x, values=y, aggfunc="sum", fill_value=0)

    ordem_x = (ordem_categorias or {}).get(x)
    if ordem_x:
        colunas_na_ordem = [valor for valor in ordem_x if valor in tabela.columns]
        colunas_restantes = [valor for valor in tabela.columns if valor not in colunas_na_ordem]
        tabela = tabela[colunas_na_ordem + colunas_restantes]

    ordem_y = (ordem_categorias or {}).get(cor)
    if ordem_y:
        linhas_na_ordem = [valor for valor in ordem_y if valor in tabela.index]
        linhas_restantes = [valor for valor in tabela.index if valor not in linhas_na_ordem]
        tabela = tabela.reindex(linhas_na_ordem + linhas_restantes)

    fig = go.Figure(
        data=go.Heatmap(
            z=tabela.values,
            x=[str(valor) for valor in tabela.columns],
            y=[str(valor) for valor in tabela.index],
            colorscale=[[0.0, "#FFFFFF"], [1.0, PRIMARY_COLOR]],
            text=tabela.values,
            texttemplate="%{text}",
            textfont={"size": 11},
            hovertemplate=f"{x}: %{{x}}<br>{cor}: %{{y}}<br>{y}: %{{z}}<extra></extra>",
            xgap=2,
            ygap=2,
            colorbar=dict(title=y),
        )
    )
    fig.update_xaxes(title=x)
    fig.update_yaxes(title=cor, autorange="reversed")
    return fig


def _construir_grafico_bolha_backlog(df_grupo: pd.DataFrame, coluna_rotulo: str) -> go.Figure:
    """
    Gráfico de bolha "Backlog Aberto: Volume × Idade × Risco" - 3 dimensões
    num só olhar, uma bolha por grupo (Area Path ou Responsável, à escolha
    de quem está vendo o dashboard - ver `_sec_backlog_bolha` em
    `render_dashboard_page`):

        eixo X = "Idade Média (dias)" parado em aberto naquele grupo;
        eixo Y = "Quantidade" de itens em aberto do grupo (reforçado pelo
            TAMANHO da bolha, pro mesmo valor "pular aos olhos" duas vezes);
        cor da bolha = "% Severidade Alta/Crítica" - canal SEQUENCIAL (um
            matiz só, claro→escuro), NUNCA uma cor por grupo: com muitos
            Area Paths/Responsáveis, uma paleta categórica deixaria
            rapidamente de diferenciar as bolhas (é exatamente o motivo de
            mapas de bolha usarem, no máximo, ~3 cores categóricas antes de
            precisar de outro canal) - aqui a cor conta a história de
            RISCO, não de identidade de quem é o grupo (isso já está no
            rótulo, visível ao passar o mouse).

            A ponta clara da escala é "#E97F78" (um rosa/vermelho já visível
            por si só), NÃO branco puro: como o fundo do app é um creme
            claro (`BACKGROUND_COLOR`, quase tão claro quanto branco), uma
            bolha branca-no-branco ficava praticamente invisível pra
            qualquer grupo com pouca (ou nenhuma) severidade alta/crítica -
            justamente os casos mais comuns num backlog saudável. A ponta
            escura ("#E63946") é a MESMA cor já usada em todo o resto do
            app pra Severidade "Critical" (`ui/theme.py::_VERMELHO_CRITICIDADE`),
            então uma bolha bem vermelha aqui lê como "risco alto" com o
            mesmo significado de cor que o resto do dashboard já ensinou.

    O quadrante mais preocupante é bolha grande, mais à direita (parada há
    mais tempo) e mais vermelha (mais itens Critical/High) ao mesmo tempo.
    """
    fig = px.scatter(
        df_grupo,
        x="Idade Média (dias)",
        y="Quantidade",
        size="Quantidade",
        color="% Severidade Alta/Crítica",
        color_continuous_scale=[[0.0, "#E97F78"], [1.0, "#E63946"]],
        range_color=[0, 100],
        hover_name=coluna_rotulo,
        size_max=46,
        labels={"% Severidade Alta/Crítica": "% Alta/Crítica"},
    )
    # A borda da bolha usa a cor de FUNDO do app (creme), não branco puro -
    # é o "anel de superfície" que separa bolhas sobrepostas (ver dataviz
    # skill: "surface ring"), e só funciona como separador visual se for a
    # cor de superfície de verdade; com o fundo creme deste app, um anel
    # branco destoava ligeiramente e ainda deixava a leitura mais difícil.
    fig.update_traces(marker=dict(line=dict(width=2, color=BACKGROUND_COLOR), sizemin=8))
    fig.update_layout(coloraxis_colorbar=dict(title="% Alta/<br>Crítica", ticksuffix="%"))
    return fig


def _construir_grafico_tendencia_multiplos_pequenos(df: pd.DataFrame) -> go.Figure:
    """
    "Múltiplos pequenos": um mini-gráfico de linha por Projeto/Area Path,
    lado a lado, todos com a MESMA escala de eixo Y (`facet_col` do Plotly
    Express já faz isso por padrão - reforçado aqui com `matches="y"` só
    pra deixar explícito) - facilita comparar o FORMATO da tendência entre
    projetos (crescendo, estável, com pico isolado etc.) sem empilhar todo
    mundo numa única linha multicolorida, que fica ilegível com muitos
    projetos e/ou muitos valores de Status ao mesmo tempo.
    """
    tem_status = "Status" in df.columns
    mapa_cores = PALETA_STATUS if tem_status and set(df["Status"].unique()) <= set(PALETA_STATUS) else None
    fig = px.line(
        df, x="Semana", y="Quantidade",
        color="Status" if tem_status else None,
        facet_col="Projeto", facet_col_wrap=3,
        color_discrete_sequence=PALETA_COLORIDA,
        color_discrete_map=mapa_cores,
        markers=True,
    )
    fig.update_yaxes(matches="y")
    # Os títulos de cada mini-gráfico vêm como "Projeto=Nome" (padrão do
    # Plotly pra facetas) - troca por só "Nome", mais limpo de ler numa
    # grade com vários mini-gráficos pequenos lado a lado.
    fig.for_each_annotation(lambda anotacao: anotacao.update(text=anotacao.text.split("=")[-1]))
    return fig


def _construir_figura(
    df: pd.DataFrame,
    tipo: str,
    x: str,
    y: str,
    cor: Optional[str] = None,
    ordem_categorias: Optional[dict[str, list[str]]] = None,
    mapa_cores_fixo: Optional[dict[str, str]] = None,
) -> go.Figure:
    """
    Monta a `Figure` do Plotly (sem desenhar nada na tela) - separado de
    `_plotar` de propósito, pra que o mesmo gráfico possa ser tanto
    desenhado no dashboard (`st.plotly_chart`) quanto reaproveitado como
    imagem no relatório em PDF (ver `core/pdf_report.py`), sem duplicar
    nenhuma lógica de construção.

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

    # Mesma ideia acima, só que pro esquema fixo de CRITICIDADE (vermelho/
    # amarelo/verde/azul - ver `ui/theme.py`) - quem chama `_plotar` já
    # calculou o mapa (`mapa_cores_fixo`, ou `None` quando não conseguiu
    # reconhecer a criticidade dos valores com confiança) e só repassa aqui.
    cor_criticidade_sem_dimensao = (
        cor is None and mapa_cores_fixo is not None and x in df.columns
    )
    if cor_criticidade_sem_dimensao:
        cor_discreta = mapa_cores_fixo

    cor_fixa_por_categoria_unica = cor_coluna_board_sem_dimensao or cor_criticidade_sem_dimensao

    def _cores_para_barras(eixo_categoria: str) -> list[str]:
        if cor_fixa_por_categoria_unica:
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
        # a Coluna do Board (ou tem esquema fixo de criticidade), usa a
        # própria coluna de nomes (`x`) como `color`.
        cor_pizza = cor or (x if cor_fixa_por_categoria_unica else None)
        fig = px.pie(df, names=x, values=y, color=cor_pizza, color_discrete_sequence=PALETA_COLORIDA,
                      color_discrete_map=cor_discreta, category_orders=ordem_categorias)
    elif tipo == "Rosca":
        cor_pizza = cor or (x if cor_fixa_por_categoria_unica else None)
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
    elif tipo == "Funil":
        # Funil: mostra a quantidade de itens em cada ESTÁGIO, na ordem em
        # que as linhas já chegam em `df` (não reordena por valor, ao
        # contrário de barras/pizza) - é o motivo de existir: pensado pra
        # "Distribuição por Coluna do Board", cujas linhas já vêm ordenadas
        # pelo fluxo real do board (Backlog -> Finalizado, ver
        # `ORDEM_COLUNAS_BOARD`), então o funil desenha exatamente esse
        # fluxo, de cima pra baixo, e cada estágio já sai com o mesmo
        # percentual de queda em relação ao primeiro (`textinfo`, recurso
        # nativo do Plotly). Reaproveita a mesma cor por categoria de
        # `_cores_para_barras` (a paleta dedicada da Coluna do Board, ou o
        # ciclo padrão por posição) - assim uma pessoa alternando entre
        # Barras/Pizza/Funil pra ver os mesmos dados NÃO vê a cor de cada
        # coluna mudar de um tipo de gráfico pro outro.
        fig = go.Figure(
            go.Funnel(
                y=df[x],
                x=df[y],
                marker=dict(color=_cores_para_barras(x)),
                textinfo="value+percent initial",
            )
        )
    elif tipo == "Mapa de Calor":
        fig = _construir_grafico_mapa_calor(df, x, y, cor, ordem_categorias)
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
    return fig


def _plotar(
    df: pd.DataFrame,
    tipo: str,
    x: str,
    y: str,
    chave: str,
    cor: Optional[str] = None,
    ordem_categorias: Optional[dict[str, list[str]]] = None,
    mapa_cores_fixo: Optional[dict[str, str]] = None,
    titulo: Optional[str] = None,
    secoes_pdf: Optional[list[dict]] = None,
) -> None:
    """
    Desenha o gráfico na tela (`st.plotly_chart`). `titulo`/`secoes_pdf` são
    opcionais: quando `secoes_pdf` é passado (lista mutável mantida por
    `render_dashboard_page`), a MESMA `Figure` desenhada aqui é anexada a
    ela com o rótulo `titulo` - é o que o relatório em PDF (botão "Gerar PDF
    do relatório", ao final do dashboard) usa pra montar o PDF, sem
    recalcular nem redesenhar nada: o PDF reaproveita exatamente o gráfico
    que acabou de ser desenhado na tela, na mesma ordem em que as seções do
    dashboard chamam esta função.
    """
    fig = _construir_figura(df, tipo, x, y, cor=cor, ordem_categorias=ordem_categorias, mapa_cores_fixo=mapa_cores_fixo)
    st.plotly_chart(fig, use_container_width=True, key=f"chart_{chave}")

    if tipo == "Radar (Preenchido)" and cor is None:
        st.caption(
            "💡 Pra sobrepor várias formas coloridas no mesmo radar (comparar Projetos, "
            "Responsáveis, etc. lado a lado), use o **construtor de gráfico personalizado** "
            "mais abaixo e escolha uma coluna em \"Agrupar por\"."
        )

    if tipo == "Pareto":
        st.caption(
            "💡 As barras mostram o valor de cada categoria, da maior para a menor; a linha "
            "é o percentual acumulado (soma das barras até ali, de 0% a 100%) - a linha "
            "pontilhada em 80% ajuda a ver quais poucas categorias já respondem pela maior "
            "parte do total (a regra 80/20)."
        )

    if secoes_pdf is not None:
        secoes_pdf.append({"titulo": titulo or chave, "fig": fig})


class _FilaGraficos:
    """
    Emparelha os gráficos do dashboard dois a dois, lado a lado (pedido
    explícito: "quero que, quando criar os gráficos, eles apareçam em duas
    colunas, dois gráficos lado a lado"), sem precisar reescrever cada seção
    numa estrutura de grade rígida - cada seção continua decidindo sozinha,
    em tempo real, SE tem algo pra mostrar (dados/mapeamento disponíveis);
    só a RENDERIZAÇÃO de cada uma vira uma função (`renderizador`), guardada
    aqui até formar um par com a próxima seção que também tiver algo pra
    mostrar.

    Mobile: `st.columns(2)` já empilha sozinho numa coluna só em telas
    estreitas (comportamento nativo do Streamlit, sem precisar de nenhuma
    media query customizada) - por isso o par vira uma coluna só, um gráfico
    embaixo do outro, automaticamente no celular.

    Conteúdo que NÃO é gráfico (cartões de KPI, tabelas, o construtor de
    gráfico personalizado) não passa por aqui - continua em largura total,
    como sempre foi. Antes de desenhar qualquer um desses, quem chama deve
    chamar `flush()` pra não deixar um gráfico "preso" esperando um par que
    nunca vem.
    """

    def __init__(self, colunas: int = 1) -> None:
        # `colunas`: 1 = um gráfico por linha (padrão - layout "clássico", de
        # antes da grade em duas colunas), 2 = dois gráficos lado a lado.
        # Controlado pelo toggle "Gráficos por linha" no topo do dashboard
        # (ver `render_dashboard_page`) - pedido explícito do usuário depois
        # de ver a versão só com 2 colunas: manter a opção de 2 colunas (pra
        # quem quiser), mas com 1 coluna como padrão, porque vários gráficos
        # têm textos de explicação longos que ficavam espremidos demais lado
        # a lado.
        self._colunas = colunas
        self._pendente = None

    def adicionar(self, renderizador) -> None:
        if self._colunas <= 1:
            renderizador()
            st.divider()
            return
        if self._pendente is None:
            self._pendente = renderizador
            return
        coluna_esquerda, coluna_direita = st.columns(2, gap="large")
        with coluna_esquerda:
            self._pendente()
        with coluna_direita:
            renderizador()
        st.divider()
        self._pendente = None

    def flush(self) -> None:
        if self._pendente is not None:
            self._pendente()
            st.divider()
            self._pendente = None


def _explicacao(texto: str, rotulo: str = "ℹ️ Sobre este indicador", expanded: bool = False) -> None:
    """
    Mostra um texto explicativo dentro de um expansor RECOLHIDO por padrão,
    em vez de um `st.caption` sempre visível - pedido explícito: os textos
    de explicação de cada gráfico (metodologia, o que entra/não entra no
    cálculo etc.) são longos e atrapalhavam a visualização dos gráficos;
    agora ficam escondidos até o usuário optar por abrir.

    `expanded=True`: exceção pontual para os gráficos mais densos do painel
    (ex.: o de bolha "Volume × Idade × Risco", que cruza 4 dimensões ao
    mesmo tempo e não tem um tipo de gráfico mais simples como alternativa)
    - nesses casos, a explicação já vem aberta, pra quem não é de TI não
    precisar saber que existe um "ℹ️" pra clicar antes de entender os eixos.
    """
    with st.expander(rotulo, expanded=expanded):
        st.caption(texto)


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

    # ------------------------------------------------- Toggle: gráficos por linha
    # Flutuante (fica fixo no canto da tela, não rola junto com o conteúdo -
    # ver CSS `.st-key-dashboard_toggle_flutuante` em `ui/theme.py`), pra dar
    # pra trocar o layout mesmo depois de já ter descido bastante pelos
    # gráficos, sem precisar voltar ao topo da página. Controla o layout de
    # TODOS os gráficos abaixo (via `_FilaGraficos`). Desligado (padrão) = 1
    # por linha (layout "clássico"); ligado = 2 por linha, pra quem preferir
    # ver mais gráficos de uma vez (bom pra gráficos mais simples, com pouco
    # texto de explicação).
    with st.container(key="dashboard_toggle_flutuante"):
        duas_colunas_por_linha = st.toggle(
            "2 por linha",
            value=False,
            key="dashboard_toggle_duas_colunas",
            help=(
                "Ligado: mostra 2 gráficos lado a lado em cada linha do painel. "
                "Desligado (padrão): 1 gráfico por linha. No celular, sempre fica "
                "um por linha, independente dessa escolha."
            ),
        )
    colunas_por_linha = 2 if duas_colunas_por_linha else 1

    # Lista mutável que vai sendo preenchida por `_plotar`/`_renderizar_construtor_grafico_personalizado`
    # conforme cada seção é desenhada abaixo - usada só pelo botão "Gerar PDF
    # do relatório" ao final da página (ver `core/pdf_report.py`).
    secoes_pdf: list[dict] = []
    # Fila que emparelha os gráficos (1 ou 2 por linha, conforme o toggle
    # acima) - ver `_FilaGraficos`.
    fila = _FilaGraficos(colunas=colunas_por_linha)

    # ---------------------------------------------------------------- KPIs
    if status_binario:
        indicadores = analytics.calcular_indicadores_gerais(df_filtrado)
        taxa_texto = f"{indicadores.taxa_sucesso}%" if indicadores.taxa_sucesso is not None else "—"
        cartoes_kpi = [
            ("Volumetria de Testes", f"{indicadores.total_registros:,}".replace(",", "."), None, True),
            ("Passaram", f"{indicadores.total_passou:,}".replace(",", "."), None, True),
            ("Não Passaram", f"{indicadores.total_falhou:,}".replace(",", "."), None, False),
            ("Taxa de Sucesso", taxa_texto, None, True),
        ]
    else:
        total = len(df_filtrado)
        distribuicao = analytics.distribuicao_status_bruto(df_filtrado, mapeamento)
        status_top = distribuicao.iloc[0]["Status"] if distribuicao is not None and not distribuicao.empty else "—"
        qtd_top = int(distribuicao.iloc[0]["Quantidade"]) if distribuicao is not None and not distribuicao.empty else 0
        qtd_status_distintos = distribuicao["Status"].nunique() if distribuicao is not None else 0
        cartoes_kpi = [
            ("Volumetria de Testes", f"{total:,}".replace(",", "."), None, True),
            ("Status Mais Frequente", str(status_top), f"{qtd_top} registros", True),
            ("Status Distintos", str(qtd_status_distintos), None, True),
        ]
    render_kpi_row(cartoes_kpi)

    st.markdown("<br>", unsafe_allow_html=True)

    # ---------------------------------------------------- Status geral
    if mapeamento.status:
        def _sec_status_geral() -> None:
            st.markdown("**Distribuição de Status**" if not status_binario else "**Passou vs. Não Passou**")
            if not status_binario:
                _explicacao(
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
                tipo_status = _selecionar_tipo_grafico("status_geral", ["Barras Horizontais", "Pizza", "Rosca", "Barras", "Treemap", "Radar (Preenchido)"])
            if status_binario:
                resumo_status = df_filtrado["__status_normalizado__"].value_counts().reset_index()
                resumo_status.columns = ["Status", "Quantidade"]
            else:
                resumo_status = analytics.distribuicao_status_bruto(df_filtrado, mapeamento)
            _plotar(
                resumo_status, tipo_status, x="Status", y="Quantidade", chave="status_geral",
                titulo="Distribuição de Status" if not status_binario else "Passou vs. Não Passou",
                secoes_pdf=secoes_pdf,
            )
        fila.adicionar(_sec_status_geral)

    # ------------------------------------------------- Area Path × Status
    if not status_binario:
        df_area_x_status = analytics.distribuicao_area_path_x_status(df_filtrado, mapeamento)
        if df_area_x_status is not None and not df_area_x_status.empty:
            def _sec_area_path_status() -> None:
                st.markdown("**Area Path × Status**")
                _explicacao(
                    "Discrimina, para cada Area Path/Projeto, quantos work items estão em cada valor de "
                    "Status - útil para confirmar que valores como UAT/QA/Deploy (quando aparecem) vêm de "
                    "um Area Path/time específico com vocabulário de Status próprio, e não de uma mistura "
                    "com a Coluna do Board."
                )
                col_area_status, _col_espaco_area_status = st.columns([1, 3])
                with col_area_status:
                    tipo_area_status = _selecionar_tipo_grafico("area_path_status", ["Barras", "Barras Horizontais", "Treemap"])
                _plotar(
                    df_area_x_status, tipo_area_status, x="Projeto", y="Quantidade", chave="area_path_status", cor="Status",
                    titulo="Area Path × Status", secoes_pdf=secoes_pdf,
                )
            fila.adicionar(_sec_area_path_status)

    # ------------------------------------------------- Backlog aberto (idade)
    # Não é gráfico (é um bloco de KPIs + tabela) - fica em largura total,
    # então esvazia qualquer gráfico pendente na fila antes (senão ele
    # ficaria "preso" esperando um par que nunca vem).
    fila.flush()
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

        # ---- Gráfico de bolha: Volume x Idade x Risco, por Area Path ou Responsável ----
        opcoes_agrupamento_bolha: dict[str, str] = {}
        if mapeamento.projeto and mapeamento.projeto in df_filtrado.columns:
            opcoes_agrupamento_bolha["Area Path / Projeto"] = mapeamento.projeto
        if mapeamento.responsavel and mapeamento.responsavel in df_filtrado.columns:
            opcoes_agrupamento_bolha["Responsável"] = mapeamento.responsavel

        if opcoes_agrupamento_bolha:
            st.markdown("**Backlog Aberto: Volume × Idade × Risco**")
            _explicacao(
                "Cada bolha é um grupo (Area Path ou Responsável, à sua escolha logo abaixo). "
                "Eixo horizontal: há quanto tempo, em média, os itens abertos daquele grupo "
                "estão parados. Eixo vertical e tamanho da bolha: quantos itens em aberto o "
                "grupo tem (os dois reforçam o mesmo número, de propósito). Cor: quanto mais "
                "vermelha, maior o percentual de itens Severidade Alta/Crítica naquele grupo - "
                "sem Severidade mapeada, todas as bolhas ficam brancas (0%). O quadrante mais "
                "preocupante é bolha grande, mais à direita e mais vermelha ao mesmo tempo: "
                "muito item, parado há muito tempo, e muito crítico.",
                expanded=True,
            )
            col_agrupar_bolha, _col_espaco_bolha = st.columns([1, 3])
            with col_agrupar_bolha:
                rotulo_agrupamento_bolha = st.selectbox(
                    "Agrupar bolhas por", list(opcoes_agrupamento_bolha.keys()), key="backlog_bolha_agrupar_por",
                )
            coluna_agrupamento_bolha = opcoes_agrupamento_bolha[rotulo_agrupamento_bolha]
            df_backlog_bolha = analytics.backlog_aberto_por_grupo(
                df_filtrado, mapeamento, coluna_agrupamento_bolha, rotulo_agrupamento_bolha
            )
            if df_backlog_bolha is not None and not df_backlog_bolha.empty:
                fig_backlog_bolha = _construir_grafico_bolha_backlog(df_backlog_bolha, rotulo_agrupamento_bolha)
                st.plotly_chart(fig_backlog_bolha, use_container_width=True, key="chart_backlog_bolha")
                if secoes_pdf is not None:
                    secoes_pdf.append({
                        "titulo": f"Backlog Aberto: Volume × Idade × Risco (por {rotulo_agrupamento_bolha})",
                        "fig": fig_backlog_bolha,
                    })
            else:
                st.info("Sem dados suficientes para montar o gráfico de bolha com os filtros atuais.")

        st.divider()

    # ------------------------------------------------------------- Sprints
    df_velocidade_sprint = analytics.itens_concluidos_por_sprint(df_filtrado, mapeamento)
    if df_velocidade_sprint is not None and not df_velocidade_sprint.empty:
        # O cartão de KPIs desta seção é largura total - esvazia a fila antes
        # dele, e só o GRÁFICO (abaixo do KPI) entra no emparelhamento.
        fila.flush()
        st.markdown("**Sprints — Itens Concluídos**")
        _explicacao(
            "Quantos itens foram concluídos em cada sprint, dos mais antigos para o mais "
            "recente (aproximado pela data mais antiga dos itens de cada sprint, já que o "
            "Azure DevOps não informa data de início/fim de sprint por esta via) - use para "
            "acompanhar se a equipe está entregando mais ou menos a cada sprint."
        )
        sprint_mais_recente = df_velocidade_sprint.iloc[-1]
        media_por_sprint = df_velocidade_sprint["Quantidade"].mean()
        render_kpi_row([
            ("Sprint Mais Recente", str(sprint_mais_recente["Sprint"]), None, True),
            ("Concluídos no Sprint Mais Recente", f"{int(sprint_mais_recente['Quantidade']):,}".replace(",", "."), None, True),
            ("Média por Sprint", f"{media_por_sprint:.1f}".replace(".", ","), None, True),
        ])

        def _sec_sprint_velocidade() -> None:
            col_tipo_sprint, _col_espaco_sprint = st.columns([1, 3])
            with col_tipo_sprint:
                tipo_sprint = _selecionar_tipo_grafico("sprint_velocidade", ["Barras", "Linha", "Área"])
            _plotar(
                df_velocidade_sprint, tipo_sprint, x="Sprint", y="Quantidade", chave="sprint_velocidade",
                titulo="Sprints — Itens Concluídos", secoes_pdf=secoes_pdf,
            )
        fila.adicionar(_sec_sprint_velocidade)

    # ------------------------------------------ Planejamento vs Efetivado
    df_planejamento = analytics.planejamento_vs_efetivado(df_filtrado, mapeamento)
    if df_planejamento is not None:
        def _sec_planejamento() -> None:
            st.markdown("**Planejamento vs. Testes Efetivados**")
            col_tipo, _col_espaco = st.columns([1, 3])
            with col_tipo:
                tipo_planejamento = _selecionar_tipo_grafico("planejamento", ["Barras", "Pizza", "Rosca"])
            _plotar(
                df_planejamento, tipo_planejamento, x="Categoria", y="Quantidade", chave="planejamento",
                titulo="Planejamento vs. Testes Efetivados", secoes_pdf=secoes_pdf,
            )
        fila.adicionar(_sec_planejamento)

    # ------------------------------------------------------ Testes por projeto
    df_projeto = analytics.testes_por_projeto(df_filtrado, mapeamento)
    if df_projeto is not None:
        def _sec_testes_projeto() -> None:
            st.markdown("**Testes por Projeto**")
            col_tipo, _col_espaco = st.columns([1, 3])
            with col_tipo:
                tipo_projeto = _selecionar_tipo_grafico("testes_projeto")
            _plotar(
                df_projeto, tipo_projeto, x="Projeto", y="Quantidade de Testes", chave="testes_projeto",
                titulo="Testes por Projeto", secoes_pdf=secoes_pdf,
            )
        fila.adicionar(_sec_testes_projeto)

    # ------------------------------------------------- Ranking de bugs
    df_bugs = analytics.ranking_bugs_por_projeto(df_filtrado, mapeamento)
    if df_bugs is not None and not df_bugs.empty:
        def _sec_bugs_projeto() -> None:
            st.markdown("**Ranking de Bugs por Projeto**")
            col_tipo, _col_espaco = st.columns([1, 3])
            with col_tipo:
                tipo_bugs = _selecionar_tipo_grafico("bugs_projeto")
            _plotar(
                df_bugs, tipo_bugs, x="Projeto", y="Quantidade de Bugs", chave="bugs_projeto",
                titulo="Ranking de Bugs por Projeto", secoes_pdf=secoes_pdf,
            )
        fila.adicionar(_sec_bugs_projeto)

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

        def _sec_tipo_teste() -> None:
            st.markdown("**Distribuição por Tipo de Teste**")
            _explicacao(
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
                _plotar(
                    df_tipo_teste, tipo_tt, x="Tipo de Teste", y="Quantidade", chave="tipo_teste",
                    titulo="Distribuição por Tipo de Teste", secoes_pdf=secoes_pdf,
                )
            else:
                st.info("Nenhum tipo restante depois da exclusão acima — ajuste a lista para ver o gráfico.")
        fila.adicionar(_sec_tipo_teste)

    # ------------------------------------------------- Taxa de sucesso por projeto
    df_taxa_projeto = analytics.taxa_sucesso_por_projeto(df_filtrado, mapeamento)
    if df_taxa_projeto is not None and not df_taxa_projeto.empty:
        def _sec_taxa_projeto() -> None:
            st.markdown("**Taxa de Sucesso por Projeto**")
            _plotar(
                df_taxa_projeto, "Barras", x="Projeto", y="Taxa de Sucesso (%)", chave="taxa_projeto",
                titulo="Taxa de Sucesso por Projeto", secoes_pdf=secoes_pdf,
            )
        fila.adicionar(_sec_taxa_projeto)

    # ------------------------------------------------- Tendência temporal
    df_tendencia = analytics.tendencia_temporal(df_filtrado, mapeamento)
    if df_tendencia is not None:
        def _sec_tendencia() -> None:
            st.markdown("**Tendência ao Longo do Tempo**")
            usar_multiplos_pequenos = False
            if mapeamento.projeto and mapeamento.projeto in df_filtrado.columns:
                usar_multiplos_pequenos = st.checkbox(
                    "Separar por Projeto (múltiplos pequenos)",
                    key="tendencia_multiplos_pequenos",
                    help=(
                        "Em vez de uma linha só com todos os projetos misturados, mostra um "
                        "mini-gráfico de tendência por Projeto, lado a lado, todos na mesma escala "
                        "de eixo Y - mais fácil de comparar o FORMATO da tendência entre times do "
                        "que tentar ler várias linhas coloridas empilhadas no mesmo gráfico."
                    ),
                )
            if usar_multiplos_pequenos:
                df_tendencia_projeto = analytics.tendencia_temporal_por_projeto(df_filtrado, mapeamento)
                if df_tendencia_projeto is not None and not df_tendencia_projeto.empty:
                    fig_tendencia_projeto = _construir_grafico_tendencia_multiplos_pequenos(df_tendencia_projeto)
                    st.plotly_chart(
                        fig_tendencia_projeto, use_container_width=True, key="chart_tendencia_multiplos_pequenos"
                    )
                    if secoes_pdf is not None:
                        secoes_pdf.append({
                            "titulo": "Tendência ao Longo do Tempo — por Projeto",
                            "fig": fig_tendencia_projeto,
                        })
                else:
                    st.info("Sem dados suficientes para separar por Projeto com os filtros atuais.")
            else:
                _plotar(df_tendencia, "Linha", x="Semana", y="Quantidade", chave="tendencia",
                        cor="Status" if "Status" in df_tendencia.columns else None,
                        titulo="Tendência ao Longo do Tempo", secoes_pdf=secoes_pdf)
        fila.adicionar(_sec_tendencia)

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
        def _sec_bugs_tempo() -> None:
            st.markdown("**Bugs Abertos vs. Solucionados**")
            _explicacao(
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
                    chave="bugs_tempo", cor="Categoria",
                    titulo="Bugs Abertos vs. Solucionados", secoes_pdf=secoes_pdf)
        fila.adicionar(_sec_bugs_tempo)

    # ------------------------------------------------- Distribuição de severidade
    df_severidade = analytics.distribuicao_severidade(df_filtrado, mapeamento)
    if df_severidade is not None and not df_severidade.empty:
        def _sec_severidade() -> None:
            st.markdown("**Distribuição por Severidade/Prioridade**")
            # Cores ESTRITAS e fixas pro vocabulário padrão do Azure DevOps
            # (ver `cor_discreta_severidade_prioridade` em `ui/theme.py`):
            # Critical=vermelho, High=laranja, Medium=amarelo, Low=verde,
            # "Não atribuído(a)"=azul - sempre, garantido, não é uma tentativa
            # de adivinhar por heurística.
            #
            # O universo de valores usado aqui é o campo **completo, sem os
            # filtros da barra lateral** (`df`, não `df_filtrado`/
            # `df_severidade`) - assim a cor de cada valor conhecido nunca
            # muda dependendo do que o filtro deixa visível no momento (ex.:
            # filtrar um período sem nenhum item "Medium" não faz o "Low"
            # mudar de cor).
            universo_severidade = (
                df[mapeamento.severidade] if mapeamento.severidade in df.columns else df_severidade["Severidade"]
            )
            mapa_cores_severidade = cor_discreta_severidade_prioridade(
                set(universo_severidade.dropna().astype(str))
            )
            _plotar(
                df_severidade, "Pizza", x="Severidade", y="Quantidade", chave="severidade",
                mapa_cores_fixo=mapa_cores_severidade,
                titulo="Distribuição por Severidade/Prioridade", secoes_pdf=secoes_pdf,
            )
        fila.adicionar(_sec_severidade)

    # ------------------------------------------------- Carga de risco por Responsável
    df_resp_x_severidade = analytics.distribuicao_responsavel_x_severidade(df_filtrado, mapeamento)
    if df_resp_x_severidade is not None and not df_resp_x_severidade.empty:
        def _sec_resp_severidade() -> None:
            st.markdown("**Carga de Risco por Responsável (Responsável × Severidade)**")
            _explicacao(
                "Cruza Responsável/Executor com Severidade/Prioridade - mostra não só QUEM tem "
                "mais itens, mas quem está segurando os mais críticos. No **Mapa de Calor** "
                "(padrão), cada linha é um Responsável, cada coluna uma Severidade, e quanto "
                "mais escura a célula, mais itens daquela pessoa estão naquela Severidade - "
                "mais fácil de ler que barras/treemap quando há muitos Responsáveis."
            )
            col_tipo_resp_sev, _col_espaco_resp_sev = st.columns([1, 3])
            with col_tipo_resp_sev:
                tipo_resp_sev = _selecionar_tipo_grafico(
                    "responsavel_severidade", ["Mapa de Calor", "Barras", "Barras Horizontais", "Treemap"]
                )
            _plotar(
                df_resp_x_severidade, tipo_resp_sev, x="Severidade", y="Quantidade",
                chave="responsavel_severidade", cor="Responsável",
                titulo="Carga de Risco por Responsável (Responsável × Severidade)", secoes_pdf=secoes_pdf,
            )
        fila.adicionar(_sec_resp_severidade)

    # ------------------------------------------------- Distribuição por Coluna do Board
    df_coluna_board_completo = analytics.distribuicao_coluna_board(df_filtrado, mapeamento)
    if df_coluna_board_completo is not None and not df_coluna_board_completo.empty:
        df_para_graficos_coluna_board = analytics.excluir_nao_atribuido_coluna_board(df_filtrado, mapeamento)
        df_coluna_board = analytics.distribuicao_coluna_board(df_para_graficos_coluna_board, mapeamento)

        def _sec_coluna_board() -> None:
            st.markdown("**Distribuição por Coluna do Board (Kanban)**")
            _explicacao(
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

            col_board, _col_espaco_board = st.columns([1, 3])
            with col_board:
                tipo_board = _selecionar_tipo_grafico(
                    "coluna_board", ["Barras", "Barras Horizontais", "Pizza", "Rosca", "Treemap", "Funil"]
                )
            if df_coluna_board is not None and not df_coluna_board.empty:
                _plotar(
                    df_coluna_board, tipo_board, x="Coluna do Board", y="Quantidade", chave="coluna_board",
                    ordem_categorias={"Coluna do Board": analytics.ORDEM_COLUNAS_BOARD},
                    titulo="Distribuição por Coluna do Board (Kanban)", secoes_pdf=secoes_pdf,
                )
            else:
                st.info('Nenhum item com Coluna do Board (fora de "Não atribuído(a)") para os filtros atuais.')
        fila.adicionar(_sec_coluna_board)

        # --------------------------------------------- Area Path × Coluna do Board
        df_area_x_board = analytics.distribuicao_area_path_x_coluna_board(
            df_para_graficos_coluna_board, mapeamento
        )
        if df_area_x_board is not None and not df_area_x_board.empty:
            def _sec_area_coluna_board() -> None:
                st.markdown("**Area Path × Coluna do Board**")
                _explicacao(
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
                        "area_path_coluna_board", ["Barras", "Barras Horizontais", "Treemap", "Mapa de Calor"]
                    )
                _plotar(
                    df_area_x_board, tipo_area_board, x="Projeto", y="Quantidade",
                    chave="area_path_coluna_board", cor="Coluna do Board",
                    ordem_categorias={"Coluna do Board": analytics.ORDEM_COLUNAS_BOARD},
                    titulo="Area Path × Coluna do Board", secoes_pdf=secoes_pdf,
                )
            fila.adicionar(_sec_area_coluna_board)

        # ------------------------------------------------- Prioridade no Board
        # Tabela (não gráfico) - largura total, então esvazia a fila antes.
        fila.flush()
        df_prioridade_board = analytics.ranking_prioridade_board(df_filtrado, mapeamento)
        if df_prioridade_board is not None and not df_prioridade_board.empty:
            st.markdown("**Prioridade Dentro do Board**")
            _explicacao(
                "Ranking dos itens em aberto, na ordem real de cima para baixo dentro de cada "
                "coluna do board (Posição 1 = topo da coluna = maior prioridade) - usa o campo "
                "oculto do Azure DevOps (Stack Rank/Backlog Priority) que controla essa ordem "
                "vertical. Só disponível para dados importados pela busca automática do Azure "
                "DevOps (não aparece em upload manual de CSV/TXT)."
            )
            with st.expander("Ver ranking de prioridade por coluna do board", expanded=False):
                st.dataframe(df_prioridade_board, use_container_width=True)
            st.divider()

            # ------------------------------------------- Severidade Calculada (posição no board)
            df_severidade_calculada = analytics.distribuicao_severidade_calculada(df_filtrado, mapeamento)
            if df_severidade_calculada is not None and df_severidade_calculada["Quantidade"].sum() > 0:
                def _sec_severidade_calculada() -> None:
                    st.markdown("**Severidade Calculada (posição no board)**")
                    _explicacao(
                        "Gráfico novo, separado do campo manual \"Severity\" (ver **Distribuição por "
                        "Severidade/Prioridade** acima, que continua igual) - aqui a severidade é "
                        "CALCULADA a partir de onde cada item em aberto está posicionado dentro da "
                        "própria Coluna do Board, do topo (mais grave) para o fundo (menos grave), de "
                        "forma proporcional ao tamanho de cada coluna: uma coluna com só 2 itens não "
                        "joga os dois para \"Crítica\" - o 1º fica \"Crítica\" e o 2º \"Média\", por "
                        "exemplo -, e colunas maiores se espalham pelos 4 níveis "
                        f"({', '.join(analytics.NIVEIS_SEVERIDADE_CALCULADA)}). Usa a mesma base de "
                        "dados do ranking acima (Stack Rank/Backlog Priority). Sempre com o mesmo "
                        "esquema de cores (Crítica=vermelho, Alta=amarelo, Média=verde, "
                        "Baixa=azul), começando no formato rosca."
                    )
                    col_sev_calc, _col_espaco_sev_calc = st.columns([1, 3])
                    with col_sev_calc:
                        tipo_severidade_calculada = _selecionar_tipo_grafico(
                            "severidade_calculada", ["Rosca", "Pizza", "Barras", "Barras Horizontais"]
                        )
                    mapa_cores_severidade_calculada = cor_discreta_criticidade(
                        set(df_severidade_calculada["Severidade Calculada"]),
                        ordem_conhecida=list(analytics.NIVEIS_SEVERIDADE_CALCULADA),
                    )
                    _plotar(
                        df_severidade_calculada, tipo_severidade_calculada,
                        x="Severidade Calculada", y="Quantidade", chave="severidade_calculada",
                        ordem_categorias={"Severidade Calculada": list(analytics.NIVEIS_SEVERIDADE_CALCULADA)},
                        mapa_cores_fixo=mapa_cores_severidade_calculada,
                        titulo="Severidade Calculada (posição no board)", secoes_pdf=secoes_pdf,
                    )
                    with st.expander("Ver detalhamento item a item da Severidade Calculada", expanded=False):
                        st.dataframe(
                            analytics.severidade_calculada_por_posicao(df_filtrado, mapeamento),
                            use_container_width=True,
                        )
                fila.adicionar(_sec_severidade_calculada)
        elif mapeamento.coluna_board and not mapeamento.prioridade_board:
            st.caption(
                "💡 Este arquivo não tem o campo de prioridade por posição no board mapeado - "
                "esse ranking só fica disponível importando os dados pela busca automática do "
                "Azure DevOps (aba **Importar Dados**)."
            )

    # ------------------------------------------------- Volume de Testes por Responsável
    if mapeamento.responsavel and mapeamento.responsavel in df_filtrado.columns:
        def _sec_volume_responsavel() -> None:
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
                    titulo="Volume de Testes por Responsável", secoes_pdf=secoes_pdf,
                )
            else:
                st.info("Sem dados suficientes de Responsável para montar este gráfico.")
        fila.adicionar(_sec_volume_responsavel)

    # ------------------------------------------------- Volume por Responsável ao longo do tempo
    df_volume_tempo, volume_tempo_truncado = analytics.volume_responsavel_por_semana(df_filtrado, mapeamento)
    if df_volume_tempo is not None and not df_volume_tempo.empty:
        def _sec_volume_responsavel_tempo() -> None:
            st.markdown("**Volume por Responsável ao Longo do Tempo**")
            _explicacao(
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
                titulo="Volume por Responsável ao Longo do Tempo", secoes_pdf=secoes_pdf,
            )
            if volume_tempo_truncado:
                st.caption(
                    "Mostrando só as 8 pessoas com mais registros no período (mais que isso deixaria "
                    "o gráfico ilegível, com muitas linhas/cores se cruzando)."
                )
        fila.adicionar(_sec_volume_responsavel_tempo)

    # Fecha qualquer gráfico ainda pendente (ex.: um número ímpar de seções
    # nesta página/nestes filtros) antes do construtor de gráfico
    # personalizado, que fica sempre em largura total (é uma seção diferente,
    # com sua própria grade de controles, não faz parte da galeria acima).
    fila.flush()

    # ------------------------------------------------- Construtor de gráfico personalizado
    _renderizar_construtor_grafico_personalizado(df_filtrado, mapeamento, secoes_pdf=secoes_pdf)

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

    # ------------------------------------------------- Relatório completo em PDF
    st.divider()
    st.markdown("### Relatório completo em PDF")
    st.caption(
        "Gera um PDF com os KPIs e TODOS os gráficos acima, exatamente como estão na tela "
        "agora (mesmos filtros de Período/Projeto/Tipos de Teste/Status aplicados na barra "
        "lateral, e o mesmo tipo de gráfico escolhido em cada seção — inclusive o gráfico "
        "personalizado, se você já tiver gerado um). Não inclui conteúdo que esteja dentro de "
        "um expansor recolhido (ex.: a tabela de dados detalhados acima) — só o que já está "
        "visível por padrão. Se mudar algum filtro depois de gerar, clique de novo para "
        "atualizar o PDF. Pode levar até um minuto (cada gráfico é desenhado um a um) - "
        "**na primeira vez** pode demorar ainda mais, se o app precisar baixar sozinho um "
        "navegador dedicado só pra essa etapa (algo que só acontece se nenhum navegador "
        "compatível já estiver instalado na máquina)."
    )
    # "Baixar PDF gerado" ao lado de "Gerar PDF do relatório" (em vez de
    # embaixo) assim que o PDF já existir em `st.session_state` - antes
    # disso, a coluna da direita simplesmente fica vazia (só "Gerar PDF do
    # relatório" aparece). A 3ª coluna é só espaço vazio, pra os dois botões
    # não esticarem a largura toda nem ficarem colados um no outro.
    col_gerar_pdf, col_baixar_pdf, _col_espaco_pdf = st.columns([1, 1, 2])
    with col_gerar_pdf:
        gerar_pdf = action_button("📄 Gerar PDF do relatório", key="btn_gerar_pdf_relatorio")
    with col_baixar_pdf:
        if st.session_state.get("pdf_relatorio_bytes"):
            st.download_button(
                "⬇️ Baixar PDF gerado",
                data=st.session_state["pdf_relatorio_bytes"],
                file_name=st.session_state.get("pdf_relatorio_nome", "relatorio_qa.pdf"),
                mime="application/pdf",
            )

    if gerar_pdf:
        # Import local (não no topo do arquivo): evita carregar reportlab/kaleido
        # toda vez que a página do dashboard é aberta, mesmo por quem nunca
        # clica em "Gerar PDF do relatório".
        from core.pdf_report import ErroGeracaoPdf, gerar_pdf_relatorio

        try:
            with loading_overlay("Montando o PDF, aguarde... (a 1ª vez pode demorar mais)"):
                resultado_carga = st.session_state.get("resultado_carga")
                nome_origem = resultado_carga.nome_arquivo if resultado_carga else "arquivo importado"
                logo_path = _ASSETS_DIR / "logo_refuturiza.png"
                pdf_bytes = gerar_pdf_relatorio(
                    secoes=secoes_pdf,
                    kpis=cartoes_kpi,
                    nome_arquivo_origem=nome_origem,
                    total_registros=len(df_filtrado),
                    resumo_filtros=_montar_resumo_filtros_ativos(),
                    logo_bytes=logo_path.read_bytes() if logo_path.exists() else None,
                )
                st.session_state["pdf_relatorio_bytes"] = pdf_bytes
                st.session_state["pdf_relatorio_nome"] = (
                    f"relatorio_qa_{agora_brasilia().strftime('%Y%m%d_%H%M')}.pdf"
                )
        except ErroGeracaoPdf as erro:
            # Erro "amigável" - mensagem já pronta pra exibir direto, sem
            # deixar o traceback cru do kaleido/reportlab estourar a página
            # inteira (ver core/pdf_report.py).
            st.session_state["pdf_relatorio_erro"] = str(erro)
            st.session_state.pop("pdf_relatorio_bytes", None)
        else:
            st.session_state.pop("pdf_relatorio_erro", None)
        finish_action("btn_gerar_pdf_relatorio")
        st.rerun()

    if st.session_state.get("pdf_relatorio_erro"):
        st.error(st.session_state["pdf_relatorio_erro"])


def _montar_resumo_filtros_ativos() -> list[str]:
    """
    Descreve, em texto simples, os filtros aplicados no momento (mesmas
    chaves de `st.session_state` lidas em `_aplicar_filtros_sidebar`) - usado
    só no cabeçalho do relatório em PDF, pra deixar claro com quais filtros
    aquele PDF foi gerado.
    """
    linhas = []
    data_inicio = st.session_state.get("filtro_data_inicio")
    data_fim = st.session_state.get("filtro_data_fim")
    if data_inicio and data_fim:
        linhas.append(f"Período: {data_inicio.strftime('%d/%m/%Y')} a {data_fim.strftime('%d/%m/%Y')}")

    for chave_estado, rotulo in (
        ("filtro_projeto", "Projeto"),
        ("filtro_sprint", "Sprint"),
        ("filtro_tipo_teste", "Tipos de Teste"),
        ("filtro_status", "Status"),
    ):
        selecionados = st.session_state.get(chave_estado)
        if selecionados:
            texto = ", ".join(selecionados) if len(selecionados) <= 6 else f"{len(selecionados)} selecionados"
            linhas.append(f"{rotulo}: {texto}")

    return linhas


def _renderizar_construtor_grafico_personalizado(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, secoes_pdf: Optional[list[dict]] = None
) -> None:
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
                    titulo=f"Gráfico Personalizado — {parametros_salvos['rotulo_x']}",
                    secoes_pdf=secoes_pdf,
                )
