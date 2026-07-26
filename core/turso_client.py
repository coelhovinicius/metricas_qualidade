"""
Cliente HTTP minimalista para o Turso (banco de dados SQLite servido via
HTTP), usado só para guardar as solicitações de criação de conta vindas da
tela de login (ver `core/solicitacoes_conta.py` e `ui/pages/admin_page.py`).

Por que sem biblioteca de banco nenhuma: o Turso expõe uma API HTTP (o
endpoint "pipeline", documentado em https://docs.turso.tech/sdk/http/reference)
que aceita comandos SQL comuns via POST simples - dá pra falar com ela só com
`requests` (já é dependência do projeto), sem instalar driver novo nem
depender de nenhum serviço intermediário (n8n, etc.). Um secret a mais
(`[turso]` no `st.secrets`), zero peça nova pra manter.

Configuração esperada em `st.secrets` (nunca no código/Git):

    [turso]
    database_url = "https://SEU-BANCO-SEUUSUARIO.turso.io"
    auth_token = "SEU_TOKEN_DE_AUTENTICACAO"

Veja o passo a passo de como gerar essas duas informações (CLI do Turso) na
mensagem que acompanha esta entrega.
"""

from __future__ import annotations

from typing import Any, Optional

import requests
import streamlit as st

TIMEOUT_SEGUNDOS = 10


class TursoError(Exception):
    """Erro amigável de configuração/comunicação com o banco de dados (Turso)."""


def _configuracao() -> tuple[str, str]:
    try:
        secao = st.secrets.get("turso")
    except Exception:
        # st.secrets pode levantar exceção quando não existe secrets.toml
        # configurado - mesmo comportamento já tratado em auth_manager.py.
        secao = None
    if not secao or not secao.get("database_url") or not secao.get("auth_token"):
        raise TursoError(
            "O banco de dados usado para guardar as solicitações de conta ainda não "
            "está configurado. Adicione a seção [turso] (database_url, auth_token) "
            "nos Secrets do Streamlit."
        )
    url = secao["database_url"].rstrip("/")
    # A CLI do Turso devolve a URL no esquema `libsql://` (usado pelos SDKs
    # nativos) - a API HTTP usada aqui precisa do mesmo host em `https://`.
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://") :]
    return url, secao["auth_token"]


def executar(sql: str, args: Optional[list[Any]] = None) -> list[dict]:
    """
    Executa um único comando SQL no Turso e devolve as linhas resultantes
    (lista de dicts coluna -> valor). Sem linhas de retorno (CREATE TABLE,
    INSERT, UPDATE), devolve lista vazia.
    """
    url, token = _configuracao()
    args = args or []

    corpo = {
        "requests": [
            {
                "type": "execute",
                "stmt": {"sql": sql, "args": [_empacotar_valor(valor) for valor in args]},
            },
            {"type": "close"},
        ]
    }

    try:
        resposta = requests.post(
            f"{url}/v2/pipeline",
            headers={"Authorization": f"Bearer {token}"},
            json=corpo,
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as exc:
        raise TursoError(f"Não foi possível conectar ao banco de dados: {exc}") from exc

    if not resposta.ok:
        raise TursoError(
            f"O banco de dados retornou um erro ({resposta.status_code}): {resposta.text[:300]}"
        )

    resultados = resposta.json().get("results", [])
    if not resultados:
        return []

    primeiro = resultados[0]
    if primeiro.get("type") == "error":
        mensagem = primeiro.get("error", {}).get("message", "erro desconhecido")
        raise TursoError(f"Erro ao executar consulta no banco de dados: {mensagem}")

    result_set = primeiro.get("response", {}).get("result", {})
    colunas = [coluna["name"] for coluna in result_set.get("cols", [])]
    linhas = []
    for linha in result_set.get("rows", []):
        linhas.append({coluna: _desempacotar_valor(valor) for coluna, valor in zip(colunas, linha)})
    return linhas


def _empacotar_valor(valor: Any) -> dict:
    if valor is None:
        return {"type": "null"}
    if isinstance(valor, bool):
        return {"type": "integer", "value": str(int(valor))}
    if isinstance(valor, int):
        return {"type": "integer", "value": str(valor)}
    if isinstance(valor, float):
        return {"type": "float", "value": valor}
    return {"type": "text", "value": str(valor)}


def _desempacotar_valor(valor: dict) -> Any:
    tipo = valor.get("type")
    bruto = valor.get("value")
    if tipo == "integer":
        return int(bruto) if bruto is not None else None
    if tipo == "float":
        return float(bruto) if bruto is not None else None
    if tipo == "null":
        return None
    return bruto
