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

# Paleta derivada da identidade visual (usada nos gráficos)
PALETA_GRAFICOS = ["#F15A24", "#2E7D5B", "#E0A93E", "#4A4A4A", "#C1440E", "#6FA98A"]
PALETA_STATUS = {
    "Passou": "#2E7D5B",
    "Falhou": "#F15A24",
    "Planejado": "#E0A93E",
    "Outro": "#8C8C8C",
    "Não informado": "#C9C2B8",
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

        /* ---------- Título de destaque da tela de login (fundo laranja) ---------- */
        /* Estiliza diretamente o subtítulo renderizado pela lib de autenticação
           dentro do formulário (evita duplicar título e sobrar espaço vazio). */
        div[data-testid="stForm"] h3 {{
            background-color: {PRIMARY_COLOR};
            color: #FFFFFF !important;
            font-weight: 700;
            font-size: 1.15rem;
            padding: 12px 20px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 18px;
        }}

        /* ---------- Botão "Entrar" do formulário de login: laranja, largura total ---------- */
        div[data-testid="stFormSubmitButton"] {{
            width: 100%;
        }}
        div[data-testid="stFormSubmitButton"] button {{
            width: 100%;
            background-color: {PRIMARY_COLOR} !important;
            color: #FFFFFF !important;
            border: none !important;
            font-weight: 600 !important;
            border-radius: 10px !important;
        }}
        div[data-testid="stFormSubmitButton"] button:hover {{
            background-color: #D14E1D !important;
            color: #FFFFFF !important;
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

        /* ---------- Expansor de mapeamento de colunas ---------- */
        .mapeamento-caixa {{
            background-color: {SECONDARY_BACKGROUND_COLOR};
            border-radius: 10px;
            padding: 12px 16px;
            border: 1px solid #ecebe6;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
