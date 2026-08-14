"""
Página "Scrum & Sprints": indicadores de fluxo, ritmo de entrega e
observabilidade do time, separados do Dashboard geral (ver
`ui/pages/dashboard_page.py`) - pedido explícito pra dar a uma Scrum Master
uma área própria, focada, sem precisar garimpar entre os indicadores de
qualidade de testes do resto do app.

Reaproveita a mesma infraestrutura de gráficos/filtros do Dashboard
(`ui/graficos.py`, `ui/filtros_dashboard.py`) - inclusive os MESMOS widgets
de filtro da barra lateral (Período/Projeto/Sprint/Tipos de Teste/Status,
mesma `key`), então o filtro escolhido aqui continua aplicado ao trocar pra
"Indicadores" e vice-versa.

Escopo dos indicadores (por que cada gráfico existe, e por que alguns
gráficos "clássicos" de Scrum NÃO estão aqui):

    - Burndown/Burnup de sprint e Cumulative Flow Diagram (CFD) clássicos
      exigem um HISTÓRICO dia a dia (quanto trabalho restava em cada dia,
      quantos itens estavam em cada coluna a cada dia). O app importa um
      retrato ÚNICO e atual dos work items (CSV exportado agora, ou busca
      automática no Azure DevOps agora) - não guarda snapshots diários -,
      então esses dois gráficos não têm como ser desenhados de forma
      honesta com os dados disponíveis hoje. Construí-los mesmo assim
      produziria um gráfico com a FORMA certa mas o conteúdo errado, o que é
      pior do que não ter o gráfico.
    - Velocity clássica (soma de Story Points concluídos por sprint) fica
      disponível quando o arquivo importado tem uma coluna de Story Points
      mapeada (ver "Velocity por Story Points (Sprint)" abaixo,
      `analytics.velocidade_por_sprint_pontos`). Como esse campo é
      preenchido MANUALMENTE pelo time durante planejamento/refinamento no
      Azure DevOps - nunca automático -, times que ainda não adotaram essa
      prática (ou adotaram só parcialmente) vão ver cobertura baixa; a
      página avisa isso na tela (`analytics.cobertura_story_points`) sempre
      que a cobertura fica abaixo do limiar de confiança. "Itens Concluídos
      por Sprint" (contagem de itens, não esforço) continua existindo ao
      lado como leitura complementar que não depende desse preenchimento -
      é a Velocity a se usar enquanto Story Points não estiver bem coberto.
    - Em compensação, os indicadores abaixo (WIP atual, mix de tipos em
      aberto, aging por coluna do board, carga por responsável, inflow
      semanal) são todos calculáveis com segurança a partir de um retrato
      atual + data de criação - o que o arquivo realmente tem -, e cobrem a
      mesma pergunta de fundo que Burndown/CFD respondem ("o fluxo está
      saudável, ou empacado em algum lugar?"), só que a partir do estado
      ATUAL em vez de uma linha do tempo.

Se/quando a Scrum Master trouxer novos indicadores específicos (metas de
sprint, capacidade planejada, etc.), este arquivo é o lugar certo pra
acrescentá-los.

Fonte de dados PRÓPRIA (independente do resto do app):
    Por padrão, esta página usa o mesmo `dataframe_bruto`/`mapeamento_colunas`
    já importados em "Importar Dados" - o mesmo dado que alimenta o
    Dashboard. Só que esse arquivo pode misturar work items de vários
    Projetos/Area Paths do Azure DevOps (pedido explícito: uma Scrum Master
    que só acompanha UM Projeto/Área precisa conseguir escolher isso, sem
    depender de como o restante do app importou os dados, e sem afetar o que
    o Dashboard mostra). Por isso esta página também pode buscar seus
    PRÓPRIOS dados direto do Azure DevOps (Organização → Projeto → Area
    Path(s) opcional → Query), através do mesmo widget reutilizável usado em
    "Importar Dados" (`ui/busca_azure_devops.py`, `namespace="scrum_azure"`
    aqui vs. `namespace="azure"` lá - estado completamente isolado, nenhuma
    das duas buscas interfere na outra). O resultado fica em
    `st.session_state["scrum_dataframe_bruto"]`/`["scrum_mapeamento_colunas"]`,
    só usado por esta página - o Dashboard/PDF/etc. nunca enxergam essa busca.
"""

from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import streamlit as st

