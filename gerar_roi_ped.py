from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

ORANGE = colors.HexColor("#E8542A")
DARK = colors.HexColor("#20242E")
GRAY = colors.HexColor("#6B7080")
LIGHT_BG = colors.HexColor("#FCEBE4")
LINE = colors.HexColor("#E4E1DD")

styles = getSampleStyleSheet()

kicker = ParagraphStyle(
    "kicker", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=8.5, textColor=ORANGE, leading=11, spaceAfter=4,
)
title = ParagraphStyle(
    "title", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=18.5, textColor=DARK, leading=22, spaceAfter=8, alignment=0,
)
intro = ParagraphStyle(
    "intro", parent=styles["Normal"], fontName="Helvetica",
    fontSize=9.2, textColor=DARK, leading=13.3, spaceAfter=10,
)
h2 = ParagraphStyle(
    "h2", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=10.5, textColor=ORANGE, spaceBefore=8, spaceAfter=5,
)
bullet = ParagraphStyle(
    "bullet", parent=styles["Normal"], fontName="Helvetica",
    fontSize=8.6, textColor=DARK, leading=12.2, spaceAfter=5,
    leftIndent=12, bulletIndent=0,
)
callout_label = ParagraphStyle(
    "callout_label", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=8.3, textColor=ORANGE, leading=10.5,
)
callout_value = ParagraphStyle(
    "callout_value", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=20, textColor=DARK, leading=23, spaceAfter=2,
)
callout_sub = ParagraphStyle(
    "callout_sub", parent=styles["Normal"], fontName="Helvetica",
    fontSize=7.8, textColor=GRAY, leading=10.8,
)
table_header = ParagraphStyle(
    "table_header", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=8, textColor=colors.white, leading=10,
)
table_cell = ParagraphStyle(
    "table_cell", parent=styles["Normal"], fontName="Helvetica",
    fontSize=8.2, textColor=DARK, leading=11,
)
table_cell_bold = ParagraphStyle(
    "table_cell_bold", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=8.2, textColor=DARK, leading=11,
)
footer_style = ParagraphStyle(
    "footer", parent=styles["Normal"], fontName="Helvetica",
    fontSize=7, textColor=GRAY,
)
italic_note = ParagraphStyle(
    "italic_note", parent=styles["Normal"], fontName="Helvetica-Oblique",
    fontSize=7.6, textColor=GRAY, leading=10.5,
)

doc = SimpleDocTemplate(
    "resumo_executivo_roi_qa.pdf",
    pagesize=A4,
    topMargin=16 * mm,
    bottomMargin=14 * mm,
    leftMargin=16 * mm,
    rightMargin=16 * mm,
    title="Indicadores - QA - Analise de ROI",
)

story = []

story.append(Paragraph("INDICADORES - QA &mdash; DASHBOARD DE M&Eacute;TRICAS DE TI", kicker))
story.append(Paragraph("An&aacute;lise de Retorno sobre Investimento (ROI)", title))
story.append(HRFlowable(width="100%", thickness=1.1, color=ORANGE, spaceAfter=10))

story.append(Paragraph(
    "A transi&ccedil;&atilde;o do acompanhamento de QA de relat&oacute;rios manuais e fragmentados "
    "(planilhas, capturas de tela e PowerPoint) para o dashboard automatizado <b>Indicadores - QA</b> "
    "eliminou o trabalho manual repetitivo da equipe de testes, integrando-se diretamente ao Azure "
    "DevOps para consolidar dados em tempo real, prontos para respaldar decis&otilde;es da lideran&ccedil;a "
    "com agilidade.",
    intro,
))

# Callout metric — leads with the defensible average, not the top-of-range figure
callout_cell = [
    Paragraph("M&Eacute;TRICA PRINCIPAL DE RETORNO", callout_label),
    Spacer(1, 3),
    Paragraph("R$ 13.950,00 / ano", callout_value),
    Spacer(1, 3),
    Paragraph(
        "Economia estimada considerando o custo total CLT carregado (encargos patronais + "
        "provis&otilde;es). Pode chegar a <b>R$ 15.950,00/ano</b> no cen&aacute;rio de maior "
        "economia de tempo, e cai para <b>R$ 11.960,00/ano</b> no cen&aacute;rio mais conservador.",
        ParagraphStyle("calloutdesc", parent=styles["Normal"], fontName="Helvetica",
                        fontSize=8.4, textColor=DARK, leading=12),
    ),
]
callout_table = Table([[callout_cell]], colWidths=[178 * mm])
callout_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
    ("BOX", (0, 0), (-1, -1), 0.75, ORANGE),
    ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ("TOPPADDING", (0, 0), (-1, -1), 9),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
]))
story.append(callout_table)
story.append(Spacer(1, 12))

