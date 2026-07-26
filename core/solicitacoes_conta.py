"""
Solicitações de criação de conta feitas na tela de login (ver
`ui/pages/login_page.py`), guardadas no Turso e exibidas só para o
administrador dentro do próprio app (ver `ui/pages/admin_page.py`).

Sem e-mail, sem mensagem, sem webhook externo: o pedido só existe dentro do
banco de dados e do painel administrativo - ninguém além de quem acessa o
painel (hoje, só o usuário `admin`) fica sabendo que uma solicitação chegou.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.turso_client import executar

_TABELA = "solicitacoes_conta_qa"

_CRIAR_TABELA_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABELA} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL,
    justificativa TEXT,
    status TEXT NOT NULL DEFAULT 'pendente',
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

STATUS_PENDENTE = "pendente"
STATUS_CRIADA = "criada"
STATUS_REJEITADA = "rejeitada"


@dataclass
class SolicitacaoConta:
    id: int
    nome: str
    email: str
    justificativa: Optional[str]
    status: str
    criado_em: str


def _garantir_tabela() -> None:
    executar(_CRIAR_TABELA_SQL)


def registrar_solicitacao(nome: str, email: str, justificativa: str) -> None:
    _garantir_tabela()
    executar(
        f"INSERT INTO {_TABELA} (nome, email, justificativa, status) VALUES (?, ?, ?, ?)",
        [nome, email, justificativa or None, STATUS_PENDENTE],
    )


def listar_solicitacoes(status: Optional[str] = None) -> list[SolicitacaoConta]:
    _garantir_tabela()
    sql = f"SELECT id, nome, email, justificativa, status, criado_em FROM {_TABELA}"
    args: list = []
    if status:
        sql += " WHERE status = ?"
        args.append(status)
    sql += " ORDER BY criado_em DESC"
    linhas = executar(sql, args)
    return [SolicitacaoConta(**linha) for linha in linhas]


def atualizar_status(id_solicitacao: int, novo_status: str) -> None:
    executar(f"UPDATE {_TABELA} SET status = ? WHERE id = ?", [novo_status, id_solicitacao])


def testar_conexao() -> None:
    """Levanta TursoError se a configuração/conexão estiver com problema (usado no painel admin)."""
    executar("SELECT 1")
