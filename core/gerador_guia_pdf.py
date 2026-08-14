"""
Monta, em memória, o PDF "Guia Completo do Usuário" (função `gerar_pdf_bytes`).

Esse PDF é o mesmo oferecido para download na página "Sobre o App" (ver
`ui/pages/sobre_page.py` -> `_sec_guia_para_baixar`), disponível para
QUALQUER pessoa logada (não só o admin) - por isso o conteúdo aqui dentro
NUNCA deve incluir nada sensível: nenhuma credencial real, nenhum e-mail de
conta de serviço real, nenhuma URL específica deste ambiente/organização.
Onde um valor real seria útil (ex.: o e-mail da conta de serviço do Google
Drive), o texto orienta a pessoa a copiar da própria tela do app, em vez de
um valor fixo aqui. De propósito, sem nenhuma menção ao nome da empresa/marca
- só "o app"/"o painel", pra este PDF poder circular livremente sem carregar
esse nome.

Duas formas de gerar o PDF a partir daqui, ambas chamando a MESMA função
(`gerar_pdf_bytes`), então o resultado é sempre idêntico:

    1. Pelo próprio app, sem terminal nenhum: botão "🔄 Gerar/Atualizar PDF
       agora" na aba "📘 Guia do Usuário" da tela de Administração (ver
       `ui/pages/admin_page.py`) - grava o resultado no banco de dados
       (Turso, ver `core/config_app.py::CHAVE_GUIA_PDF_BASE64`), de onde a
       tela "Sobre o App" já lê primeiro na hora de oferecer o download.
       Esse é o caminho recomendado - é o único que sobrevive a reinícios/
       redeploys no Streamlit Community Cloud, cujo disco é temporário.
    2. Rodando `python scripts/gerar_guia_usuario_pdf.py` localmente - grava
       só em disco (`assets/Guia_do_Usuario_QA.pdf`), útil pra conferir o
       arquivo sem abrir o app, mas esse arquivo em disco sozinho NÃO chega
       aos outros usuários em produção (ver aviso no próprio script).

Paleta e fontes espelham `ui/theme.py` (PRIMARY_COLOR/TEXT_COLOR/
BACKGROUND_COLOR) para o PDF parecer parte do mesmo produto, não um
documento genérico colado por cima.
"""

from __future__ import annotations

import base64
import hashlib
import inspect
import io
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Paleta (mesmas cores de ui/theme.py) e estilos
# ---------------------------------------------------------------------------

ORANGE = colors.HexColor("#F15A24")
DARK = colors.HexColor("#1A1A1A")
GRAY = colors.HexColor("#6B6B6B")
LIGHT_BG = colors.HexColor("#FFF4E5")  # mesmo tom do .sobre-callout em ui/theme.py
LINE = colors.HexColor("#ECEBE6")
WARN_BORDER = colors.HexColor("#F0C989")
GREEN_BG = colors.HexColor("#E6F4EA")
GREEN_TEXT = colors.HexColor("#1E7B34")

PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 32 * mm

_styles = getSampleStyleSheet()

