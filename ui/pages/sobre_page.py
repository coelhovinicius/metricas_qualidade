"""
Página "Sobre o App": explica, de forma visual, todos os fluxos do
app - do login até o relatório em PDF, incluindo o que cada
gráfico do painel mostra e como funciona a Administração.

É só uma tela informativa (não lê nem grava nenhum dado do usuário) -
visível pra QUALQUER pessoa logada, não só o admin, porque o objetivo é
ajudar qualquer um a entender o app inteiro, inclusive o que existe do lado
da Administração mesmo que ela não tenha acesso a essa página.

Os diagramas em cartões (a maior parte da página) são montados em HTML/CSS
puro (ver classes `.sobre-fluxo-*`/`.sobre-catalogo-*`/`.sobre-estado-*` em
`ui/theme.py`), de propósito: recalculam a cada carregamento de página, e uma
dependência de sistema a mais ali (Graphviz/Mermaid) seria risco
desnecessário. Já a imagem do "Fluxograma completo do app" (retângulos +
setas) É gerada com Graphviz (ver `core/gerador_fluxograma.py`) - mas raras
vezes, não a cada carregamento: o resultado fica pronto, guardado no banco de
dados (Turso) ou em `assets/`, e esta página só SERVE o PNG já pronto (ver
`_obter_bytes_fluxograma` abaixo), nunca gera nada na hora.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

import streamlit as st

from auth.auth_manager import AuthManager
from core.config_app import (
    CHAVE_CODIGO_VISAO_ADMIN_SOBRE_APP,
    CHAVE_FLUXOGRAMA_COMPLETO_BASE64,
    CHAVE_FLUXOGRAMA_PUBLICO_BASE64,
    obter_configuracao,
)
from core.gerador_guia_pdf import obter_bytes_pdf_atual
from ui.components import render_header
from ui.pages.admin_page import usuario_e_admin

# ui/pages/sobre_page.py -> ui/pages -> ui -> raiz do projeto -> assets/
_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
# Nome só pra sugerir no download (`file_name=`) - o CONTEÚDO em si vem do
# banco de dados (Turso) sempre que existir, ver
# `core/gerador_guia_pdf.py::obter_bytes_pdf_atual`; este arquivo em disco é
# usado só como versão padrão/de fallback, incluída no próprio repositório,
# para quando ainda ninguém clicou em "🔄 Gerar/Atualizar PDF agora" em
# Administração neste ambiente.
_CAMINHO_GUIA_PDF = _ASSETS_DIR / "Guia_do_Usuario_QA.pdf"

# Imagens do "Fluxograma completo do app" em retângulos + setas de verdade
# (complementando os cartões em HTML/CSS logo abaixo, que continuam existindo
# porque trazem a descrição de cada passo com mais detalhe do que cabe numa
# caixinha de diagrama). Duas versões, pela mesma regra de segregação por
# papel do resto desta página (ver `_usuario_tem_visao_admin`): uma com as
# duas trilhas, outra com a trilha administrativa trancada. Cada uma tem um
# nome de arquivo local (fallback, incluído no repositório) e uma chave no
# Turso (fonte "viva", gravada pelo botão "🔄 Gerar/Atualizar fluxograma
# agora" em Administração - ver `_obter_bytes_fluxograma` abaixo).
_CAMINHO_FLUXOGRAMA_COMPLETO = _ASSETS_DIR / "fluxograma_completo.png"
_CAMINHO_FLUXOGRAMA_PUBLICO = _ASSETS_DIR / "fluxograma_publico.png"


def _obter_bytes_fluxograma(chave_base64: str, caminho_fallback: Path) -> Optional[bytes]:
    """
    Bytes do PNG do fluxograma (uma das duas versões), prontos para
    `st.image`/`st.download_button` - mesma prioridade de
    `_obter_bytes_guia_pdf` acima: (1) versão gravada no Turso pelo botão
    "🔄 Gerar/Atualizar fluxograma agora" em Administração; (2) se ainda não
    existir nenhuma lá, cai para o arquivo padrão incluído no repositório
    (gerado por `scripts/gerar_fluxograma_diagrama.py`). Qualquer falha ao
    falar com o banco é silenciosa aqui, com o mesmo fallback.
    """
    try:
        base64_imagem = obter_configuracao(chave_base64)
    except Exception:
        base64_imagem = None
    if base64_imagem:
        try:
            return base64.b64decode(base64_imagem)
        except (ValueError, TypeError):
            pass
    if caminho_fallback.exists():
        return caminho_fallback.read_bytes()
    return None


_CHAVE_SESSAO_VISAO_ADMIN_DESBLOQUEADA = "sobre_app_visao_admin_desbloqueada"


def _usuario_tem_visao_admin() -> bool:
    """
    True se o usuário logado deve ver o conteúdo administrativo desta página
    (a trilha "quem administra" do fluxograma completo e a seção
    "Administração" inteira) - ou porque ele É o admin, ou porque já
    desbloqueou com o código certo nesta mesma sessão do navegador (ver
    `_desbloquear_conteudo_admin`, e o código em si definido em
    Administração → "Código de acesso ao conteúdo administrativo de 'Sobre
    o App'"). Guardado em `st.session_state` (não no banco) de propósito: o
    desbloqueio vale só para esta sessão de navegador específica, não fica
    "ligado" pra sempre nem afeta outras pessoas.
    """
    if usuario_e_admin(AuthManager.current_username()):
        return True
    return bool(st.session_state.get(_CHAVE_SESSAO_VISAO_ADMIN_DESBLOQUEADA))


def _desbloquear_conteudo_admin() -> None:
    """
    Campo + botão para quem não é admin digitar o código liberado pela
    pessoa administradora e desbloquear, só nesta sessão do navegador, o
    conteúdo administrativo desta página. Sem nenhum código configurado
    ainda (`obter_configuracao` devolve vazio/None), nem mostra o campo -
    não haveria nada para acertar.
    """
    try:
        codigo_configurado = obter_configuracao(CHAVE_CODIGO_VISAO_ADMIN_SOBRE_APP)
    except Exception:
        codigo_configurado = None

    if not codigo_configurado:
        st.caption(
            "🔒 Esta parte descreve as funcionalidades exclusivas de quem administra o app. "
            "A pessoa administradora ainda não liberou um código de acesso para este "
            "conteúdo."
        )
        return

    st.caption(
        "🔒 Esta parte descreve as funcionalidades exclusivas de quem administra o app. Se "
        "você recebeu um código de acesso da pessoa administradora, digite abaixo para "
        "desbloquear (vale só para esta sua sessão)."
    )
    col_codigo, col_botao = st.columns([3, 1])
    with col_codigo:
        codigo_digitado = st.text_input(
            "Código de acesso", key="input_codigo_desbloqueio_admin",
            label_visibility="collapsed", placeholder="Código de acesso",
        )
    with col_botao:
        desbloquear = st.button(
            "Desbloquear", key="btn_desbloquear_admin_sobre_app", use_container_width=True,
        )
    if desbloquear:
        if codigo_digitado.strip() and codigo_digitado.strip() == codigo_configurado.strip():
            st.session_state[_CHAVE_SESSAO_VISAO_ADMIN_DESBLOQUEADA] = True
            st.rerun()
        else:
            st.error("Código incorreto.")


# ---------------------------------------------------------------------------
# Componentes de diagrama (blocos HTML/CSS reutilizáveis - ver docstring do
# módulo pra explicação de por que HTML/CSS em vez de uma lib de diagrama).
# ---------------------------------------------------------------------------


def _passo(numero: str, titulo: str, texto: str = "", decisao: bool = False) -> None:
    """Um "cartão" de etapa do fluxo - `numero` pode ser 1, 2, 3... ou um ícone/símbolo (ex.: "?" pra decisão, "✓" pra fim)."""
    classe = "sobre-fluxo-passo sobre-fluxo-decisao" if decisao else "sobre-fluxo-passo"
    texto_html = f"<br>{texto}" if texto else ""
    st.markdown(
        f"""
        <div class="{classe}">
            <div class="sobre-fluxo-numero">{numero}</div>
            <div class="sobre-fluxo-texto"><strong>{titulo}</strong>{texto_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _seta(nota: str = "") -> None:
    """A setinha vertical entre uma etapa e a próxima, com uma nota pequena opcional (ex.: "os dois caminhos se encontram aqui")."""
    nota_html = f"<small>{nota}</small>" if nota else ""
    st.markdown(f'<div class="sobre-fluxo-seta">↓{nota_html}</div>', unsafe_allow_html=True)


def _bifurcacao(ramos: list[tuple[str, list[tuple[str, str, str]]]]) -> None:
    """
    Desenha 2+ "ramos" (caminhos alternativos) lado a lado - cada ramo é
    (título do ramo, [(número/ícone, título do passo, texto do passo), ...]).
    Em telas estreitas, os ramos empilham um embaixo do outro (CSS já cuida
    disso, ver `@media` em `ui/theme.py`).

    Construído como UM ÚNICO `st.markdown` (em vez de vários, um por
    cartão) de propósito: o `display: flex` que coloca os ramos lado a lado
    só funciona se os ramos forem filhos diretos do mesmo elemento pai no
    HTML - com um `st.markdown` por cartão, cada um viraria um bloco
    separado do Streamlit, não filhos de um `.sobre-fluxo-bifurcacao` comum.

    Cada pedaço de HTML abaixo é montado numa ÚNICA LINHA (sem indentação/
    quebra de linha no meio), de propósito - já vimos isso quebrar de
    verdade: ao juntar vários pedaços em várias linhas com `"".join(...)`,
    sobra uma linha em branco (só espaços) na junção de um cartão com o
    próximo, e o parser de Markdown do Streamlit entende isso como O FIM do
    bloco de HTML - tudo que vem depois passa a ser lido como texto puro
    (aparecendo na tela como se fosse um bloco de código, com as tags
    `<div>` visíveis em vez de renderizadas). Uma única linha contínua por
    cartão, sem nenhuma linha em branco em lugar nenhum, elimina esse risco.
    """
    colunas_html = []
    for titulo_ramo, passos in ramos:
        passos_html = "".join(
            f'<div class="sobre-fluxo-passo"><div class="sobre-fluxo-numero">{numero}</div>'
            f'<div class="sobre-fluxo-texto"><strong>{titulo}</strong>'
            f'{f"<br>{texto}" if texto else ""}</div></div>'
            for numero, titulo, texto in passos
        )
        colunas_html.append(
            f'<div class="sobre-fluxo-ramo"><div class="sobre-fluxo-ramo-titulo">{titulo_ramo}</div>'
            f'{passos_html}</div>'
        )
    st.markdown(
        f'<div class="sobre-fluxo-bifurcacao">{"".join(colunas_html)}</div>',
        unsafe_allow_html=True,
    )


def _callout(texto: str) -> None:
    st.markdown(f'<div class="sobre-callout">{texto}</div>', unsafe_allow_html=True)


def _catalogo_categoria(titulo: str, cartoes: list[tuple[str, str]]) -> None:
    """
    Um grupo de "cartões" de gráfico (título + descrição de uma linha),
    organizados em grade - ver `_sec_catalogo_graficos`.

    Mesmo cuidado de `_bifurcacao` acima (ver docstring lá): cada cartão é
    montado numa única linha, sem nenhuma linha em branco na junção entre
    cartões - isso já quebrou a renderização (virava texto/código visível em
    vez de HTML) quando escrito em várias linhas indentadas.
    """
    cartoes_html = "".join(
        f'<div class="sobre-catalogo-card"><div class="sobre-catalogo-card-titulo">{titulo_cartao}</div>'
        f'<div class="sobre-catalogo-card-desc">{desc_cartao}</div></div>'
        for titulo_cartao, desc_cartao in cartoes
    )
    st.markdown(
        f'<div class="sobre-catalogo-categoria">{titulo}</div>'
        f'<div class="sobre-catalogo-grade">{cartoes_html}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Seções da página
# ---------------------------------------------------------------------------


def _sec_visao_geral() -> None:
    st.markdown("### Visão geral: do login ao relatório")
    st.caption(
        "O caminho principal do app, resumido. Cada etapa é detalhada numa seção retrátil "
        "logo abaixo - clique para abrir."
    )
    _passo("1", "Fazer login", "Ou pedir acesso, se ainda não tiver conta (ver \"Login e acesso\" abaixo).")
    _seta()
    _passo("?", "Como importar os dados?", decisao=True)
    _bifurcacao([
        ("📄 Enviar arquivo (.csv/.txt)", [
            ("A", "Selecionar o arquivo e clicar em \"Processar arquivo\"", ""),
        ]),
        ("☁️ Buscar Query no Azure DevOps", [
            ("B", "PAT → Organização → Projeto → Query → \"Baixar relatório atualizado\"", ""),
        ]),
        ("📁 Buscar arquivo no Google Drive", [
            ("C", "Navegar até a pasta/subpasta → escolher o .csv → \"Importar arquivo selecionado\"", ""),
        ]),
    ])
    _seta("os três caminhos se encontram aqui")
    _passo("2", "Confirmar o Mapeamento de Colunas", "Revisa (ou ajusta) o que o app já sugeriu sozinho.")
    _seta()
    _passo("3", "Explorar o Painel de Indicadores", "Filtros + mais de 20 gráficos + gráfico personalizado.")
    _seta()
    _passo("✓", "Gerar PDF do Relatório", "Opcional - reaproveita exatamente os gráficos já visíveis na tela.")
    st.markdown("<br>", unsafe_allow_html=True)
    _callout(
        "⚙️ <strong>Administração</strong> roda à parte desse caminho principal - disponível a qualquer "
        "momento no menu lateral, só pra quem faz login como admin. Ver a seção retrátil "
        "\"Administração\" mais abaixo."
    )


def _sec_fluxograma_completo(mostrar_trilha_admin: bool) -> None:
    """
    Fluxograma completo do app: diferente de `_sec_visao_geral` (só o
    caminho principal de quem importa/analisa dados), aqui aparecem as DUAS
    trilhas que rodam em paralelo - a de quem usa o app no dia a dia, e a de
    quem administra (login `admin`) - e, principalmente, ONDE uma trilha
    depende da outra. Antes desta seção, a Administração só aparecia como um
    aviso solto no fim de `_sec_visao_geral`, sem mostrar que ela também tem
    passos próprios nem que duas ações específicas dela (aprovar solicitação
    de acesso, configurar a credencial do Google Drive) são pré-requisito
    para passos da trilha comum - o "fluxograma completo" pedido é reunir as
    duas coisas numa figura só, com essas dependências explícitas.

    `mostrar_trilha_admin` (ver `_usuario_tem_visao_admin`) controla a
    segregação de conteúdo por papel: quando False, a coluna da direita e os
    avisos 🔗 (que descrevem COMO a administração resolve cada travamento,
    incluindo onde no código/Secrets isso mora) viram uma versão resumida,
    só avisando que aquele conteúdo existe e está disponível pra quem
    desbloquear (ver "⚙️ Administração" mais abaixo na página).
    """
    st.markdown("### Fluxograma completo do app")
    st.caption(
        "As duas trilhas rodam em paralelo, não uma depois da outra - a coluna da direita "
        "(Administração) não tem uma 'ordem' fixa como a da esquerda, e fica disponível o tempo "
        "todo pra quem loga como `admin`."
    )

    if mostrar_trilha_admin:
        chave_base64, caminho_fallback = CHAVE_FLUXOGRAMA_COMPLETO_BASE64, _CAMINHO_FLUXOGRAMA_COMPLETO
    else:
        chave_base64, caminho_fallback = CHAVE_FLUXOGRAMA_PUBLICO_BASE64, _CAMINHO_FLUXOGRAMA_PUBLICO
    bytes_imagem = _obter_bytes_fluxograma(chave_base64, caminho_fallback)
    if bytes_imagem:
        st.image(bytes_imagem, use_container_width=True)
        st.download_button(
            "⬇️ Baixar este fluxograma (imagem)",
            data=bytes_imagem,
            file_name=caminho_fallback.name,
            mime="image/png",
            key=f"btn_baixar_fluxograma_{caminho_fallback.stem}",
        )
    st.caption(
        "A imagem acima é o resumo visual (retângulos + setas); os cartões abaixo detalham cada "
        "passo com uma descrição de uma ou duas linhas."
    )
    st.markdown("<br>", unsafe_allow_html=True)

    if mostrar_trilha_admin:
        ramo_admin = ("⚙️ Trilha de quem administra (login admin)", [
            ("A", "Configurar a conta de serviço do Google Drive", "Uma vez só, em Administração → Google Drive - ver aviso 🔗 abaixo."),
            ("B", "Aprovar ou rejeitar solicitações de acesso", "Fila de \"Pendentes\" em Administração → Solicitações de Acesso."),
            ("C", "Revogar acesso (ou reverter depois)", "Quando alguém sai, ou por engano."),
            ("D", "Acompanhar os Logs do Sistema", "Acessos, erros técnicos, e ações feitas no próprio painel."),
        ])
    else:
        ramo_admin = ("⚙️ Trilha de quem administra", [
            ("🔒", "Conteúdo visível só para quem administra", "Peça um código de acesso à pessoa administradora para desbloquear (seção \"Administração\", mais abaixo)."),
        ])
    _bifurcacao([
        ("🙋 Trilha de quem usa o app", [
            ("1", "Pedir acesso", "Só se ainda não tiver conta - formulário na tela de login."),
            ("2", "Fazer login", "Usuário e senha, criados pelo admin fora do app (ver trilha ao lado)."),
            ("3", "Importar dados", "Enviar arquivo, Azure DevOps, ou Google Drive - qualquer um dos três."),
            ("4", "Confirmar mapeamento de colunas", "Revisa o que o app já sugeriu sozinho."),
            ("5", "Explorar o Painel de Indicadores", "Filtros + mais de 20 gráficos + gráfico personalizado."),
            ("✓", "Gerar PDF do Relatório", "Opcional, a qualquer momento a partir do painel."),
        ]),
        ramo_admin,
    ])
    st.markdown("<br>", unsafe_allow_html=True)
    if mostrar_trilha_admin:
        _callout(
            "🔗 <strong>Login trava em \"B\".</strong> A pessoa só consegue fazer login (passo 2 da "
            "trilha da esquerda) depois que o admin marca a solicitação como \"Criada\" - e cria de "
            "verdade o usuário/senha fora do app (nos Secrets do Streamlit ou em <code>auth/users.yaml</code>)."
        )
        _callout(
            "🔗 <strong>\"Buscar arquivo no Google Drive\" trava em \"A\".</strong> Sem o admin "
            "configurar a credencial da conta de serviço (passo A), essa opção de importação (passo 3) "
            "mostra um aviso e não deixa navegar - os outros dois caminhos (Enviar arquivo / Azure "
            "DevOps) funcionam independente disso. Depois que a credencial existe, cada pessoa "
            "configura a PRÓPRIA pasta sozinha (dentro do passo 3), sem precisar do admin de novo."
        )
        _callout(
            "Os passos \"C\" e \"D\" da direita não travam nada da trilha da esquerda - são só "
            "manutenção contínua, disponíveis o tempo todo, sem uma ordem obrigatória entre si nem em "
            "relação ao que a pessoa comum está fazendo."
        )
    else:
        _callout(
            "🔗 Alguns passos da trilha da esquerda dependem de uma ação prévia de quem administra "
            "(ex.: login depende de aprovação de acesso; \"Buscar arquivo no Google Drive\" depende de "
            "uma credencial configurada) - os detalhes de como a administração resolve cada um estão "
            "disponíveis só para quem desbloquear o conteúdo administrativo (seção \"Administração\", "
            "mais abaixo)."
        )


def _sec_guia_para_baixar() -> None:
    """
    Área com o "Guia Completo do Usuário" - visível pra QUALQUER pessoa
    logada (mesma regra do resto desta página), reunindo num só lugar tudo
    que falta pra alguém novo se virar sozinho: como gerar um PAT do Azure
    DevOps, e quais colunas configurar na query pra cada gráfico funcionar
    (conteúdo que não cabia nos fluxogramas acima, mais operacionais do que
    "como o app funciona"). O PDF (montado por
    `core/gerador_guia_pdf.py`, regravável a qualquer momento pelo botão
    "🔄 Gerar/Atualizar PDF agora" em Administração → "📘 Guia do Usuário") é
    a versão completa, pronta pra baixar e repassar pra qualquer pessoa nova
    - o conteúdo abaixo, em tela, é um resumo dos dois pontos que só existem
    aqui (o resto do guia já está coberto pelas outras seções desta
    página).
    """
    st.caption(
        "Reúne tudo que uma pessoa nova precisa pra usar o app sozinha - inclusive gerar um "
        "PAT do Azure DevOps e montar a query certa. Pode ser baixado em PDF pra repassar pra "
        "qualquer usuário novo."
    )

    bytes_pdf = obter_bytes_pdf_atual()
    if bytes_pdf:
        st.download_button(
            "⬇️ Baixar Guia Completo do Usuário (PDF)",
            data=bytes_pdf,
            file_name=_CAMINHO_GUIA_PDF.name,
            mime="application/pdf",
            key="btn_baixar_guia_usuario_pdf",
        )
    else:
        st.info(
            "O PDF deste guia ainda não foi gerado neste ambiente - peça para a pessoa "
            "administradora clicar em \"🔄 Gerar/Atualizar PDF agora\" (Administração → "
            "\"📘 Guia do Usuário\"). O conteúdo abaixo já funciona normalmente, independente "
            "do PDF."
        )

    st.markdown("<br>**Como gerar o seu PAT (Personal Access Token) do Azure DevOps**", unsafe_allow_html=True)
    _passo("1", "Acesse dev.azure.com e faça login normalmente")
    _seta()
    _passo("2", "Ícone de usuário (canto superior direito)", "→ \"Personal Access Tokens\".")
    _seta()
    _passo("3", "Clique em \"+ New Token\"")
    _seta()
    _passo("4", "Dê um nome e escolha a validade", "Recomendado: 90 dias - depois é só gerar outro.")
    _seta()
    _passo("5", "Em Scopes, marque \"Work Items\" → \"Read\"", "Só leitura - o app nunca cria, edita ou apaga nada no Azure DevOps.")
    _seta()
    _passo("✓", "Clique em \"Create\" e copie o token na hora", "O Azure DevOps só mostra o valor completo uma vez.")
    _callout(
        "É seguro colar esse PAT no app: ele nunca é salvo em disco, banco de dados ou nas "
        "configurações - fica só na memória da sua sessão do navegador enquanto você está "
        "logado, e desaparece ao sair ou fechar a aba de verdade."
    )

    st.markdown("<br>**Colunas para configurar na sua query do Azure DevOps**", unsafe_allow_html=True)
    st.caption(
        "Vale para \"Enviar arquivo\" e \"Google Drive\" (os dois dependem do CSV exportado "
        "manualmente) - a busca automática por PAT já traz tudo isso sozinha, sem precisar "
        "configurar nada na query."
    )
    st.table([
        {"Adicione esta coluna": "ID", "Vira, no app": "Caso de Teste / ID"},
        {"Adicione esta coluna": "Work Item Type", "Vira, no app": "Tipos de Teste"},
        {"Adicione esta coluna": "State", "Vira, no app": "Status"},
        {"Adicione esta coluna": "Area Path", "Vira, no app": "Projeto"},
        {"Adicione esta coluna": "Assigned To", "Vira, no app": "Responsável"},
        {"Adicione esta coluna": "Created By", "Vira, no app": "Autor / Criado por"},
        {"Adicione esta coluna": "Created Date", "Vira, no app": "Data de Criação"},
        {"Adicione esta coluna": "Severity (ou Priority)", "Vira, no app": "Severidade / Prioridade"},
        {"Adicione esta coluna": "Board Column *", "Vira, no app": "Coluna do Board"},
        {"Adicione esta coluna": "Iteration Path **", "Vira, no app": "Sprint"},
    ])
    _callout(
        "<strong>*</strong> Nem sempre aparece na lista de colunas (depende do processo/"
        "template do projeto no Azure DevOps) - se faltar, só esse indicador fica "
        "indisponível pra arquivos exportados manualmente.<br><strong>**</strong> É "
        "\"Iteration Path\", não \"Iteration ID\" - são campos diferentes; o Path é o texto "
        "da sprint, o ID é só um número interno sem uso aqui."
    )
    st.caption(
        "Passo a passo completo (com onde clicar no Azure DevOps) e o restante do guia estão "
        "no PDF acima."
    )


def _sec_login() -> None:
    st.markdown("**Chegando na tela de login**")
    _passo("1", "Preencher Usuário e Senha", "e clicar em \"Entrar\".")
    _seta()
    _passo("?", "Credenciais corretas?", decisao=True)
    _bifurcacao([
        ("✅ Sim", [
            ("→", "Login registrado no log", "Segue direto para \"Importar Dados\"."),
        ]),
        ("❌ Não", [
            ("→", "Mensagem de erro na tela", "\"Usuário ou senha incorretos\" - campos limpam, pode tentar de novo."),
        ]),
    ])
    st.caption(
        "F5/recarregar a página não pede senha de novo, enquanto o cookie de sessão for válido - "
        "mas abrir uma aba/janela NOVA com um cookie antigo força um novo login (proteção contra "
        "sessão esquecida aberta no navegador)."
    )

    st.markdown("<br>**Ainda não tenho conta**", unsafe_allow_html=True)
    _passo("1", "Clicar em \"Solicitar acesso\"", "Abre um formulário: Nome completo, E-mail, Motivo do acesso.")
    _seta()
    _passo("2", "Confirmar", "Nome/e-mail válidos e sem pedido pendente para o mesmo e-mail.")
    _seta()
    _passo("✓", "Pedido fica \"Pendente\"", "Um administrador aprova ou rejeita depois (ver \"Administração\").")
    _callout(
        "Solicitar acesso <strong>não cria a conta sozinho</strong> - só registra o pedido pro "
        "administrador ver. A conta em si (usuário/senha) continua sendo criada manualmente por "
        "ele, fora do app."
    )


def _sec_importacao() -> None:
    _passo("?", "Como você quer importar os dados?", decisao=True)
    _bifurcacao([
        ("📄 Enviar arquivo (.csv/.txt)", [
            ("1", "Escolher o arquivo", "Limite de 20MB."),
            ("2", "Clicar em \"Processar arquivo\"", "Codificação e separador são detectados sozinhos."),
        ]),
        ("☁️ Buscar Query no Azure DevOps", [
            ("1", "Colar o PAT", "Fica só na memória da sessão do navegador - nunca é salvo em disco."),
            ("2", "Escolher/Carregar a Organização", ""),
            ("3", "Escolher o Projeto", "Area Path(s) do board é opcional, mais abaixo."),
            ("4", "(Opcional) Escolher Area Path(s)", "Filtra o resultado por sub-caminho, se preenchido."),
            ("5", "Escolher a Query salva", "Ou criar uma nova, direto no Azure DevOps, pelo link fornecido."),
            ("6", "Clicar em \"Baixar relatório atualizado\"", ""),
        ]),
        ("📁 Buscar arquivo no Google Drive", [
            ("1", "Compartilhar a sua pasta no Drive", "Com o e-mail da conta de serviço, mostrado na própria tela."),
            ("2", "Colar o link/ID dessa pasta e salvar", "Uma vez só - fica guardado pra você, ninguém mais precisa mexer."),
            ("3", "Navegar até a pasta/subpasta e escolher o .csv", "Só arquivos .csv aparecem na lista."),
            ("4", "Clicar em \"Importar arquivo selecionado\"", "Baixa o arquivo do Drive e processa igual a um envio manual."),
        ]),
    ])
    _seta("os três caminhos se encontram aqui")
    _passo("✓", "Segue para a confirmação do Mapeamento de Colunas")

    st.markdown("<br>", unsafe_allow_html=True)
    _callout(
        "🚩 <strong>Verificação de identidade do PAT.</strong> Toda busca automática no Azure DevOps "
        "consulta, na hora, quem é o DONO de verdade do PAT usado (direto na API do Azure DevOps) e "
        "compara com quem está logado no app. Se dois nomes diferentes aparecerem, o log em "
        "Administração → Logs do Sistema é marcado com \"POSSÍVEL ANOMALIA\" - não bloqueia nada, é só "
        "um alerta visual pro administrador conferir depois."
    )
    _callout(
        "📁 <strong>Google Drive.</strong> Cada pessoa configura a PRÓPRIA pasta, direto na tela "
        "Importar Dados - não existe uma pasta única compartilhada por todo mundo, nem depende do "
        "administrador pra trocar. O administrador só é responsável por configurar a conta de "
        "serviço em si (ver \"Administração\" abaixo); a busca só fica disponível depois disso. O "
        "conteúdo da sua pasta pode mudar a qualquer momento por fora do app (novo arquivo, arquivo "
        "apagado etc.); use \"🔄 Atualizar lista desta pasta\" pra reconsultar sem precisar sair e "
        "voltar na tela."
    )
    st.caption(
        "Nos três caminhos, importar um arquivo/relatório novo sempre SUBSTITUI o anterior - não "
        "acumula dados de importações diferentes."
    )


def _sec_mapeamento() -> None:
    _passo("1", "Ver a prévia dos dados importados", "As 20 primeiras linhas, num expansor.")
    _seta()
    _passo("2", "Revisar o mapeamento sugerido", "Projeto, Status, Datas, Severidade, Coluna do Board, Sprint... - já vem pré-preenchido, ajuste o que precisar.")
    _seta()
    _passo("3", "(Opcional) Adicionar campos personalizados", "Pra usar depois no gráfico personalizado.")
    _seta()
    _passo("✓", "Clicar em \"Confirmar mapeamento e gerar indicadores\"", "Vai direto para o Painel de Indicadores.")


def _sec_catalogo_graficos() -> None:
    st.caption(
        "Diferente dos fluxos acima, os gráficos do painel não têm uma ordem obrigatória entre si - "
        "são vistas independentes dos MESMOS dados já filtrados pela barra lateral, então aqui um "
        "catálogo por tema conta a história melhor que um fluxograma (que exigiria desenhar setas "
        "entre coisas que não têm uma sequência de verdade umas com as outras)."
    )

    _catalogo_categoria("Visão geral e qualidade", [
        ("Distribuição de Status / Passou vs. Não Passou", "O panorama geral de Status - o nome muda conforme o vocabulário do arquivo (binário Passou/Falhou, ou livre tipo New/Active/Closed)."),
        ("Area Path × Status", "Só aparece com Status \"livre\" - mostra qual Area Path usa qual vocabulário de Status."),
        ("Distribuição por Severidade/Prioridade", "Cores fixas: Critical=vermelho, High=laranja, Medium=amarelo, Low=verde, não atribuído=azul."),
    ])
    _catalogo_categoria("Backlog e tempo parado", [
        ("Backlog Aberto — Tempo Parado", "KPIs + tabela dos itens que ainda não chegaram a um status final, e há quanto tempo."),
        ("Backlog Aberto: Volume × Idade × Risco", "Gráfico de bolha - quem (Area Path/Responsável) tem mais itens, mais velhos e mais críticos ao mesmo tempo."),
    ])
    _catalogo_categoria("Ritmo e tendência", [
        ("Sprints — Itens Concluídos", "Quantos itens foram concluídos em cada sprint, em ordem cronológica aproximada."),
        ("Planejamento vs. Testes Efetivados", "Compara o planejado com o que de fato foi executado."),
        ("Tendência ao Longo do Tempo", "Volume por semana - com a opção \"múltiplos pequenos\" pra comparar o formato da curva entre Projetos."),
        ("Bugs Abertos vs. Solucionados", "Acumulado semanal, discriminando o que está fora do controle da QA (aguardando validação externa)."),
    ])
    _catalogo_categoria("Fluxo do board (Kanban)", [
        ("Distribuição por Coluna do Board", "Onde os itens estão parados hoje - com um gráfico de Funil mostrando a queda estágio a estágio."),
        ("Area Path × Coluna do Board", "Cruza Projeto com Coluna do Board - com Mapa de Calor pra quando há muitas combinações."),
        ("Prioridade Dentro do Board", "Ranking de posição vertical dentro de cada coluna (só em dados vindos do Azure DevOps)."),
        ("Severidade Calculada (posição no board)", "Severidade inferida pela posição relativa do item dentro da coluna."),
    ])
    _catalogo_categoria("Projetos, tipos e pessoas", [
        ("Testes por Projeto / Ranking de Bugs por Projeto", "Volumes básicos, por Projeto."),
        ("Distribuição por Tipo de Teste", "Com opção de excluir tipos \"contêiner\" (Test Plan/Test Suite) da contagem."),
        ("Taxa de Sucesso por Projeto", "Só quando o Status é binário (Passou/Falhou)."),
        ("Volume de Testes por Responsável", "Com opção de abrir também por Projeto."),
        ("Volume por Responsável ao Longo do Tempo", "Semanal, limitado às 8 pessoas com mais volume no período."),
        ("Carga de Risco por Responsável", "Mapa de calor Responsável × Severidade - quem segura os itens mais críticos, não só quem tem mais itens."),
    ])
    _catalogo_categoria("Customização e exportação", [
        ("Monte seu gráfico personalizado", "Escolhe Eixo/Agrupamento/Métrica/Tipo de gráfico livremente, com qualquer coluna do arquivo."),
        ("Tabela de dados detalhados", "Dados já filtrados, com botão para exportar em CSV."),
        ("Gerar PDF do Relatório", "Reaproveita exatamente os gráficos já visíveis na tela (nada dentro de expansores recolhidos entra no PDF)."),
    ])


def _sec_administracao() -> None:
    st.caption("Visível só para quem faz login como usuário `admin`. Tem três partes (uma aba para cada):")

    st.markdown("**1. Ciclo de vida de uma solicitação de conta**")
    st.markdown(
        """
        <div class="sobre-estado-badges">
            <span class="sobre-estado-badge sobre-estado-pendente">Pendente</span>
            <span class="sobre-estado-badge sobre-estado-criada">Criada</span>
            <span class="sobre-estado-badge sobre-estado-rejeitada">Rejeitada</span>
            <span class="sobre-estado-badge sobre-estado-revogada">Revogada</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.table([
        {"De": "Pendente", "Ação do admin": "✅ Marcar como criada", "Vira": "Criada"},
        {"De": "Pendente", "Ação do admin": "❌ Rejeitar", "Vira": "Rejeitada"},
        {"De": "Criada", "Ação do admin": "🚫 Revogar acesso", "Vira": "Revogada"},
        {"De": "Revogada", "Ação do admin": "↩️ Reverter revogação", "Vira": "Pendente"},
        {"De": "Rejeitada", "Ação do admin": "♻️ Recuperar", "Vira": "Pendente"},
        {"De": "Revogada / Rejeitada", "Ação do admin": "🗑️ Excluir", "Vira": "(some da lista)"},
    ])
    _callout(
        "Nenhuma dessas ações cria ou apaga a conta de verdade (usuário/senha) - isso continua "
        "manual, fora do app. O painel só controla o STATUS do pedido e registra quem fez o quê, "
        "pra auditoria. E-mails na lista de protegidos não podem ser revogados sem querer."
    )

    st.markdown("<br>**2. Logs do Sistema**", unsafe_allow_html=True)
    _catalogo_categoria("", [
        ("🗂️ Ações no Painel", "Tudo que um admin faz nas solicitações, mais os downloads via PAT do Azure DevOps (incluindo o alerta de possível anomalia)."),
        ("⚠️ Erros Técnicos", "Falhas capturadas em qualquer página - já abre em modo \"com detalhes\" (traceback completo)."),
        ("🔑 Login / Acessos", "Toda tentativa de login, sucesso ou falha."),
    ])
    st.caption("Cada tipo de log tem seletor de quantidade, botão de atualizar, e opção de limpar entradas antigas por número de dias.")

    st.markdown("<br>**3. Google Drive**", unsafe_allow_html=True)
    st.markdown(
        "Diagnóstico da conta de serviço usada na busca de arquivo no Google Drive (ver "
        "\"Importação de dados\" acima) - mostra o e-mail dela e um botão \"Testar conexão\". Não "
        "existe mais uma pasta única configurada por aqui: cada usuário guarda a PRÓPRIA pasta "
        "direto na tela Importar Dados, sem depender do administrador para trocar."
    )
    _callout(
        "A credencial da conta de serviço (a chave sensível) NÃO é configurada por aqui - fica só "
        "nos Secrets do Streamlit (produção) ou num arquivo local, nunca colada/enviada pela tela "
        "do app, pelo mesmo motivo de nenhuma senha/PAT ser guardado em disco neste sistema."
    )


# ---------------------------------------------------------------------------
# Entrada da página
# ---------------------------------------------------------------------------


def render_sobre_page() -> None:
    render_header(
        titulo="Sobre o App",
        subtitulo="Como o app funciona, do login até o relatório em PDF.",
    )

    # Calculado uma vez só por carregamento de página e reaproveitado nos
    # dois pontos que segregam conteúdo por papel (fluxograma + seção
    # "Administração", mais abaixo) - ver `_usuario_tem_visao_admin`.
    visao_admin = _usuario_tem_visao_admin()

    _sec_visao_geral()

    st.divider()
    _sec_fluxograma_completo(visao_admin)

    st.divider()
    st.markdown("### 📘 Guia Completo do Usuário")
    with st.expander("Como gerar seu PAT, montar a query certa, e baixar o guia em PDF", expanded=True):
        _sec_guia_para_baixar()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("### Detalhe de cada etapa")

    with st.expander("🔐 Login, acesso e solicitação de conta"):
        _sec_login()

    with st.expander("📥 Importação de dados — os três caminhos"):
        _sec_importacao()

    with st.expander("🗂️ Confirmar o mapeamento de colunas"):
        _sec_mapeamento()

    with st.expander("📊 O que cada gráfico do Painel de Indicadores mostra", expanded=False):
        _sec_catalogo_graficos()

    titulo_secao_admin = (
        "🔓 Administração (desbloqueado)" if visao_admin
        else "🔒 Administração (só para o admin, ou quem tiver o código de acesso)"
    )
    with st.expander(titulo_secao_admin):
        if visao_admin:
            _sec_administracao()
        else:
            _desbloquear_conteudo_admin()

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Esta página é só informativa - não lê nem altera nenhum dado do arquivo importado ou da "
        "sua sessão."
    )