from auth.auth_manager import AuthManager
from core import analytics
from core.column_mapper import MapeamentoColunas, detectar_mapeamento
from core.fuso_horario import agora_brasilia
from ui.analise_grafico import renderizar_botao_analise_ia
from ui.busca_azure_devops import ResultadoBuscaAzureDevOps, renderizar_busca_azure_devops
from ui.components import render_header, render_kpi_row
from ui.filtros_dashboard import aplicar_filtros_sidebar
from ui.graficos import (
    FilaGraficos,
    construir_figura,
    construir_grafico_bolha_backlog,
    explicacao,
    plotar,
    selecionar_tipo_grafico,
)

# Tipos de work item que são artefatos de organização/execução de QA (não
# itens de ENTREGA do Scrum em si) - excluídos por padrão dos indicadores
# desta página (ajustável no expansor "Escopo desta página" logo abaixo do
# cabeçalho). Comparação normalizada em minúsculas, então bate com "Test
# Case", "test case", "TEST CASE" etc.
_PALAVRAS_TIPO_FORA_DE_ENTREGA = ("test case", "test plan", "test suite", "shared steps", "shared parameter")


def _tipos_fora_de_entrega_padrao(tipos_disponiveis: list[str]) -> list[str]:
    return [
        valor
        for valor in tipos_disponiveis
        if any(palavra in valor.lower() for palavra in _PALAVRAS_TIPO_FORA_DE_ENTREGA)
    ]


# Abaixo deste percentual de itens de entrega com Story Points preenchido, a
# seção "Velocity por Story Points" mostra um aviso explícito de baixa
# cobertura (em vez de deixar o número baixo falar sozinho e passar a
# impressão errada de "o time entregou pouco esforço", quando na verdade é
# "a maior parte do que foi entregue não tem Story Points registrado").
_LIMIAR_COBERTURA_STORY_POINTS_BAIXA = 30.0

_OPCAO_FONTE_IMPORTADA = "Arquivo já importado no app"
_OPCAO_FONTE_PROPRIA = "Buscar direto no Azure DevOps (só para esta página)"


def _renderizar_selecao_fonte_dados() -> None:
    """
    Expansor com a escolha de fonte de dados desta página (ver docstring do
    módulo) - "Arquivo já importado no app" (padrão, mesmo dado do
    Dashboard) ou "Buscar direto no Azure DevOps" (Organização/Projeto/Area
    Path(s) opcional/Query PRÓPRIOS desta página, via
    `ui.busca_azure_devops.renderizar_busca_azure_devops`, completamente
    isolados do resto do app).

    Não devolve nada - grava o resultado em `st.session_state["scrum_dataframe_bruto"]`/
    `["scrum_mapeamento_colunas"]`/`["scrum_resultado_carga"]`, lidos por
    `render_scrum_page` logo depois de chamar esta função.
    """
    tem_busca_propria_guardada = st.session_state.get("scrum_dataframe_bruto") is not None

    st.caption(
        "Por padrão, esta página usa o mesmo arquivo/dados já importados no resto do app "
        "(página **Importar Dados**), igual ao Dashboard. Se esse arquivo mistura work items de "
        "vários Projetos/Area Paths do Azure DevOps, ou se você só quer olhar um recorte "
        "diferente aqui, escolha a segunda opção abaixo para buscar direto no Azure DevOps "
        "(Organização → Projeto → Area Path(s) opcional → Query) - o resultado vale só para "
        "**esta página**; o Dashboard e o resto do app continuam usando o que já estiver "
        "importado normalmente, sem nenhuma mudança."
    )

    opcoes = [_OPCAO_FONTE_IMPORTADA, _OPCAO_FONTE_PROPRIA]
    escolha_padrao = _OPCAO_FONTE_PROPRIA if tem_busca_propria_guardada else _OPCAO_FONTE_IMPORTADA
    escolha = st.radio(
        "Fonte de dados desta página",
        options=opcoes,
        index=opcoes.index(st.session_state.get("scrum_fonte_dados_escolha", escolha_padrao)),
        key="scrum_fonte_dados_escolha",
        horizontal=True,
    )

    if escolha == _OPCAO_FONTE_IMPORTADA:
        if tem_busca_propria_guardada:
            st.caption(
                "💡 Você já tem uma busca própria guardada nesta sessão do navegador - escolha a "
                "outra opção acima para voltar a usá-la, sem precisar buscar de novo."
            )
        return

    def _ao_concluir(resultado: ResultadoBuscaAzureDevOps) -> None:
        st.session_state["scrum_dataframe_bruto"] = resultado.dataframe
        st.session_state["scrum_mapeamento_colunas"] = detectar_mapeamento(resultado.dataframe)
        st.session_state["scrum_resultado_carga"] = {
            "organizacao": resultado.organizacao,
            "projeto": resultado.projeto,
            "area_paths_filtro": resultado.area_paths_filtro,
            "total_itens": len(resultado.dataframe),
        }
        time.sleep(0.3)

    # Reaproveita o PAT já colado em "Importar Dados" nesta mesma sessão do
    # navegador, só como conveniência inicial - a partir daqui o PAT desta
    # busca vive na própria chave (`scrum_azure_pat_persistido`) e muda
    # independente do da outra tela (ver docstring de `renderizar_busca_azure_devops`).
    renderizar_busca_azure_devops(
        namespace="scrum_azure",
        ao_concluir_busca=_ao_concluir,
        pat_inicial=st.session_state.get("azure_pat_persistido", ""),
        rotulo_botao_baixar="Buscar dados para Scrum & Sprints",
        contexto_log="via Scrum & Sprints",
    )

    dados_propria = st.session_state.get("scrum_resultado_carga")
    if dados_propria:
        area_paths_texto = (
            f" · Area Path(s): {', '.join(dados_propria['area_paths_filtro'])}"
            if dados_propria["area_paths_filtro"] else ""
        )
        st.success(
            f"✅ Usando busca própria: **{dados_propria['organizacao']}/{dados_propria['projeto']}**"
            f"{area_paths_texto} · {dados_propria['total_itens']} itens."
        )
        if st.button(
            "🗑️ Descartar busca própria e voltar ao arquivo importado",
            key="scrum_descartar_fonte_propria",
        ):
            st.session_state["scrum_dataframe_bruto"] = None
            st.session_state["scrum_mapeamento_colunas"] = None
            st.session_state["scrum_resultado_carga"] = None
            st.session_state["scrum_fonte_dados_escolha"] = _OPCAO_FONTE_IMPORTADA
            st.rerun()