titulo_capa = ParagraphStyle(
    "titulo_capa", parent=_styles["Title"], fontName="Helvetica-Bold",
    fontSize=28, textColor=DARK, leading=33, alignment=0, spaceAfter=6,
)
subtitulo_capa = ParagraphStyle(
    "subtitulo_capa", parent=_styles["Normal"], fontName="Helvetica",
    fontSize=13, textColor=GRAY, leading=18, spaceAfter=4,
)
kicker = ParagraphStyle(
    "kicker", parent=_styles["Normal"], fontName="Helvetica-Bold",
    fontSize=10, textColor=ORANGE, leading=13, spaceAfter=10,
)
h1 = ParagraphStyle(
    "h1", parent=_styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=16, textColor=DARK, spaceBefore=4, spaceAfter=10,
)
h2 = ParagraphStyle(
    "h2", parent=_styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=12.5, textColor=ORANGE, spaceBefore=14, spaceAfter=6,
)
h3 = ParagraphStyle(
    "h3", parent=_styles["Heading3"], fontName="Helvetica-Bold",
    fontSize=10.5, textColor=DARK, spaceBefore=8, spaceAfter=4,
)
body = ParagraphStyle(
    "body", parent=_styles["Normal"], fontName="Helvetica",
    fontSize=9.3, textColor=DARK, leading=13.5, spaceAfter=6,
)
bullet = ParagraphStyle(
    "bullet", parent=body, leftIndent=12, spaceAfter=4,
)
step_text = ParagraphStyle(
    "step_text", parent=body, spaceAfter=2,
)
step_num = ParagraphStyle(
    "step_num", parent=_styles["Normal"], fontName="Helvetica-Bold",
    fontSize=11, textColor=colors.white, alignment=1, leading=14,
)
callout_text = ParagraphStyle(
    "callout_text", parent=body, spaceAfter=0,
)
table_header = ParagraphStyle(
    "table_header", parent=_styles["Normal"], fontName="Helvetica-Bold",
    fontSize=8.6, textColor=colors.white, leading=11,
)
table_cell = ParagraphStyle(
    "table_cell", parent=_styles["Normal"], fontName="Helvetica",
    fontSize=8.4, textColor=DARK, leading=11.5,
)
table_cell_bold = ParagraphStyle(
    "table_cell_bold", parent=table_cell, fontName="Helvetica-Bold",
)
footer_style = ParagraphStyle(
    "footer", parent=_styles["Normal"], fontName="Helvetica",
    fontSize=7.3, textColor=GRAY,
)
toc_item = ParagraphStyle(
    "toc_item", parent=body, fontName="Helvetica-Bold", fontSize=10,
    textColor=DARK, spaceAfter=7,
)
toc_subitem = ParagraphStyle(
    "toc_subitem", parent=toc_item, fontName="Helvetica", fontSize=9.3,
    textColor=GRAY, leftIndent=14, spaceAfter=5,
)


def passo(numero: str, titulo: str, texto: str = "") -> Table:
    """Um "cartão de passo" numerado (bolinha laranja + título + texto) - a
    mesma linguagem visual dos fluxogramas da página Sobre o App."""
    celula_num = Table([[Paragraph(numero, step_num)]], colWidths=[7 * mm], rowHeights=[7 * mm])
    celula_num.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ORANGE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [3.5, 3.5, 3.5, 3.5]),
    ]))
    texto_html = f"<b>{titulo}</b>"
    if texto:
        texto_html += f"<br/>{texto}"
    conteudo = Paragraph(texto_html, step_text)
    linha = Table(
        [[celula_num, conteudo]],
        colWidths=[10 * mm, CONTENT_W - 10 * mm],
    )
    linha.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return linha


def callout(texto: str, tipo: str = "dica") -> Table:
    """Caixa de destaque (dica/atenção), mesmo estilo visual do `.sobre-callout`
    e `.sobre-fluxo-decisao` do app."""
    cores = {
        "dica": (LIGHT_BG, WARN_BORDER),
        "atencao": (colors.HexColor("#FDECEA"), colors.HexColor("#E8A19B")),
        "ok": (GREEN_BG, colors.HexColor("#A8D5B5")),
    }
    fundo, borda = cores.get(tipo, cores["dica"])
    tabela = Table([[Paragraph(texto, callout_text)]], colWidths=[CONTENT_W])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fundo),
        ("BOX", (0, 0), (-1, -1), 0.75, borda),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return tabela


def tabela_colunas(linhas: list[tuple[str, str, str]], larguras=None) -> Table:
    cabecalho = [Paragraph(t, table_header) for t in ("Coluna/Campo", "Vira, no app", "Alimenta")]
    dados = [cabecalho]
    for a, b, c in linhas:
        dados.append([Paragraph(a, table_cell_bold), Paragraph(b, table_cell), Paragraph(c, table_cell)])
    larguras = larguras or [42 * mm, 40 * mm, CONTENT_W - 82 * mm]
    t = Table(dados, colWidths=larguras, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAF8")]),
    ]))
    return t


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(16 * mm, 14 * mm, PAGE_W - 16 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.3)
    canvas.setFillColor(GRAY)
    canvas.drawString(16 * mm, 10 * mm, "Painel de Qualidade — Guia Completo do Usuário")
    canvas.drawRightString(PAGE_W - 16 * mm, 10 * mm, f"Página {doc.page}")
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Conteúdo
# ---------------------------------------------------------------------------


