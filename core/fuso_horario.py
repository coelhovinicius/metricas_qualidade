"""
Fuso horário único usado em TODO o app: horário de Brasília (America/Sao_Paulo,
UTC-3 - sem horário de verão desde 2019, então é sempre UTC-3 fixo).

Antes desta padronização, datas/horários vinham de fontes com fusos
diferentes e sem conversão nenhuma:
    - `datetime.now()` (Python) usa o fuso do SERVIDOR onde o app está
      rodando (pode ser UTC, pode ser outro - não é garantido ser o horário
      de Brasília);
    - a API do Azure DevOps devolve timestamps em UTC (ISO 8601, ex.:
      "2026-01-15T13:45:00Z");
    - o banco (Turso/SQLite) grava `criado_em` com `datetime('now')`, que no
      SQLite é sempre UTC.

Este módulo centraliza a conversão pra horário de Brasília em um único
lugar, pra todo o app mostrar (e calcular "hoje"/"agora") de forma
consistente, no formato brasileiro (dd/mm/aaaa, hh:mm).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


def agora_brasilia() -> datetime:
    """"Agora", já no horário de Brasília (UTC-3) - usar no lugar de `datetime.now()`."""
    return datetime.now(FUSO_BRASILIA)


def formatar_data_hora_brasil(valor) -> str:
    """
    Formata um TIMESTAMP (data + hora) no padrão brasileiro (dd/mm/aaaa,
    hh:mm), convertendo pro horário de Brasília antes de formatar.

    Uso: valores com horário relevante vindos de uma fonte em UTC - o
    `criado_em` gravado pelo banco (Turso/SQLite grava `datetime('now')`
    sempre em UTC) ou um timestamp ISO 8601 vindo da API do Azure DevOps
    (ex.: "2026-01-15T13:45:00Z"). Aceita `datetime`, `pandas.Timestamp` ou
    string. Valores SEM fuso horário explícito (naive) são tratados como UTC
    antes de converter, já que é sempre esse o caso das duas fontes acima.

    NÃO use para uma data pura sem horário (ex.: "Data de Criação" já
    convertida pra `date`, ou os filtros de período do dashboard) - nesse
    caso não existe horário pra converter, e a conversão de fuso arriscaria
    mudar o DIA por causa do deslocamento de -3h. Pra isso, use
    `formatar_data_brasil` (sem nenhuma conversão de fuso).

    Devolve "—" para valores vazios/inválidos, em vez de deixar estourar
    uma exceção - datas ausentes/mal formatadas não devem derrubar a tela.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "—"
    timestamp = pd.Timestamp(valor)
    if pd.isna(timestamp):
        return "—"
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    timestamp = timestamp.tz_convert(FUSO_BRASILIA)
    return timestamp.strftime("%d/%m/%Y, %H:%M")


def formatar_data_brasil(valor) -> str:
    """
    Formata uma DATA pura (sem horário relevante) no padrão brasileiro
    dd/mm/aaaa - sem nenhuma conversão de fuso horário (não há horário pra
    converter; ver aviso em `formatar_data_hora_brasil`).
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "—"
    timestamp = pd.Timestamp(valor)
    if pd.isna(timestamp):
        return "—"
    return timestamp.strftime("%d/%m/%Y")
