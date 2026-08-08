"""
Logs do sistema, guardados no mesmo banco Turso já usado pelas solicitações
de conta (ver `core/turso_client.py`/`core/solicitacoes_conta.py`) e visíveis
só no painel administrativo (`ui/pages/admin_page.py`).

Três categorias (ver `TIPO_PAINEL`/`TIPO_ERRO`/`TIPO_LOGIN` abaixo):

    - Ações no painel: auditoria de tudo que um administrador faz em cima das
      solicitações de conta (marcar como criada, revogar, rejeitar, reverter,
      recuperar, excluir) - hoje só dá pra ver o status ATUAL de cada
      solicitação; isto guarda o histórico de quando/quem mudou o quê.
    - Erros técnicos: falhas capturadas durante o uso do app (ex.: falha ao
      buscar do Azure DevOps, exceção não tratada em alguma página) - pra dar
      pra diagnosticar problemas sem depender só do que apareceu na tela pro
      usuário (que costuma ver uma mensagem amigável, sem o detalhe técnico).
    - Login/acessos: toda vez que alguém consegue (ou tenta e falha) entrar
      no app.

Registrar um log NUNCA quebra a ação que está sendo registrada: qualquer
falha ao gravar (ex.: Turso não configurado ou temporariamente fora do ar) é
silenciosamente ignorada dentro de `registrar_log` - perder uma linha de log
é sempre preferível a fazer uma ação real (ex.: revogar um acesso) falhar só
porque o registro dela não pôde ser salvo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.turso_client import TursoError, executar

_TABELA = "logs_sistema_qa"

_CRIAR_TABELA_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABELA} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    usuario TEXT,
    mensagem TEXT NOT NULL,
    detalhes TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

TIPO_PAINEL = "painel"
TIPO_ERRO = "erro"
TIPO_LOGIN = "login"

ROTULOS_TIPO_LOG = {
    TIPO_PAINEL: "Ações no Painel",
    TIPO_ERRO: "Erros Técnicos",
    TIPO_LOGIN: "Login / Acessos",
}


@dataclass
class LogSistema:
    id: int
    tipo: str
    usuario: Optional[str]
    mensagem: str
    detalhes: Optional[str]
    criado_em: str


def _garantir_tabela() -> None:
    executar(_CRIAR_TABELA_SQL)


def registrar_log(tipo: str, usuario: Optional[str], mensagem: str, detalhes: Optional[str] = None) -> None:
    """
    Grava uma linha de log (best-effort - ver aviso no docstring do módulo).

    `usuario` aceita `None` (ex.: uma tentativa de login sem usuário digitado
    ainda não faz sentido registrar, mas um erro técnico disparado antes do
    login também não tem usuário associado).
    """
    try:
        _garantir_tabela()
        executar(
            f"INSERT INTO {_TABELA} (tipo, usuario, mensagem, detalhes) VALUES (?, ?, ?, ?)",
            [tipo, usuario or None, mensagem, detalhes or None],
        )
    except TursoError:
        pass


def listar_logs(tipo: Optional[str] = None, limite: int = 200) -> list[LogSistema]:
    _garantir_tabela()
    sql = f"SELECT id, tipo, usuario, mensagem, detalhes, criado_em FROM {_TABELA}"
    args: list = []
    if tipo:
        sql += " WHERE tipo = ?"
        args.append(tipo)
    sql += " ORDER BY criado_em DESC LIMIT ?"
    args.append(limite)
    linhas = executar(sql, args)
    return [LogSistema(**linha) for linha in linhas]


def contar_logs(tipo: Optional[str] = None) -> int:
    _garantir_tabela()
    sql = f"SELECT COUNT(*) AS total FROM {_TABELA}"
    args: list = []
    if tipo:
        sql += " WHERE tipo = ?"
        args.append(tipo)
    linhas = executar(sql, args)
    return int(linhas[0]["total"]) if linhas else 0


def limpar_logs_antigos(dias: int, tipo: Optional[str] = None) -> int:
    """
    Apaga logs com mais de `dias` dias (opcionalmente só de um `tipo`).
    Devolve quantas linhas foram apagadas - usado no painel pra dar um
    feedback concreto ("42 logs apagados") em vez de um "concluído" genérico.
    """
    _garantir_tabela()
    antes = contar_logs(tipo=tipo)
    sql = f"DELETE FROM {_TABELA} WHERE criado_em < datetime('now', ?)"
    args: list = [f"-{dias} days"]
    if tipo:
        sql += " AND tipo = ?"
        args.append(tipo)
    executar(sql, args)
    depois = contar_logs(tipo=tipo)
    return antes - depois