def _montar_story() -> list:
    story = []

    # ---- Capa ----
    story.append(Spacer(1, 55 * mm))
    story.append(Paragraph("PAINEL DE QUALIDADE", kicker))
    story.append(Paragraph("Guia Completo do Usuário", titulo_capa))
    story.append(Paragraph(
        "Tudo o que você precisa para entrar, importar dados (por qualquer um dos três "
        "caminhos), montar a query certa no Azure DevOps e navegar pelos indicadores.",
        subtitulo_capa,
    ))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="35%", thickness=2, color=ORANGE, hAlign="LEFT"))
    story.append(PageBreak())

    # ---- Sumário ----
    story.append(Paragraph("Sumário", h1))
    sumario = [
        ("1. Visão geral do app", toc_item),
        ("2. Acesso: pedir conta e fazer login", toc_item),
        ("3. Importar dados — as três formas", toc_item),
        ("3.1  Enviar arquivo (.csv/.txt)", toc_subitem),
        ("3.2  Buscar Query no Azure DevOps (com seu PAT)", toc_subitem),
        ("3.3  Buscar arquivo no Google Drive", toc_subitem),
        ("4. Como montar a query no Azure DevOps (para os gráficos funcionarem)", toc_item),
        ("5. Confirmar o mapeamento de colunas", toc_item),
        ("6. Navegando no Painel de Indicadores", toc_item),
        ("7. Analisar um gráfico com IA (opcional)", toc_item),
        ("8. Gerando o relatório em PDF", toc_item),
        ("9. Perguntas frequentes", toc_item),
    ]
    for texto_item, estilo_item in sumario:
        story.append(Paragraph(texto_item, estilo_item))
    story.append(PageBreak())

    # ---- 1. Visão geral ----
    story.append(Paragraph("1. Visão geral do app", h1))
    story.append(Paragraph(
        "Este app transforma um arquivo de testes (do Azure DevOps, ou qualquer planilha "
        "parecida) em indicadores visuais — sem precisar montar relatório manual toda vez. "
        "O caminho é sempre o mesmo, do início ao fim:",
        body,
    ))
    story.append(passo("1", "Login (ou pedir acesso, se ainda não tiver conta)"))
    story.append(passo("2", "Importar dados", "Enviar arquivo, Azure DevOps (PAT) ou Google Drive — qualquer um dos três"))
    story.append(passo("3", "Confirmar o mapeamento de colunas", "Revisar o que o app já sugeriu sozinho"))
    story.append(passo("4", "Explorar o Painel de Indicadores", "Filtros + mais de 20 gráficos + gráfico personalizado"))
    story.append(passo("5", "Gerar o relatório em PDF", "Opcional, a qualquer momento a partir do painel"))
    story.append(Spacer(1, 4))
    story.append(callout(
        "Este guia cobre a jornada de quem <b>usa</b> o app no dia a dia. Se você for a pessoa "
        "administradora, a área \"Administração\" (aprovar acessos, configurar a credencial do "
        "Google Drive, ver logs) tem as próprias instruções na tela — não repetidas aqui.",
        "dica",
    ))
    story.append(PageBreak())

    # ---- 2. Acesso ----
    story.append(Paragraph("2. Acesso: pedir conta e fazer login", h1))
    story.append(Paragraph("Ainda não tenho uma conta", h2))
    story.append(passo("1", "Na tela de login, clique em \"Solicitar acesso\"", "Abre um formulário: Nome completo, E-mail e Motivo do acesso."))
    story.append(passo("2", "Preencha e confirme", "Se já existir um pedido pendente com o mesmo e-mail, um pedido novo é bloqueado até o primeiro ser analisado."))
    story.append(passo("✓", "Aguarde a pessoa administradora aprovar", "Não existe e-mail automático de aviso — o \"pronto\" precisa vir dela por fora do app."))
    story.append(callout(
        "Solicitar acesso <b>não cria a conta sozinho</b> — só registra o pedido. O usuário/senha em "
        "si continuam sendo criados manualmente, fora do app, pela pessoa administradora.",
        "atencao",
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Fazendo login", h2))
    story.append(passo("1", "Abra o link do painel e digite Usuário/Senha", "Os mesmos que a pessoa administradora te passou."))
    story.append(passo("2", "Clique em Entrar"))
    story.append(passo("✓", "Pronto", "Um F5/recarregar a página não pede login de novo por um tempo (sessão salva em cookie). Fechar a aba/janela de verdade, ou clicar em \"Sair\", encerra a sessão."))
    story.append(PageBreak())

    # ---- 3. Importar dados ----
    story.append(Paragraph("3. Importar dados — as três formas", h1))
    story.append(Paragraph(
        "Na tela \"Importar Dados\", escolha uma das três opções no topo. As três entregam o "
        "mesmo resultado final (um arquivo de dados pronto para mapear) — a diferença é só de "
        "onde o arquivo vem.",
        body,
    ))
    story.append(tabela_colunas(
        [
            ("Enviar arquivo", "Upload direto do seu computador", "Mais simples; exige exportar o CSV manualmente toda vez que quiser dados atualizados."),
            ("Azure DevOps (PAT)", "Busca automática, direto da API", "Sempre traz TODOS os campos que o app usa, inclusive dois indicadores exclusivos (seção 3.2)."),
            ("Google Drive", "Busca um .csv já deixado numa pasta sua", "Bom para quem já tem uma rotina de exportar e guardar o CSV numa pasta."),
        ],
        larguras=[38 * mm, 55 * mm, CONTENT_W - 93 * mm],
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3.1  Enviar arquivo (.csv/.txt)", h2))
    story.append(passo("1", "Deixe selecionada \"Enviar arquivo (.csv/.txt)\""))
    story.append(passo("2", "Escolha o arquivo do seu computador", "Limite de 20MB; normalmente um export do Azure DevOps (ver seção 4)."))
    story.append(passo("✓", "Clique em \"Processar arquivo\"", "Codificação e separador de colunas são detectados sozinhos."))
    story.append(PageBreak())

    story.append(Paragraph("3.2  Buscar Query no Azure DevOps (com seu PAT)", h2))
    story.append(Paragraph(
        "Um <b>Personal Access Token (PAT)</b> é como uma senha temporária e pessoal que você "
        "gera no próprio Azure DevOps, só para o app conseguir ler os work items em seu nome — "
        "sem usar sua senha de verdade. É individual: o PAT que você gera é só seu.",
        body,
    ))
    story.append(Paragraph("Como gerar o seu PAT", h3))
    story.append(passo("1", "Acesse dev.azure.com e faça login normalmente"))
    story.append(passo("2", "Clique no ícone de usuário (canto superior direito) → \"Personal Access Tokens\""))
    story.append(passo("3", "Clique em \"+ New Token\""))
    story.append(passo("4", "Dê um nome (ex.: \"Painel de Qualidade\") e escolha a validade", "Recomendado: 90 dias — depois é só gerar outro, é rápido."))
    story.append(passo("5", "Em Scopes, marque \"Work Items\" → \"Read\"", "Só leitura — o app nunca cria, edita ou apaga nada no Azure DevOps."))
    story.append(passo("✓", "Clique em \"Create\" e copie o token na hora", "O Azure DevOps só mostra o valor completo uma vez — se perder, gera outro."))
    story.append(callout(
        "<b>É seguro colar seu PAT aqui?</b> Sim. Ele nunca é salvo em disco, banco de dados ou nas "
        "configurações do app — fica só na memória da sua sessão do navegador enquanto você está "
        "logado, e desaparece ao sair ou fechar a aba de verdade.",
        "ok",
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Usando o PAT no app", h3))
    story.append(passo("1", "Selecione \"Buscar Query no Azure DevOps\" e cole o PAT"))
    story.append(passo("2", "Escolha/Carregue a Organização"))
    story.append(passo("3", "Escolha o Projeto", "Os passos seguintes carregam sozinhos."))
    story.append(passo("4", "(Opcional) Escolha Area Path(s)", "Deixe em branco para trazer tudo que a query já retorna."))
    story.append(passo("5", "Escolha a Query salva", "Se ainda não existir, use \"Criar nova query\" (abre o Azure DevOps) e depois \"Atualizar lista\"."))
    story.append(passo("✓", "Clique em \"Baixar relatório atualizado\""))
    story.append(callout(
        "Este é o único caminho que traz os indicadores \"Prioridade Dentro do Board\" e "
        "\"Severidade Calculada\" — eles dependem de um campo que o Azure DevOps não deixa "
        "exportar em CSV manual, em nenhuma configuração de query.",
        "dica",
    ))
    story.append(PageBreak())

    story.append(Paragraph("3.3  Buscar arquivo no Google Drive", h2))
    story.append(Paragraph(
        "Cada pessoa configura a <b>própria</b> pasta do Google Drive — ninguém depende da "
        "pessoa administradora para trocar de pasta, e ninguém enxerga a pasta configurada por "
        "outra pessoa.",
        body,
    ))
    story.append(passo("1", "Selecione \"Buscar arquivo no Google Drive\""))
    story.append(passo("2", "Copie o e-mail da conta de serviço mostrado na própria tela", "Esse e-mail é específico do seu ambiente — sempre confira direto na tela do app, não reutilize um e-mail de outro lugar."))
    story.append(passo("3", "No Google Drive, compartilhe sua pasta com esse e-mail", "Botão direito na pasta → Compartilhar → cole o e-mail → permissão de Leitor."))
    story.append(passo("4", "Copie o link da pasta e cole no app, clique em \"Salvar minha pasta\"", "O app testa o acesso antes de salvar — só confirma se realmente enxergou a pasta."))
    story.append(passo("5", "Navegue até o arquivo e escolha o .csv"))
    story.append(passo("✓", "Clique em \"Importar arquivo selecionado\""))
    story.append(callout(
        "Se a tela avisar que \"a conta de serviço do Google Drive ainda não foi configurada\", "
        "isso não depende de você — peça para a pessoa administradora configurar em "
        "Administração → Google Drive antes. Enquanto isso, use \"Enviar arquivo\" normalmente.",
        "atencao",
    ))
    story.append(PageBreak())

    # ---- 4. Query ----
    story.append(Paragraph("4. Como montar a query no Azure DevOps", h1))
    story.append(Paragraph(
        "Vale tanto para \"Enviar arquivo\" quanto para \"Google Drive\" (os dois usam o mesmo "
        "CSV exportado manualmente). O app reconhece cada campo <b>pelo nome da coluna</b> — "
        "então uma coluna que não existir no arquivo simplesmente não vira indicador nenhum, "
        "mesmo que o dado exista no Azure DevOps. A solução: configurar a query uma vez com as "
        "colunas abaixo, salvar, e reexportar sempre que precisar de dados atualizados.",
        body,
    ))
    story.append(Paragraph("Passo a passo", h2))
    story.append(passo("1", "Abra sua query em Boards → Queries"))
    story.append(passo("2", "Clique no ícone de colunas (\"Column Options\")"))
    story.append(passo("3", "Busque e adicione cada campo da tabela abaixo"))
    story.append(passo("4", "Salve a query", "Não precisa refazer isso na próxima vez."))
    story.append(passo("✓", "Nos resultados, use \"Export to CSV\""))
    story.append(Spacer(1, 8))
    story.append(tabela_colunas([
        ("ID", "Caso de Teste / ID", "Identificação de cada item; sempre disponível."),
        ("Work Item Type", "Tipos de Teste", "Distribuição por Tipo de Teste."),
        ("State", "Status", "Quase todos os gráficos de qualidade/status."),
        ("Area Path", "Projeto", "Todos os gráficos \"por Projeto\"."),
        ("Assigned To", "Responsável", "Volume e Carga de Risco por Responsável."),
        ("Created By", "Autor/Criado por", "Reserva quando \"Assigned To\" está vazio."),
        ("Created Date", "Data de Criação", "Tendência ao longo do tempo, backlog parado."),
        ("Severity (ou Priority)", "Severidade/Prioridade", "Cores fixas: Critical/High/Medium/Low."),
        ("Board Column *", "Coluna do Board", "Distribuição por Coluna, Area Path × Coluna, Funil."),
        ("Iteration Path **", "Sprint", "Sprints — Itens Concluídos, Volume por Responsável no tempo."),
        ("Story Points ***", "Story Points", "Velocity clássica do Scrum, na página Scrum & Sprints."),
    ]))
    story.append(Spacer(1, 6))
    story.append(callout(
        "<b>*</b> Nem sempre aparece na lista de colunas — depende do processo/template do seu "
        "projeto. Se não encontrar, esse indicador específico fica indisponível para arquivos "
        "exportados manualmente; o resto do app funciona normal.",
        "atencao",
    ))
    story.append(Spacer(1, 4))
    story.append(callout(
        "<b>**</b> É \"Iteration Path\", não \"Iteration ID\" — são campos diferentes. Iteration "
        "Path é o texto (\"Projeto\\Sprint 24\"); Iteration ID é só um número interno, sem uso "
        "aqui. Se vier só o ID por engano, o app pode sugerir errado — dá para corrigir na tela "
        "de confirmação de mapeamento (próxima seção).",
        "atencao",
    ))
    story.append(Spacer(1, 4))
    story.append(callout(
        "<b>***</b> Normalmente só existe em tipos como User Story/Product Backlog Item — Bugs, "
        "Tasks e Test Cases costumam não ter esse campo, o que é esperado. Com pouca cobertura, "
        "o gráfico de Velocity avisa em vez de mostrar um número enganoso.",
        "atencao",
    ))
    story.append(PageBreak())

    # ---- 5. Mapeamento ----
    story.append(Paragraph("5. Confirmar o mapeamento de colunas", h1))
    story.append(Paragraph(
        "Depois de importar (por qualquer um dos três caminhos), esta tela aparece antes do "
        "painel de indicadores:",
        body,
    ))
    story.append(passo("1", "Prévia dos dados importados", "As 20 primeiras linhas, num expansor — confira se o arquivo leu certo."))
    story.append(passo("2", "Revise o mapeamento sugerido", "Projeto, Status, Datas, Severidade, Coluna do Board, Sprint... já vem pré-preenchido; ajuste manualmente o que não bateu."))
    story.append(passo("3", "(Opcional) Campos personalizados", "Colunas que não se encaixam nos campos fixos (ex.: Cliente, Ambiente) — ficam disponíveis no gráfico personalizado."))
    story.append(passo("✓", "Clique em \"Confirmar mapeamento e gerar indicadores\""))
    story.append(callout(
        "Campo deixado como \"— não mapeado —\" só faz os gráficos que dependem dele não "
        "aparecerem — não trava o app. Não se preocupe em preencher tudo se algum campo "
        "simplesmente não existe no seu arquivo.",
        "dica",
    ))
    story.append(PageBreak())

    # ---- 6. Painel ----
    story.append(Paragraph("6. Navegando no Painel de Indicadores", h1))
    story.append(Paragraph("Barra lateral (filtros, aplicam-se ao painel inteiro)", h2))
    for texto in [
        "<b>Período</b> — datas \"De\"/\"Até\"; clique em \"Confirmar intervalo\" para aplicar.",
        "<b>Projeto, Sprint, Tipos de Teste e Status</b> — seleção múltipla, tudo marcado por padrão (sem filtro nenhum até você desmarcar algo).",
    ]:
        story.append(Paragraph("•  " + texto, bullet))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Corpo da página", h2))
    for texto in [
        "<b>Cartões de KPI</b> no topo — números-resumo (adaptam sozinhos ao vocabulário do seu Status: Passou/Falhou, ou fluxo tipo New/Active/Closed).",
        "<b>Gráficos</b> — cada um com seletor próprio de \"Tipo de gráfico\" (Barras, Pizza, Linha, Treemap, Mapa de Calor, Radar, Pareto, Funil... as opções variam por gráfico).",
        "<b>Gráfico personalizado</b> — monte do zero: Eixo, Agrupar por, Métrica e Tipo de gráfico livremente, com qualquer coluna do arquivo.",
        "<b>Dados detalhados</b> — tabela completa já filtrada, com exportação em CSV.",
    ]:
        story.append(Paragraph("•  " + texto, bullet))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Catálogo de gráficos disponíveis", h2))
    story.append(Paragraph("Cada um só aparece se os campos de que depende estiverem mapeados.", body))
    catalogo = [
        ("Visão geral e qualidade", "Distribuição de Status; Area Path × Status; Distribuição por Severidade/Prioridade."),
        ("Backlog e tempo parado", "Backlog Aberto — Tempo Parado; Backlog Aberto: Volume × Idade × Risco (bolha)."),
        ("Ritmo e tendência", "Sprints — Itens Concluídos; Planejamento vs. Efetivado; Tendência ao Longo do Tempo; Bugs Abertos vs. Solucionados."),
        ("Fluxo do board (Kanban)", "Distribuição por Coluna do Board; Area Path × Coluna do Board; Prioridade Dentro do Board *; Severidade Calculada *."),
        ("Projetos, tipos e pessoas", "Testes/Bugs por Projeto; Distribuição por Tipo de Teste; Taxa de Sucesso por Projeto; Volume por Responsável; Volume por Responsável no Tempo; Carga de Risco por Responsável."),
    ]
    for titulo_cat, itens in catalogo:
        story.append(Paragraph(f"<b>{titulo_cat}:</b> {itens}", bullet))
    story.append(Spacer(1, 4))
    story.append(callout(
        "<b>*</b> Só aparecem com dados vindos da busca automática por PAT (ver seção 3.2) — não "
        "com CSV manual/Google Drive, mesmo com a query bem configurada.",
        "atencao",
    ))
    story.append(PageBreak())

    # ---- 7. Análise por IA ----
    story.append(Paragraph("7. Analisar um gráfico com IA (opcional)", h1))
    story.append(Paragraph(
        "Logo abaixo de praticamente todo gráfico (no Painel de Indicadores e em Scrum & "
        "Sprints) existe um botão <b>\"🤖 Analisar com IA\"</b>. Ele gera, na hora, um texto "
        "explicando o que os dados daquele gráfico específico mostram — considerando os filtros "
        "que você já aplicou na tela naquele momento —, pontos de atenção e uma sugestão "
        "prática.",
        body,
    ))
    story.append(passo("1", "Clique em \"🤖 Analisar com IA\", logo abaixo do gráfico", "A tela fica bloqueada com um aviso de carregamento por alguns segundos, enquanto a análise é gerada."))
    story.append(passo("2", "O texto aparece num cartão, logo abaixo do botão", "Com o título \"🤖 Análise por IA\"."))
    story.append(passo("✓", "Clique em \"Limpar análise\" para gerar de novo", "Útil, por exemplo, depois de mudar um filtro na barra lateral."))
    story.append(callout(
        "Este recurso é <b>opcional</b> e depende de uma automação de IA configurada pela pessoa "
        "administradora, por fora do app — se ainda não estiver configurada no seu ambiente, o "
        "botão simplesmente não aparece em nenhum gráfico. Se você acha que deveria estar "
        "disponível e não está, avise a pessoa administradora.",
        "dica",
    ))
    story.append(Spacer(1, 4))
    story.append(callout(
        "<b>Privacidade:</b> em qualquer gráfico com uma coluna de Responsável, os nomes reais "
        "<b>nunca</b> são enviados para a IA — só rótulos genéricos (\"Colaborador 1\", "
        "\"Colaborador 2\"...), sempre o mesmo rótulo para a mesma pessoa dentro de uma mesma "
        "análise. O gráfico continua mostrando os nomes reais normalmente na sua tela; só o que "
        "é enviado para a IA é anonimizado.",
        "ok",
    ))
    story.append(PageBreak())

    # ---- 8. PDF ----
    story.append(Paragraph("8. Gerando o relatório em PDF", h1))
    story.append(Paragraph(
        "No final da página do dashboard, a seção \"Relatório completo em PDF\" monta um PDF "
        "com os KPIs e todos os gráficos visíveis na tela naquele momento — com os mesmos "
        "filtros e tipos de gráfico já escolhidos.",
        body,
    ))
    story.append(passo("1", "Clique em \"Gerar PDF do relatório\"", "Pode levar até um minuto — cada gráfico é desenhado individualmente."))
    story.append(passo("2", "Aguarde o botão \"Baixar PDF gerado\" aparecer"))
    story.append(callout(
        "Se mudar algum filtro depois de gerar, clique no botão de novo — o arquivo já baixado "
        "não se atualiza sozinho. Conteúdo dentro de um expansor recolhido não entra no PDF, só "
        "o que já está visível na tela por padrão.",
        "dica",
    ))
    story.append(PageBreak())

    # ---- 9. FAQ ----
    story.append(Paragraph("9. Perguntas frequentes", h1))
    faq = [
        ("Esqueci minha senha.", "Fale com a pessoa administradora — a redefinição é feita por ela; não existe \"esqueci minha senha\" automático."),
        ("Um gráfico que eu esperava ver não aparece.", "Ele depende de um campo que não foi mapeado (ou, no caso dos dois gráficos exclusivos do PAT, não está disponível via CSV — ver seção 6). Volte em \"Importar Dados\" e confira o mapeamento."),
        ("Meu PAT do Azure DevOps é seguro para usar aqui?", "Sim — nunca é salvo em disco/banco/configurações do app; fica só na memória da sua sessão de navegador e some ao sair."),
        ("Preciso pedir acesso de novo se meu login parar de funcionar?", "Não necessariamente — confirme primeiro com a pessoa administradora se sua conta ainda existe/está ativa."),
        ("Importar um arquivo novo apaga o anterior?", "Sim, sempre substitui — não acumula dados de importações diferentes."),
        ("Não vejo o botão \"Analisar com IA\" em nenhum gráfico.", "Esse recurso depende de uma automação configurada pela pessoa administradora, por fora do app — sem ela configurada, o botão simplesmente não aparece em lugar nenhum. Confirme com a pessoa administradora se o recurso está habilitado no seu ambiente."),
    ]
    for pergunta, resposta in faq:
        story.append(KeepTogether([
            Paragraph(pergunta, h3),
            Paragraph(resposta, body),
        ]))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=6))
    story.append(Paragraph(
        "Dúvidas que não estão aqui: fale com a pessoa administradora do seu ambiente. Este guia "
        "também está disponível, sempre atualizado, na página \"Sobre o App\" dentro do próprio "
        "painel.",
        footer_style,
    ))

    return story


def gerar_pdf_bytes() -> bytes:
    """
    Monta o PDF inteiro em memória e devolve os bytes prontos - sem tocar em
    nenhum arquivo em disco. É a função reaproveitada tanto pelo botão de
    Administração (que grava o resultado no Turso) quanto pelo script de
    linha de comando (que grava um arquivo local).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        title="Painel de Qualidade - Guia Completo do Usuário",
    )
    doc.build(_montar_story(), onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()


def hash_conteudo_atual() -> str:
    """
    "Impressão digital" (hash) do CONTEÚDO do guia que o código rodando agora
    geraria - calculada a partir do código-fonte de `_montar_story` (o
    texto, os passos, as tabelas, os avisos - tudo que aparece de fato no
    PDF), não do PDF em si. Isso importa porque dois PDFs gerados a partir
    do MESMO conteúdo nunca são byte-a-byte idênticos entre si (o reportlab
    embute a data/hora de criação em cada geração) - comparar os PDFs
    diretamente sempre acusaria "diferente", mesmo sem nenhuma mudança real.

    Comparando este hash com o hash salvo junto da última versão gerada (ver
    `core/config_app.py::CHAVE_GUIA_PDF_HASH`), a Administração consegue
    mostrar "há uma alteração de conteúdo ainda não enviada para o PDF" de
    forma confiável, e sabe dizer "sem alterações pendentes" quando o código
    não mudou desde a última vez que alguém clicou em gerar.
    """
    codigo_fonte = inspect.getsource(_montar_story)
    return hashlib.sha256(codigo_fonte.encode("utf-8")).hexdigest()


# core/gerador_guia_pdf.py -> core -> raiz do projeto -> assets/
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_CAMINHO_GUIA_PDF_FALLBACK = _ASSETS_DIR / "Guia_do_Usuario_QA.pdf"


def obter_bytes_pdf_atual() -> Optional[bytes]:
    """
    Bytes do PDF "Guia Completo do Usuário" já prontos para oferecer como
    download - mesma lógica usada por `ui/pages/sobre_page.py` (antes
    duplicada lá, agora centralizada aqui para qualquer outra tela reutilizar,
    ex.: o modal de "novidades" pós-login em `ui/novidades.py`). Prioridade:
    (1) versão gravada no banco de dados (Turso) pelo botão de Administração -
    é a fonte "viva", que sobrevive a reinícios/redeploys mesmo em hospedagem
    com disco temporário (Streamlit Community Cloud); (2) se ainda não existir
    nenhuma lá, cai para o arquivo padrão já incluído no repositório. Qualquer
    falha ao falar com o banco é silenciosa aqui, com o mesmo fallback - este
    PDF é só um material de apoio, não deve travar nenhuma tela por causa dele.
    """
    # Import local (não no topo do arquivo) para evitar import circular: este
    # módulo é importado bem cedo (ex.: por scripts de linha de comando que
    # não têm nada a ver com o banco de dados), e `core.config_app` puxa
    # `core.turso_client` só por causa desta função específica.
    from core.config_app import CHAVE_GUIA_PDF_BASE64, obter_configuracao

    try:
        base64_pdf = obter_configuracao(CHAVE_GUIA_PDF_BASE64)
    except Exception:
        base64_pdf = None
    if base64_pdf:
        try:
            return base64.b64decode(base64_pdf)
        except (ValueError, TypeError):
            pass
    if _CAMINHO_GUIA_PDF_FALLBACK.exists():
        return _CAMINHO_GUIA_PDF_FALLBACK.read_bytes()
    return None