story.append(Paragraph("ECONOMIA DIRETA DE TEMPO E RECURSOS (2 QAs)", h2))
story.append(Paragraph(
    "<b>Tempo economizado:</b> 5 a 10 horas semanais combinadas entre os 2 QAs "
    "(ponto m&eacute;dio de 7,5h/semana) antes gastas na compila&ccedil;&atilde;o e "
    "formata&ccedil;&atilde;o manual de relat&oacute;rios.",
    bullet,
))

calc_data = [
    [Paragraph("Base de c&aacute;lculo", table_header),
     Paragraph("Economia mensal", table_header),
     Paragraph("Economia anual", table_header)],
    [Paragraph("Sal&aacute;rio bruto", table_cell),
     Paragraph("R$ 445 &ndash; 885<br/><font color='#6B7080'>m&eacute;dia R$ 665</font>", table_cell),
     Paragraph("R$ 5.330 &ndash; 10.620<br/><font color='#6B7080'>m&eacute;dia R$ 7.975</font>", table_cell)],
    [Paragraph("Custo total CLT (carregado)", table_cell_bold),
     Paragraph("R$ 997 &ndash; 1.330<br/><font color='#6B7080'>m&eacute;dia R$ 1.163</font>", table_cell_bold),
     Paragraph("R$ 11.960 &ndash; 15.950<br/><font color='#6B7080'>m&eacute;dia R$ 13.950</font>", table_cell_bold)],
]
calc_table = Table(calc_data, colWidths=[55 * mm, 61.5 * mm, 61.5 * mm])
calc_table.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), DARK),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("GRID", (0, 0), (-1, -1), 0.5, LINE),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#FBF6F3")),
]))
story.append(calc_table)
story.append(Paragraph(
    "Faixa de custo-hora usada: R$ 20,45 (base bruta, divisor de 220h/m&ecirc;s) a "
    "R$ 30,68&ndash;40,91 (base CLT carregada, aproxima&ccedil;&atilde;o de mercado de 50% a 100% "
    "de encargos sobre o bruto &mdash; recomenda-se confirmar o percentual exato com o "
    "financeiro/RH).",
    italic_note,
))

story.append(Paragraph("BENEF&Iacute;CIOS ADICIONAIS (N&Atilde;O QUANTIFICADOS)", h2))
story.append(Paragraph(
    "&bull; <b>Observabilidade em tempo real para o CIO:</b> vis&atilde;o executiva imediata das "
    "m&eacute;tricas de qualidade do Azure DevOps, sem depender da montagem manual da equipe.",
    bullet,
))
story.append(Paragraph(
    "&bull; <b>Elimina&ccedil;&atilde;o de interrup&ccedil;&otilde;es e silos:</b> dev leads, PMs e "
    "outras &aacute;reas consultam o dashboard diretamente, reduzindo a troca de contexto dos QAs.",
    bullet,
))
story.append(Paragraph(
    "&bull; <b>Mitiga&ccedil;&atilde;o antecipada de riscos:</b> tend&ecirc;ncias negativas ficam "
    "vis&iacute;veis mais cedo, reduzindo retrabalho e o risco de falhas chegarem &agrave; produ&ccedil;&atilde;o.",
    bullet,
))

story.append(Spacer(1, 4))
story.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=6))
story.append(Paragraph(
    "<b>Nota de infraestrutura:</b> o Indicadores - QA opera no Streamlit Community Cloud com custo de "
    "hospedagem zero, com uma c&oacute;pia de fallback gratuita configurada no Render (via Docker) "
    "para garantir continuidade em eventuais instabilidades do servi&ccedil;o principal.",
    italic_note,
))

story.append(Spacer(1, 10))
story.append(Paragraph(
    "Indicadores - QA &mdash; Relat&oacute;rio de Retorno de Investimento (ROI) &nbsp;|&nbsp; "
    "Confidencial &ndash; apenas para lideran&ccedil;a",
    footer_style,
))

doc.build(story)
print("OK")
