"""
Infraestrutura de gráficos compartilhada entre páginas do app (Dashboard e
Scrum/Sprints, ver `ui/pages/dashboard_page.py` e `ui/pages/scrum_page.py`).

Centraliza aqui tudo que NÃO é específico de uma seção/gráfico em particular:
o dispatcher que decide qual função do Plotly chamar por "Tipo de gráfico"
(`construir_figura`), o wrapper que desenha na tela e opcionalmente alimenta
o relatório em PDF (`plotar`), o seletor de tipo (`selecionar_tipo_grafico`),
o emparelhamento de gráficos dois a dois (`FilaGraficos`) e os construtores
de gráficos "especiais" que não são um `px.<tipo>` direto (Pareto, Mapa de
Calor, Bolha). Extraído de `ui/pages/dashboard_page.py` quando a página de
Scrum/Sprints foi criada, pra que as duas páginas usem exatamente a mesma
lógica de desenho/cor em vez de duas cópias que podem divergir com o tempo.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui.theme import (
    BACKGROUND_COLOR,
    PALETA_BUGS_TEMPO,
    PALETA_COLORIDA,
    PALETA_GRAFICOS,
    PALETA_STATUS,
    PRIMARY_COLOR,
    cor_discreta_coluna_board,
)

TIPOS_GRAFICO_PADRAO = ["Barras", "Barras Horizontais", "Pizza", "Rosca", "Linha", "Área", "Treemap", "Pareto", "Radar (Preenchido)"]


def selecionar_tipo_grafico(chave: str, opcoes: list[str] = None) -> str:
    opcoes = opcoes or TIPOS_GRAFICO_PADRAO
    return st.selectbox("Tipo de gráfico", opcoes, key=f"tipo_grafico_{chave}")


def explicacao(texto: str, rotulo: str = "ℹ️ Sobre este indicador", expanded: bool = False) -> None:
    """
    Mostra um texto explicativo dentro de um expansor RECOLHIDO por padrão,
    em vez de um `st.caption` sempre visível - pedido explícito: os textos
    de explicação de cada gráfico (metodologia, o que entra/não entra no
    cálculo etc.) são longos e atrapalhavam a visualização dos gráficos;
    agora ficam escondidos até o usuário optar por abrir.

    `expanded=True`: exceção pontual para os gráficos mais densos de cada
    página (ex.: o de bolha "Volume × Idade × Risco", que cruza várias
    dimensões ao mesmo tempo e não tem um tipo de gráfico mais simples como
    alternativa) - nesses casos, a explicação já vem aberta, pra quem não é
    de TI não precisar saber que existe um "ℹ️" pra clicar antes de entender
    os eixos.
    """
    with st.expander(rotulo, expanded=expanded):
        st.caption(texto)


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


def construir_grafico_bolha_backlog(df_grupo: pd.DataFrame, coluna_rotulo: str) -> go.Figure:
    """
    Gráfico de bolha "Volume × Idade × Risco" - 3 dimensões num só olhar, uma
    bolha por grupo (Area Path, Responsável, ou Coluna do Board, à escolha
    de quem chama):

        eixo X = "Idade Média (dias)" parado em aberto naquele grupo;
        eixo Y = "Quantidade" de itens em aberto do grupo (reforçado pelo
            TAMANHO da bolha, pro mesmo valor "pular aos olhos" duas vezes);
        cor da bolha = "% Severidade Alta/Crítica" - canal SEQUENCIAL (um
            matiz só, claro→escuro), NUNCA uma cor por grupo: com muitos
            grupos, uma paleta categórica deixaria rapidamente de
            diferenciar as bolhas (é exatamente o motivo de mapas de bolha
            usarem, no máximo, ~3 cores categóricas antes de precisar de
            outro canal) - aqui a cor conta a história de RISCO, não de
            identidade de quem é o grupo (isso já está no rótulo, visível
            ao passar o mouse).

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


def construir_figura(
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
    `plotar` de propósito, pra que o mesmo gráfico possa ser tanto desenhado
    na tela (`st.plotly_chart`) quanto reaproveitado como imagem no
    relatório em PDF (ver `core/pdf_report.py`), sem duplicar nenhuma lógica
    de construção.

    `ordem_categorias` (opcional): dict eixo/coluna -> lista com a ordem
    desejada das categorias (ex.: {"Coluna do Board": analytics.ORDEM_COLUNAS_BOARD}),
    repassado direto pro `category_orders` do Plotly Express - sem isso, a
    ordem das categorias segue a ordem das linhas do dataframe recebido, o
    que nem sempre é suficiente quando a mesma coluna aparece espalhada (ex.:
    cruzada com Projeto) e precisa de uma ordem única e consistente em todo
    o gráfico (barras, cor/legenda e empilhamento).

    A lista de ordem pode ser (e costuma ser, com `ORDEM_COLUNAS_BOARD`) mais
    longa do que os valores que realmente aparecem em `df` - ex.: um board
    específico não usa todas as ~19 colunas "canônicas" do fluxo padrão. Sem
    filtrar isso, o Plotly usa a lista inteira como `categoryarray` do eixo e
    desenha um "furo" (tick vazio, sem barra) pra cada categoria da lista que
    não existe nos dados - por isso, antes de repassar pro Plotly, cada lista
    é reduzida só aos valores que realmente aparecem em `df[coluna]`.
    """
    if ordem_categorias:
        ordem_categorias = {
            coluna: [valor for valor in ordem if valor in set(df[coluna])]
            for coluna, ordem in ordem_categorias.items()
            if coluna in df.columns
        }

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
    # amarelo/verde/azul - ver `ui/theme.py`) - quem chama `plotar` já
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


def plotar(
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
    opcionais: quando `secoes_pdf` é passado (lista mutável mantida por quem
    chama), a MESMA `Figure` desenhada aqui é anexada a ela com o rótulo
    `titulo` - é o que o relatório em PDF (botão "Gerar PDF do relatório")
    usa pra montar o PDF, sem recalcular nem redesenhar nada: o PDF
    reaproveita exatamente o gráfico que acabou de ser desenhado na tela, na
    mesma ordem em que as seções da página chamam esta função.
    """
    fig = construir_figura(df, tipo, x, y, cor=cor, ordem_categorias=ordem_categorias, mapa_cores_fixo=mapa_cores_fixo)
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


class FilaGraficos:
    """
    Emparelha os gráficos de uma página dois a dois, lado a lado (pedido
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
        # Controlado pelo toggle "Gráficos por linha" no topo de cada página
        # que usa esta classe - pedido explícito do usuário depois de ver a
        # versão só com 2 colunas: manter a opção de 2 colunas (pra quem
        # quiser), mas com 1 coluna como padrão, porque vários gráficos têm
        # textos de explicação longos que ficavam espremidos demais lado a
        # lado.
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