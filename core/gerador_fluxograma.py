"""
Monta, em memória (sem tocar em disco), as duas imagens do "Fluxograma
completo do app" mostrado em "Sobre o App" - retângulos + setas, no estilo
tradicional de diagrama de fluxo, gerados com Graphviz.

Por que isso é uma exceção à regra geral de "sem Graphviz/Mermaid" do resto
de "Sobre o App" (ver docstring de `ui/pages/sobre_page.py`): aquela regra
vale para os CARTÕES em HTML/CSS, que precisam recalcular a cada carregamento
de página - ali, uma dependência de sistema a mais (o binário `dot`) seria
risco desnecessário. Já esta imagem é gerada RARAMENTE (só quando o fluxo do
app muda de verdade) e o resultado é reaproveitado por muito tempo depois -
o mesmo raciocínio já usado para o PDF do Guia do Usuário (ver
`core/gerador_guia_pdf.py`): vale a pena pagar o custo de uma dependência a
mais (aqui, `graphviz` no `requirements.txt` e o pacote de sistema
`graphviz` no `packages.txt`, que fornece o binário `dot`) para poder gerar
isso com um clique em Administração, sem precisar de terminal.

Este módulo é reaproveitado por dois lugares:
    - `ui/pages/admin_page.py` (botão "🔄 Gerar/Atualizar fluxograma agora",
      aba "📘 Guia do Usuário") - grava o resultado no Turso, para sobreviver
      a reinícios/redeploys no Streamlit Community Cloud (disco temporário).
    - `scripts/gerar_fluxograma_diagrama.py` - wrapper de linha de comando,
      pra quem preferir gerar localmente e commitar o PNG resultante direto
      no repositório (`assets/`), sem depender do banco de dados.
"""

from __future__ import annotations

import hashlib

import graphviz

_LARANJA = "#F15A24"
_LARANJA_CLARO = "#FFF3EC"
_CINZA_ESCURO = "#6B6558"
_CINZA_CLARO = "#F2F1EC"
_TEXTO = "#1A1A1A"
_BORDA_DECISAO = "#F15A24"
_FUNDO_DECISAO = "#FFF8F5"


def _grafo_base(nome: str) -> graphviz.Digraph:
    g = graphviz.Digraph(nome, format="png")
    g.attr(
        rankdir="TB",
        bgcolor="#FFFFFF",
        fontname="Helvetica",
        fontsize="11",
        pad="0.4",
        nodesep="0.4",
        ranksep="0.5",
        splines="ortho",
        dpi="170",
    )
    g.attr(
        "node",
        fontname="Helvetica",
        fontsize="11",
        shape="box",
        style="rounded,filled",
        color=_LARANJA,
        fillcolor=_LARANJA_CLARO,
        fontcolor=_TEXTO,
        margin="0.2,0.14",
        width="2.15",
    )
    g.attr("edge", fontname="Helvetica", fontsize="9", color="#B9B4A6", arrowsize="0.7")
    return g


def _quebrar_linha(texto: str) -> str:
    """Dentro de um label HTML do Graphviz, `\\n` não vira quebra de linha
    (some sem deixar espaço, grudando as palavras) - precisa ser `<br/>`."""
    return texto.replace("\n", "<br/>")


def _caixa_usuario(g: graphviz.Digraph, id_: str, titulo: str, texto: str = "") -> None:
    titulo_html = _quebrar_linha(titulo)
    label = f"<<b>{titulo_html}</b>" + (f"<br/><font point-size='9'>{texto}</font>>" if texto else ">")
    g.node(id_, label=label)


def _caixa_admin(g: graphviz.Digraph, id_: str, titulo: str, texto: str = "") -> None:
    titulo_html = _quebrar_linha(titulo)
    label = f"<<b>{titulo_html}</b>" + (f"<br/><font point-size='9'>{texto}</font>>" if texto else ">")
    g.node(id_, label=label, color=_CINZA_ESCURO, fillcolor=_CINZA_CLARO)


def _caixa_decisao(g: graphviz.Digraph, id_: str, titulo: str) -> None:
    titulo_html = _quebrar_linha(titulo)
    g.node(
        id_, label=f"<<b>{titulo_html}</b>>",
        shape="diamond", style="filled,dashed", color=_BORDA_DECISAO,
        fillcolor=_FUNDO_DECISAO, margin="0.15,0.1",
    )