def render_scrum_page() -> None:
    render_header(
        titulo="🏃 Scrum & Sprints",
        subtitulo="Fluxo, ritmo de entrega e observabilidade do time — visão pensada para Scrum Master.",
    )

    with st.expander(
        "🔎 Fonte de dados desta página (Organização/Projeto/Area Path)", expanded=False,
    ):
        _renderizar_selecao_fonte_dados()

    usa_fonte_propria = st.session_state.get("scrum_fonte_dados_escolha") == _OPCAO_FONTE_PROPRIA

    if usa_fonte_propria:
        df_bruto = st.session_state.get("scrum_dataframe_bruto")
        mapeamento: Optional[MapeamentoColunas] = st.session_state.get("scrum_mapeamento_colunas")
        if df_bruto is None or mapeamento is None:
            st.info(
                "Nenhuma busca própria feita ainda para esta página. Abra o expansor acima para "
                "buscar direto no Azure DevOps, ou volte para \"Arquivo já importado no app\"."
            )
            return
    else:
        df_bruto = st.session_state.get("dataframe_bruto")
        mapeamento = st.session_state.get("mapeamento_colunas")
        if df_bruto is None or mapeamento is None or not st.session_state.get("mapeamento_confirmado"):
            st.info(
                "Nenhum arquivo processado ainda. Vá até a página **Importar Dados** no menu lateral, "
                "envie um arquivo e confirme o mapeamento de colunas — ou abra o expansor acima para "
                "buscar dados só para esta página, direto no Azure DevOps."
            )
            return

    df = analytics.preparar_dados(df_bruto, mapeamento)
    df_filtrado = aplicar_filtros_sidebar(df, mapeamento)

    if df_filtrado.empty:
        st.warning("Nenhum registro corresponde aos filtros selecionados.")
        return

    # ------------------------------------------------------- Escopo da página
    # Por padrão, tira artefatos de organização/execução de QA (Test Case,
    # Test Plan, Test Suite, Shared Steps/Parameter) - uma Scrum Master
    # acompanha itens de ENTREGA (Story/Bug/Task/Feature/...), não os
    # artefatos que a QA usa pra organizar a execução dos testes.
    df_scrum = df_filtrado
    if mapeamento.tipo_teste and mapeamento.tipo_teste in df_filtrado.columns:
        tipos_disponiveis = sorted(df_filtrado[mapeamento.tipo_teste].dropna().astype(str).unique().tolist())
        padrao_excluidos = _tipos_fora_de_entrega_padrao(tipos_disponiveis)
        with st.expander("⚙️ Escopo desta página — Tipos de trabalho considerados", expanded=False):
            st.caption(
                "Por padrão, esta página conta só itens de ENTREGA do Scrum (User Story, Bug, Task, "
                "Feature, Spike etc.) — artefatos de organização/execução de QA (Test Case, Test "
                "Plan, Test Suite, Shared Steps/Parameter) ficam fora, porque não são itens que uma "
                "Scrum Master acompanharia num board de sprint. Ajuste livremente abaixo se quiser "
                "incluí-los."
            )
            tipos_excluidos_selecionados = st.multiselect(
                "Tipos de trabalho fora do escopo desta página",
                options=tipos_disponiveis,
                default=padrao_excluidos,
                key="scrum_tipos_excluidos",
            )
        if tipos_excluidos_selecionados:
            df_scrum = df_filtrado[
                ~df_filtrado[mapeamento.tipo_teste].astype(str).isin(tipos_excluidos_selecionados)
            ]

    if df_scrum.empty:
        st.warning("Nenhum item de entrega (fora do escopo excluído acima) para os filtros atuais.")
        return

    # -------------------------------------------- Sprint real: aviso/limite
    df_velocidade_sprint = analytics.itens_concluidos_por_sprint(df_scrum, mapeamento)
    sprint_tem_variedade = (
        df_velocidade_sprint is not None
        and not df_velocidade_sprint.empty
        and df_velocidade_sprint["Sprint"].nunique() > 1
    )

    # ------------------------------------- Velocity por Story Points (esforço)
    cobertura_sp = analytics.cobertura_story_points(df_scrum, mapeamento)
    df_velocidade_pontos = (
        analytics.velocidade_por_sprint_pontos(df_scrum, mapeamento) if mapeamento.story_points else None
    )
    velocidade_pontos_disponivel = (
        sprint_tem_variedade
        and df_velocidade_pontos is not None
        and not df_velocidade_pontos.empty
    )
    cobertura_sp_baixa = bool(
        cobertura_sp is not None and cobertura_sp["percentual"] < _LIMIAR_COBERTURA_STORY_POINTS_BAIXA
    )

    with st.expander("ℹ️ Sobre os dados de Sprint nesta página", expanded=not sprint_tem_variedade):
        if not mapeamento.sprint:
            st.caption(
                "O arquivo importado não tem uma coluna mapeada como **Sprint** (o app procura por "
                "\"Sprint\"/\"Iteration Path\"/\"Iteration\" no cabeçalho) — os indicadores que "
                "dependem de sprint real (ex.: Itens Concluídos por Sprint) não aparecem até isso "
                "ser mapeado. Os demais indicadores desta página (fluxo, WIP, aging por coluna do "
                "board, carga por responsável) não dependem de Sprint e continuam válidos "
                "normalmente."
            )
        elif not sprint_tem_variedade:
            st.caption(
                "O campo mapeado como Sprint (**Iteration Path**, no export do Azure DevOps) está "
                "com o MESMO valor em todo o arquivo — os work items ainda não têm um sprint "
                "individual registrado, só o node raiz do Team Project. Por isso o gráfico "
                "**Itens Concluídos por Sprint** não aparece agora (mostraria uma única barra sem "
                "significado real). Para esse indicador funcionar, a query que gera o arquivo (ou a "
                "configuração de Iteration dos work items no Azure DevOps) precisa referenciar o "
                "sprint específico de cada item, não só o Team Project. Os demais indicadores desta "
                "página (fluxo, WIP atual, aging por coluna do board, carga por responsável) não "
                "dependem de Sprint real e continuam válidos normalmente."
            )
        else:
            st.caption(
                "Sprint aqui vem do campo Iteration Path do Azure DevOps, agrupado e ordenado "
                "cronologicamente pela data mais antiga dos itens de cada sprint (o Azure DevOps não "
                "expõe data de início/fim de sprint por esta via)."
            )

    with st.container(key="dashboard_toggle_flutuante"):
        duas_colunas_por_linha = st.toggle(
            "2 por linha", value=False, key="scrum_toggle_duas_colunas",
            help=(
                "Ligado: mostra 2 gráficos lado a lado em cada linha. Desligado (padrão): 1 gráfico "
                "por linha. No celular, sempre fica um por linha, independente dessa escolha."
            ),
        )
    fila = FilaGraficos(colunas=2 if duas_colunas_por_linha else 1)

    # ---------------------------------------------------------------- KPIs
    indicadores_aberto = analytics.calcular_backlog_aberto(df_scrum, mapeamento)
    df_criados_semana = analytics.tendencia_temporal(df_scrum, mapeamento)

    cartoes_kpi: list[tuple[str, str, Optional[str], bool]] = []
    if indicadores_aberto is not None:
        idade_texto = (
            f"{indicadores_aberto.idade_media_dias:.0f} dias"
            if indicadores_aberto.idade_media_dias is not None
            else "—"
        )
        cartoes_kpi.append(
            ("WIP Total (itens em aberto)", f"{indicadores_aberto.total_abertos:,}".replace(",", "."), None, True)
        )
        cartoes_kpi.append(("Idade Média do WIP", idade_texto, None, False))
    if df_criados_semana is not None and not df_criados_semana.empty:
        n_semanas = min(4, len(df_criados_semana))
        itens_periodo = int(df_criados_semana.tail(n_semanas)["Quantidade"].sum())
        rotulo_periodo = f"Itens Criados (últimas {n_semanas} semana{'s' if n_semanas != 1 else ''})"
        cartoes_kpi.append((rotulo_periodo, f"{itens_periodo:,}".replace(",", "."), None, True))
    if sprint_tem_variedade:
        cartoes_kpi.append((
            "Concluídos no Sprint Mais Recente",
            f"{int(df_velocidade_sprint.iloc[-1]['Quantidade']):,}".replace(",", "."),
            None, True,
        ))
    if velocidade_pontos_disponivel:
        media_pontos_sprint = df_velocidade_pontos["Story Points Concluídos"].mean()
        cartoes_kpi.append((
            "Velocity Média (Story Points/Sprint)",
            f"{media_pontos_sprint:.1f}".replace(".", ","),
            f"{cobertura_sp['percentual']:.0f}% de cobertura" if cobertura_sp else None,
            not cobertura_sp_baixa,
        ))
    if cartoes_kpi:
        render_kpi_row(cartoes_kpi)
        st.divider()

    # ---------------------------------------- Itens Concluídos por Sprint
    if sprint_tem_variedade:
        st.markdown("**Itens Concluídos por Sprint**")
        explicacao(
            "Quantos itens foram concluídos em cada sprint, dos mais antigos para o mais recente "
            "(aproximado pela data mais antiga dos itens de cada sprint, já que o Azure DevOps não "
            "informa data de início/fim de sprint por esta via) - use para acompanhar se a equipe "
            "está entregando mais ou menos a cada sprint. É uma velocity por CONTAGEM de itens, não "
            "por esforço/Story Points (o arquivo importado não tem esse campo)."
        )
        media_por_sprint = df_velocidade_sprint["Quantidade"].mean()
        render_kpi_row([
            ("Sprint Mais Recente", str(df_velocidade_sprint.iloc[-1]["Sprint"]), None, True),
            ("Média por Sprint", f"{media_por_sprint:.1f}".replace(".", ","), None, True),
        ])

        def _sec_sprint_velocidade() -> None:
            col_tipo, _col_espaco = st.columns([1, 3])
            with col_tipo:
                tipo_sprint = selecionar_tipo_grafico("scrum_sprint_velocidade", ["Barras", "Linha", "Área"])
            plotar(
                df_velocidade_sprint, tipo_sprint, x="Sprint", y="Quantidade", chave="scrum_sprint_velocidade",
                titulo="Itens Concluídos por Sprint",
            )
            renderizar_botao_analise_ia(
                chave="scrum_sprint_velocidade",
                titulo="Itens Concluídos por Sprint",
                descricao=(
                    "Quantidade de itens concluídos em cada sprint, dos mais antigos para o mais "
                    "recente - velocity por CONTAGEM de itens (não por Story Points)."
                ),
                tipo_grafico=tipo_sprint.lower(),
                dados=df_velocidade_sprint,
                contexto_extra={
                    "sprint_mais_recente": str(df_velocidade_sprint.iloc[-1]["Sprint"]),
                    "quantidade_sprint_mais_recente": int(df_velocidade_sprint.iloc[-1]["Quantidade"]),
                    "media_itens_por_sprint": media_por_sprint,
                },
                nome_usuario=AuthManager.current_username(),
            )
        fila.adicionar(_sec_sprint_velocidade)

    # ---------------------------------------- Velocity por Story Points (esforço)
    if velocidade_pontos_disponivel:
        st.markdown("**Velocity por Story Points (Sprint)**")
        if cobertura_sp_baixa:
            st.warning(
                f"⚠️ Story Points está preenchido em só {cobertura_sp['preenchidos']} de "
                f"{cobertura_sp['total']} itens de entrega no período/filtro atual "
                f"({cobertura_sp['percentual']:.1f}%). Itens sem esse campo preenchido não entram na "
                "soma abaixo — os valores por sprint tendem a aparecer bem mais baixos do que o "
                "esforço real entregue, não porque o time entregou pouco. Peça ao time para preencher "
                "Story Points durante o planejamento/refinamento no Azure DevOps para este indicador "
                "refletir a realidade; até lá, prefira **Itens Concluídos por Sprint** (acima) como "
                "referência principal de ritmo."
            )
        explicacao(
            "Soma de Story Points dos itens concluídos em cada sprint — a Velocity clássica do Scrum, "
            "por esforço estimado (diferente de **Itens Concluídos por Sprint** acima, que conta "
            "itens, não pontos). Só soma itens com Story Points preenchido."
        )

        def _sec_velocidade_pontos() -> None:
            col_tipo, _col_espaco = st.columns([1, 3])
            with col_tipo:
                tipo_velocidade_pontos = selecionar_tipo_grafico(
                    "scrum_velocidade_pontos", ["Barras", "Linha", "Área"]
                )
            plotar(
                df_velocidade_pontos, tipo_velocidade_pontos, x="Sprint", y="Story Points Concluídos",
                chave="scrum_velocidade_pontos", titulo="Velocity por Story Points (Sprint)",
            )
            renderizar_botao_analise_ia(
                chave="scrum_velocidade_pontos",
                titulo="Velocity por Story Points (Sprint)",
                descricao=(
                    "Soma de Story Points dos itens concluídos em cada sprint — a Velocity clássica do "
                    "Scrum, por esforço estimado (diferente de Itens Concluídos por Sprint, que conta "
                    "itens, não pontos)."
                ),
                tipo_grafico=tipo_velocidade_pontos.lower(),
                dados=df_velocidade_pontos,
                contexto_extra={"cobertura_story_points_baixa": cobertura_sp_baixa},
                nome_usuario=AuthManager.current_username(),
            )
        fila.adicionar(_sec_velocidade_pontos)

    # ---------------------------------------- Itens Criados por Semana (inflow)
    if df_criados_semana is not None and not df_criados_semana.empty:
        def _sec_criados_semana() -> None:
            st.markdown("**Itens Criados por Semana**")
            explicacao(
                "Volume de itens de entrega criados a cada semana — a \"entrada\" de trabalho no "
                "fluxo do time. Compare com o WIP atual e o aging abaixo: se a entrada é maior do "
                "que a capacidade de concluir, o backlog tende a crescer com o tempo, mesmo que o "
                "time esteja trabalhando normalmente."
            )
            col_tipo, _col_espaco = st.columns([1, 3])
            with col_tipo:
                tipo_criados = selecionar_tipo_grafico("scrum_criados_semana", ["Linha", "Área", "Barras"])
            plotar(
                df_criados_semana, tipo_criados, x="Semana", y="Quantidade", chave="scrum_criados_semana",
                cor="Status" if "Status" in df_criados_semana.columns else None,
                titulo="Itens Criados por Semana",
            )
            renderizar_botao_analise_ia(
                chave="scrum_criados_semana",
                titulo="Itens Criados por Semana",
                descricao="Volume de itens de entrega criados a cada semana — a entrada de trabalho no fluxo do time.",
                tipo_grafico=tipo_criados.lower(),
                dados=df_criados_semana,
                nome_usuario=AuthManager.current_username(),
            )
        fila.adicionar(_sec_criados_semana)

    # -------------------------------------------- Itens em aberto (WIP), base
    df_aberto = analytics.filtrar_itens_em_aberto(df_scrum, mapeamento)

    # ---------------------------------------- Mix de Tipos de Trabalho em Aberto
    if df_aberto is not None and not df_aberto.empty and mapeamento.tipo_teste:
        df_mix_tipos = analytics.distribuicao_tipo_teste(df_aberto, mapeamento)
        if df_mix_tipos is not None and not df_mix_tipos.empty:
            def _sec_mix_tipos() -> None:
                st.markdown("**Mix de Tipos de Trabalho em Aberto**")
                explicacao(
                    "Do que é feito o que está aberto AGORA (não o histórico inteiro do arquivo) — "
                    "ajuda a enxergar se o time está dominado por dívida técnica (muito Bug em "
                    "aberto) ou por trabalho novo (muita Story/Feature)."
                )
                col_tipo, _col_espaco = st.columns([1, 3])
                with col_tipo:
                    tipo_mix = selecionar_tipo_grafico(
                        "scrum_mix_tipos",
                        ["Treemap", "Barras", "Pizza", "Rosca", "Barras Horizontais", "Radar (Preenchido)"],
                    )
                plotar(
                    df_mix_tipos, tipo_mix, x="Tipo de Teste", y="Quantidade", chave="scrum_mix_tipos",
                    titulo="Mix de Tipos de Trabalho em Aberto",
                )
                renderizar_botao_analise_ia(
                    chave="scrum_mix_tipos",
                    titulo="Mix de Tipos de Trabalho em Aberto",
                    descricao=(
                        "Composição, por Tipo de Work Item, do que está aberto agora — ajuda a ver se o "
                        "time está dominado por dívida técnica (muito Bug) ou trabalho novo (muita "
                        "Story/Feature)."
                    ),
                    tipo_grafico=tipo_mix.lower(),
                    dados=df_mix_tipos,
                    nome_usuario=AuthManager.current_username(),
                )
            fila.adicionar(_sec_mix_tipos)

    # ---------------------------------------- WIP atual por Coluna do Board
    if df_aberto is not None and not df_aberto.empty and mapeamento.coluna_board and mapeamento.coluna_board in df_aberto.columns:
        df_aberto_com_board = analytics.excluir_nao_atribuido_coluna_board(df_aberto, mapeamento)
        df_wip_coluna = analytics.distribuicao_coluna_board(df_aberto_com_board, mapeamento)
        if df_wip_coluna is not None and not df_wip_coluna.empty:
            def _sec_wip_coluna() -> None:
                st.markdown("**WIP Atual por Coluna do Board**")
                explicacao(
                    "Onde estão, agora, os itens ainda não concluídos — na ordem real do fluxo "
                    "(Backlog → Finalizado). Uma coluna \"inchada\" no meio do fluxo é sinal de "
                    "gargalo: mais itens entrando do que saindo daquela etapa."
                )
                col_tipo, _col_espaco = st.columns([1, 3])
                with col_tipo:
                    tipo_wip = selecionar_tipo_grafico(
                        "scrum_wip_coluna", ["Barras", "Barras Horizontais", "Funil", "Pizza", "Rosca", "Treemap"]
                    )
                plotar(
                    df_wip_coluna, tipo_wip, x="Coluna do Board", y="Quantidade", chave="scrum_wip_coluna",
                    ordem_categorias={"Coluna do Board": analytics.ORDEM_COLUNAS_BOARD},
                    titulo="WIP Atual por Coluna do Board",
                )
                renderizar_botao_analise_ia(
                    chave="scrum_wip_coluna",
                    titulo="WIP Atual por Coluna do Board",
                    descricao="Onde estão, agora, os itens ainda não concluídos, na ordem real do fluxo (Backlog → Finalizado).",
                    tipo_grafico=tipo_wip.lower(),
                    dados=df_wip_coluna,
                    nome_usuario=AuthManager.current_username(),
                )
            fila.adicionar(_sec_wip_coluna)

    fila.flush()

    # ------------------------------ Onde o trabalho está parado (por coluna)
    if mapeamento.coluna_board and mapeamento.coluna_board in df_scrum.columns:
        df_backlog_coluna = analytics.backlog_aberto_por_grupo(
            df_scrum, mapeamento, mapeamento.coluna_board, "Coluna do Board"
        )
        if df_backlog_coluna is not None and not df_backlog_coluna.empty:
            st.markdown("**Onde o Trabalho Está Parado: Volume × Idade × Risco, por Coluna do Board**")
            explicacao(
                "Cada bolha é uma Coluna do Board. Eixo horizontal: há quanto tempo, em média, os "
                "itens abertos naquela coluna estão parados. Eixo vertical e tamanho da bolha: "
                "quantos itens em aberto a coluna tem. Cor: quanto mais vermelha, maior o percentual "
                "de itens Severidade Alta/Crítica ali — sem Severidade mapeada, todas ficam brancas "
                "(0%). O quadrante mais preocupante é bolha grande, mais à direita e mais vermelha ao "
                "mesmo tempo: muito item, parado há muito tempo, e muito crítico — geralmente aponta "
                "o gargalo real do fluxo.",
                expanded=True,
            )
            tipo_backlog_coluna = selecionar_tipo_grafico(
                "scrum_backlog_coluna", ["Bolha (Volume × Idade × Risco)", "Barras", "Barras Horizontais"]
            )
            if tipo_backlog_coluna == "Bolha (Volume × Idade × Risco)":
                fig_backlog_coluna = construir_grafico_bolha_backlog(df_backlog_coluna, "Coluna do Board")
            else:
                fig_backlog_coluna = construir_figura(
                    df_backlog_coluna, tipo_backlog_coluna, x="Coluna do Board", y="Quantidade"
                )
                st.caption(
                    "💡 Esta visualização mostra só o Volume por coluna — para ver também Idade "
                    "Média e % de Severidade Alta/Crítica ao mesmo tempo, escolha **Bolha (Volume × "
                    "Idade × Risco)** acima."
                )
            st.plotly_chart(fig_backlog_coluna, use_container_width=True, key="chart_scrum_backlog_coluna")
            renderizar_botao_analise_ia(
                chave="scrum_backlog_coluna",
                titulo="Onde o Trabalho Está Parado: Volume × Idade × Risco, por Coluna do Board",
                descricao=(
                    "Backlog aberto agrupado por Coluna do Board: volume de itens em aberto, idade "
                    "média parado e percentual de itens Severidade Alta/Crítica em cada coluna."
                ),
                tipo_grafico="bolha (volume x idade x risco)" if tipo_backlog_coluna == "Bolha (Volume × Idade × Risco)" else tipo_backlog_coluna.lower(),
                dados=df_backlog_coluna,
                nome_usuario=AuthManager.current_username(),
            )
            st.divider()

    # ---------------------------------------- Carga de Trabalho em Aberto por Responsável
    if df_aberto is not None and not df_aberto.empty and mapeamento.responsavel and mapeamento.responsavel in df_aberto.columns:
        df_carga_responsavel = analytics.volume_por_responsavel(df_aberto, mapeamento)
        if df_carga_responsavel is not None and not df_carga_responsavel.empty:
            # "Em aberto agora" é só um retrato do momento - poucos itens em
            # aberto pra alguém não quer dizer "trabalhou pouco" (pode ser o
            # oposto: concluiu bastante recentemente, por isso sobrou pouco
            # em aberto). Pra dar à IA uma base mais justa, calculamos também
            # quanto cada Responsável CONCLUIU nos últimos 30 dias (itens que
            # saíram do estado aberto - o complemento de `df_aberto` dentro
            # de `df_scrum`) e mandamos junto no contexto, além do retrato
            # atual isolado.
            df_concluidos_scrum = df_scrum.loc[~df_scrum.index.isin(df_aberto.index)]
            coluna_data_scrum = mapeamento.coluna_data_principal(df_scrum)
            df_concluidos_recente_resp = None
            if coluna_data_scrum and coluna_data_scrum in df_concluidos_scrum.columns:
                datas_concluidos = pd.to_datetime(df_concluidos_scrum[coluna_data_scrum], errors="coerce")
                limite_recente = pd.Timestamp(agora_brasilia().date()) - pd.Timedelta(days=30)
                df_concluidos_recente = df_concluidos_scrum.loc[datas_concluidos >= limite_recente]
                if not df_concluidos_recente.empty:
                    df_concluidos_recente_resp = analytics.volume_por_responsavel(df_concluidos_recente, mapeamento)

            def _sec_carga_responsavel() -> None:
                st.markdown("**Carga de Trabalho em Aberto por Responsável**")
                explicacao(
                    "Quantos itens cada pessoa tem em aberto AGORA (não o histórico) — ajuda a "
                    "enxergar sobrecarga concentrada antes que vire gargalo ou risco de burnout. "
                    "Poucos itens em aberto não é sinônimo de pouco trabalho: pode ser o oposto "
                    "(a pessoa concluiu bastante recentemente). A análise por IA deste gráfico "
                    "também recebe quanto cada um concluiu nos últimos 30 dias, pra não julgar só "
                    "pela foto do momento."
                )
                col_tipo, _col_espaco = st.columns([1, 3])
                with col_tipo:
                    tipo_carga = selecionar_tipo_grafico(
                        "scrum_carga_responsavel", ["Barras", "Barras Horizontais", "Treemap", "Pizza", "Rosca"]
                    )
                plotar(
                    df_carga_responsavel, tipo_carga, x="Responsável", y="Quantidade",
                    chave="scrum_carga_responsavel", titulo="Carga de Trabalho em Aberto por Responsável",
                )
                renderizar_botao_analise_ia(
                    chave="scrum_carga_responsavel",
                    titulo="Carga de Trabalho em Aberto por Responsável",
                    descricao=(
                        "Quantos itens cada pessoa tem em aberto agora - é um RETRATO DO MOMENTO, não "
                        "um histórico de esforço. Poucos itens em aberto para alguém pode significar "
                        "que a pessoa concluiu bastante recentemente (ver itens_concluidos_ultimos_30_dias_por_responsavel "
                        "no contexto), não que trabalhou pouco - cruze as duas informações antes de "
                        "comentar sobre qualquer pessoa."
                    ),
                    tipo_grafico=tipo_carga.lower(),
                    dados=df_carga_responsavel,
                    contexto_extra={
                        "itens_concluidos_ultimos_30_dias_por_responsavel": (
                            df_concluidos_recente_resp.to_dict(orient="records")
                            if df_concluidos_recente_resp is not None
                            else []
                        ),
                    },
                    nome_usuario=AuthManager.current_username(),
                )
            fila.adicionar(_sec_carga_responsavel)

    fila.flush()

    st.info(
        "💡 Esta página vai crescer conforme a Scrum Master trouxer indicadores mais específicos "
        "(ex.: metas de sprint, capacidade planejada vs. entregue). O que está aqui hoje usa só o "
        "que já dá pra calcular com segurança a partir do arquivo importado — ver o expansor "
        "\"Sobre os dados de Sprint\" acima pra entender os limites atuais."
    )
