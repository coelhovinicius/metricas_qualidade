"""
Constantes visuais e CSS customizado da aplicação.

As cores abaixo espelham exatamente o `.streamlit/config.toml`, para que
componentes customizados (cards, overlay de carregamento, cabeçalho) fiquem
visualmente consistentes com o tema nativo do Streamlit.
"""

from __future__ import annotations

import streamlit as st

PRIMARY_COLOR = "#F15A24"
BACKGROUND_COLOR = "#FAF6F0"
SECONDARY_BACKGROUND_COLOR = "#FFFFFF"
TEXT_COLOR = "#1A1A1A"

# Paleta categórica usada nos gráficos (Testes por Projeto, Tipo de Teste,
# Severidade, Responsáveis, Treemap, etc.). 8 matizes distintos, com a laranja
# da marca na liderança (mantém a identidade visual nos gráficos de série
# única) seguida de azul, água, amarelo, magenta, verde, violeta e vermelho -
# ordem validada para diferenciação em daltonismo (protanopia/deuteranopia)
# e leitura em visão normal, então NÃO reordene os slots livremente: a ordem
# em si é o que garante que cores vizinhas no gráfico não fiquem parecidas.
# Água, amarelo e magenta têm contraste mais baixo contra fundo branco -
# por isso os gráficos de barra usam rótulos de valor visíveis (text_auto) e
# sempre existe a tabela de dados detalhados como alternativa de leitura.
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
