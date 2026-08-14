"""
Cliente HTTP minimalista para acionar um fluxo (workflow) do n8n que faz a
analise por IA de um grafico do painel - ver `ui/analise_grafico.py` para o
botao "Analisar com IA" que usa este modulo, hoje em piloto em dois graficos
(Backlog Aberto: Volume x Idade x Risco, no Dashboard; e Itens Concluidos por
Sprint, em Scrum & Sprints).

Por que via n8n em vez de chamar uma API de IA (Anthropic/OpenAI/etc.)
diretamente daqui: a decisao foi reaproveitar um fluxo n8n que a propria
Refuturiza ja mantem, com as chaves/creditos de IA que ja usam noutros
projetos - sem duplicar gerenciamento de chave de API dentro deste app. Este
cliente so envia os dados do grafico para uma URL de webhook do n8n (via
POST) e devolve o texto de analise que o fluxo do n8n responder; qual modelo
de IA e usado, qual o prompt exato, etc. e responsabilidade inteiramente do
fluxo n8n do outro lado, nao deste app.

Configuracao esperada em `st.secrets` (nunca no codigo/Git):

    [n8n]
    webhook_url = "https://SEU-N8N.exemplo.com/webhook/analise-grafico"
    auth_token = "TOKEN_OPCIONAL_SE_O_WEBHOOK_EXIGIR_AUTENTICACAO"

`auth_token` e opcional - se preenchido, e enviado como
`Authorization: Bearer <auth_token>`. Se o webhook do n8n nao exigir
autenticacao (ou usar outro mecanismo, como um segredo na propria URL),
basta deixar `auth_token` de fora dos Secrets.

Contrato esperado do webhook do n8n:

    - Requisicao (POST, corpo JSON):
        {
            "titulo": "...",            # nome do grafico
            "descricao": "...",         # o que o grafico representa
            "tipo_grafico": "...",      # ex.: "bolha", "barras"
            "dados": [ {...}, {...} ],  # linhas dos dados atuais do grafico
            "contexto": {
                "filtros_ativos": ["Periodo: ...", "Projeto: ..."],
                "total_linhas": 42,
                ...                      # campos extras conforme o grafico
            },
        }

    - Resposta esperada (HTTP 2xx): JSON com o texto da analise em uma das
      chaves "analise", "resposta", "texto", "output" ou "message" (aceita
      tambem uma lista com um unico item nesse formato) - ou, na falta de
      JSON reconhecivel, o proprio corpo da resposta como texto simples.
"""

from __future__ import annotations

import datetime
import math
from typing import Any, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st

TIMEOUT_SEGUNDOS = 75

_CHAVES_TEXTO_RESPOSTA = ("analise", "análise", "resposta", "texto", "text", "output", "message")


class N8nError(Exception):
    """Erro amigavel de configuracao/comunicacao com o fluxo n8n de analise por IA."""


def _configuracao() -> tuple[str, Optional[str]]:
    try:
        secao = st.secrets.get("n8n")
    except Exception:
        # st.secrets pode levantar excecao quando nao existe secrets.toml
        # configurado - mesmo comportamento ja tratado em turso_client.py.
        secao = None
    if not secao or not secao.get("webhook_url"):
        raise N8nError(
            "A analise por IA ainda nao esta configurada. Adicione a secao [n8n] "
            "(pelo menos webhook_url) nos Secrets do Streamlit."
        )
    return secao["webhook_url"].rstrip("/"), secao.get("auth_token")


