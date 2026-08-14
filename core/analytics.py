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

from core.fuso_horario import agora_brasilia
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
_CAMPOS_ROTULAVEIS = ("projeto", "responsavel", "tipo_teste", "severidade", "coluna_board", "sprint")

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


def _valor_esta_vazio(valor: object) -> bool:
    """
    True para nulos "de verdade" (NaN/None/NaT) e para variações textuais de
    "vazio" (ex.: célula em branco que alguma etapa anterior tenha
    convertido para a string "nan"). Usado tanto para decidir se um valor
    deve ganhar o rótulo "Não atribuído(a)" quanto para decidir se o
    Responsável deve cair no fallback de Criado por (ver `preparar_dados`).
    """
    if pd.isna(valor):
        return True
    if isinstance(valor, str) and valor.strip().lower() in _VALORES_CONSIDERADOS_VAZIOS:
        return True
    return False


def _rotular_valores_vazios(serie: pd.Series, rotulo: str = ROTULO_VAZIO_PADRAO) -> pd.Series:
    """
    Substitui nulos (e variações textuais de "vazio", ex.: célula em branco
    que alguma etapa anterior tenha convertido para a string "nan") por um
    rótulo amigável - assim tabelas e gráficos nunca mostram "NaN"/"nan" cru.
    """

    def _rotular(valor: object) -> object:
        return rotulo if _valor_esta_vazio(valor) else valor

    return serie.apply(_rotular)


