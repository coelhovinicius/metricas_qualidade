"""
Controle de acesso à área "Integração GLPI x Azure DevOps" (ver
`ui/pages/integracao_glpi_page.py`).

Diferente do resto do app (onde só existe UM usuário administrador fixo,
`USUARIO_ADMIN` em `ui/pages/admin_page.py`), esta área precisa de uma lista
de pessoas autorizadas que pode crescer/encolher sem editar código nem fazer
deploy novo - por isso vive como uma tabela própria no Turso (mesmo banco já
usado por `core/solicitacoes_conta.py` e `core/logs_sistema.py`), gerenciada
direto pela aba "🔗 Integração GLPI" dentro de Administração.

O usuário administrador (`USUARIO_ADMIN`) sempre tem acesso a esta área,
independente de estar ou não nesta tabela - ver `usuario_pode_acessar` em
`ui/pages/integracao_glpi_page.py`, que combina as duas checagens. Esta
tabela guarda só os usuários EXTRAS que o administrador quiser liberar.

`username` aqui é sempre o login deste app (`AuthManager.current_username()`),
o mesmo valor cadastrado em `[auth.credentials.usernames.*]` nos Secrets do
Streamlit (ou em `auth/users.yaml` local) - não é e-mail nem nome de exibição.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.turso_client import executar

_TABELA = "usuarios_autorizados_glpi_qa"

_CRIAR_TABELA_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABELA} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    observacao TEXT,
    adicionado_por TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


@dataclass
class UsuarioAutorizadoGlpi:
    id: int
    username: str
    observacao: str | None
    adicionado_por: str | None
    criado_em: str


def _garantir_tabela() -> None:
    executar(_CRIAR_TABELA_SQL)


def listar_usuarios_autorizados() -> list[UsuarioAutorizadoGlpi]:
    _garantir_tabela()
    linhas = executar(
        f"SELECT id, username, observacao, adicionado_por, criado_em FROM {_TABELA} "
        "ORDER BY criado_em DESC"
    )
    return [UsuarioAutorizadoGlpi(**linha) for linha in linhas]


def usuario_esta_na_lista(username: str | None) -> bool:
    """
    True se `username` está cadastrado nesta tabela (independente de ser ou
    não o administrador - essa checagem combinada fica em
    `ui/pages/integracao_glpi_page.py::usuario_pode_acessar`).
    """
    if not username:
        return False
    _garantir_tabela()
    linhas = executar(
        f"SELECT COUNT(*) AS total FROM {_TABELA} WHERE lower(username) = lower(?)",
        [username.strip()],
    )
    return bool(linhas) and int(linhas[0]["total"]) > 0


def adicionar_usuario_autorizado(username: str, adicionado_por: str | None, observacao: str = "") -> None:
    _garantir_tabela()
    username_limpo = username.strip()
    if not username_limpo:
        return
    # INSERT OR IGNORE: evita erro de UNIQUE se o admin tentar adicionar o
    # mesmo username duas vezes (ex.: duplo clique) - simplesmente não faz
    # nada na segunda tentativa, em vez de estourar um TursoError.
    executar(
        f"INSERT OR IGNORE INTO {_TABELA} (username, observacao, adicionado_por) VALUES (?, ?, ?)",
        [username_limpo, observacao.strip() or None, adicionado_por],
    )


def remover_usuario_autorizado(id_registro: int) -> None:
    executar(f"DELETE FROM {_TABELA} WHERE id = ?", [id_registro])