def _montar_trilha_usuario(g: graphviz.Digraph) -> None:
    with g.subgraph(name="cluster_usuario") as c:
        c.attr(
            label="🙋 Trilha de quem usa o app", fontsize="13", fontname="Helvetica-Bold",
            style="rounded,dashed", color="#DDD8CB", bgcolor="#FFFDFB", margin="16",
        )
        _caixa_usuario(c, "u1", "1. Pedir acesso", "Só se ainda não tiver conta")
        _caixa_usuario(c, "u2", "2. Fazer login", "Usuário e senha, criados pelo admin")
        _caixa_decisao(c, "u3", "Como importar\nos dados?")
        _caixa_usuario(c, "u3a", "📄 Enviar arquivo", ".csv/.txt, até 20MB")
        _caixa_usuario(c, "u3b", "☁️ Azure DevOps", "PAT + Organização + Query")
        _caixa_usuario(c, "u3c", "📁 Google Drive", "Navega e escolhe o .csv")
        _caixa_usuario(c, "u4", "4. Confirmar mapeamento", "de colunas")
        _caixa_usuario(c, "u5", "5. Painel de Indicadores", "Filtros + 20+ gráficos")
        _caixa_usuario(c, "u6", "✓ Gerar PDF do Relatório", "Opcional")

        c.edge("u1", "u2")
        c.edge("u2", "u3")
        c.edge("u3", "u3a")
        c.edge("u3", "u3b")
        c.edge("u3", "u3c")
        c.edge("u3a", "u4")
        c.edge("u3b", "u4")
        c.edge("u3c", "u4")
        c.edge("u4", "u5")
        c.edge("u5", "u6")


def _montar_trilha_admin_completa(g: graphviz.Digraph) -> None:
    with g.subgraph(name="cluster_admin") as c:
        c.attr(
            label="⚙️ Trilha de quem administra (login admin)", fontsize="13",
            fontname="Helvetica-Bold", style="rounded,dashed", color="#DDD8CB",
            bgcolor="#FAFAF8", margin="16",
        )
        _caixa_admin(c, "a1", "A. Configurar conta de\nserviço do Google Drive", "Uma vez só")
        _caixa_admin(c, "a2", "B. Aprovar/rejeitar\nsolicitações de acesso", "Fila de pendentes")
        _caixa_admin(c, "a3", "C. Revogar acesso", "Ou reverter depois")
        _caixa_admin(c, "a4", "D. Acompanhar Logs\ndo Sistema", "Acessos, erros, ações")
        c.edge("a1", "a2", style="invis")
        c.edge("a2", "a3", style="invis")
        c.edge("a3", "a4", style="invis")

    g.edge("a2", "u2", style="dashed", color=_LARANJA, xlabel="trava o login", fontcolor=_LARANJA, constraint="false")
    g.edge("a1", "u3c", style="dashed", color=_LARANJA, xlabel="trava esta opção", fontcolor=_LARANJA, constraint="false")


def _montar_trilha_admin_trancada(g: graphviz.Digraph) -> None:
    with g.subgraph(name="cluster_admin") as c:
        c.attr(
            label="⚙️ Trilha de quem administra", fontsize="13", fontname="Helvetica-Bold",
            style="rounded,dashed", color="#DDD8CB", bgcolor="#FAFAF8", margin="16",
        )
        c.node(
            "a_lock",
            label="<<b>🔒 Conteúdo visível só<br/>para quem administra</b>"
            "<br/><font point-size='9'>Peça um código de acesso à pessoa<br/>"
            "administradora para desbloquear</font>>",
            color=_CINZA_ESCURO, fillcolor=_CINZA_CLARO,
        )


def _grafo_completo() -> graphviz.Digraph:
    g = _grafo_base("fluxograma_completo")
    _montar_trilha_usuario(g)
    _montar_trilha_admin_completa(g)
    return g


def _grafo_publico() -> graphviz.Digraph:
    g = _grafo_base("fluxograma_publico")
    _montar_trilha_usuario(g)
    _montar_trilha_admin_trancada(g)
    return g


def gerar_bytes_completo() -> bytes:
    """PNG (bytes, em memória) do fluxograma com as duas trilhas."""
    return _grafo_completo().pipe(format="png")


def gerar_bytes_publico() -> bytes:
    """PNG (bytes, em memória) do fluxograma com a trilha administrativa trancada."""
    return _grafo_publico().pipe(format="png")


def hash_conteudo_completo() -> str:
    """
    "Impressão digital" (hash) do CONTEÚDO (fonte DOT, não os bytes do PNG)
    que o código atual geraria para a versão completa - mesmo raciocínio de
    `core/gerador_guia_pdf.py::hash_conteudo_atual`: dois PNGs do MESMO
    diagrama não são idênticos byte a byte entre si (o Graphviz não garante
    reprodutibilidade binária perfeita entre execuções), então comparar os
    PNGs diretamente acusaria "diferente" mesmo sem nenhuma mudança real de
    conteúdo. Usar a fonte DOT (texto) em vez do PNG evita esse falso
    positivo.
    """
    return hashlib.sha256(_grafo_completo().source.encode("utf-8")).hexdigest()


def hash_conteudo_publico() -> str:
    """Como `hash_conteudo_completo`, para a versão com a trilha admin trancada."""
    return hashlib.sha256(_grafo_publico().source.encode("utf-8")).hexdigest()
