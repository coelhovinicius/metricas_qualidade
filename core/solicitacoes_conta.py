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
STATUS_REVOGADA = "revogada"  # já foi criada, mas o acesso foi revogado depois


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


def existe_solicitacao_pendente_com_email(email: str) -> bool:
    """
    True se já existe uma solicitação com status 'pendente' para esse e-mail.

    Usado na tela de login para bloquear o envio de uma segunda solicitação
    enquanto a primeira ainda não foi analisada pelo administrador (antes
    disso, era possível mandar várias solicitações pendentes com o mesmo
    e-mail, poluindo a lista de "Pendentes" do painel administrativo sem
    necessidade). Comparação por e-mail é sempre feita ignorando
    maiúsculas/minúsculas (`lower(...)` dos dois lados) - "Fulano@Empresa.com"
    e "fulano@empresa.com" contam como o mesmo e-mail.

    Solicitações já 'rejeitada' não entram nessa checagem de propósito: se o
    pedido foi rejeitado, a pessoa deve poder tentar de novo (ex.: corrigindo
    algo, ou pedindo de novo depois de um tempo) sem ficar bloqueada para
    sempre por causa de uma tentativa antiga já encerrada.
    """
    _garantir_tabela()
    linhas = executar(
        f"SELECT COUNT(*) AS total FROM {_TABELA} WHERE status = ? AND lower(email) = lower(?)",
        [STATUS_PENDENTE, email.strip()],
    )
    return bool(linhas) and int(linhas[0]["total"]) > 0


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


def excluir_solicitacao(id_solicitacao: int) -> None:
    """Apaga a solicitação de vez (usado nos botões 'Excluir' de Revogadas/Rejeitadas)."""
    executar(f"DELETE FROM {_TABELA} WHERE id = ?", [id_solicitacao])


def testar_conexao() -> None:
    """Levanta TursoError se a configuração/conexão estiver com problema (usado no painel admin)."""
    executar("SELECT 1")
