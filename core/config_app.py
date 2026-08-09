"""
Pequena tabela de configurações gerais do app, guardadas no Turso (mesmo
banco já usado por `core/solicitacoes_conta.py`/`core/logs_sistema.py`) -
hoje usada só para a pasta do Google Drive de cada usuário (ver
`ui/pages/upload_page.py` → "Buscar arquivo no Google Drive"), mas escrita
como um key-value genérico (chave/valor em texto) caso surjam outras
configurações administráveis pelo próprio app no futuro, sem precisar de
uma tabela nova pra cada uma.

Diferente dos Secrets do Streamlit (usados para CREDENCIAIS - PAT, senha de
banco, chave de conta de serviço): isto aqui é para CONFIGURAÇÃO comum, não
sensível, que faz sentido o próprio usuário (ou administrador) poder alterar
de dentro do app, sem precisar mexer no painel do Streamlit Community Cloud
toda vez.
"""

from __future__ import annotations

from typing import Optional

from core.turso_client import executar

_TABELA = "configuracoes_app_qa"

_CRIAR_TABELA_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABELA} (
    chave TEXT PRIMARY KEY,
    valor TEXT,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

_PREFIXO_CHAVE_GOOGLE_DRIVE_PASTA_RAIZ = "google_drive_pasta_raiz_id__"


def chave_pasta_raiz_google_drive(nome_usuario: str) -> str:
    """
    Monta a chave usada para guardar a pasta do Google Drive de UM usuário
    específico (ver `ui/pages/upload_page.py` → "Buscar arquivo no Google
    Drive"). De propósito, NÃO existe mais uma "pasta raiz única" global
    configurada pelo administrador - cada usuário logado guarda a própria
    pasta, numa chave separada por `nome_usuario`: ninguém depende do
    administrador para trocar de pasta, e ninguém enxerga (nem precisa
    saber) a pasta configurada por outra pessoa.
    """
    return f"{_PREFIXO_CHAVE_GOOGLE_DRIVE_PASTA_RAIZ}{nome_usuario}"


def _garantir_tabela() -> None:
    executar(_CRIAR_TABELA_SQL)


def obter_configuracao(chave: str) -> Optional[str]:
    """Devolve o valor guardado para `chave`, ou `None` se nunca foi configurado."""
    _garantir_tabela()
    linhas = executar(f"SELECT valor FROM {_TABELA} WHERE chave = ?", [chave])
    return linhas[0]["valor"] if linhas else None


def definir_configuracao(chave: str, valor: str) -> None:
    """Grava (ou substitui, se já existir) o valor de `chave`."""
    _garantir_tabela()
    executar(
        f"""
        INSERT INTO {_TABELA} (chave, valor, atualizado_em) VALUES (?, ?, datetime('now'))
        ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, atualizado_em = excluded.atualizado_em
        """,
        [chave, valor],
    )
