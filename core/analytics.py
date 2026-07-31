"""
Cálculo dos indicadores de qualidade a partir do arquivo importado.

Cada função recebe o dataframe já com o mapeamento de colunas confirmado e
devolve estruturas prontas para plotagem (DataFrames agregados) ou valores
escalares para os cartões de KPI. Funções são tolerantes a colunas ausentes:
quando uma métrica não pode ser calculada por falta de dado no arquivo, ela
retorna `None`/DataFrame vazio, e a camada de UI decide como comunicar isso -
campos marcados como "— não mapeado —" nunca entram no cálculo dos gráficos.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from core.column_mapper import (
    MapeamentoColunas,
    eh_status_binario_reconhecivel,
    extrair_nome_de_email,
    normalizar_status,
    normalizar_texto,
    simplificar_valor_projeto,
)


@dataclass
class IndicadoresGerais:
    total_registros: int
    total_passou: int
    total_falhou: int
    total_planejado: int
    total_outros: int
    taxa_sucesso: Optional[float]  # percentual sobre executados (passou+falhou)


@dataclass
class IndicadoresBacklogAberto:
    total_abertos: int
    idade_media_dias: Optional[float]
    idade_mediana_dias: Optional[float]
    mais_90_dias: int
    mais_180_dias: int
    mais_365_dias: int


ROTULO_VAZIO_PADRAO = "Não atribuído(a)"

# Campos "de identidade" (usados para agrupar/colorir gráficos) cujos valores
# vazios ganham o rótulo amigável acima em vez de aparecer como célula em
# branco/NaN em tabelas e gráficos. Status fica de fora de propósito: já tem
# seu próprio rótulo estabelecido ("Não informado", aplicado em
# `distribuicao_status_bruto`).
_CAMPOS_ROTULAVEIS = ("projeto", "responsavel", "tipo_teste", "severidade", "coluna_board")

_VALORES_CONSIDERADOS_VAZIOS = {"", "nan", "none", "null", "nat", "<na>"}

# Ordem "oficial" das colunas do board Kanban, do início ao fim do fluxo de
# trabalho - informada pelo usuário, refletindo o board real usado no Azure
# DevOps. Serve para duas coisas:
#   1) Ordenar os gráficos de Coluna do Board na ordem real do fluxo
#      (Backlog -> Finalizado), em vez de por quantidade ou ordem
#      alfabética - só assim dá pra enxergar o funil/gargalo de verdade;
#   2) Juntar variações de acentuação/maiúsculas-minúsculas do mesmo nome de
#      coluna como uma coluna só (ex.: "Pronto para QA", "pronto para qa" e
#      "PRONTO PARA QA" contam juntas) - times diferentes podem ter digitado
#      o nome da coluna de formas ligeiramente diferentes ao configurar o
#      board no Azure DevOps.
#
# Importante: esta lista NUNCA descarta nem esconde uma coluna real que não
# esteja nela - times com colunas de board diferentes destas (nomes
# próprios, outro fluxo) continuam aparecendo nos gráficos exatamente como
# vieram do Azure DevOps, só ficam ordenados depois das colunas reconhecidas
# (ver `ordem_coluna_board`/`canonizar_coluna_board`).
ORDEM_COLUNAS_BOARD: list[str] = [
    "Backlog",
    "Em Refinamento de Negócios",
    "Pronto para Refinamento Técnico",
    "Em Refinamento Técnico",
    "Pronto para Validação de Produtos",
    "Em Validação de Produtos",
    "Pronto para Dev",
    "Em Desenvolvimento",
    "Pronto para Code Review",
    "Code Review",
    "Pronto para QA",
    "Teste QA",
    "Pronto para UAT",
    "Teste UAT",
    "Aguardando CAB",
    "Aguardando Subida em Produção",
    "Testes em Produção",
    "Cancelados",
    "Finalizado",
]

_ORDEM_COLUNAS_BOARD_POR_TEXTO_NORMALIZADO: dict[str, int] = {
    normalizar_texto(nome): indice for indice, nome in enumerate(ORDEM_COLUNAS_BOARD)
}


def canonizar_coluna_board(valor: object) -> object:
    """
    Casa um valor de Coluna do Board vindo do Azure DevOps com o nome
    "oficial" em `ORDEM_COLUNAS_BOARD`, ignorando acentuação e
    maiúsculas/minúsculas. Quando bate, devolve o nome oficial (com a
    grafia padronizada); quando não bate com nenhum nome conhecido, devolve
    o valor original sem nenhuma alteração - nunca inventa nem descarta uma
    coluna real do board só por ela não estar na lista.
    """
    if pd.isna(valor):
        return valor
    texto = str(valor).strip()
    if not texto:
        return valor
    indice = _ORDEM_COLUNAS_BOARD_POR_TEXTO_NORMALIZADO.get(normalizar_texto(texto))
    return ORDEM_COLUNAS_BOARD[indice] if indice is not None else texto


def ordem_coluna_board(valor: object) -> tuple[int, str]:
    """
    Chave de ordenação para a Coluna do Board: colunas reconhecidas em
    `ORDEM_COLUNAS_BOARD` vêm primeiro, na ordem real do fluxo; colunas
    desconhecidas (nomes próprios de outro time) vêm em seguida, em ordem
    alfabética; "Não atribuído(a)" (rótulo de célula vazia) sempre por
    último.
    """
    texto = str(valor)
    if texto == ROTULO_VAZIO_PADRAO:
        return (len(ORDEM_COLUNAS_BOARD) + 1, texto)
    indice = _ORDEM_COLUNAS_BOARD_POR_TEXTO_NORMALIZADO.get(normalizar_texto(texto))
    if indice is not None:
        return (indice, texto)
    return (len(ORDEM_COLUNAS_BOARD), texto)


def _rotular_valores_vazios(serie: pd.Series, rotulo: str = ROTULO_VAZIO_PADRAO) -> pd.Series:
    """
    Substitui nulos (e variações textuais de "vazio", ex.: célula em branco
    que alguma etapa anterior tenha convertido para a string "nan") por um
    rótulo amigável - assim tabelas e gráficos nunca mostram "NaN"/"nan" cru.
    """

    def _rotular(valor: object) -> object:
        if pd.isna(valor):
            return rotulo
        if isinstance(valor, str) and valor.strip().lower() in _VALORES_CONSIDERADOS_VAZIOS:
            return rotulo
        return valor

    return serie.apply(_rotular)


def preparar_dados(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> pd.DataFrame:
    """
    Aplica as limpezas necessárias antes de calcular qualquer indicador:
        - Extrai apenas o nome da coluna de responsável (remove "<email>");
        - Simplifica a coluna de projeto quando ela vem de uma hierarquia de
          Area Path ou de uma coluna com múltiplos valores (ex.: Tags usada
          como aproximação de projeto);
        - Casa a coluna do board com o nome "oficial" da etapa do fluxo
          (ex.: "pronto para qa" e "Pronto Para QA" viram "Pronto para QA"),
          ignorando acentuação e maiúsculas/minúsculas - ver
          `ORDEM_COLUNAS_BOARD`/`canonizar_coluna_board`;
        - Rotula valores vazios de Projeto/Responsável/Tipo de Teste/
          Severidade como "Não atribuído(a)" (em vez de célula em branco);
        - Converte colunas de data para o tipo data (sem hora);
        - Adiciona `__status_binario_reconhecido__` indicando se a coluna de
          status contém vocabulário Passou/Falhou/Planejado reconhecível;
        - Adiciona `__status_normalizado__` (só tem sentido quando o item
          acima é verdadeiro).
    """
    df = df.copy()

    if mapeamento.responsavel and mapeamento.responsavel in df.columns:
        df[mapeamento.responsavel] = df[mapeamento.responsavel].apply(extrair_nome_de_email)

    if mapeamento.projeto and mapeamento.projeto in df.columns:
        df[mapeamento.projeto] = df[mapeamento.projeto].apply(simplificar_valor_projeto)

    if mapeamento.coluna_board and mapeamento.coluna_board in df.columns:
        df[mapeamento.coluna_board] = df[mapeamento.coluna_board].apply(canonizar_coluna_board)

    for campo in _CAMPOS_ROTULAVEIS:
        coluna = getattr(mapeamento, campo)
        if coluna and coluna in df.columns:
            df[coluna] = _rotular_valores_vazios(df[coluna])

    for coluna_data in (mapeamento.data_planejada, mapeamento.data_execucao, mapeamento.data_criacao):
        if coluna_data and coluna_data in df.columns:
            df[coluna_data] = pd.to_datetime(df[coluna_data], errors="coerce", dayfirst=True).dt.date

    if mapeamento.status and mapeamento.status in df.columns:
        binario = eh_status_binario_reconhecivel(df, mapeamento.status)
        df["__status_binario_reconhecido__"] = binario
        df["__status_normalizado__"] = df[mapeamento.status].apply(normalizar_status) if binario else "Outro"
        df["__status_bruto__"] = df[mapeamento.status]
    else:
        df["__status_binario_reconhecido__"] = False
        df["__status_normalizado__"] = "Não informado"
        df["__status_bruto__"] = "Não informado"

    return df


def status_e_binario(df: pd.DataFrame) -> bool:
    return bool(df["__status_binario_reconhecido__"].iloc[0]) if len(df) else False


def calcular_indicadores_gerais(df: pd.DataFrame) -> IndicadoresGerais:
    contagem = df["__status_normalizado__"].value_counts()
    total_passou = int(contagem.get("Passou", 0))
    total_falhou = int(contagem.get("Falhou", 0))
    total_planejado = int(contagem.get("Planejado", 0))
    total_outros = int(len(df) - total_passou - total_falhou - total_planejado)

    executados = total_passou + total_falhou
    taxa_sucesso = round((total_passou / executados) * 100, 1) if executados > 0 else None

    return IndicadoresGerais(
        total_registros=len(df),
        total_passou=total_passou,
        total_falhou=total_falhou,
        total_planejado=total_planejado,
        total_outros=total_outros,
        taxa_sucesso=taxa_sucesso,
    )


def distribuicao_status_bruto(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    """Distribuição real dos valores de status, sem tentar classificar Passou/Falhou."""
    if not mapeamento.status or mapeamento.status not in df.columns:
        return None
    resultado = (
        df[mapeamento.status]
        .fillna("Não informado")
        .value_counts()
        .reset_index()
    )
    resultado.columns = ["Status", "Quantidade"]
    return resultado.sort_values("Quantidade", ascending=False)


def planejamento_vs_efetivado(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> Optional[pd.DataFrame]:
    """
    Compara Planejado vs Efetivamente Executado.

    Estratégia (em ordem de prioridade conforme dados disponíveis):
        1) Se o status é binário reconhecível e existe a categoria
           "Planejado" -> compara contagem de planejados vs (passou+falhou);
        2) Senão, se existem datas de planejamento e de execução/criação
           mapeadas -> compara quantos registros têm cada data preenchida.
        3) Caso nada disso exista, retorna None (indicador fica oculto).
    """
    if status_e_binario(df) and (df["__status_normalizado__"] == "Planejado").any():
        planejado = int((df["__status_normalizado__"] == "Planejado").sum())
        efetivado = int(df["__status_normalizado__"].isin(["Passou", "Falhou"]).sum())
        return pd.DataFrame(
            {"Categoria": ["Planejado", "Efetivamente Testado"], "Quantidade": [planejado, efetivado]}
        )

    coluna_execucao_ou_criacao = mapeamento.data_execucao or mapeamento.data_criacao
    tem_data_planejada = mapeamento.data_planejada and mapeamento.data_planejada in df.columns
    tem_data_execucao = coluna_execucao_ou_criacao and coluna_execucao_ou_criacao in df.columns

    if tem_data_planejada and tem_data_execucao:
        planejado = int(df[mapeamento.data_planejada].notna().sum())
        efetivado = int(df[coluna_execucao_ou_criacao].notna().sum())
        return pd.DataFrame(
            {"Categoria": ["Planejado", "Efetivamente Testado"], "Quantidade": [planejado, efetivado]}
        )

    return None


def testes_por_projeto(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    if not mapeamento.projeto or mapeamento.projeto not in df.columns:
        return None
    resultado = (
        df.groupby(mapeamento.projeto, dropna=False)
        .size()
        .reset_index(name="Quantidade de Testes")
        .rename(columns={mapeamento.projeto: "Projeto"})
        .sort_values("Quantidade de Testes", ascending=False)
    )
    return resultado


def taxa_sucesso_por_projeto(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    if not mapeamento.projeto or mapeamento.projeto not in df.columns or not status_e_binario(df):
        return None
    agrupado = df.groupby(mapeamento.projeto, dropna=False)["__status_normalizado__"]
    linhas = []
    for projeto, valores in agrupado:
        passou = (valores == "Passou").sum()
        falhou = (valores == "Falhou").sum()
        executados = passou + falhou
        taxa = round((passou / executados) * 100, 1) if executados > 0 else None
        linhas.append({"Projeto": projeto, "Passou": passou, "Falhou": falhou, "Taxa de Sucesso (%)": taxa})
    resultado = pd.DataFrame(linhas).sort_values("Taxa de Sucesso (%)", ascending=False, na_position="last")
    return resultado


def ranking_bugs_por_projeto(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    if not mapeamento.projeto or mapeamento.projeto not in df.columns:
        return None

    if mapeamento.tipo_teste and mapeamento.tipo_teste in df.columns:
        subset = df[df[mapeamento.tipo_teste].astype(str).str.contains("bug", case=False, na=False)]
    elif status_e_binario(df):
        subset = df[df["__status_normalizado__"] == "Falhou"]
    else:
        return None

    if subset.empty:
        return pd.DataFrame(columns=["Projeto", "Quantidade de Bugs"])

    resultado = (
        subset.groupby(mapeamento.projeto, dropna=False)
        .size()
        .reset_index(name="Quantidade de Bugs")
        .rename(columns={mapeamento.projeto: "Projeto"})
        .sort_values("Quantidade de Bugs", ascending=False)
    )
    return resultado


def distribuicao_tipo_teste(
    df: pd.DataFrame,
    mapeamento: MapeamentoColunas,
    tipos_excluidos: Optional[set[str]] = None,
) -> Optional[pd.DataFrame]:
    """
    Distribuição de registros por Tipo de Teste (ex.: Bug, Test Case, Test Plan...).

    `tipos_excluidos` tira da conta valores que não representam um item de
    teste individual de fato - ex.: no Azure DevOps, "Test Plan" e "Test
    Suite" são contêineres organizacionais que podem agrupar dezenas de Test
    Cases cada um, então contar "1 Test Plan" ao lado de "1 Test Case" nessa
    distribuição não é uma comparação de volume válida. A comparação é feita
    de forma normalizada (case/acento-insensível), então "Test Plan" também
    bate com "test plan" ou "TEST PLAN".
    """
    if not mapeamento.tipo_teste or mapeamento.tipo_teste not in df.columns:
        return None

    dados = df
    if tipos_excluidos:
        normalizados_excluidos = {_normalizar_texto_simples(valor) for valor in tipos_excluidos}
        dados = dados[
            ~dados[mapeamento.tipo_teste].apply(lambda v: _normalizar_texto_simples(v) in normalizados_excluidos)
        ]

    if dados.empty:
        return pd.DataFrame(columns=["Tipo de Teste", "Quantidade"])

    resultado = (
        dados.groupby(mapeamento.tipo_teste, dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={mapeamento.tipo_teste: "Tipo de Teste"})
        .sort_values("Quantidade", ascending=False)
    )
    return resultado


def tendencia_temporal(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    coluna_data = mapeamento.coluna_data_principal()
    if not coluna_data or coluna_data not in df.columns:
        return None

    datas = pd.to_datetime(df[coluna_data], errors="coerce")
    if datas.notna().sum() == 0:
        return None

    temp = df.copy()
    temp["__data__"] = datas
    temp = temp.dropna(subset=["__data__"])
    temp["__semana__"] = temp["__data__"].dt.to_period("W").dt.start_time

    coluna_agrupamento = "__status_bruto__" if mapeamento.status else None
    if coluna_agrupamento:
        resultado = (
            temp.groupby(["__semana__", coluna_agrupamento])
            .size()
            .reset_index(name="Quantidade")
            .rename(columns={"__semana__": "Semana", coluna_agrupamento: "Status"})
        )
    else:
        resultado = (
            temp.groupby(["__semana__"])
            .size()
            .reset_index(name="Quantidade")
            .rename(columns={"__semana__": "Semana"})
        )
    return resultado


def ranking_responsaveis(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    if not mapeamento.responsavel or mapeamento.responsavel not in df.columns:
        return None
    resultado = (
        df.groupby(mapeamento.responsavel, dropna=False)
        .size()
        .reset_index(name="Testes Executados")
        .rename(columns={mapeamento.responsavel: "Responsável"})
        .sort_values("Testes Executados", ascending=False)
    )
    return resultado


def distribuicao_severidade(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    if not mapeamento.severidade or mapeamento.severidade not in df.columns:
        return None
    resultado = (
        df.groupby(mapeamento.severidade, dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={mapeamento.severidade: "Severidade"})
        .sort_values("Quantidade", ascending=False)
    )
    return resultado


def distribuicao_coluna_board(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    """
    Distribuição de registros pela Coluna do Board (Kanban) - ex.: Backlog,
    Pronto para Dev, Pronto para QA, Pronto para UAT, Finalizado...

    Nem todo tipo de work item do Azure DevOps aparece num board Kanban - por
    exemplo, Test Case vive dentro de Test Plans/Test Suites, não no board,
    então nunca tem uma coluna própria (isso é assim na origem dos dados, não
    uma limitação deste app). Quando a busca é feita pela integração
    automática com o Azure DevOps, esses itens já chegam aqui com a coluna do
    item "pai" vinculado herdada (ver `core/azure_devops_client.py`,
    `_completar_board_column_via_item_pai`), quando esse vínculo existir. Só
    os que continuam sem nenhuma coluna (nem própria, nem herdada) ficam
    rotulados como "Não atribuído(a)" (ver `preparar_dados`/`_CAMPOS_ROTULAVEIS`)
    e aparecem na distribuição como uma categoria própria, em vez de sumir
    silenciosamente - assim fica claro que parte dos itens não tem coluna de
    board associada, em vez de parecer que a contagem está errada.

    A ordenação segue o fluxo real do board (Backlog -> Finalizado, ver
    `ORDEM_COLUNAS_BOARD`) em vez de quantidade ou ordem alfabética - assim
    dá pra enxergar onde está o gargalo. Colunas com nome próprio (fora
    dessa lista) aparecem depois das reconhecidas, e "Não atribuído(a)"
    sempre por último. A junção de variações de acentuação/maiúsculas já
    aconteceu em `preparar_dados` (ver `canonizar_coluna_board`), então aqui
    é só agrupar e ordenar.
    """
    if not mapeamento.coluna_board or mapeamento.coluna_board not in df.columns:
        return None
    resultado = (
        df.groupby(mapeamento.coluna_board, dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={mapeamento.coluna_board: "Coluna do Board"})
    )
    resultado["__ordem__"] = resultado["Coluna do Board"].apply(ordem_coluna_board)
    resultado = resultado.sort_values("__ordem__").drop(columns="__ordem__").reset_index(drop=True)
    return resultado


def detalhamento_nao_atribuido_coluna_board(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> Optional[pd.DataFrame]:
    """
    Quebra os itens rotulados como "Não atribuído(a)" em `distribuicao_coluna_board`
    por Tipo de Teste/Work Item Type, para ajudar a diagnosticar POR QUE tantos
    itens caíram nessa categoria - existem 3 motivos possíveis, e só olhando os
    dados reais dá pra saber qual é:

        1) O tipo de work item nunca aparece em nenhum board Kanban no próprio
           Azure DevOps (ex.: Test Case, que vive em Test Plans/Test Suites) E
           não tem um item "pai" vinculado (Parent) para herdar a coluna dele -
           nesse caso "Não atribuído(a)" é o resultado correto/esperado, não é
           um bug.
        2) O item tem um pai vinculado, mas esse pai também não está em
           nenhuma coluna (ex.: pai é um Epic/Feature que também não está no
           board, ou o próprio pai também é um tipo fora do board).
        3) O item É de um tipo que normalmente aparece no board (ex.: Bug,
           User Story) mas mesmo assim veio sem Coluna do Board da própria
           API do Azure DevOps - isso acontece quando o Area Path do item não
           está associado a nenhum Time (Team), ou quando o Time responsável
           não tem uma coluna mapeada para o State atual do item nas
           configurações do board dele. É uma característica dos dados/da
           configuração do board no Azure DevOps, não algo que este app
           calcula ou poderia inferir sozinho.

    Se a maioria dos itens "Não atribuído(a)" for de um tipo que claramente
    não vive em board (Test Case, Shared Steps, etc.), é o motivo 1/2 - normal.
    Se aparecerem tipos como Bug/User Story/Task em quantidade relevante, vale
    conferir a configuração do board daquele Time no Azure DevOps (motivo 3).
    """
    if not mapeamento.coluna_board or mapeamento.coluna_board not in df.columns:
        return None
    nao_atribuidos = df[df[mapeamento.coluna_board] == ROTULO_VAZIO_PADRAO]
    if nao_atribuidos.empty:
        return None
    if not mapeamento.tipo_teste or mapeamento.tipo_teste not in df.columns:
        return None
    resultado = (
        nao_atribuidos.groupby(mapeamento.tipo_teste, dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={mapeamento.tipo_teste: "Tipo"})
        .sort_values("Quantidade", ascending=False)
        .reset_index(drop=True)
    )
    return resultado


def excluir_nao_atribuido_coluna_board_por_tipo(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, tipos_incluidos: set
) -> pd.DataFrame:
    """
    Devolve uma cópia de `df` sem as linhas "Não atribuído(a)" de Coluna do
    Board cujo Tipo de Teste/Work Item Type NÃO esteja em `tipos_incluidos` -
    usado pra deixar o usuário reincluir, tipo a tipo, itens sem coluna de
    board nos gráficos de Coluna do Board (por padrão todos ficam de fora,
    já que a intenção é enxergar o fluxo real do board sem o "ruído" de
    itens que nunca estiveram nele - ver
    `detalhamento_nao_atribuido_coluna_board`, que gera a lista de tipos
    disponível pra essa reinclusão).

    Nunca afeta: linhas com uma Coluna do Board de verdade (só mexe nas
    rotuladas "Não atribuído(a)"); nem o restante do dashboard - é usado só
    na hora de montar os gráficos de Coluna do Board, o resto dos
    indicadores continua vendo todos os itens normalmente. Se Coluna do
    Board ou Tipo de Teste não estiverem mapeados, devolve `df` sem
    alteração (não tem como filtrar sem esses dois campos).
    """
    if not mapeamento.coluna_board or mapeamento.coluna_board not in df.columns:
        return df
    if not mapeamento.tipo_teste or mapeamento.tipo_teste not in df.columns:
        return df
    eh_nao_atribuido = df[mapeamento.coluna_board] == ROTULO_VAZIO_PADRAO
    tipo_nao_incluido = ~df[mapeamento.tipo_teste].isin(tipos_incluidos)
    return df[~(eh_nao_atribuido & tipo_nao_incluido)]


def distribuicao_area_path_x_coluna_board(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> Optional[pd.DataFrame]:
    """
    Cruza Projeto/Area Path com Coluna do Board (Kanban): quantos work items
    de cada Area Path estão parados em cada coluna - de Backlog a Finalizado.

    Diferente de `distribuicao_coluna_board` (que só soma o total por coluna,
    sem discriminar de onde vêm), esta função devolve uma linha por
    combinação (Projeto, Coluna do Board) - é o que permite montar um
    gráfico de barras empilhadas/agrupadas (ou treemap hierárquico) que
    mostra, por exemplo, "BACKOFFICE tem 12 itens parados em Pronto para QA,
    e só 2 em Backlog", em vez de só o total geral de "Pronto para QA".

    Depende dos dois campos estarem mapeados (Projeto e Coluna do Board) -
    sem um dos dois, não tem como cruzar, e a função devolve `None`.

    Dentro de cada Projeto, as colunas ficam na ordem real do fluxo do board
    (Backlog -> Finalizado, ver `ORDEM_COLUNAS_BOARD`) em vez de por
    quantidade - mesmo critério de `distribuicao_coluna_board`.
    """
    if not mapeamento.projeto or mapeamento.projeto not in df.columns:
        return None
    if not mapeamento.coluna_board or mapeamento.coluna_board not in df.columns:
        return None
    resultado = (
        df.groupby([mapeamento.projeto, mapeamento.coluna_board], dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={mapeamento.projeto: "Projeto", mapeamento.coluna_board: "Coluna do Board"})
    )
    resultado["__ordem__"] = resultado["Coluna do Board"].apply(ordem_coluna_board)
    resultado = (
        resultado.sort_values(["Projeto", "__ordem__"])
        .drop(columns="__ordem__")
        .reset_index(drop=True)
    )
    return resultado


def distribuicao_area_path_x_status(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> Optional[pd.DataFrame]:
    """
    Cruza Projeto/Area Path com Status: quantos work items de cada Area Path
    estão em cada valor de status - ex.: "BACKOFFICE tem 8 em New e 3 em
    Closed, enquanto Bug Team tem 5 em UAT e 2 em Deploy".

    Existe porque times diferentes dentro da mesma organização do Azure
    DevOps podem usar templates de processo (Basic/Agile/Scrum/CMMI ou
    customizados) com vocabulários de State completamente diferentes entre
    si - não é incomum um time usar só New/Active/Closed enquanto outro usa
    estados próprios como "UAT", "QA" ou "Deploy" dentro do campo
    System.State (Status), o que é uma configuração legítima do Azure
    DevOps e não tem nenhuma relação com a Coluna do Board (outro campo,
    `System.BoardColumn`, buscado e mapeado separadamente - ver
    `distribuicao_coluna_board`). Quando vários Area Paths com processos
    diferentes são selecionados juntos, a distribuição geral de Status
    (`distribuicao_status_bruto`) mistura naturalmente esses vocabulários
    num único gráfico; esta função permite discriminar visualmente qual
    Area Path contribui com qual valor, deixando claro que não é uma mistura
    indevida de campos.

    Depende dos dois campos estarem mapeados (Projeto e Status) - sem um dos
    dois, não tem como cruzar, e a função devolve `None`.
    """
    if not mapeamento.projeto or mapeamento.projeto not in df.columns:
        return None
    if not mapeamento.status or mapeamento.status not in df.columns:
        return None
    resultado = (
        df.groupby([mapeamento.projeto, mapeamento.status], dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={mapeamento.projeto: "Projeto", mapeamento.status: "Status"})
        .sort_values(["Projeto", "Quantidade"], ascending=[True, False])
    )
    return resultado


def filtrar_por_intervalo_datas(
    df: pd.DataFrame, coluna_data: Optional[str], data_inicio, data_fim
) -> pd.DataFrame:
    """Filtra o dataframe pelo intervalo [data_inicio, data_fim] na coluna de data informada."""
    if not coluna_data or coluna_data not in df.columns or data_inicio is None or data_fim is None:
        return df
    datas = pd.to_datetime(df[coluna_data], errors="coerce").dt.date
    mascara = datas.between(data_inicio, data_fim)
    return df[mascara.fillna(False)]


def construir_grafico_personalizado(
    df: pd.DataFrame,
    coluna_x: str,
    coluna_metrica: Optional[str],
    modo_metrica: str,
    coluna_grupo: Optional[str] = None,
) -> pd.DataFrame:
    """
    Monta os dados para o construtor de gráfico personalizado.

    modo_metrica:
        "contagem" -> conta ocorrências de cada valor de `coluna_x`;
        "soma"     -> soma os valores numéricos de `coluna_metrica` agrupados por `coluna_x`.

    coluna_grupo (opcional):
        Uma segunda dimensão de agrupamento (vira a cor/série/empilhamento do
        gráfico), para comparações do tipo "Projeto x Status" em um único
        gráfico. Precisa ser diferente de `coluna_x` e de `coluna_metrica` -
        essa validação é feita antes, na interface (ver
        `ui.pages.dashboard_page._renderizar_construtor_grafico_personalizado`),
        para impedir escolher a mesma coluna em mais de uma dimensão.
    """
    colunas_agrupamento = [coluna_x] if not coluna_grupo else [coluna_x, coluna_grupo]

    if modo_metrica == "soma" and coluna_metrica:
        resultado = (
            df.groupby(colunas_agrupamento, dropna=False)[coluna_metrica]
            .sum(numeric_only=True)
            .reset_index()
            .rename(columns={coluna_metrica: "Valor"})
        )
    else:
        resultado = df.groupby(colunas_agrupamento, dropna=False).size().reset_index(name="Valor")

    renomeio = {coluna_x: "Categoria"}
    if coluna_grupo:
        renomeio[coluna_grupo] = "Grupo"
    resultado = resultado.rename(columns=renomeio)
    return resultado.sort_values("Valor", ascending=False)


# ---------------------------------------------------------------------------
# Backlog aberto: há quanto tempo os itens que ainda não chegaram a um estado
# terminal (Finalizado/Closed/Done/...) estão parados. Pensado especialmente
# para exports de ferramentas de fluxo de trabalho (ex.: Azure DevOps), onde
# o status não é um Passou/Falhou tradicional e "Taxa de Sucesso" não se
# aplica - mas "há quanto tempo o backlog está parado" é um indicador tão ou
# mais relevante da saúde do processo de QA.
# ---------------------------------------------------------------------------

_PALAVRAS_ESTADO_TERMINAL = {
    "finalizado",
    "finalizada",
    "concluido",
    "concluida",
    "closed",
    "fechado",
    "fechada",
    "done",
    "completo",
    "completa",
    "resolvido",
    "resolvida",
    "resolved",
    "cancelado",
    "cancelada",
    "cancelled",
    "canceled",
    "rejeitado",
    "rejeitada",
    "rejected",
    "aprovado",
    "aprovada",
    "approved",
    "removido",
    "removida",
}


def _normalizar_texto_simples(valor: object) -> str:
    texto = str(valor).strip().lower()
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def _estado_e_terminal(valor: object) -> bool:
    texto = _normalizar_texto_simples(valor)
    return any(palavra in texto for palavra in _PALAVRAS_ESTADO_TERMINAL)


def _mascara_itens_em_aberto(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.Series]:
    """
    True para as linhas cujo status ainda não chegou a um estado terminal.

    - Status binário reconhecível (Passou/Falhou/Planejado): "aberto" é tudo
      que ainda não é Passou nem Falhou (ou seja, Planejado/Outro).
    - Status como fluxo de trabalho livre (ex.: New/Ready/Design/Finalizado/
      Closed do Azure DevOps): "aberto" é tudo cujo valor bruto não contém
      vocabulário reconhecido de estado terminal.
    """
    if not mapeamento.status or mapeamento.status not in df.columns:
        return None

    if status_e_binario(df):
        return ~df["__status_normalizado__"].isin(["Passou", "Falhou"])

    status_bruto = df["__status_bruto__"] if "__status_bruto__" in df.columns else df[mapeamento.status]
    return ~status_bruto.apply(_estado_e_terminal)


def calcular_backlog_aberto(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> Optional[IndicadoresBacklogAberto]:
    """Estatísticas de idade (em dias, a partir da coluna de data principal) dos itens ainda em aberto."""
    coluna_data = mapeamento.coluna_data_principal()
    if not coluna_data or coluna_data not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    datas = pd.to_datetime(df[coluna_data], errors="coerce")
    indices_abertos = df.index[mascara_aberto & datas.notna()]

    if len(indices_abertos) == 0:
        return IndicadoresBacklogAberto(0, None, None, 0, 0, 0)

    hoje = pd.Timestamp(datetime.now().date())
    idade_dias = (hoje - datas.loc[indices_abertos]).dt.days

    return IndicadoresBacklogAberto(
        total_abertos=int(len(indices_abertos)),
        idade_media_dias=round(float(idade_dias.mean()), 1),
        idade_mediana_dias=float(idade_dias.median()),
        mais_90_dias=int((idade_dias > 90).sum()),
        mais_180_dias=int((idade_dias > 180).sum()),
        mais_365_dias=int((idade_dias > 365).sum()),
    )


def ranking_itens_mais_antigos_abertos(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, top_n: int = 15
) -> Optional[pd.DataFrame]:
    """Tabela com os itens em aberto há mais tempo, do mais antigo para o mais recente."""
    coluna_data = mapeamento.coluna_data_principal()
    if not coluna_data or coluna_data not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    datas = pd.to_datetime(df[coluna_data], errors="coerce")
    trabalho = df.loc[mascara_aberto & datas.notna()].copy()
    if trabalho.empty:
        return pd.DataFrame(columns=["Status", "Responsável", "Idade (dias)"])

    hoje = pd.Timestamp(datetime.now().date())
    trabalho["Idade (dias)"] = (hoje - datas.loc[trabalho.index]).dt.days
    trabalho["Status"] = (
        trabalho["__status_bruto__"] if "__status_bruto__" in trabalho.columns else trabalho[mapeamento.status]
    )
    trabalho["Responsável"] = (
        trabalho[mapeamento.responsavel]
        if mapeamento.responsavel and mapeamento.responsavel in trabalho.columns
        else "—"
    )

    colunas_saida = ["Status", "Responsável", "Idade (dias)"]
    if mapeamento.projeto and mapeamento.projeto in trabalho.columns:
        trabalho["Projeto"] = trabalho[mapeamento.projeto]
        colunas_saida = ["Projeto"] + colunas_saida

    return (
        trabalho[colunas_saida]
        .sort_values("Idade (dias)", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


def bugs_abertos_vs_solucionados(
    df: pd.DataFrame,
    mapeamento: MapeamentoColunas,
    colunas_aguardando_externo: Optional[set[str]] = None,
) -> Optional[pd.DataFrame]:
    """
    Evolução acumulada de bugs por semana de criação, em duas ou três
    categorias:

        - "Em Andamento (QA)": ainda não chegou a um estado terminal (ver
          `_estado_e_terminal`) e não está parado numa coluna do board
          marcada como fora do controle da QA.
        - "Aguardando Validação Externa": ainda não chegou a um estado
          terminal, mas está parado numa coluna do board escolhida como fora
          do controle da QA - ex.: a QA já corrigiu e o item está em "Pronto
          para UAT"/"Aguardando Homologação", esperando o time de Produto/
          Negócio/UX validar, o que foge do escopo e do prazo da QA. Só
          existe quando `mapeamento.coluna_board` está mapeado E
          `colunas_aguardando_externo` não é vazio - caso contrário, esse
          tempo de espera fica misturado em "Em Andamento (QA)" como antes.
        - "Finalizado": já chegou a um estado terminal.

    Importante sobre a leitura deste gráfico: a maioria dos exports (ex.:
    Azure DevOps) não traz uma data de resolução/fechamento nem um histórico
    de mudança de coluna do board - só a data de criação. Por isso, cada
    categoria reflete a situação ATUAL de cada bug (estado/coluna de hoje),
    não o histórico exato de cada data passada. Ou seja: mostra "dos bugs
    criados até a semana X, quantos estão em cada situação hoje" - uma visão
    por coorte de criação, não um retrato histórico dia a dia.

    Requer tipo_teste mapeado (pra isolar os itens de bug) e status mapeado
    (pra saber o que é terminal); sem os dois, retorna None.
    """
    coluna_data = mapeamento.coluna_data_principal()
    if not coluna_data or coluna_data not in df.columns:
        return None
    if not mapeamento.tipo_teste or mapeamento.tipo_teste not in df.columns:
        return None

    bugs = df[df[mapeamento.tipo_teste].astype(str).str.contains("bug", case=False, na=False)].copy()
    if bugs.empty:
        return None

    mascara_aberto = _mascara_itens_em_aberto(bugs, mapeamento)
    if mascara_aberto is None:
        return None

    datas = pd.to_datetime(bugs[coluna_data], errors="coerce")
    bugs = bugs.loc[datas.notna()].copy()
    if bugs.empty:
        return None
    mascara_aberto = mascara_aberto.loc[bugs.index]

    usa_coluna_board = bool(
        colunas_aguardando_externo
        and mapeamento.coluna_board
        and mapeamento.coluna_board in bugs.columns
    )
    if usa_coluna_board:
        valores_board = bugs[mapeamento.coluna_board].astype(str)
        mascara_aguardando_externo = mascara_aberto & valores_board.isin(colunas_aguardando_externo)
    else:
        mascara_aguardando_externo = pd.Series(False, index=bugs.index)

    categoria = pd.Series("Finalizado", index=bugs.index)
    categoria.loc[mascara_aberto & ~mascara_aguardando_externo] = "Em Andamento (QA)"
    categoria.loc[mascara_aguardando_externo] = "Aguardando Validação Externa"

    bugs["__data__"] = datas.loc[bugs.index]
    bugs["__semana__"] = bugs["__data__"].dt.to_period("W").dt.start_time
    bugs["__categoria__"] = categoria

    colunas_categoria = ["Em Andamento (QA)", "Finalizado"]
    if usa_coluna_board:
        colunas_categoria.insert(1, "Aguardando Validação Externa")

    por_semana = (
        bugs.groupby("__semana__")["__categoria__"]
        .value_counts()
        .unstack(fill_value=0)
        .reindex(columns=colunas_categoria, fill_value=0)
        .sort_index()
    )
    acumulado = por_semana.cumsum()
    acumulado["Bugs Criados (acumulado)"] = acumulado[colunas_categoria].sum(axis=1)

    resultado = acumulado.reset_index().rename(columns={"__semana__": "Semana"})
    return resultado[["Semana", "Bugs Criados (acumulado)", *colunas_categoria]]


# ---------------------------------------------------------------------------
# Scorecard de Qualidade: dados para o radar preenchido que compara várias
# dimensões de qualidade AO MESMO TEMPO - uma forma colorida por entidade
# escolhida pelo usuário (Projeto, Responsável, Tipo de Teste, ou qualquer
# outra coluna), cada eixo com uma nota de 0 a 10. Diferente do construtor de
# gráfico personalizado (uma métrica só, espalhada por categorias), aqui cada
# eixo é uma métrica DIFERENTE - por isso cada uma passa por uma normalização
# própria antes de entrar no mesmo gráfico (senão "quantidade de testes" e
# "taxa de sucesso em %" não seriam comparáveis na mesma escala radial).
# ---------------------------------------------------------------------------

CRITERIOS_SCORECARD: dict[str, str] = {
    "taxa_sucesso": "Taxa de Sucesso",
    "cobertura": "Cobertura / Volume",
    "taxa_bugs_invertida": "Taxa de Bugs (invertida)",
    "aderencia_planejado": "Aderência ao Planejado",
    "severidade_critica_invertida": "Severidade Crítica (invertida)",
    "agilidade_backlog_invertida": "Agilidade do Backlog (invertida)",
}

_PALAVRAS_SEVERIDADE_CRITICA = {
    "critico",
    "critica",
    "critical",
    "alto",
    "alta",
    "high",
    "urgente",
    "urgent",
    "blocker",
    "bloqueador",
    "bloqueadora",
}


def _eh_severidade_critica(valor: object) -> bool:
    texto = _normalizar_texto_simples(valor)
    return any(palavra in texto for palavra in _PALAVRAS_SEVERIDADE_CRITICA)


def calcular_scorecard_qualidade(
    df: pd.DataFrame,
    mapeamento: MapeamentoColunas,
    coluna_entidade: str,
    criterios: list[str],
    colunas_aguardando_externo: Optional[set[str]] = None,
    limite_entidades: int = 8,
) -> tuple[Optional[pd.DataFrame], list[str], bool]:
    """
    Monta os dados do "Scorecard de Qualidade": um radar preenchido em que
    cada forma colorida é uma entidade (valor distinto de `coluna_entidade`,
    ex.: um Projeto) e cada eixo é uma nota de 0 a 10 num critério de
    `criterios` (chaves de `CRITERIOS_SCORECARD`).

    Cada critério só entra no resultado se os dados atuais permitirem
    calculá-lo (ex.: "Taxa de Sucesso" exige status binário reconhecível;
    "Aderência ao Planejado" exige datas de planejamento/execução ou a
    categoria "Planejado" no status). Critérios pedidos mas não calculáveis
    voltam em `criterios_indisponiveis`, para a interface avisar o motivo em
    vez de simplesmente omiti-los sem explicação.

    "Agilidade do Backlog" usa a mesma definição de "item em aberto" do
    indicador de Backlog Aberto, e - quando `colunas_aguardando_externo` é
    informado - desconta itens parados numa coluna do board marcada como
    fora do controle da QA (mesma lógica de `bugs_abertos_vs_solucionados`),
    para não penalizar a QA por uma espera que não é dela.

    Entidades sem executados/planejados/etc. suficientes para calcular um
    critério recebem nota 0 nesse eixo (em vez de um buraco no polígono) -
    é uma escolha deliberada para manter o radar sempre fechado e legível;
    a interface deve avisar essa convenção ao usuário.

    Se `coluna_entidade` tiver mais de `limite_entidades` valores distintos,
    mantém só os `limite_entidades` com mais registros (senão o radar fica
    ilegível, com cores repetidas na paleta) - o terceiro item do retorno
    indica se esse corte aconteceu.

    Retorna (dados_longos, criterios_indisponiveis, entidades_truncadas):
        dados_longos tem colunas ["Entidade", "Critério", "Nota"], ou é None
        se a coluna de entidade não existe ou nenhum critério pôde ser
        calculado.
    """
    if not coluna_entidade or coluna_entidade not in df.columns or df.empty:
        return None, [], False

    disponiveis: list[str] = []
    indisponiveis: list[str] = []

    if "taxa_sucesso" in criterios:
        if status_e_binario(df):
            disponiveis.append("taxa_sucesso")
        else:
            indisponiveis.append(CRITERIOS_SCORECARD["taxa_sucesso"])

    if "cobertura" in criterios:
        disponiveis.append("cobertura")  # sempre calculável: é só contagem de registros

    tem_tipo_teste = bool(mapeamento.tipo_teste and mapeamento.tipo_teste in df.columns)
    if "taxa_bugs_invertida" in criterios:
        if tem_tipo_teste:
            disponiveis.append("taxa_bugs_invertida")
        else:
            indisponiveis.append(CRITERIOS_SCORECARD["taxa_bugs_invertida"])

    aderencia_modo: Optional[str] = None
    if "aderencia_planejado" in criterios:
        if status_e_binario(df) and (df["__status_normalizado__"] == "Planejado").any():
            aderencia_modo = "status"
        else:
            coluna_execucao_ou_criacao = mapeamento.data_execucao or mapeamento.data_criacao
            if (
                mapeamento.data_planejada
                and mapeamento.data_planejada in df.columns
                and coluna_execucao_ou_criacao
                and coluna_execucao_ou_criacao in df.columns
            ):
                aderencia_modo = "datas"
        if aderencia_modo:
            disponiveis.append("aderencia_planejado")
        else:
            indisponiveis.append(CRITERIOS_SCORECARD["aderencia_planejado"])

    tem_severidade = bool(mapeamento.severidade and mapeamento.severidade in df.columns)
    if "severidade_critica_invertida" in criterios:
        if tem_severidade:
            disponiveis.append("severidade_critica_invertida")
        else:
            indisponiveis.append(CRITERIOS_SCORECARD["severidade_critica_invertida"])

    coluna_data_principal = mapeamento.coluna_data_principal()
    tem_backlog = bool(
        mapeamento.status
        and mapeamento.status in df.columns
        and coluna_data_principal
        and coluna_data_principal in df.columns
    )
    mascara_aberto_backlog = None
    datas_backlog = None
    if "agilidade_backlog_invertida" in criterios:
        if tem_backlog:
            disponiveis.append("agilidade_backlog_invertida")
            mascara_aberto_backlog = _mascara_itens_em_aberto(df, mapeamento)
            datas_backlog = pd.to_datetime(df[coluna_data_principal], errors="coerce")
            mascara_aberto_backlog = mascara_aberto_backlog & datas_backlog.notna()
            if (
                colunas_aguardando_externo
                and mapeamento.coluna_board
                and mapeamento.coluna_board in df.columns
            ):
                valores_board = df[mapeamento.coluna_board].astype(str)
                mascara_aberto_backlog = mascara_aberto_backlog & ~valores_board.isin(colunas_aguardando_externo)
        else:
            indisponiveis.append(CRITERIOS_SCORECARD["agilidade_backlog_invertida"])

    if not disponiveis:
        return None, indisponiveis, False

    entidades = _rotular_valores_vazios(df[coluna_entidade]).astype(str)

    contagem_entidades = entidades.value_counts()
    entidades_mantidas = contagem_entidades.index.tolist()
    entidades_truncadas = len(entidades_mantidas) > limite_entidades
    if entidades_truncadas:
        entidades_mantidas = contagem_entidades.head(limite_entidades).index.tolist()

    linhas: list[tuple[str, str, float]] = []

    for entidade in entidades_mantidas:
        indices = entidades.index[entidades == entidade]
        subset = df.loc[indices]
        total = len(subset)

        if "taxa_sucesso" in disponiveis:
            passou = int((subset["__status_normalizado__"] == "Passou").sum())
            falhou = int((subset["__status_normalizado__"] == "Falhou").sum())
            executados = passou + falhou
            nota = round((passou / executados) * 10, 2) if executados > 0 else 0.0
            linhas.append((entidade, "taxa_sucesso", nota))

        if "cobertura" in disponiveis:
            linhas.append((entidade, "cobertura", float(total)))  # normalizada depois, entre entidades

        if "taxa_bugs_invertida" in disponiveis:
            bugs = int(
                subset[mapeamento.tipo_teste].astype(str).str.contains("bug", case=False, na=False).sum()
            )
            proporcao = (bugs / total) if total else 0.0
            linhas.append((entidade, "taxa_bugs_invertida", round(10 * (1 - proporcao), 2)))

        if "aderencia_planejado" in disponiveis:
            if aderencia_modo == "status":
                planejado = int((subset["__status_normalizado__"] == "Planejado").sum())
                efetivado = int(subset["__status_normalizado__"].isin(["Passou", "Falhou"]).sum())
            else:
                coluna_execucao_ou_criacao = mapeamento.data_execucao or mapeamento.data_criacao
                planejado = int(subset[mapeamento.data_planejada].notna().sum())
                efetivado = int(subset[coluna_execucao_ou_criacao].notna().sum())
            if planejado > 0:
                nota = round(min(efetivado / planejado, 1.0) * 10, 2)
            else:
                nota = 10.0 if efetivado > 0 else 0.0
            linhas.append((entidade, "aderencia_planejado", nota))

        if "severidade_critica_invertida" in disponiveis:
            criticos = int(subset[mapeamento.severidade].apply(_eh_severidade_critica).sum())
            proporcao = (criticos / total) if total else 0.0
            linhas.append((entidade, "severidade_critica_invertida", round(10 * (1 - proporcao), 2)))

        if "agilidade_backlog_invertida" in disponiveis:
            mascara_subset = mascara_aberto_backlog.loc[indices]
            if mascara_subset.any():
                idade_media = (
                    pd.Timestamp(datetime.now().date()) - datas_backlog.loc[indices][mascara_subset]
                ).dt.days.mean()
                nota = max(0.0, min(10.0, 10 - (idade_media / 90) * 10))
            else:
                nota = 10.0  # nada em aberto (descontada a espera externa): melhor cenário possível
            linhas.append((entidade, "agilidade_backlog_invertida", round(nota, 2)))

    tabela = pd.DataFrame(linhas, columns=["Entidade", "__criterio__", "Nota"])

    if "cobertura" in disponiveis:
        bruta = tabela.loc[tabela["__criterio__"] == "cobertura", "Nota"]
        minimo, maximo = bruta.min(), bruta.max()
        if maximo > minimo:
            tabela.loc[tabela["__criterio__"] == "cobertura", "Nota"] = (
                (bruta - minimo) / (maximo - minimo) * 10
            ).round(2)
        else:
            tabela.loc[tabela["__criterio__"] == "cobertura", "Nota"] = 10.0

    ordem_disponiveis = [chave for chave in CRITERIOS_SCORECARD if chave in disponiveis]
    tabela["Critério"] = pd.Categorical(
        tabela["__criterio__"].map(CRITERIOS_SCORECARD),
        categories=[CRITERIOS_SCORECARD[chave] for chave in ordem_disponiveis],
        ordered=True,
    )
    tabela = (
        tabela.drop(columns="__criterio__")
        .sort_values(["Entidade", "Critério"])
        .reset_index(drop=True)
    )

    return tabela[["Entidade", "Critério", "Nota"]], indisponiveis, entidades_truncadas
