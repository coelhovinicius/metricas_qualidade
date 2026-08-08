"""
Constantes visuais e CSS customizado da aplicação.

As cores abaixo espelham exatamente o `.streamlit/config.toml`, para que
componentes customizados (cards, overlay de carregamento, cabeçalho) fiquem
visualmente consistentes com o tema nativo do Streamlit.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

import streamlit as st

from core.analytics import ORDEM_COLUNAS_BOARD

PRIMARY_COLOR = "#F15A24"
BACKGROUND_COLOR = "#FAF6F0"
SECONDARY_BACKGROUND_COLOR = "#FFFFFF"
TEXT_COLOR = "#1A1A1A"

# Paleta "de marca" original, com 8 matizes - hoje usada só como destaque
# pontual (a linha de % acumulado do gráfico de Pareto, `PALETA_GRAFICOS[7]`
# em `ui/pages/dashboard_page.py`). A coloração categoria-a-categoria de
# TODOS os gráficos (barras, pizza, treemap etc.) usa a `PALETA_COLORIDA`
# bem mais ampla logo abaixo - pedido explícito de ter o máximo de cores
# possível em vez de um esquema restrito. Mantida por compatibilidade com
# esse uso pontual; se não for mais referenciada em nenhum outro lugar,
# pode ser removida no futuro.
PALETA_GRAFICOS = [
    "#F15A24",  # laranja (marca)
    "#2a78d6",  # azul
    "#1baf7a",  # água
    "#eda100",  # amarelo
    "#e87ba4",  # magenta
    "#008300",  # verde
    "#4a3aa7",  # violeta
    "#e34948",  # vermelho
]
PALETA_STATUS = {
    "Passou": "#2E7D5B",
    "Falhou": "#F15A24",
    "Planejado": "#E0A93E",
    "Outro": "#8C8C8C",
    "Não informado": "#C9C2B8",
}

# Cores do gráfico "Bugs Abertos vs. Solucionados" - mesma paleta semântica de
# PALETA_STATUS (verde = resolvido, laranja = ainda é trabalho ativo da QA),
# com o âmbar de "Planejado" reaproveitado para "aguardando validação
# externa" (não é nem "resolvido" nem "trabalho pendente da QA" - é uma
# espera fora do controle do time).
PALETA_BUGS_TEMPO = {
    "Em Andamento (QA)": "#F15A24",
    "Aguardando Validação Externa": "#E0A93E",
    "Finalizado": "#2E7D5B",
}

# Paleta "arco-íris": bem mais ampla e variada que PALETA_GRAFICOS (8 tons),
# usada como padrão em TODOS os gráficos categóricos do painel - pedido
# explícito de ter o máximo de cores possível, bem coloridas, pra destacar
# bem a diferença entre categorias, em vez de um esquema restrito/específico
# (as tentativas anteriores - só 8 cores, depois uma extensão que começava
# repetindo essas mesmas 8 - ficavam "sem graça"/pouco variadas pro gosto
# pedido). 30 tons nitidamente diferentes entre si (inclusive tons "primos"
# tratados como cores separadas de propósito, ex.: azul/azul claro/azul
# marinho, laranja claro/laranja escuro, roxo/lilás/ameixa/violeta - dá pra
# escolher entre eles porque o pedido foi por variedade, não por mínimo
# necessário).
#
# IMPORTANTE sobre a ORDEM da lista (bug corrigido nesta versão): gráficos
# com poucas categorias usam sempre as primeiras posições da lista, na
# ordem em que aparecem aqui (Plotly colore por posição - 1ª categoria leva
# a cor 0, 2ª leva a cor 1, etc.). Na primeira versão desta paleta as cores
# estavam agrupadas por família (azul, azul claro e azul marinho uma atrás
# da outra; depois verde, verde claro, verde escuro...) - então QUALQUER
# gráfico com só 2 ou 3 categorias (ex.: "Passou vs. Não Passou") acabava
# pegando 2-3 tons de azul entre si, todos parecidos, exatamente o problema
# de "cores confusas" reportado. Agora as cores estão intercaladas: cada
# posição vem de uma família de cor diferente da vizinha (azul, verde,
# vermelho, amarelo, rosa, roxo, laranja, magenta...), e só depois de
# passar por toda a variedade de famílias é que aparecem as variações
# claras/escuras da mesma família - assim, não importa quantas categorias
# o gráfico tiver (2, 3, 5, 10...), as cores usadas sempre vêm de famílias
# bem diferentes entre si primeiro. Conferido programaticamente: com as 2 a
# 8 primeiras cores da lista, a diferença mínima entre elas ainda é grande
# (bem acima do que a primeira versão, agrupada por família, conseguia).
# PALETA_GRAFICOS (8 cores) continua existindo só pelo uso pontual que já
# tinha fora de "colorir categoria por categoria" (a linha de % acumulado
# do gráfico de Pareto).
PALETA_COLORIDA = [
    "#2A78D6",  # azul
    "#1DB954",  # verde
    "#E63946",  # vermelho
    "#F4C430",  # amarelo
    "#E8578B",  # rosa
    "#8E44AD",  # roxo
    "#F15A24",  # laranja
    "#D6007F",  # magenta
    "#00B8A9",  # turquesa
    "#795548",  # marrom
    "#607D8B",  # cinza azulado
    "#5AC8FA",  # azul claro
    "#8BC34A",  # verde claro
    "#FF6F61",  # coral
    "#C9A227",  # dourado
    "#FF4FA3",  # rosa choque
    "#5E3B9C",  # violeta
    "#FFA552",  # laranja claro
    "#006D77",  # azul petróleo
    "#3A4750",  # cinza carvão
    "#0B3D66",  # azul marinho
    "#1B5E20",  # verde escuro
    "#9C1D1D",  # vermelho escuro
    "#FFE066",  # amarelo claro
    "#B39DDB",  # lilás
    "#C1440E",  # laranja escuro
    "#17BECF",  # ciano
    "#B2D732",  # verde lima
    "#6A3B6E",  # ameixa
    "#808000",  # verde oliva
]

ROTULO_NAO_ATRIBUIDO_BOARD = "Não atribuído(a)"

PALETA_COLUNA_BOARD: dict[str, str] = {
    nome: PALETA_COLORIDA[indice % len(PALETA_COLORIDA)]
    for indice, nome in enumerate(ORDEM_COLUNAS_BOARD)
}
PALETA_COLUNA_BOARD[ROTULO_NAO_ATRIBUIDO_BOARD] = "#8C8C8C"


def cor_discreta_coluna_board(valores_presentes) -> dict[str, str]:
    """
    Monta o `color_discrete_map` da Coluna do Board a partir da paleta fixa
    acima (`PALETA_COLUNA_BOARD`), e completa - sem repetir nenhuma cor já
    usada - qualquer valor que apareça nos dados mas não esteja na lista
    oficial (coluna com nome próprio de algum time). Recebe os valores
    realmente presentes no gráfico (não a lista oficial inteira) pra não
    gerar mapa maior do que o necessário.
    """
    mapa = dict(PALETA_COLUNA_BOARD)
    cores_livres = [cor for cor in PALETA_COLORIDA if cor not in mapa.values()]
    indice_extra = 0
    for valor in sorted(str(valor) for valor in valores_presentes if str(valor) not in mapa):
        if indice_extra < len(cores_livres):
            mapa[valor] = cores_livres[indice_extra]
        else:
            mapa[valor] = PALETA_COLORIDA[indice_extra % len(PALETA_COLORIDA)]
        indice_extra += 1
    return mapa


# ==============================================================================
# Esquema de cores fixo para indicadores de CRITICIDADE (severidade/prioridade)
# ==============================================================================
# Pedido explícito: ao contrário de PALETA_COLORIDA (cor por POSIÇÃO, sem
# significado), aqui a cor tem que ter sempre o mesmo SIGNIFICADO em
# qualquer indicador que meça criticidade, no app inteiro:
#   Crítica/maior criticidade -> sempre vermelho
#   Alta                      -> sempre amarelo
#   Média                     -> sempre verde
#   Baixa/menor criticidade   -> sempre azul (só existe com 4 níveis)
# As cores usadas são as mesmas de PALETA_COLORIDA (vermelho/amarelo/verde/
# azul já presentes nela), só reordenadas por significado em vez de posição.

_VERMELHO_CRITICIDADE = "#E63946"
_AMARELO_CRITICIDADE = "#F4C430"
_VERDE_CRITICIDADE = "#1DB954"
_AZUL_CRITICIDADE = "#2A78D6"

# Com 3 níveis: vermelho (maior) / amarelo (média) / verde (menor) - sem azul
# (pedido explícito: "Caso só haja 3 opções de criticidade, utiliza vermelho
# para a maior criticidade, amarelo para média e verde para baixa").
_CORES_CRITICIDADE_3_NIVEIS = (_VERMELHO_CRITICIDADE, _AMARELO_CRITICIDADE, _VERDE_CRITICIDADE)
# Com 4 níveis: vermelho / amarelo / verde / azul.
_CORES_CRITICIDADE_4_NIVEIS = (_VERMELHO_CRITICIDADE, _AMARELO_CRITICIDADE, _VERDE_CRITICIDADE, _AZUL_CRITICIDADE)


def _espectro_temperatura_criticidade(quantidade: int) -> list[str]:
    """
    Espectro de temperatura do mais quente (vermelho, mais crítico) ao mais
    frio (azul, menos crítico), interpolado linearmente em N tons - usado
    quando há MAIS de 4 níveis de criticidade (pedido explícito: "Caso haja
    mais cores, faça um espectro de temperatura, do mais quente ao mais
    frio"). As pontas do espectro são as mesmas cores vermelho/azul usadas
    nos esquemas de 3/4 níveis, pra manter consistência visual entre eles.
    """
    if quantidade <= 1:
        return [_VERMELHO_CRITICIDADE]
    inicio = (0xE6, 0x39, 0x46)  # vermelho
    fim = (0x2A, 0x78, 0xD6)  # azul
    cores = []
    for indice in range(quantidade):
        fracao = indice / (quantidade - 1)
        r = round(inicio[0] + (fim[0] - inicio[0]) * fracao)
        g = round(inicio[1] + (fim[1] - inicio[1]) * fracao)
        b = round(inicio[2] + (fim[2] - inicio[2]) * fracao)
        cores.append(f"#{r:02X}{g:02X}{b:02X}")
    return cores


def cor_discreta_criticidade_ordenada(valores_do_mais_para_o_menos_critico: list[str]) -> dict[str, str]:
    """
    Recebe os valores de um indicador de criticidade JÁ NA ORDEM do mais
    crítico pro menos crítico e devolve o `color_discrete_map` fixo
    correspondente: vermelho/amarelo/verde para 3 níveis, +azul para 4
    níveis, ou um espectro de temperatura vermelho->azul para qualquer
    outra quantidade (1, 2, 5+).
    """
    quantidade = len(valores_do_mais_para_o_menos_critico)
    if quantidade == 3:
        cores = _CORES_CRITICIDADE_3_NIVEIS
    elif quantidade == 4:
        cores = _CORES_CRITICIDADE_4_NIVEIS
    else:
        cores = _espectro_temperatura_criticidade(quantidade)
    return dict(zip(valores_do_mais_para_o_menos_critico, cores))


# Palavras-chave (PT/EN, sem acento, minúsculas) usadas para tentar reconhecer
# a criticidade de um valor de texto livre - ordem = mais crítico primeiro.
_PALAVRAS_CHAVE_CRITICIDADE: tuple[tuple[int, tuple[str, ...]], ...] = (
    (0, ("critica", "critical", "blocker", "blocking", "urgente", "urgent")),
    (1, ("alta", "alto", "high", "major")),
    (2, ("media", "medio", "medium", "normal", "moderate", "moderada", "moderado")),
    (3, ("baixa", "baixo", "low", "minor", "trivial")),
)

_PADRAO_PREFIXO_NUMERICO_CRITICIDADE = re.compile(r"^\s*(\d+)\s*[-–—.:)]")


def _normalizar_texto_criticidade(valor: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower()


def tentar_ordenar_criticidade(valores: list[str]) -> Optional[list[str]]:
    """
    Tenta descobrir, sozinho, a ordem "mais crítico -> menos crítico" de uma
    lista de valores de TEXTO LIVRE (ex.: o campo manual "Severity"/"Priority"
    do Azure DevOps, que não segue um vocabulário fixo de um projeto pro
    outro). Devolve a lista reordenada só quando consegue reconhecer TODOS os
    valores com confiança; devolve `None` quando não consegue - quem chamar
    deve então manter a paleta padrão (`PALETA_COLORIDA`) em vez de arriscar
    aplicar uma cor com o significado ERRADO (ex.: pintar "Baixa" de
    vermelho), o que seria pior do que não colorir de forma especial.

    Duas estratégias, nesta ordem:
      1. Prefixo numérico (padrão comum do Azure DevOps: "1 - Critical",
         "2 - High", "3 - Medium", "4 - Low") - quanto MENOR o número, mais
         crítico, mesma convenção nativa da ferramenta.
      2. Palavras-chave conhecidas em PT/EN (crítica/alta/média/baixa,
         critical/high/medium/low, e sinônimos comuns).
    """
    if not valores:
        return None

    prefixos: list[tuple[int, str]] = []
    todos_tem_prefixo = True
    for valor in valores:
        casamento = _PADRAO_PREFIXO_NUMERICO_CRITICIDADE.match(str(valor))
        if not casamento:
            todos_tem_prefixo = False
            break
        prefixos.append((int(casamento.group(1)), valor))
    if todos_tem_prefixo:
        return [valor for _, valor in sorted(prefixos, key=lambda item: item[0])]

    rankeados: list[tuple[int, str]] = []
    for valor in valores:
        texto_normalizado = _normalizar_texto_criticidade(valor)
        rank_encontrado = None
        for rank, palavras in _PALAVRAS_CHAVE_CRITICIDADE:
            if any(palavra in texto_normalizado for palavra in palavras):
                rank_encontrado = rank
                break
        if rank_encontrado is None:
            return None
        rankeados.append((rank_encontrado, valor))
    rankeados.sort(key=lambda item: item[0])
    return [valor for _, valor in rankeados]


def cor_discreta_criticidade(
    valores_presentes,
    ordem_conhecida: Optional[list[str]] = None,
) -> Optional[dict[str, str]]:
    """
    Monta o `color_discrete_map` de um indicador de criticidade qualquer.

    `ordem_conhecida`: quando o CHAMADOR já sabe de antemão a ordem "mais
    crítico -> menos crítico" (ex.: Severidade Calculada, que segue sempre
    `NIVEIS_SEVERIDADE_CALCULADA` em `core/analytics.py`), passa a lista
    completa aqui - a função só filtra pros valores realmente presentes,
    mantendo essa ordem. Sem isso (campo de texto livre, tipo o "Severity"
    manual do Azure DevOps), tenta descobrir a ordem sozinha via
    `tentar_ordenar_criticidade` - se não conseguir reconhecer todos os
    valores com confiança, devolve `None` (o app deve então manter a cor
    padrão de sempre, sem forçar nenhum esquema).
    """
    valores_presentes = {str(valor) for valor in valores_presentes}
    if not valores_presentes:
        return None
    if ordem_conhecida:
        ordenados = [valor for valor in ordem_conhecida if valor in valores_presentes]
        if len(ordenados) != len(valores_presentes):
            # Apareceu algum valor fora da lista oficial conhecida - não dá
            # pra confiar cegamente na ordem, então desiste (paleta padrão)
            # em vez de devolver um mapa incompleto silenciosamente.
            return None
    else:
        ordenados = tentar_ordenar_criticidade(sorted(valores_presentes))
        if ordenados is None:
            return None
    return cor_discreta_criticidade_ordenada(ordenados)


# ==============================================================================
# Cores FIXAS e ESTRITAS específicas do gráfico "Distribuição por
# Severidade/Prioridade" (campo manual "Severity"/"Priority" do Azure DevOps)
# ==============================================================================
# Pedido explícito do usuário, com prioridade sobre o esquema genérico de
# criticidade acima (`cor_discreta_criticidade`) especificamente para ESTE
# gráfico: em vez de tentar adivinhar a ordem por heurística, os 5 valores
# abaixo (vocabulário padrão de Severity do Azure DevOps, + o rótulo do
# próprio app para valor vazio) têm cor fixa garantida, sempre a mesma,
# reconhecidos por casamento EXATO (ignorando acento/maiúscula e um possível
# prefixo numérico tipo "1 - Critical"):
#   Critical           -> vermelho
#   High                -> laranja
#   Medium              -> amarelo
#   Low                 -> verde
#   Não atribuído(a)    -> azul (rótulo do app pra valor vazio - ver
#                          ROTULO_VAZIO_PADRAO em core/analytics.py)
_LARANJA_SEVERIDADE = "#F15A24"  # laranja de marca (PRIMARY_COLOR)

_CORES_SEVERIDADE_PRIORIDADE_POR_TEXTO_NORMALIZADO: dict[str, str] = {
    "critical": _VERMELHO_CRITICIDADE,
    "high": _LARANJA_SEVERIDADE,
    "medium": _AMARELO_CRITICIDADE,
    "low": _VERDE_CRITICIDADE,
    _normalizar_texto_criticidade("Não atribuído(a)"): _AZUL_CRITICIDADE,
}


def cor_discreta_severidade_prioridade(valores_presentes) -> dict[str, str]:
    """
    Mapa de cores ESTRITO pro gráfico "Distribuição por Severidade/Prioridade":
    Critical=vermelho, High=laranja, Medium=amarelo, Low=verde e
    "Não atribuído(a)"=azul, sempre - reconhecimento por casamento EXATO
    (não por palavra-chave/substring como `tentar_ordenar_criticidade`),
    ignorando acento/maiúscula e um possível prefixo numérico ("1 - Critical",
    "2 - High" etc., padrão comum do Azure DevOps).

    Diferente de `cor_discreta_criticidade`, esta função NUNCA devolve `None`:
    qualquer valor presente que não seja um dos 5 acima (ex.: alguém digitou
    um valor de Severity fora do padrão) ainda ganha uma cor, só que puxada
    da paleta colorida padrão do app (`PALETA_COLORIDA`) em vez de uma das 5
    cores fixas - assim o gráfico nunca fica com fatia sem cor nenhuma, mas
    os 5 valores conhecidos NUNCA mudam de cor por causa disso.
    """
    valores_presentes = {str(valor) for valor in valores_presentes}
    mapa: dict[str, str] = {}
    indice_cor_extra = 0
    for valor in sorted(valores_presentes):
        texto_sem_prefixo = valor
        casamento_prefixo = _PADRAO_PREFIXO_NUMERICO_CRITICIDADE.match(valor)
        if casamento_prefixo:
            texto_sem_prefixo = valor[casamento_prefixo.end():]
        cor = _CORES_SEVERIDADE_PRIORIDADE_POR_TEXTO_NORMALIZADO.get(
            _normalizar_texto_criticidade(texto_sem_prefixo)
        )
        if cor is None:
            cor = PALETA_COLORIDA[indice_cor_extra % len(PALETA_COLORIDA)]
            indice_cor_extra += 1
        mapa[valor] = cor
    return mapa


def injetar_css_global() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Poppins', -apple-system, sans-serif;
        }}

        /* ---------- Cabeçalho da aplicação ---------- */
        .refu-header {{
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 4px 0 20px 0;
            border-bottom: 2px solid {PRIMARY_COLOR}22;
            margin-bottom: 24px;
        }}
        .refu-header img {{
            height: 48px;
        }}
        .refu-header-texto {{
            background-color: {PRIMARY_COLOR};
            border-radius: 10px;
            padding: 10px 18px;
        }}
        .refu-header-titulo {{
            font-size: 1.05rem;
            font-weight: 600;
            color: #FFFFFF;
            line-height: 1.2;
        }}
        .refu-header-subtitulo {{
            font-size: 0.85rem;
            color: #FFEFE8;
        }}

        /* ---------- Cartões de KPI ---------- */
        .kpi-card {{
            background-color: {SECONDARY_BACKGROUND_COLOR};
            border: 1px solid #ecebe6;
            border-radius: 14px;
            padding: 18px 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            height: 100%;
        }}
        .kpi-card .kpi-label {{
            font-size: 0.8rem;
            font-weight: 600;
            color: #6b6b6b;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }}
        .kpi-card .kpi-valor {{
            font-size: 2rem;
            font-weight: 700;
            color: {TEXT_COLOR};
            margin-top: 4px;
        }}
        .kpi-card .kpi-delta {{
            font-size: 0.85rem;
            font-weight: 600;
            margin-top: 2px;
        }}
        .kpi-delta.positivo {{ color: #2E7D5B; }}
        .kpi-delta.negativo {{ color: {PRIMARY_COLOR}; }}

        /* ---------- Overlay de carregamento (bloqueia interação) ---------- */
        .loading-overlay {{
            position: fixed;
            inset: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(26, 26, 26, 0.62);
            backdrop-filter: blur(2px);
            z-index: 999999;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: #FFFFFF;
            font-size: 1.15rem;
            font-weight: 600;
            gap: 18px;
            pointer-events: all;
            cursor: not-allowed;
        }}
        .loading-spinner {{
            width: 46px;
            height: 46px;
            border: 4px solid rgba(255,255,255,0.35);
            border-top-color: {PRIMARY_COLOR};
            border-radius: 50%;
            animation: refu-spin 0.8s linear infinite;
        }}
        @keyframes refu-spin {{
            to {{ transform: rotate(360deg); }}
        }}

        /* ---------- Toggle "2 por linha" flutuante (dashboard) ---------- */
        /* Fica fixo num canto da tela, por cima do conteúdo, em vez de ocupar
           espaço lá no topo da página - continua acessível mesmo depois de
           rolar bastante pelos gráficos, sem precisar voltar ao topo pra
           trocar o layout. `st.container(key="dashboard_toggle_flutuante")`
           em dashboard_page.py gera a classe `st-key-dashboard_toggle_flutuante`
           usada aqui (mesma técnica dos botões acima). `width: fit-content`
           evita que o container flutuante estique pra largura inteira da
           tela (comportamento padrão dos blocos do Streamlit). z-index fica
           abaixo do overlay de carregamento (999999), mas acima de qualquer
           gráfico/conteúdo normal da página. */
        .st-key-dashboard_toggle_flutuante {{
            position: fixed;
            top: 84px;
            right: 28px;
            z-index: 9999;
            width: fit-content;
            max-width: 60vw;
            background-color: #FFFFFF;
            border: 1px solid #ecebe6;
            border-radius: 999px;
            padding: 6px 18px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.14);
        }}
        .st-key-dashboard_toggle_flutuante label {{
            margin-bottom: 0 !important;
        }}
        @media (max-width: 900px) {{
            .st-key-dashboard_toggle_flutuante {{
                top: auto;
                bottom: 18px;
                right: 14px;
                padding: 5px 14px;
            }}
        }}

        /* ---------- Card do formulário de login (antes era só um bloco solto) ---------- */
        div[data-testid="stForm"] {{
            background-color: {SECONDARY_BACKGROUND_COLOR};
            border: 1px solid #ecebe6;
            border-radius: 16px;
            padding: 30px 32px 22px 32px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.05);
        }}

        /* ---------- Espaçamentos mais compactos SÓ na tela de login ---------- */
        /* Objetivo: caber a tela inteira (até o botão "Solicitar acesso") sem
           precisar de F11 (tela cheia) num navegador em janela normal. O
           Streamlit reserva, por padrão, uma margem grande no topo do
           conteúdo principal (`padding-top` de ~96px, espaço pra uma barra de
           ferramentas que este app não usa) - some com boa parte do espaço
           disponível antes mesmo do cabeçalho aparecer.

           `:has()` (suportado por Chrome/Edge/Firefox atuais) permite mirar o
           contêiner principal (`stMainBlockContainer`) só QUANDO ele contém a
           marca `st-key-refu_tela_login` - ou seja, só na tela de login,
           deixando o espaçamento padrão intacto em todas as outras páginas do
           app (dashboard, importação, admin, etc.), que não têm esse
           problema e não devem ser afetadas por este ajuste. */
        /* 68px, não menos: o Streamlit desenha uma barra fixa no topo
           (ícone de menu, "Deploy" em modo desenvolvimento, etc.) com
           `position: absolute` e 60px de altura - ela não empurra o conteúdo
           pra baixo sozinha (`position: absolute` não ocupa espaço no fluxo
           normal), então um `padding-top` menor que a altura dela faz o
           cabeçalho da tela de login ficar por BAIXO dessa barra, cortado -
           68px = 60px da barra + uma folga pequena. */
        .stMainBlockContainer:has(.st-key-refu_tela_login) {{
            padding-top: 68px !important;
            padding-bottom: 40px !important;
        }}
        .st-key-refu_tela_login .refu-header {{
            padding: 4px 0 8px 0 !important;
            margin-bottom: 10px !important;
        }}
        .st-key-refu_tela_login div[data-testid="stForm"] {{
            padding: 16px 32px 12px 32px !important;
        }}
        .st-key-refu_tela_login div[data-testid="stForm"] h3 {{
            padding: 2px 0 10px 0 !important;
            margin-bottom: 12px !important;
        }}
        .st-key-refu_tela_login div[data-testid="stCaptionContainer"] {{
            margin: 2px 0 !important;
        }}
        /* Espaço entre os campos (Usuário/Senha/botão "Entrar") dentro do
           formulário, e entre os blocos fora dele (cartão do formulário,
           aviso de status, aviso de conta, botão "Solicitar acesso") - o
           padrão do Streamlit (16px) é confortável, mas em telas mais baixas
           ainda ajuda economizar um pouco aqui. */
        .st-key-refu_tela_login div[data-testid="stVerticalBlock"] {{
            gap: 10px !important;
        }}

        /* ---------- Título "Acesso ao Painel de Qualidade" ---------- */
        /* Antes tinha fundo laranja com fonte branca - agora é texto escuro sem
           fundo, só com uma linha fina abaixo pra separar do formulário. */
        div[data-testid="stForm"] h3 {{
            background-color: transparent;
            color: {TEXT_COLOR} !important;
            font-weight: 700;
            font-size: 1.3rem;
            padding: 2px 0 16px 0;
            border-radius: 0;
            border-bottom: 2px solid #ecebe6;
            text-align: center;
            margin-bottom: 20px;
        }}

        /* ---------- Botão "Entrar" do formulário de login: laranja, largura total ---------- */
        /* A lib de autenticação (streamlit-authenticator) monta o botão "Entrar"
           dentro de uma coluna interna própria - se essa coluna for mais estreita
           que o formulário (comum em libs de login mais antigas, que reservam só
           uma fração da largura pro botão), só dar `width: 100%` no botão não
           basta, porque 100% de uma coluna estreita continua estreito. Por isso,
           além de esticar o botão em si, força QUALQUER coluna dentro do
           formulário de login a ocupar a largura inteira (o formulário de login
           não tem nenhum layout lado-a-lado de propósito, então isso é seguro
           aqui - diferente do resto do app, onde colunas lado a lado são usadas
           de propósito e não devem ser afetadas). */
        div[data-testid="stForm"] div[data-testid="stHorizontalBlock"] {{
            display: block !important;
        }}
        div[data-testid="stForm"] div[data-testid="column"] {{
            width: 100% !important;
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }}
        /* Streamlit recentes encolhem o `stElementContainer` que embrulha o
           botão para o tamanho do próprio texto ("Entrar"), em vez de esticar
           pra largura do formulário - dar `width: 100%` só no botão (abaixo)
           não resolve, porque 100% de um contêiner que já encolheu pro
           conteúdo continua do tamanho do conteúdo. `:has()` acha esse
           contêiner específico (o que tem um `stFormSubmitButton` dentro),
           sem depender do nome de classe interno gerado a partir da label do
           botão (que muda se o texto "Entrar" mudar, e não é uma API
           garantida do Streamlit). */
        div[data-testid="stForm"] div[data-testid="stElementContainer"]:has(div[data-testid="stFormSubmitButton"]) {{
            width: 100% !important;
            flex: 1 1 100% !important;
        }}
        div[data-testid="stFormSubmitButton"] {{
            width: 100%;
            margin-top: 6px;
        }}
        div[data-testid="stFormSubmitButton"] button {{
            width: 100%;
            background-color: {PRIMARY_COLOR} !important;
            color: #FFFFFF !important;
            border: none !important;
            font-weight: 600 !important;
            font-size: 1rem !important;
            padding: 14px 20px !important;
            border-radius: 10px !important;
        }}
        div[data-testid="stFormSubmitButton"] button:hover {{
            background-color: #D14E1D !important;
            color: #FFFFFF !important;
        }}

        /* ---------- Contorno mais visível em campos de texto/senha/área de texto ---------- */
        /* O contorno padrão do Streamlit é cinza bem claro - some visualmente em
           cima do fundo branco do card de login (e de qualquer container branco
           da aplicação, como o formulário de solicitação de conta). Aplica pra
           toda a aplicação (Usuário/Senha do login, PAT do Azure DevOps, campos
           do formulário de solicitação de conta, etc.), não só a tela de login.

           Campos de senha (`Senha`, no login) têm um botão nativo de
           "mostrar/ocultar senha" (o ícone de olho) - o Streamlit desenha esse
           botão DENTRO de um contêiner próprio, `stTextInputRootElement`, que
           é mais largo que o `<input>` (reserva espaço extra à direita pro
           ícone). Contornar o `<input>` diretamente (como era feito antes)
           deixa esse espaço do ícone FORA do contorno - visualmente parecia
           que a borda direita da caixa estava cortada/incompleta, bem antes
           de chegar no canto real do campo. Por isso o contorno vai no
           `stTextInputRootElement` (o contêiner que já inclui o ícone), e o
           `<input>` em si fica sem borda própria/com fundo transparente, pra
           não desenhar dois contornos um dentro do outro. `stTextArea` não
           tem esse botão de olho, então continua sendo contornado direto no
           `<textarea>` mesmo, sem problema. */
        div[data-testid="stTextInput"] div[data-testid="stTextInputRootElement"] {{
            border: 1.5px solid #a8a196 !important;
            border-radius: 8px !important;
            background-color: #FFFFFF !important;
        }}
        div[data-testid="stTextInput"] input {{
            border: none !important;
            background-color: transparent !important;
            padding: 10px 12px !important;
        }}
        div[data-testid="stTextArea"] textarea {{
            border: 1.5px solid #a8a196 !important;
            border-radius: 8px !important;
            background-color: #FFFFFF !important;
            padding: 10px 12px !important;
        }}
        div[data-testid="stTextInput"] div[data-testid="stTextInputRootElement"]:focus-within,
        div[data-testid="stTextArea"] textarea:focus {{
            border-color: {PRIMARY_COLOR} !important;
            box-shadow: 0 0 0 1px {PRIMARY_COLOR}55 !important;
            outline: none !important;
        }}

        /* ---------- Botões primários ---------- */
        div.stButton > button[kind="primary"] {{
            font-weight: 600;
            border-radius: 10px;
        }}
        div.stButton > button:disabled {{
            opacity: 0.6;
            cursor: not-allowed;
        }}

        /* ---------- Botão azul padrão Microsoft Azure DevOps ---------- */
        /* `st.container(key="ado_btn_carregar_organizacao")` em upload_page.py
           gera a classe CSS `st-key-ado_btn_carregar_organizacao` no container
           (recurso nativo do Streamlit desde a versão que introduziu `key=` em
           st.container - bem mais confiável que tentar casar elementos via
           seletor de irmão adjacente, que depende da estrutura interna exata
           do HTML gerado e mudou entre versões do Streamlit). */
        .st-key-ado_btn_carregar_organizacao button {{
            background-color: #0078D4 !important;
            color: #FFFFFF !important;
            border: 1px solid #0078D4 !important;
            font-weight: 600 !important;
            border-radius: 6px !important;
        }}
        .st-key-ado_btn_carregar_organizacao button:hover {{
            background-color: #005A9E !important;
            border-color: #005A9E !important;
            color: #FFFFFF !important;
        }}
        .st-key-ado_btn_carregar_organizacao button:disabled {{
            background-color: #8fb9d9 !important;
            border-color: #8fb9d9 !important;
        }}

        /* ---------- Botão "Solicitar acesso" (tela de login) ---------- */
        /* Mesma técnica de `key=` do container, aplicada ao botão em
           login_page.py - laranja com fonte branca, igual ao "Entrar", já que
           agora ele abre um modal (`st.dialog`) em vez de expandir um texto de
           link. */
        .st-key-refu_btn_solicitar_acesso button {{
            width: 100% !important;
            background-color: {PRIMARY_COLOR} !important;
            color: #FFFFFF !important;
            border: none !important;
            font-weight: 600 !important;
            font-size: 0.95rem !important;
            padding: 10px 20px !important;
            border-radius: 10px !important;
            margin-top: 6px;
        }}
        .st-key-refu_btn_solicitar_acesso button:hover {{
            background-color: #D14E1D !important;
            color: #FFFFFF !important;
        }}

        /* ---------- Expansor de mapeamento de colunas ---------- */
        .mapeamento-caixa {{
            background-color: {SECONDARY_BACKGROUND_COLOR};
            border-radius: 10px;
            padding: 12px 16px;
            border: 1px solid #ecebe6;
        }}

        /* ---------- Página "Sobre o App": diagramas de fluxo em HTML/CSS ---------- */
        /* Feito em HTML/CSS puro (sem Graphviz/Mermaid) de propósito: zero
           dependência nova pra instalar (nem no ambiente do app, nem no
           computador de quem for rodar localmente), funciona 100% offline, e
           herda a mesma paleta/fonte do resto do app em vez de ficar com a
           cara de um diagrama genérico. Ver `ui/pages/sobre_page.py`. */
        .sobre-fluxo-passo {{
            display: flex;
            align-items: flex-start;
            gap: 14px;
            background-color: #FFFFFF;
            border: 1px solid #ecebe6;
            border-radius: 12px;
            padding: 14px 18px;
            margin-bottom: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        .sobre-fluxo-passo.sobre-fluxo-decisao {{
            background-color: #FFF8F5;
            border-color: {PRIMARY_COLOR}55;
            border-style: dashed;
        }}
        .sobre-fluxo-numero {{
            flex-shrink: 0;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            background-color: {PRIMARY_COLOR};
            color: #FFFFFF;
            font-weight: 700;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .sobre-fluxo-decisao .sobre-fluxo-numero {{
            background-color: #6B6558;
        }}
        .sobre-fluxo-texto {{
            font-size: 0.9rem;
            line-height: 1.45;
            color: {TEXT_COLOR};
        }}
        .sobre-fluxo-texto strong {{
            display: block;
            margin-bottom: 2px;
            font-size: 0.95rem;
        }}
        .sobre-fluxo-seta {{
            text-align: center;
            color: #C9C4B8;
            font-size: 1.3rem;
            line-height: 1.1;
            margin: 2px 0 6px 0;
        }}
        .sobre-fluxo-seta small {{
            display: block;
            font-size: 0.68rem;
            color: #9B9B9B;
            font-weight: 400;
        }}
        .sobre-fluxo-bifurcacao {{
            display: flex;
            gap: 16px;
            margin-bottom: 4px;
            align-items: stretch;
        }}
        .sobre-fluxo-ramo {{
            flex: 1;
            min-width: 0;
            border: 1.5px dashed #ddd8cb;
            border-radius: 14px;
            padding: 14px;
            background-color: #FAFAF8;
        }}
        .sobre-fluxo-ramo-titulo {{
            font-weight: 700;
            font-size: 0.9rem;
            margin-bottom: 10px;
            color: {TEXT_COLOR};
        }}
        .sobre-fluxo-ramo .sobre-fluxo-passo {{
            padding: 9px 12px;
            margin-bottom: 6px;
        }}
        .sobre-fluxo-ramo .sobre-fluxo-numero {{
            width: 22px;
            height: 22px;
            font-size: 0.72rem;
        }}
        .sobre-fluxo-ramo .sobre-fluxo-texto {{
            font-size: 0.82rem;
        }}
        .sobre-callout {{
            background-color: #FFF4E5;
            border: 1px solid #F0C989;
            border-radius: 12px;
            padding: 12px 16px;
            font-size: 0.85rem;
            line-height: 1.5;
            color: {TEXT_COLOR};
            margin: 10px 0;
        }}
        .sobre-catalogo-categoria {{
            font-weight: 700;
            font-size: 1rem;
            margin: 22px 0 10px 0;
            padding-bottom: 6px;
            border-bottom: 2px solid {PRIMARY_COLOR}33;
        }}
        .sobre-catalogo-grade {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 12px;
            margin-bottom: 6px;
        }}
        .sobre-catalogo-card {{
            border: 1px solid #ecebe6;
            border-radius: 12px;
            padding: 14px 16px;
            background-color: #FFFFFF;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }}
        .sobre-catalogo-card-titulo {{
            font-weight: 600;
            font-size: 0.88rem;
            margin-bottom: 4px;
            color: {TEXT_COLOR};
        }}
        .sobre-catalogo-card-desc {{
            font-size: 0.78rem;
            color: #6b6b6b;
            line-height: 1.4;
        }}
        .sobre-estado-badges {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin: 10px 0 16px 0;
        }}
        .sobre-estado-badge {{
            padding: 6px 16px;
            border-radius: 999px;
            font-weight: 600;
            font-size: 0.82rem;
        }}
        .sobre-estado-pendente {{ background-color: #FFF4E5; color: #B26A00; }}
        .sobre-estado-criada {{ background-color: #E6F4EA; color: #1E7B34; }}
        .sobre-estado-rejeitada {{ background-color: #FDECEA; color: #C62828; }}
        .sobre-estado-revogada {{ background-color: #F1F1F1; color: #555555; }}
        @media (max-width: 700px) {{
            .sobre-fluxo-bifurcacao {{ flex-direction: column; }}
        }}

        /* ==========================================================================
           Responsividade: telas muito grandes (evita ficar "pequeno e esticado")
           e telas muito pequenas/mobile (evita títulos grandes demais e má leitura).
           ========================================================================== */

        /* Telas muito grandes (monitores ultrawide/4K): trava a largura útil do
           conteúdo central em vez de deixar tudo esticar por toda a tela. */
        @media (min-width: 1800px) {{
            .main .block-container {{
                max-width: 1600px;
                margin-left: auto;
                margin-right: auto;
            }}
            .refu-header-titulo {{ font-size: 1.2rem; }}
            .kpi-card .kpi-valor {{ font-size: 2.3rem; }}
        }}

        /* Tablets/telas pequenas */
        @media (max-width: 900px) {{
            .refu-header-titulo {{ font-size: 0.95rem; }}
            .kpi-card .kpi-valor {{ font-size: 1.7rem; }}
        }}

        /* Mobile */
        @media (max-width: 640px) {{
            .refu-header {{ gap: 10px; padding-bottom: 14px; margin-bottom: 16px; }}
            .refu-header img {{ height: 32px; }}
            .refu-header-texto {{ padding: 8px 12px; }}
            .refu-header-titulo {{ font-size: 0.85rem; }}
            .refu-header-subtitulo {{ font-size: 0.68rem; }}
            .kpi-card {{ padding: 12px 14px; }}
            .kpi-card .kpi-label {{ font-size: 0.68rem; }}
            .kpi-card .kpi-valor {{ font-size: 1.4rem; margin-top: 2px; }}
            div[data-testid="stForm"] {{ padding: 20px 16px 14px 16px; }}
            div[data-testid="stForm"] h3 {{ font-size: 1.05rem; padding-bottom: 12px; }}
            div[data-testid="stFormSubmitButton"] button {{ padding: 12px 16px !important; font-size: 0.95rem !important; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
