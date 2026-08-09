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

# Guarda o PDF inteiro do "Guia Completo do Usuário" (ver
# `core/gerador_guia_pdf.py`), codificado em base64 num único valor TEXT -
# gravado pelo botão "🔄 Gerar/Atualizar PDF agora" em Administração e lido
# pela tela "Sobre o App" na hora de oferecer o download pra qualquer
# usuário. É uma chave só (não por usuário, como a de cima): o guia é o
# mesmo pra todo mundo. Guardar aqui (em vez de só em disco) é o que faz o
# PDF sobreviver a reinícios/redeploys no Streamlit Community Cloud, cujo
# disco é temporário.
CHAVE_GUIA_PDF_BASE64 = "guia_usuario_pdf_base64"

# Guarda a "impressão digital" (hash) do CONTEÚDO do guia usado na última vez
# que o PDF acima foi gerado (ver `core/gerador_guia_pdf.py::
# hash_conteudo_atual`). Comparando esse valor salvo com o hash do código
# rodando AGORA, a Administração consegue avisar "há uma alteração no código
# do guia ainda não gerada" sem precisar reabrir o PDF inteiro pra conferir.
CHAVE_GUIA_PDF_HASH = "guia_usuario_pdf_hash"

# "Código de acesso" que libera, dentro de "Sobre o App", o conteúdo que
# descreve os fluxos exclusivos de Administração (a trilha "quem administra"
# do fluxograma, e a seção "Administração") para quem NÃO é o admin - ver
# `ui/pages/sobre_page.py::_usuario_tem_visao_admin`. Por padrão vazio/não
# configurado (ninguém além do admin enxerga esse conteúdo); o admin define
# um valor em Administração e repassa, por fora do app, só para quem quiser
# dar essa visibilidade extra. Não é uma senha de autenticação de verdade -
# é só um "seletor" de conteúdo informativo, guardado como configuração
# comum (mesma tabela genérica das demais chaves deste módulo).
CHAVE_CODIGO_VISAO_ADMIN_SOBRE_APP = "sobre_app_codigo_visao_admin"

# Guardam as duas imagens (PNG, em base64) do "Fluxograma completo do app"
# mostrado em "Sobre o App" - ver `core/gerador_fluxograma.py` e o botão
# "🔄 Gerar/Atualizar fluxograma agora" em Administração → "📘 Guia do
# Usuário". Mesmo raciocínio de CHAVE_GUIA_PDF_BASE64 acima: gravar aqui (e
# não só no arquivo em assets/) é o que faz a imagem sobreviver a
# reinícios/redeploys no Streamlit Community Cloud, cujo disco é temporário.
# Duas chaves de conteúdo (uma por versão - completa e pública) e duas de
# hash (para o indicador "há alteração pendente", ver CHAVE_GUIA_PDF_HASH).
CHAVE_FLUXOGRAMA_COMPLETO_BASE64 = "fluxograma_completo_base64"
CHAVE_FLUXOGRAMA_COMPLETO_HASH = "fluxograma_completo_hash"
CHAVE_FLUXOGRAMA_PUBLICO_BASE64 = "fluxograma_publico_base64"
CHAVE_FLUXOGRAMA_PUBLICO_HASH = "fluxograma_publico_hash"


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


def obter_configuracao_com_data(chave: str) -> Optional[tuple[str, str]]:
    """
    Como `obter_configuracao`, mas devolve também `atualizado_em` (data/hora
    da última gravação, em UTC) - usado onde a tela precisa mostrar "gerado
    em ..." (ex.: o botão de regenerar o Guia do Usuário em PDF, na aba
    "📘 Guia do Usuário" de Administração). Devolve `None` se `chave` nunca
    foi configurada.
    """
    _garantir_tabela()
    linhas = executar(f"SELECT valor, atualizado_em FROM {_TABELA} WHERE chave = ?", [chave])
    if not linhas:
        return None
    return linhas[0]["valor"], linhas[0]["atualizado_em"]
