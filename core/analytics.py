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
_CAMPOS_ROTULAVEIS = ("projeto", "responsavel", "tipo_teste", "severidade")

_VALORES_CONSIDERADOS_VAZIOS = {"", "nan", "none", "null", "nat", "<na>"}


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


def distribuicao_tipo_teste(df: pd.DataFrame, mapeamento: MapeamentoColunas) -> Optional[pd.DataFrame]:
    """Distribuição de registros por Tipo de Teste (ex.: Bug, Test Case, Test Plan...)."""
    if not mapeamento.tipo_teste or mapeamento.tipo_teste not in df.columns:
        return None
    resultado = (
        df.groupby(mapeamento.tipo_teste, dropna=False)
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
    df: pd.DataFrame, coluna_x: str, coluna_metrica: Optional[str], modo_metrica: str
) -> pd.DataFrame:
    """
    Monta os dados para o construtor de gráfico personalizado (itens 4.5-4.7).

    modo_metrica:
        "contagem" -> conta ocorrências de cada valor de `coluna_x`;
        "soma"     -> soma os valores numéricos de `coluna_metrica` agrupados por `coluna_x`.
    """
    if modo_metrica == "soma" and coluna_metrica:
        resultado = (
            df.groupby(coluna_x, dropna=False)[coluna_metrica]
            .sum(numeric_only=True)
            .reset_index()
            .rename(columns={coluna_metrica: "Valor"})
        )
    else:
        resultado = df.groupby(coluna_x, dropna=False).size().reset_index(name="Valor")

    resultado = resultado.rename(columns={coluna_x: "Categoria"})
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
