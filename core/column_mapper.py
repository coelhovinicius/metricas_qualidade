"""
Detecção automática do "papel" de cada coluna do arquivo importado.

Como a estrutura do CSV/TXT pode variar de arquivo para arquivo, este módulo
usa correspondência por palavras-chave (com normalização de acentos/caixa)
para tentar identificar automaticamente quais colunas representam:

    projeto, status, data planejada, data de execução, data de criação,
    tipo de teste (Bug/Test Case/etc.), responsável/executor, identificador
    do caso de teste e severidade/prioridade.

O resultado é um mapeamento sugerido (`MapeamentoColunas`) que a interface
exibe ao usuário para confirmação/ajuste antes de gerar os indicadores -
garantindo que a detecção automática nunca produza um dashboard silenciosamente
errado. Campos não mapeados (`None`) são ignorados na geração dos gráficos.

Também é possível anexar campos personalizados (`campos_personalizados`),
relacionando um rótulo livre a qualquer coluna do arquivo, além dos campos
canônicos fixos.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# Palavras-chave (já normalizadas: minúsculas e sem acento) associadas a cada
# campo canônico que a aplicação sabe interpretar.
#
# "projeto" e "severidade" incluem também termos em inglês (area path, team
# project, severity, priority) porque exports do Azure DevOps costumam trazer
# os nomes de campo nesse idioma por padrão, mesmo em organizações que operam
# em português no restante da interface.
PALAVRAS_CHAVE: dict[str, list[str]] = {
    "projeto": [
        "projeto",
        "sistema",
        "produto",
        "modulo",
        "aplicacao",
        "squad",
        "app",
        "area path",
        "team project",
        "project",
    ],
    "status": ["status", "resultado", "situacao", "conclusao", "state"],
    "data_planejada": ["data planejada", "planejamento", "data prevista", "previsto", "data plan"],
    "data_execucao": [
        "data execucao",
        "data de execucao",
        "data teste",
        "executado em",
        "data real",
        "data efetiva",
    ],
    "data_criacao": [
        "data de criacao",
        "created date",
        "data criacao",
        "criado em",
        "data abertura",
        "data cadastro",
    ],
    "tipo_teste": [
        "work item type",
        "tipo de teste",
        "tipo teste",
        "categoria",
        "tipo",
    ],
    "responsavel": ["responsavel", "executor", "tester", "analista", "assigned to", "atribuido"],
    "caso_teste": ["caso de teste", "id teste", "test case", "cenario", "caso teste", "id caso", "id"],
    "severidade": ["severidade", "prioridade", "criticidade", "severity", "priority"],
}

# Palavras curtas (<=3 caracteres) só devem "casar" como token isolado, para
# evitar falsos positivos por substring (ex.: "id" dentro de "validado").
_TAMANHO_MINIMO_SUBSTRING = 4

# Padrão "Nome Completo <email@dominio.com>" usado, por exemplo, em exports
# do Azure DevOps para colunas de responsável/atribuído.
_PADRAO_NOME_EMAIL = re.compile(r"^\s*(.*?)\s*<[^<>]+>\s*$")


def _normalizar(texto: str) -> str:
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto


def _tokens(texto: str) -> list[str]:
    return re.split(r"[^a-z0-9]+", texto)


def extrair_nome_de_email(valor: object) -> object:
    """
    Converte "Fulano de Tal <fulano@dominio.com>" em "Fulano de Tal".
    Valores sem esse padrão são retornados inalterados.
    """
    if pd.isna(valor):
        return valor
    texto = str(valor)
    correspondencia = _PADRAO_NOME_EMAIL.match(texto)
    return correspondencia.group(1) if correspondencia else texto


def extrair_primeiro_valor_de_lista(valor: object, separador: str = ";") -> object:
    """Para colunas com múltiplos valores por linha (ex.: Tags "Legado; Melhoria"), retorna só o primeiro."""
    if pd.isna(valor):
        return valor
    texto = str(valor)
    partes = [parte.strip() for parte in texto.split(separador) if parte.strip()]
    return partes[0] if partes else texto


def simplificar_valor_projeto(valor: object) -> object:
    """
    Normaliza valores usados como "Projeto" quando a coluna de origem não é um
    campo simples de projeto:
        - Hierarquia de Area Path do Azure DevOps
          ("Produto e Tecnologia\\Modulo") -> usa apenas o último nível
          ("Modulo"), que é o que de fato distingue um item do outro;
        - Múltiplos valores separados por ";" (ex.: coluna Tags usada como
          aproximação de projeto) -> usa o primeiro valor.

    Colunas de projeto "normais" (um valor simples por linha, sem "\\" nem
    ";") passam por aqui sem qualquer alteração.
    """
    if pd.isna(valor):
        return valor
    texto = str(valor).strip()
    if not texto:
        return valor

    if "\\" in texto:
        partes = [parte.strip() for parte in texto.split("\\") if parte.strip()]
        if partes:
            texto = partes[-1]

    if ";" in texto:
        partes = [parte.strip() for parte in texto.split(";") if parte.strip()]
        if partes:
            texto = partes[0]

    return texto


@dataclass
class MapeamentoColunas:
    projeto: Optional[str] = None
    status: Optional[str] = None
    data_planejada: Optional[str] = None
    data_execucao: Optional[str] = None
    data_criacao: Optional[str] = None
    tipo_teste: Optional[str] = None
    responsavel: Optional[str] = None
    caso_teste: Optional[str] = None
    severidade: Optional[str] = None
    campos_personalizados: dict[str, str] = field(default_factory=dict)
    confianca: dict[str, float] = field(default_factory=dict)

    def como_dict(self) -> dict[str, Optional[str]]:
        return {
            "projeto": self.projeto,
            "status": self.status,
            "data_planejada": self.data_planejada,
            "data_execucao": self.data_execucao,
            "data_criacao": self.data_criacao,
            "tipo_teste": self.tipo_teste,
            "responsavel": self.responsavel,
            "caso_teste": self.caso_teste,
            "severidade": self.severidade,
        }

    def coluna_data_principal(self) -> Optional[str]:
        """Coluna de data usada por padrão em filtros de período e tendência temporal."""
        return self.data_execucao or self.data_criacao or self.data_planejada


def detectar_mapeamento(df: pd.DataFrame) -> MapeamentoColunas:
    """Sugere automaticamente qual coluna do dataframe corresponde a cada campo canônico."""
    colunas_normalizadas = {coluna: _normalizar(coluna) for coluna in df.columns}
    mapeamento = MapeamentoColunas()
    colunas_ja_usadas: set[str] = set()

    ordem_campos = [
        "projeto",
        "status",
        "data_planejada",
        "data_execucao",
        "data_criacao",
        "tipo_teste",
        "responsavel",
        "caso_teste",
        "severidade",
    ]

    for campo in ordem_campos:
        palavras = PALAVRAS_CHAVE[campo]
        melhor_coluna = None
        melhor_score = 0.0

        for coluna_original, coluna_normalizada in colunas_normalizadas.items():
            if coluna_original in colunas_ja_usadas:
                continue
            tokens_coluna = _tokens(coluna_normalizada)
            for palavra in palavras:
                if len(palavra) < _TAMANHO_MINIMO_SUBSTRING:
                    casou = palavra in tokens_coluna
                else:
                    casou = palavra in coluna_normalizada
                if casou:
                    score = len(palavra) / max(len(coluna_normalizada), 1)
                    if score > melhor_score:
                        melhor_score = score
                        melhor_coluna = coluna_original

        if melhor_coluna is not None:
            setattr(mapeamento, campo, melhor_coluna)
            mapeamento.confianca[campo] = round(melhor_score, 2)
            colunas_ja_usadas.add(melhor_coluna)

    # Fallback: quando não existe uma coluna explícita de Projeto/Area Path/
    # Team Project, mas existe uma coluna "Tags" com mais de um valor
    # distinto, ela é usada como aproximação de "Projeto"/módulo - comum em
    # exports do Azure DevOps sem Area Path populado de forma útil. Fica
    # marcado com confiança baixa (0.1), e o usuário sempre pode desfazer na
    # tela de confirmação do mapeamento se não fizer sentido para o arquivo.
    if mapeamento.projeto is None:
        coluna_tags = next(
            (
                coluna_original
                for coluna_original, coluna_normalizada in colunas_normalizadas.items()
                if coluna_normalizada == "tags" and coluna_original not in colunas_ja_usadas
            ),
            None,
        )
        if coluna_tags is not None:
            valores = df[coluna_tags].dropna().astype(str).str.strip()
            valores = valores[valores != ""]
            if valores.nunique() >= 2:
                mapeamento.projeto = coluna_tags
                mapeamento.confianca["projeto"] = 0.1
                colunas_ja_usadas.add(coluna_tags)

    return mapeamento


# ---------------------------------------------------------------------------
# Suporte opcional a classificação Passou/Falhou (usado apenas quando o
# arquivo importado realmente contém esse tipo de informação - ex.: planilhas
# de execução de teste tradicionais). Para dados de fluxo de trabalho (ex.:
# Azure DevOps: New/Closed/Ready...), essa classificação não é aplicada; a
# aplicação mostra a distribuição real dos valores de status nesses casos.
# ---------------------------------------------------------------------------

VALORES_PASSOU = {"passou", "pass", "sucesso", "aprovado", "ok", "success", "concluido", "concluida"}
VALORES_FALHOU = {
    "falhou",
    "fail",
    "falha",
    "reprovado",
    "erro",
    "failed",
    "nao passou",
    "não passou",
    "bloqueado",
}
VALORES_PLANEJADO = {"planejado", "planned", "a executar", "pendente", "não executado", "nao executado"}


def normalizar_status(valor: object) -> str:
    """Classifica um valor de status livre em: Passou, Falhou, Planejado ou Outro."""
    texto = _normalizar(valor)
    if any(chave in texto for chave in VALORES_PASSOU):
        return "Passou"
    if any(chave in texto for chave in VALORES_FALHOU):
        return "Falhou"
    if any(chave in texto for chave in VALORES_PLANEJADO):
        return "Planejado"
    return "Outro" if texto and texto != "nan" else "Não informado"


def eh_status_binario_reconhecivel(df: pd.DataFrame, coluna_status: str, limiar: float = 0.3) -> bool:
    """
    Indica se a coluna de status contém vocabulário reconhecível de
    Passou/Falhou/Planejado em proporção relevante (>= limiar), o que
    determina se a aplicação usa os KPIs binários tradicionais ou a
    distribuição genérica de status.
    """
    if coluna_status not in df.columns or df.empty:
        return False
    classificados = df[coluna_status].apply(normalizar_status)
    reconhecidos = classificados.isin(["Passou", "Falhou", "Planejado"]).sum()
    return (reconhecidos / len(df)) >= limiar