def _tornar_serializavel(valor: Any) -> Any:
    """
    Converte, recursivamente, tipos comuns do pandas/numpy (Timestamp,
    numpy.int64/float64/bool_, NaN/NaT etc.) para tipos nativos do Python
    aceitos pelo `json.dumps` padrao usado por `requests` - sem isso, enviar
    `dados`/`contexto` vindos direto de um DataFrame (`to_dict`) ou de uma
    agregacao (`.mean()`, `.sum()`) quebra com `TypeError` na hora do POST.
    """
    if isinstance(valor, dict):
        return {chave: _tornar_serializavel(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_tornar_serializavel(item) for item in valor]
    if valor is pd.NaT:
        return None
    if isinstance(valor, (pd.Timestamp, datetime.datetime, datetime.date)):
        return valor.isoformat()
    if isinstance(valor, np.generic):
        item = valor.item()
        return None if isinstance(item, float) and math.isnan(item) else item
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return valor


def analisar_grafico(
    *,
    titulo: str,
    descricao: str,
    tipo_grafico: str,
    dados: list[dict[str, Any]],
    contexto: dict[str, Any],
) -> str:
    """
    Envia os dados atuais de UM grafico (ja filtrados como estao na tela) para
    o webhook n8n configurado e devolve o texto de analise gerado. Levanta
    `N8nError` (mensagem ja amigavel, pronta para `st.error`) em qualquer
    problema de configuracao, rede ou resposta inesperada.
    """
    webhook_url, auth_token = _configuracao()

    corpo = {
        "titulo": titulo,
        "descricao": descricao,
        "tipo_grafico": tipo_grafico,
        "dados": _tornar_serializavel(dados),
        "contexto": _tornar_serializavel(contexto),
    }
    cabecalhos = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}

    try:
        resposta = requests.post(webhook_url, json=corpo, headers=cabecalhos, timeout=TIMEOUT_SEGUNDOS)
    except requests.Timeout as exc:
        raise N8nError(
            "O fluxo de analise por IA demorou demais para responder (mais de "
            f"{TIMEOUT_SEGUNDOS}s) e foi interrompido. Tente novamente em instantes."
        ) from exc
    except requests.RequestException as exc:
        raise N8nError(
            f"Nao foi possivel falar com o fluxo de analise por IA configurado ({exc}). "
            "Verifique se a URL em [n8n] webhook_url esta correta e acessivel."
        ) from exc

    if not resposta.ok:
        raise N8nError(
            f"O fluxo de analise por IA respondeu com erro (HTTP {resposta.status_code}). "
            "Verifique o fluxo n8n configurado."
        )

    texto = _extrair_texto_analise(resposta)
    if not texto:
        # Mostra um trecho maior do corpo bruto da resposta na propria
        # mensagem de erro (que o app exibe com `st.error`) - sem isso, fica
        # impossivel descobrir o que o n8n devolveu de fato sem abrir a aba
        # Executions do n8n toda vez que algo sai diferente do esperado. O
        # limite foi ampliado (era 500 caracteres) porque o corpo enviado ao
        # n8n inclui os "dados" do grafico (que podem ser longos) - se algum
        # campo relevante (ex.: "error" de um dos provedores de IA) vier
        # DEPOIS de "dados" na resposta ecoada, um limite curto o escondia.
        previa = resposta.text.strip().replace("\n", " ")
        if len(previa) > 4000:
            previa = previa[:4000] + "... (truncado)"
        raise N8nError(
            "O fluxo de analise por IA respondeu, mas sem nenhum texto de analise "
            "reconhecivel. Verifique o formato de resposta do fluxo n8n configurado. "
            f"Corpo bruto recebido: {previa or '(vazio)'}"
        )
    return texto


def _buscar_texto_em_dict(corpo: dict[str, Any], profundidade: int = 2) -> str:
    """
    Procura o texto da analise em `corpo`, olhando primeiro as chaves
    conhecidas no nivel atual e, se nao achar nada utilizavel, descendo por
    ate `profundidade` niveis dentro de valores que sejam dict - alguns nos
    "Basic LLM Chain" do n8n, quando configurados com um parser de saida
    estruturada, devolvem o resultado aninhado (ex.: {"output": {"analise":
    "..."}}) em vez de uma string solta em "output".
    """
    for chave in _CHAVES_TEXTO_RESPOSTA:
        valor = corpo.get(chave)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    if profundidade > 0:
        for valor in corpo.values():
            if isinstance(valor, dict):
                texto = _buscar_texto_em_dict(valor, profundidade - 1)
                if texto:
                    return texto
    return ""


def _extrair_texto_analise(resposta: requests.Response) -> str:
    try:
        corpo_json = resposta.json()
    except ValueError:
        return resposta.text.strip()

    # Alguns fluxos n8n devolvem uma lista com um unico item (comportamento
    # padrao do node "Respond to Webhook" quando alimentado por um item so).
    if isinstance(corpo_json, list) and len(corpo_json) == 1:
        corpo_json = corpo_json[0]

    if isinstance(corpo_json, dict):
        return _buscar_texto_em_dict(corpo_json)

    if isinstance(corpo_json, str):
        return corpo_json.strip()

    return resposta.text.strip()