def preparar_dados(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> pd.DataFrame:
    """
    Aplica as limpezas necessárias antes de calcular qualquer indicador:
        - Extrai apenas o nome da coluna de responsável (remove "<email>");
        - Quando o Responsável vier vazio e a coluna Criado por/Created By
          estiver mapeada, usa quem criou o item como reserva do
          Responsável (só nesse caso - nunca sobrescreve um Responsável já
          preenchido);
        - Simplifica a coluna de projeto quando ela vem de uma hierarquia de
          Area Path ou de uma coluna com múltiplos valores (ex.: Tags usada
          como aproximação de projeto);
        - Simplifica a coluna de Sprint da mesma forma, quando vem de uma
          hierarquia de Iteration Path (ex.: "Projeto\\Release 1\\Sprint 24"
          vira só "Sprint 24");
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

        # Reserva: quando o Responsável (Assigned To) vier vazio, usa quem
        # abriu o item (Criado por / Created By) no lugar - só nesse caso.
        # Itens que já têm um Responsável de verdade NUNCA são sobrescritos
        # pelo Criado por, mesmo que sejam pessoas diferentes. Se o Criado
        # por também estiver mapeado mas vazio (ou não estiver mapeado), o
        # item continua sem responsável e cai no rótulo padrão
        # "Não atribuído(a)" mais abaixo, exatamente como antes.
        if mapeamento.criado_por and mapeamento.criado_por in df.columns:
            valores_criado_por = df[mapeamento.criado_por].apply(extrair_nome_de_email)
            mascara_responsavel_vazio = df[mapeamento.responsavel].apply(_valor_esta_vazio)
            df.loc[mascara_responsavel_vazio, mapeamento.responsavel] = valores_criado_por[
                mascara_responsavel_vazio
            ]

    if mapeamento.projeto and mapeamento.projeto in df.columns:
        df[mapeamento.projeto] = df[mapeamento.projeto].apply(simplificar_valor_projeto)

    if mapeamento.sprint and mapeamento.sprint in df.columns:
        # Mesma simplificação de hierarquia usada em Projeto/Area Path: o
        # Iteration Path do Azure DevOps costuma vir como
        # "Projeto\Release 1\Sprint 24" - fica só "Sprint 24".
        df[mapeamento.sprint] = df[mapeamento.sprint].apply(simplificar_valor_projeto)

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
    coluna_data = mapeamento.coluna_data_principal(df)
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


def tendencia_temporal_por_projeto(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    """
    Mesma base de `tendencia_temporal` (contagem por semana), só que abrindo
    também por Projeto/Area Path - é o que alimenta os "múltiplos pequenos"
    no dashboard (um mini-gráfico de tendência por Projeto, lado a lado,
    todos na mesma escala de eixo Y), pra comparar o FORMATO da tendência
    entre times sem empilhar todo mundo numa única linha multicolorida
    (que fica ilegível com muitos projetos e/ou muitos valores de Status
    juntos).

    Devolve `None` sem Projeto mapeado - sem essa coluna não tem como abrir
    por projeto (use `tendencia_temporal` nesse caso).
    """
    if not mapeamento.projeto or mapeamento.projeto not in df.columns:
        return None
    coluna_data = mapeamento.coluna_data_principal(df)
    if not coluna_data or coluna_data not in df.columns:
        return None

    datas = pd.to_datetime(df[coluna_data], errors="coerce")
    if datas.notna().sum() == 0:
        return None

    temp = df.copy()
    temp["__data__"] = datas
    temp = temp.dropna(subset=["__data__"])
    temp["__semana__"] = temp["__data__"].dt.to_period("W").dt.start_time

    coluna_status = "__status_bruto__" if mapeamento.status else None
    colunas_agrupamento = ["__semana__", mapeamento.projeto] + ([coluna_status] if coluna_status else [])
    resultado = (
        temp.groupby(colunas_agrupamento, dropna=False)
        .size()
        .reset_index(name="Quantidade")
    )
    renomear = {"__semana__": "Semana", mapeamento.projeto: "Projeto"}
    if coluna_status:
        renomear[coluna_status] = "Status"
    return resultado.rename(columns=renomear)


def volume_por_responsavel(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, agrupar_por_projeto: bool = False
) -> Optional[pd.DataFrame]:
    """
    Quantidade de registros (testes/itens) por Responsável/Executor - base do
    gráfico "Volume de Testes por Responsável" no dashboard.

    Com `agrupar_por_projeto=True` (e Projeto mapeado nos dados), abre a
    contagem também por Projeto: devolve uma linha por combinação
    Responsável × Projeto (colunas ["Responsável", "Projeto", "Quantidade"]),
    já ordenada com o Responsável de maior volume total primeiro (e, dentro
    dele, o Projeto de maior volume primeiro) - é o que permite colorir o
    gráfico por Projeto e mostrar não só "quanto" cada pessoa fez, mas "em
    que projeto(s)".

    Sem agrupar (ou sem Projeto mapeado nos dados), devolve uma linha por
    Responsável (colunas ["Responsável", "Quantidade"]), da maior pra menor.
    """
    if not mapeamento.responsavel or mapeamento.responsavel not in df.columns:
        return None

    usar_projeto = bool(agrupar_por_projeto and mapeamento.projeto and mapeamento.projeto in df.columns)
    if usar_projeto:
        resultado = (
            df.groupby([mapeamento.responsavel, mapeamento.projeto], dropna=False)
            .size()
            .reset_index(name="Quantidade")
            .rename(columns={mapeamento.responsavel: "Responsável", mapeamento.projeto: "Projeto"})
        )
        ordem_responsaveis = (
            resultado.groupby("Responsável")["Quantidade"].sum().sort_values(ascending=False).index
        )
        resultado["Responsável"] = pd.Categorical(
            resultado["Responsável"], categories=ordem_responsaveis, ordered=True
        )
        resultado = (
            resultado.sort_values(["Responsável", "Quantidade"], ascending=[True, False])
            .reset_index(drop=True)
        )
        resultado["Responsável"] = resultado["Responsável"].astype(str)
        return resultado

    resultado = (
        df.groupby(mapeamento.responsavel, dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={mapeamento.responsavel: "Responsável"})
        .sort_values("Quantidade", ascending=False)
    )
    return resultado


def volume_responsavel_por_semana(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, limite_responsaveis: int = 8
) -> tuple[Optional[pd.DataFrame], bool]:
    """
    Volume de registros por Responsável/Executor ao longo do tempo, agregado
    por SEMANA - mesma granularidade já usada em "Tendência ao Longo do
    Tempo" e "Bugs Abertos vs. Solucionados" (`tendencia_temporal`,
    `bugs_abertos_vs_solucionados`). Por DIA, o volume individual costuma ser
    baixo (poucas unidades por pessoa), o que deixa a série extremamente
    "serrilhada" e domina mais pelo dia da semana (ex.: quase sempre menos
    aos fins de semana) do que por variação real de ritmo - por semana, o
    padrão de fato relevante (alguém acelerando, desacelerando, ou saindo do
    ritmo do time) fica muito mais visível.

    Se houver mais de `limite_responsaveis` pessoas distintas com dado no
    período, mantém só as `limite_responsaveis` de maior volume total (senão
    o gráfico fica ilegível, com cores demais/linhas se sobrepondo) - o
    segundo item do retorno avisa se esse corte aconteceu.

    Retorna (dados, truncado): dados tem colunas ["Semana", "Responsável",
    "Quantidade"], ou é None se faltar a coluna de data principal ou a de
    Responsável nos dados.
    """
    coluna_data = mapeamento.coluna_data_principal(df)
    if not coluna_data or coluna_data not in df.columns:
        return None, False
    if not mapeamento.responsavel or mapeamento.responsavel not in df.columns:
        return None, False

    datas = pd.to_datetime(df[coluna_data], errors="coerce")
    if datas.notna().sum() == 0:
        return None, False

    temp = df.copy()
    temp["__data__"] = datas
    temp = temp.dropna(subset=["__data__"])
    temp["__semana__"] = temp["__data__"].dt.to_period("W").dt.start_time

    contagem_responsaveis = temp[mapeamento.responsavel].value_counts()
    truncado = len(contagem_responsaveis) > limite_responsaveis
    if truncado:
        mantidos = set(contagem_responsaveis.head(limite_responsaveis).index)
        temp = temp[temp[mapeamento.responsavel].isin(mantidos)]

    resultado = (
        temp.groupby(["__semana__", mapeamento.responsavel], dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={"__semana__": "Semana", mapeamento.responsavel: "Responsável"})
        .sort_values("Semana")
        .reset_index(drop=True)
    )
    return resultado, truncado


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


def distribuicao_responsavel_x_severidade(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> Optional[pd.DataFrame]:
    """
    Cruza Responsável/Executor com Severidade/Prioridade: quantos itens de
    cada pessoa estão em cada nível de severidade - base do gráfico "Carga
    de Risco por Responsável" no dashboard (por padrão, um mapa de calor:
    linhas = Responsável, colunas = Severidade, cor = quantidade). Mostra
    não só QUEM tem mais itens, mas quem está segurando os mais críticos -
    diferente de `volume_por_responsavel` (só quantidade, sem discriminar
    por severidade).

    Devolve `None` sem os dois campos mapeados (Responsável e Severidade) -
    sem os dois não tem como cruzar.
    """
    if not mapeamento.responsavel or mapeamento.responsavel not in df.columns:
        return None
    if not mapeamento.severidade or mapeamento.severidade not in df.columns:
        return None
    resultado = (
        df.groupby([mapeamento.responsavel, mapeamento.severidade], dropna=False)
        .size()
        .reset_index(name="Quantidade")
        .rename(columns={mapeamento.responsavel: "Responsável", mapeamento.severidade: "Severidade"})
    )
    return resultado


_PALAVRAS_SEVERIDADE_ALTA_CRITICA = ("critical", "high")


def _severidade_e_alta_ou_critica(valor: object) -> bool:
    """
    True quando `valor` (um valor bruto de Severidade/Prioridade) contém a
    palavra "critical" ou "high" (ignorando acento/maiúscula, e prefixo
    numérico tipo "1 - Critical") - usado só para calcular o percentual de
    itens de alto risco em `backlog_aberto_por_grupo`, não é o mesmo
    esquema estrito de 5 cores de `cor_discreta_severidade_prioridade`
    (ui/theme.py) - aqui é só "alto risco sim/não" para uma métrica
    agregada, não uma cor exata por categoria.
    """
    if pd.isna(valor):
        return False
    texto = normalizar_texto(str(valor))
    return any(palavra in texto for palavra in _PALAVRAS_SEVERIDADE_ALTA_CRITICA)


def backlog_aberto_por_grupo(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, coluna_grupo: str, rotulo_grupo: str
) -> Optional[pd.DataFrame]:
    """
    Agrupa o backlog aberto (mesma definição de itens "em aberto" usada em
    `calcular_backlog_aberto`/`ranking_itens_mais_antigos_abertos`) por uma
    coluna escolhida (ex.: Area Path/Projeto ou Responsável), calculando
    por grupo:

        - Quantidade: quantos itens em aberto o grupo tem;
        - "Idade Média (dias)": média de dias parado desde a data de
          referência do item (mesmo cálculo do KPI "Idade Média" da seção
          Backlog Aberto);
        - "% Severidade Alta/Crítica": qual fração desses itens em aberto é
          Severidade "Critical"/"High" (ver `_severidade_e_alta_ou_critica`) -
          fica em 0 se Severidade não estiver mapeada (não dá pra calcular).

    É a base do gráfico de bolha "Backlog Aberto: Volume × Idade × Risco" no
    dashboard - cada linha do resultado vira uma bolha (X = idade média,
    Y/tamanho = quantidade, cor = % de alta severidade).

    Devolve `None` sem Data principal mapeada, sem `coluna_grupo` presente
    nos dados, ou sem nenhum item em aberto com data válida.
    """
    coluna_data = mapeamento.coluna_data_principal(df)
    if not coluna_data or coluna_data not in df.columns:
        return None
    if not coluna_grupo or coluna_grupo not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    datas = pd.to_datetime(df[coluna_data], errors="coerce")
    trabalho = df.loc[mascara_aberto & datas.notna()].copy()
    if trabalho.empty:
        return None

    hoje = pd.Timestamp(agora_brasilia().date())
    trabalho["__idade_dias__"] = (hoje - datas.loc[trabalho.index]).dt.days
    trabalho["__grupo__"] = _rotular_valores_vazios(trabalho[coluna_grupo])

    if mapeamento.severidade and mapeamento.severidade in trabalho.columns:
        trabalho["__severidade_alta__"] = trabalho[mapeamento.severidade].apply(_severidade_e_alta_ou_critica)
    else:
        trabalho["__severidade_alta__"] = False

    resultado = (
        trabalho.groupby("__grupo__")
        .agg(
            Quantidade=("__idade_dias__", "size"),
            __idade_media__=("__idade_dias__", "mean"),
            __qtd_alta__=("__severidade_alta__", "sum"),
        )
        .reset_index()
        .rename(columns={"__grupo__": rotulo_grupo})
    )
    resultado["Idade Média (dias)"] = resultado["__idade_media__"].round(1)
    resultado["% Severidade Alta/Crítica"] = (
        resultado["__qtd_alta__"] / resultado["Quantidade"] * 100
    ).round(1)
    resultado = resultado.drop(columns=["__idade_media__", "__qtd_alta__"])
    return resultado.sort_values("Quantidade", ascending=False).reset_index(drop=True)


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


def excluir_nao_atribuido_coluna_board(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> pd.DataFrame:
    """
    Devolve uma cópia de `df` sem as linhas "Não atribuído(a)" de Coluna do
    Board - usado só na hora de montar os gráficos de Coluna do Board
    (Distribuição por Coluna do Board / Area Path × Coluna do Board), pra
    que eles mostrem só o fluxo real do board, sem o "ruído" de itens que
    nunca estiveram em nenhuma coluna (ver `detalhamento_nao_atribuido_coluna_board`
    pra entender/conferir quem são esses itens, por tipo).

    Sempre exclui, sem exceção - não existe opção de reincluir por tipo.
    Nunca afeta: linhas com uma Coluna do Board de verdade (só mexe nas
    rotuladas "Não atribuído(a)"); nem o restante do dashboard - o resto dos
    indicadores continua vendo todos os itens normalmente. Se Coluna do
    Board não estiver mapeada, devolve `df` sem alteração (não tem como
    filtrar sem esse campo).
    """
    if not mapeamento.coluna_board or mapeamento.coluna_board not in df.columns:
        return df
    return df[df[mapeamento.coluna_board] != ROTULO_VAZIO_PADRAO]


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


def filtrar_itens_em_aberto(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    """
    Devolve só as linhas de `df` cujo status ainda não chegou a um estado
    terminal - mesmo critério usado internamente por `calcular_backlog_aberto`/
    `ranking_itens_mais_antigos_abertos`/`backlog_aberto_por_grupo`, só que
    aqui exposto como o próprio subconjunto filtrado (não uma estatística
    calculada em cima dele), pra alimentar indicadores de "estado ATUAL do
    trabalho em andamento" (WIP) que olham outra dimensão além de idade -
    ex.: WIP atual por Coluna do Board e mix de Tipos de Trabalho em aberto,
    ambos em `ui/pages/scrum_page.py`.

    Requer Status mapeado; sem isso, retorna `None` (não tem como saber o que
    é aberto/terminal).
    """
    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None
    return df.loc[mascara_aberto].copy()


def calcular_backlog_aberto(
    df: pd.DataFrame, mapeamento: MapeamentoColunas
) -> Optional[IndicadoresBacklogAberto]:
    """Estatísticas de idade (em dias, a partir da coluna de data principal) dos itens ainda em aberto."""
    coluna_data = mapeamento.coluna_data_principal(df)
    if not coluna_data or coluna_data not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    datas = pd.to_datetime(df[coluna_data], errors="coerce")
    indices_abertos = df.index[mascara_aberto & datas.notna()]

    if len(indices_abertos) == 0:
        return IndicadoresBacklogAberto(0, None, None, 0, 0, 0)

    hoje = pd.Timestamp(agora_brasilia().date())
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
    coluna_data = mapeamento.coluna_data_principal(df)
    if not coluna_data or coluna_data not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    datas = pd.to_datetime(df[coluna_data], errors="coerce")
    trabalho = df.loc[mascara_aberto & datas.notna()].copy()
    if trabalho.empty:
        return pd.DataFrame(columns=["Status", "Responsável", "Idade (dias)"])

    hoje = pd.Timestamp(agora_brasilia().date())
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


def itens_concluidos_por_sprint(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, top_n: int = 12
) -> Optional[pd.DataFrame]:
    """
    Quantidade de itens concluídos (estado terminal) por Sprint, na ordem
    cronológica real dos sprints - não alfabética, já que nomes de sprint
    (ex.: "Sprint 9" viria depois de "Sprint 10" em ordem alfabética/texto)
    não seguem a ordem cronológica sozinhos.

    Como o Azure DevOps não expõe data de início/fim do sprint pela mesma via
    já usada por este app (import de work items, não de configuração do
    Team), a ordem cronológica é aproximada pela data mais antiga
    (`coluna_data_principal`) entre os itens concluídos de cada sprint - na
    prática funciona bem, porque os itens de um sprint tendem a ser
    criados/executados dentro da janela de tempo daquele sprint.

    Limitado aos `top_n` sprints mais recentes (por essa mesma aproximação),
    para manter o gráfico de comparação legível - sprints mais antigos ficam
    de fora deste gráfico específico, mas continuam contando normalmente para
    qualquer outro indicador do dashboard.

    Requer Sprint mapeado, além de status e data (para saber o que está
    concluído e em que ordem os sprints ficam) - sem algum dos três, retorna
    `None`.
    """
    if not mapeamento.sprint or mapeamento.sprint not in df.columns:
        return None
    coluna_data = mapeamento.coluna_data_principal(df)
    if not coluna_data or coluna_data not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    concluidos = df.loc[~mascara_aberto].copy()
    concluidos = concluidos[concluidos[mapeamento.sprint].notna() & (concluidos[mapeamento.sprint] != ROTULO_VAZIO_PADRAO)]
    if concluidos.empty:
        return pd.DataFrame(columns=["Sprint", "Quantidade"])

    concluidos["__data_ordenacao__"] = pd.to_datetime(concluidos[coluna_data], errors="coerce")

    ordem_sprints = (
        concluidos.groupby(mapeamento.sprint)["__data_ordenacao__"]
        .min()
        .sort_values()
        .index.tolist()
    )
    ordem_sprints = ordem_sprints[-top_n:]

    resultado = (
        concluidos[concluidos[mapeamento.sprint].isin(ordem_sprints)]
        .groupby(mapeamento.sprint)
        .size()
        .reindex(ordem_sprints, fill_value=0)
        .reset_index()
    )
    resultado.columns = ["Sprint", "Quantidade"]
    return resultado


def cobertura_story_points(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[dict[str, float]]:
    """
    Preenchimento do campo Story Points no arquivo importado: quantos itens
    (de `df`, já filtrado pelo escopo que o chamador quiser considerar) têm
    um valor numérico válido, de quantos no total.

    Story Points é preenchido MANUALMENTE pelo time durante planejamento/
    refinamento no próprio Azure DevOps - nunca é calculado automaticamente
    pela plataforma. Times que ainda não adotaram essa prática (ou adotaram
    só parcialmente) deixam a maioria dos itens vazios; usado por
    `ui/pages/scrum_page.py` pra decidir quando avisar que a Velocity por
    Story Points (`velocidade_por_sprint_pontos`) está sendo calculada em
    cima de poucos itens, e por isso tende a aparecer artificialmente baixa
    - não porque o time entregou pouco, mas porque a maior parte do que foi
    entregue não tem esforço estimado registrado.

    Retorna `None` sem Story Points mapeado nos dados. Com `df` vazio,
    devolve percentual 0.0 (evita divisão por zero) em vez de `None`, porque
    aqui a resposta "0% preenchido" ainda é uma resposta válida.
    """
    if not mapeamento.story_points or mapeamento.story_points not in df.columns:
        return None
    total = len(df)
    preenchidos = int(pd.to_numeric(df[mapeamento.story_points], errors="coerce").notna().sum())
    percentual = round((preenchidos / total) * 100, 1) if total > 0 else 0.0
    return {"preenchidos": preenchidos, "total": total, "percentual": percentual}


def velocidade_por_sprint_pontos(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, top_n: int = 12
) -> Optional[pd.DataFrame]:
    """
    Soma de Story Points dos itens CONCLUÍDOS (estado terminal) por Sprint -
    a Velocity clássica do Scrum, por esforço estimado (diferente de
    `itens_concluidos_por_sprint`, que conta ITENS, não pontos). Mesma
    aproximação de ordem cronológica dos sprints usada lá: pela data mais
    antiga (`coluna_data_principal`) entre os itens concluídos de cada
    sprint, já que o Azure DevOps não expõe data de início/fim de sprint por
    esta via de import.

    Itens concluídos SEM valor numérico válido em Story Points somam 0
    dentro do respectivo sprint (não são descartados da CONTAGEM de sprints
    exibidos) - o eixo de sprints é o MESMO de `itens_concluidos_por_sprint`
    (todo sprint com pelo menos um item concluído aparece aqui, mesmo que
    nenhum desses itens tenha Story Points preenchido). Isso é proposital:
    um sprint que entregou itens mas aparece com 0 pontos aqui é justamente
    o sinal de baixa cobertura que a Scrum Master precisa enxergar - se esse
    sprint simplesmente sumisse do eixo, pareceria "esse sprint não existe"
    em vez de "esse sprint não tem esforço registrado" (ver
    `cobertura_story_points`, que a UI usa para avisar sobre isso de forma
    explícita).

    Limitado aos `top_n` sprints mais recentes, mesmo critério de
    `itens_concluidos_por_sprint`.

    Requer Story Points, Sprint, Status e a coluna de data principal
    mapeados - sem algum dos quatro, retorna `None`.
    """
    if not mapeamento.story_points or mapeamento.story_points not in df.columns:
        return None
    if not mapeamento.sprint or mapeamento.sprint not in df.columns:
        return None
    coluna_data = mapeamento.coluna_data_principal(df)
    if not coluna_data or coluna_data not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    concluidos = df.loc[~mascara_aberto].copy()
    concluidos = concluidos[
        concluidos[mapeamento.sprint].notna() & (concluidos[mapeamento.sprint] != ROTULO_VAZIO_PADRAO)
    ]
    if concluidos.empty:
        return pd.DataFrame(columns=["Sprint", "Story Points Concluídos"])

    concluidos["__data_ordenacao__"] = pd.to_datetime(concluidos[coluna_data], errors="coerce")
    concluidos["__pontos__"] = pd.to_numeric(concluidos[mapeamento.story_points], errors="coerce")

    ordem_sprints = (
        concluidos.groupby(mapeamento.sprint)["__data_ordenacao__"]
        .min()
        .sort_values()
        .index.tolist()
    )
    ordem_sprints = ordem_sprints[-top_n:]

    resultado = (
        concluidos[concluidos[mapeamento.sprint].isin(ordem_sprints)]
        .groupby(mapeamento.sprint)["__pontos__"]
        .sum()  # skipna por padrão: grupo sem NENHUM valor válido soma 0.0, não NaN
        .reindex(ordem_sprints, fill_value=0)
        .reset_index()
    )
    resultado.columns = ["Sprint", "Story Points Concluídos"]
    return resultado


def ranking_prioridade_board(
    df: pd.DataFrame, mapeamento: MapeamentoColunas, top_n_por_coluna: int = 10
) -> Optional[pd.DataFrame]:
    """
    Ranking dos itens em aberto dentro de cada Coluna do Board, ordenados
    pela posição real que ocupam no board do Azure DevOps - do topo (maior
    prioridade, Posição 1) para baixo.

    Usa o campo oculto do Azure DevOps conhecido como "Stack Rank" (processos
    Agile/Basic/CMMI) ou "Backlog Priority" (processo Scrum) - é ele que
    controla a ordem vertical dos itens dentro de cada coluna do
    board/backlog, e funciona ao contrário do que a intuição sugere: quanto
    MENOR o valor numérico do campo, mais ACIMA o item fica (maior
    prioridade). Ver `core/azure_devops_client.py` (COLUNA_PRIORIDADE_BOARD)
    - esse campo só é buscado pela integração automática com a API do Azure
    DevOps; normalmente não vem em export manual/CSV, porque fica escondido
    do formulário do work item por padrão no Azure DevOps.

    Requer `mapeamento.prioridade_board` E `mapeamento.coluna_board`
    mapeados, além de status (para isolar só os itens em aberto) - sem algum
    dos três, retorna `None`. Itens sem valor numérico válido de prioridade,
    ou sem Coluna do Board preenchida, são excluídos do ranking (não tem como
    posicioná-los sem essa informação).
    """
    if not mapeamento.prioridade_board or mapeamento.prioridade_board not in df.columns:
        return None
    if not mapeamento.coluna_board or mapeamento.coluna_board not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    trabalho = df.loc[mascara_aberto].copy()
    trabalho = trabalho[trabalho[mapeamento.coluna_board] != ROTULO_VAZIO_PADRAO]
    trabalho["__prioridade_numerica__"] = pd.to_numeric(trabalho[mapeamento.prioridade_board], errors="coerce")
    trabalho = trabalho[trabalho["__prioridade_numerica__"].notna()]

    colunas_saida = ["Coluna do Board", "Posição", "Status", "Responsável", "Prioridade (valor bruto)"]
    if trabalho.empty:
        return pd.DataFrame(columns=colunas_saida)

    trabalho["Status"] = (
        trabalho["__status_bruto__"] if "__status_bruto__" in trabalho.columns else trabalho[mapeamento.status]
    )
    trabalho["Responsável"] = (
        trabalho[mapeamento.responsavel]
        if mapeamento.responsavel and mapeamento.responsavel in trabalho.columns
        else "—"
    )
    if mapeamento.projeto and mapeamento.projeto in trabalho.columns:
        trabalho["Projeto"] = trabalho[mapeamento.projeto]
        colunas_saida = ["Projeto"] + colunas_saida

    partes = []
    for valor_coluna_board, grupo in trabalho.groupby(mapeamento.coluna_board, dropna=False):
        grupo_ordenado = grupo.sort_values("__prioridade_numerica__", ascending=True).head(top_n_por_coluna).copy()
        grupo_ordenado["Posição"] = range(1, len(grupo_ordenado) + 1)
        grupo_ordenado["Coluna do Board"] = valor_coluna_board
        partes.append(grupo_ordenado)

    resultado = pd.concat(partes, ignore_index=True)
    resultado["Prioridade (valor bruto)"] = resultado["__prioridade_numerica__"]
    resultado["__ordem_coluna__"] = resultado["Coluna do Board"].apply(ordem_coluna_board)
    resultado = resultado.sort_values(["__ordem_coluna__", "Posição"]).reset_index(drop=True)
    return resultado[colunas_saida]


# Níveis da severidade calculada, do mais grave (topo da coluna) para o menos
# grave (fundo da coluna) - nomes e quantidade (4) definidos junto com o
# usuário para este indicador especificamente; não tem relação com os
# valores que o campo manual "Severity" do Azure DevOps costuma usar.
NIVEIS_SEVERIDADE_CALCULADA: tuple[str, ...] = ("Crítica", "Alta", "Média", "Baixa")


def _bucket_severidade_calculada(posicao: int, total_na_coluna: int, niveis: tuple[str, ...]) -> str:
    """
    Converte a posição de um item (1 = topo da coluna) dentro de uma coluna
    do board com `total_na_coluna` itens em um dos `niveis`, proporcionalmente
    ao tamanho da coluna - não por faixas fixas de posição.

    Fórmula: `indice = floor((posicao - 1) * len(niveis) / total_na_coluna)`,
    com `indice` sempre em `[0, len(niveis) - 1]` (o `min()` abaixo é só uma
    proteção defensiva contra arredondamento; matematicamente o resultado já
    fica sempre abaixo de `len(niveis)`).

    Por que proporcional em vez de faixa fixa (ex.: "posição 1-2 = Crítica"):
    uma coluna com 2 itens não deve ter os dois em "Crítica" só porque ambos
    são "top 2" - o segundo item, ali, é o ÚLTIMO da coluna, não deveria levar
    o mesmo peso do primeiro. Com a fórmula proporcional:
      - Coluna com 1 item: fica em "Crítica" (é o topo E o fundo ao mesmo tempo).
      - Coluna com 2 itens: 1º = "Crítica", 2º = "Média" (nunca os dois iguais).
      - Coluna com 4 itens (= número de níveis): cada item cai em um nível
        diferente, um a um.
      - Coluna com muitos itens (ex.: 20): a distribuição se aproxima de 25%
        por nível, com os últimos itens da coluna sempre caindo em "Baixa".
    """
    indice = ((posicao - 1) * len(niveis)) // total_na_coluna
    indice = min(indice, len(niveis) - 1)
    return niveis[indice]


def severidade_calculada_por_posicao(
    df: pd.DataFrame,
    mapeamento: MapeamentoColunas,
    niveis: tuple[str, ...] = NIVEIS_SEVERIDADE_CALCULADA,
) -> Optional[pd.DataFrame]:
    """
    Atribui a cada item em aberto uma "Severidade Calculada" derivada da
    posição real dele dentro da própria Coluna do Board (topo = mais grave),
    em vez do campo manual "Severity" do Azure DevOps (ver `distribuicao_severidade`,
    que continua existindo e não é afetada por esta função).

    Reaproveita exatamente a mesma base de dados/regras de elegibilidade que
    `ranking_prioridade_board` (mesmos campos obrigatórios, mesmo filtro de
    itens em aberto, mesma exclusão de itens sem Coluna do Board ou sem valor
    numérico de prioridade válido) - a diferença é que aqui NÃO existe corte
    de `top_n_por_coluna`: o cálculo precisa considerar TODOS os itens de
    cada coluna para saber o tamanho real do grupo (`total_na_coluna`), senão
    a proporção ficaria errada.

    Requer `mapeamento.prioridade_board` E `mapeamento.coluna_board`
    mapeados (só disponível para dados importados pela busca automática do
    Azure DevOps - o campo de prioridade por posição no board não vem em
    upload manual de CSV/TXT) - sem algum dos dois, retorna `None`.

    Ver `_bucket_severidade_calculada` para a fórmula de conversão
    posição -> nível.
    """
    if not mapeamento.prioridade_board or mapeamento.prioridade_board not in df.columns:
        return None
    if not mapeamento.coluna_board or mapeamento.coluna_board not in df.columns:
        return None

    mascara_aberto = _mascara_itens_em_aberto(df, mapeamento)
    if mascara_aberto is None:
        return None

    trabalho = df.loc[mascara_aberto].copy()
    trabalho = trabalho[trabalho[mapeamento.coluna_board] != ROTULO_VAZIO_PADRAO]
    trabalho["__prioridade_numerica__"] = pd.to_numeric(trabalho[mapeamento.prioridade_board], errors="coerce")
    trabalho = trabalho[trabalho["__prioridade_numerica__"].notna()]

    colunas_saida = [
        "Coluna do Board", "Posição", "Total na Coluna", "Severidade Calculada", "Status", "Responsável",
    ]
    if trabalho.empty:
        return pd.DataFrame(columns=colunas_saida)

    trabalho["Status"] = (
        trabalho["__status_bruto__"] if "__status_bruto__" in trabalho.columns else trabalho[mapeamento.status]
    )
    trabalho["Responsável"] = (
        trabalho[mapeamento.responsavel]
        if mapeamento.responsavel and mapeamento.responsavel in trabalho.columns
        else "—"
    )
    if mapeamento.projeto and mapeamento.projeto in trabalho.columns:
        trabalho["Projeto"] = trabalho[mapeamento.projeto]
        colunas_saida = ["Projeto"] + colunas_saida

    partes = []
    for valor_coluna_board, grupo in trabalho.groupby(mapeamento.coluna_board, dropna=False):
        grupo_ordenado = grupo.sort_values("__prioridade_numerica__", ascending=True).copy()
        total_na_coluna = len(grupo_ordenado)
        grupo_ordenado["Posição"] = range(1, total_na_coluna + 1)
        grupo_ordenado["Total na Coluna"] = total_na_coluna
        grupo_ordenado["Severidade Calculada"] = [
            _bucket_severidade_calculada(posicao, total_na_coluna, niveis)
            for posicao in grupo_ordenado["Posição"]
        ]
        grupo_ordenado["Coluna do Board"] = valor_coluna_board
        partes.append(grupo_ordenado)

    resultado = pd.concat(partes, ignore_index=True)
    resultado["__ordem_coluna__"] = resultado["Coluna do Board"].apply(ordem_coluna_board)
    resultado = resultado.sort_values(["__ordem_coluna__", "Posição"]).reset_index(drop=True)
    return resultado[colunas_saida]


def distribuicao_severidade_calculada(
    df: pd.DataFrame,
    mapeamento: MapeamentoColunas,
    niveis: tuple[str, ...] = NIVEIS_SEVERIDADE_CALCULADA,
) -> Optional[pd.DataFrame]:
    """
    Contagem de itens em aberto por "Severidade Calculada" (ver
    `severidade_calculada_por_posicao`), pronta para um gráfico de
    distribuição NOVO e SEPARADO do gráfico "Distribuição por
    Severidade/Prioridade" já existente (que usa o campo manual "Severity") -
    por escolha explícita do usuário, este indicador não substitui nem altera
    aquele.

    Ordem das categorias no resultado segue sempre `niveis` (Crítica -> Alta
    -> Média -> Baixa por padrão), mesmo quando algum nível tem 0 itens -
    assim o gráfico sempre mostra as 4 categorias na mesma ordem/posição,
    em vez de reordenar por quantidade a cada filtro aplicado.
    """
    detalhado = severidade_calculada_por_posicao(df, mapeamento, niveis=niveis)
    if detalhado is None:
        return None
    colunas_saida = ["Severidade Calculada", "Quantidade"]
    if detalhado.empty:
        resultado = pd.DataFrame({"Severidade Calculada": list(niveis), "Quantidade": [0] * len(niveis)})
        return resultado[colunas_saida]

    resultado = (
        detalhado.groupby("Severidade Calculada")
        .size()
        .reindex(niveis, fill_value=0)
        .reset_index()
    )
    resultado.columns = colunas_saida
    return resultado


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
    coluna_data = mapeamento.coluna_data_principal(df)
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
