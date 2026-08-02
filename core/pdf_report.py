"""
Geração do "Relatório Completo em PDF" do dashboard.

O botão "Gerar PDF do relatório" (ver `ui.pages.dashboard_page.render_dashboard_page`,
no final da página) monta, durante o próprio desenho de cada seção do
dashboard, uma lista `secoes_pdf` com {"titulo": ..., "fig": <mesma Figure
Plotly desenhada na tela>} (ver `ui.pages.dashboard_page._plotar`). Essa
lista só é passada pra `gerar_pdf_relatorio` (função deste módulo) depois
que TODAS as seções já foram desenhadas - ou seja, o PDF nunca "desalinha"
do que está sendo mostrado: mesmos filtros aplicados (Período/Projeto/Tipos
de Teste/Status), mesmo tipo de gráfico escolhido em cada seção, mesma
ordem, e o gráfico personalizado só entra se o usuário já tiver gerado um.

Conteúdo dentro de expansores recolhidos na tela (ex.: tabela de dados
detalhados, detalhamento de itens sem Coluna do Board) NÃO entra no PDF -
só o que já está visível por padrão.

Cada gráfico Plotly é rasterizado como PNG via `kaleido` (ver comentário em
requirements.txt sobre a versão usada - precisou ser >=1.0 por causa de um
bug do kaleido 0.2.1 no Windows com espaço no caminho do projeto) e o
documento em si é montado com `reportlab`. O kaleido>=1.0 procura um
Chrome/Chromium/Edge/Brave já instalado no sistema e só baixa um "Chrome
for Testing" próprio (uma vez só, com acesso à internet) se não achar
nenhum - ver `_rasterizar_com_fallback_de_chrome`. No Streamlit Community
Cloud, o pacote `chromium` do `packages.txt` (raiz do projeto) garante que
sempre existe um navegador do sistema pronto pra uso - ver comentário
detalhado logo acima de `_chrome_download_ok`, abaixo.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Optional

import kaleido
import plotly.graph_objects as go
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Mesma paleta "de marca" de `ui/theme.py` (não importa de lá de propósito -
# este módulo não depende de Streamlit/da camada de UI, só de reportlab/
# plotly, pra poder ser testado e reaproveitado de forma isolada).
COR_PRIMARIA = colors.HexColor("#F15A24")
COR_TEXTO = colors.HexColor("#1A1A1A")
COR_CINZA = colors.HexColor("#6B6B6B")
COR_BORDA = colors.HexColor("#ECEBE6")
COR_FUNDO_KPI = colors.HexColor("#FAF6F0")

MARGEM = 2 * cm
LARGURA_UTIL = A4[0] - 2 * MARGEM


class ErroGeracaoPdf(Exception):
    """
    Erro "amigável" de geração de PDF - a mensagem já vem pronta pra ser
    mostrada direto na tela (`st.error`, ver `ui.pages.dashboard_page`),
    em vez de deixar o traceback cru do kaleido/reportlab estourar a
    aplicação inteira.
    """


# kaleido>=1.0 já procura sozinho, na ordem: (1) um "Chrome for Testing"
# baixado anteriormente por ele mesmo (se já existir no disco), (2) um
# Chrome/Chromium/Edge/Brave já instalado no sistema (via PATH, registro do
# Windows, ou caminhos típicos tipo /usr/bin/chromium no Linux). Só quando
# NENHUM dos dois existe é que vale a pena baixar um (~100MB, só na primeira
# vez) - por isso a estratégia abaixo é "tenta renderizar primeiro" (rápido,
# e funciona de cara pra quem já tem algum desses navegadores instalado) e
# só aciona o download como recuperação de um erro real. `_chrome_download_ok`/
# `_mensagem_erro_chrome` evitam repetir uma tentativa de download que já
# falhou uma vez pra cada gráfico seguinte do mesmo PDF (senão, um problema
# de rede faria o app tentar baixar de novo - e demorar de novo - pra cada
# um dos ~15 gráficos do relatório, em vez de falhar rápido depois da 1ª vez).
#
# No Streamlit Community Cloud, o container é minimalista: não tem NENHUM
# Chrome/Chromium instalado, então cai sempre no caso (2) - baixa um "Chrome
# for Testing" próprio. Só que esse binário baixado também precisa de
# bibliotecas do sistema (libnss3, libgtk-3-0, libasound2 etc.) pra
# CONSEGUIR ABRIR, e o container não tem elas por padrão - o download
# funciona, mas o navegador baixado "fecha sozinho ao iniciar"
# (erro "The browser seemed to close immediately after starting"). Por
# isso existe o `packages.txt` na raiz do projeto, com a linha `chromium`:
# ele manda o Streamlit Community Cloud instalar o Chromium do sistema via
# apt ANTES do app rodar, o que já traz essas bibliotecas junto (como
# dependência do pacote) - suficiente pra qualquer Chrome/Chromium (inclusive
# um "Chrome for Testing" já baixado antes) conseguir abrir.
_chrome_download_ok = False
_mensagem_erro_chrome: Optional[str] = None


def _rasterizar(fig: go.Figure) -> bytes:
    return fig.to_image(format="png", width=1400, height=760, scale=2)


def _rasterizar_com_fallback_de_chrome(fig: go.Figure) -> bytes:
    global _chrome_download_ok, _mensagem_erro_chrome
    try:
        return _rasterizar(fig)
    except Exception as erro_render:  # noqa: BLE001 - qualquer falha pode ser "sem navegador"
        if _mensagem_erro_chrome is not None:
            raise ErroGeracaoPdf(_mensagem_erro_chrome) from erro_render

        if not _chrome_download_ok:
            try:
                kaleido.get_chrome_sync()
                _chrome_download_ok = True
            except Exception as erro_download:  # noqa: BLE001 - rede, permissão, etc.
                _mensagem_erro_chrome = (
                    "Não foi possível transformar os gráficos em imagem para o PDF: "
                    "nenhum navegador compatível (Chrome/Edge/Brave) foi encontrado no "
                    "sistema, e o download automático de um navegador próprio pelo "
                    "kaleido também falhou. Verifique sua conexão com a internet e "
                    "tente gerar o PDF de novo. Se o problema persistir, com o "
                    "ambiente virtual do projeto ativado, rode `plotly_get_chrome` no "
                    f"terminal e tente novamente.\n\nDetalhe técnico: {erro_download}"
                )
                raise ErroGeracaoPdf(_mensagem_erro_chrome) from erro_download

        try:
            return _rasterizar(fig)
        except Exception as erro_retry:
            _mensagem_erro_chrome = (
                "Não foi possível transformar um dos gráficos em imagem para o PDF, "
                f"mesmo após preparar o navegador.\n\nDetalhe técnico: {erro_retry}"
            )
            raise ErroGeracaoPdf(_mensagem_erro_chrome) from erro_retry


def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "titulo_capa": ParagraphStyle(
            "TituloCapa", parent=base["Title"], textColor=COR_PRIMARIA,
            fontName="Helvetica-Bold", fontSize=20, leading=24, spaceAfter=4, alignment=0,
        ),
        "subtitulo_capa": ParagraphStyle(
            "SubtituloCapa", parent=base["Normal"], textColor=COR_CINZA, fontSize=10, leading=14,
        ),
        "secao": ParagraphStyle(
            "Secao", parent=base["Heading2"], textColor=COR_TEXTO,
            fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=16, spaceAfter=8,
        ),
        "aviso": ParagraphStyle(
            "Aviso", parent=base["Normal"], textColor=COR_CINZA, fontSize=9, leading=12, spaceAfter=3,
        ),
        "rodape": ParagraphStyle(
            "Rodape", parent=base["Normal"], textColor=COR_CINZA, fontSize=8, leading=11,
        ),
    }


def _figura_para_imagem(fig: go.Figure, largura_pt: float) -> Image:
    """
    Rasteriza uma figura Plotly (via kaleido) como PNG e devolve como
    `Image` do reportlab, já escalada pra largura útil da página.

    Trabalha sobre uma CÓPIA da figura recebida - nunca modifica o objeto
    original (que pode ainda estar referenciado em `st.session_state`/na
    tela). A única mudança aplicada na cópia é forçar fundo branco (na tela
    o gráfico é transparente sobre o fundo claro do app; a página do PDF é
    branca, então isso evita qualquer "mancha" visual).
    """
    copia = go.Figure(fig)
    copia.update_layout(
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        polar_bgcolor="#FFFFFF",
        font_color="#1A1A1A",
        # A margem apertada (10px) usada na tela (`_construir_figura`, em
        # `ui/pages/dashboard_page.py`) só funciona lá porque o gráfico é
        # responsivo/interativo - rasterizado num tamanho fixo pelo kaleido,
        # 10px não é suficiente pro título + números do eixo Y (eram
        # cortados, mostrando só "0" repetido). Aqui a margem é generosa de
        # propósito, já pensada pro tamanho fixo da imagem no PDF.
        margin=dict(l=90, r=50, t=60, b=80),
        font_size=15,
        legend=dict(font=dict(size=13)),
    )
    png_bytes = _rasterizar_com_fallback_de_chrome(copia)
    imagem = Image(io.BytesIO(png_bytes))
    proporcao = imagem.imageHeight / imagem.imageWidth
    imagem.drawWidth = largura_pt
    imagem.drawHeight = largura_pt * proporcao
    return imagem


def _tabela_kpis(kpis: list[tuple], estilos: dict[str, ParagraphStyle]) -> Table:
    """
    `kpis`: lista de tuplas (label, valor, ...) - mesmo formato aceito por
    `ui.components.render_kpi_row` (só os 2 primeiros itens de cada tupla
    são usados aqui; os demais, ex.: delta, são só um detalhe visual da
    tela que o PDF não precisa reproduzir).
    """
    estilo_label = ParagraphStyle(
        "KpiLabel", fontName="Helvetica", fontSize=8, textColor=COR_CINZA, leading=10,
    )
    estilo_valor = ParagraphStyle(
        "KpiValor", fontName="Helvetica-Bold", fontSize=15, textColor=COR_TEXTO, leading=18, spaceBefore=2,
    )

    linha_label = [Paragraph(str(label).upper(), estilo_label) for label, *_ in kpis]
    linha_valor = [Paragraph(str(valor), estilo_valor) for _, valor, *_ in kpis]

    largura_coluna = LARGURA_UTIL / max(len(kpis), 1)
    tabela = Table([linha_label, linha_valor], colWidths=[largura_coluna] * len(kpis))
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COR_FUNDO_KPI),
                ("BOX", (0, 0), (-1, -1), 0.75, COR_BORDA),
                ("INNERGRID", (0, 0), (-1, -1), 0.75, COR_BORDA),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return tabela


def gerar_pdf_relatorio(
    *,
    secoes: list[dict[str, Any]],
    kpis: list[tuple],
    nome_arquivo_origem: str,
    total_registros: int,
    resumo_filtros: list[str],
    logo_bytes: Optional[bytes] = None,
) -> bytes:
    """
    Monta o PDF completo e devolve os bytes prontos para `st.download_button`.

    `secoes`: lista de dicts {"titulo": str, "fig": plotly.graph_objects.Figure},
    já na ordem em que devem aparecer no PDF (ver `ui.pages.dashboard_page`).
    `kpis`: mesma lista de tuplas passada pra `ui.components.render_kpi_row`.
    `resumo_filtros`: linhas de texto já prontas descrevendo os filtros
    aplicados (ver `ui.pages.dashboard_page._montar_resumo_filtros_ativos`).
    `logo_bytes`: bytes do PNG da logo (opcional) - se não vier, o PDF
    simplesmente não tem logo no topo, sem erro.

    Levanta `ErroGeracaoPdf` (com mensagem já pronta pra exibir na tela) se
    o navegador usado para rasterizar os gráficos não puder ser preparado,
    ou se algum gráfico específico falhar ao virar imagem.
    """
    estilos = _estilos()
    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=MARGEM,
        bottomMargin=MARGEM,
        title="Relatório de Indicadores de Qualidade - Refuturiza QA",
    )

    elementos: list = []

    if logo_bytes:
        try:
            logo = Image(io.BytesIO(logo_bytes))
            proporcao = logo.imageHeight / logo.imageWidth
            logo.drawWidth = 3 * cm
            logo.drawHeight = 3 * cm * proporcao
            elementos.append(logo)
            elementos.append(Spacer(1, 8))
        except Exception:
            # Uma logo corrompida/ilegível nunca deve impedir o resto do PDF.
            pass

    elementos.append(Paragraph("Relatório de Indicadores de Qualidade", estilos["titulo_capa"]))
    elementos.append(Paragraph("Refuturiza QA", estilos["subtitulo_capa"]))
    elementos.append(Spacer(1, 10))

    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    linhas_cabecalho = [
        f"Gerado em: {agora}",
        f"Arquivo de origem: {nome_arquivo_origem}",
        f"Total de registros (com os filtros aplicados): {total_registros:,}".replace(",", "."),
        *resumo_filtros,
    ]
    for linha in linhas_cabecalho:
        elementos.append(Paragraph(linha, estilos["aviso"]))
    elementos.append(Spacer(1, 14))

    if kpis:
        elementos.append(_tabela_kpis(kpis, estilos))
        elementos.append(Spacer(1, 6))

    for secao in secoes:
        bloco = [
            Paragraph(secao["titulo"], estilos["secao"]),
            _figura_para_imagem(secao["fig"], LARGURA_UTIL),
        ]
        elementos.append(KeepTogether(bloco))

    elementos.append(Spacer(1, 16))
    elementos.append(
        Paragraph(
            "Gerado automaticamente pelo painel Refuturiza QA. Não inclui conteúdo de "
            "expansores recolhidos na tela (ex.: tabela de dados detalhados, "
            "detalhamento de itens sem Coluna do Board).",
            estilos["rodape"],
        )
    )

    documento.build(elementos)
    return buffer.getvalue()
