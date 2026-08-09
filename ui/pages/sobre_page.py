"""
Página "Sobre o App": explica, de forma visual, todos os fluxos do
Refuturiza QA - do login até o relatório em PDF, incluindo o que cada
gráfico do painel mostra e como funciona a Administração.

É só uma tela informativa (não lê nem grava nenhum dado do usuário) -
visível pra QUALQUER pessoa logada, não só o admin, porque o objetivo é
ajudar qualquer um a entender o app inteiro, inclusive o que existe do lado
da Administração mesmo que ela não tenha acesso a essa página.

Os diagramas são montados em HTML/CSS puro (ver classes `.sobre-fluxo-*`/
`.sobre-catalogo-*`/`.sobre-estado-*` em `ui/theme.py`), de propósito: nada
de Graphviz (precisa do binário `dot` instalado no sistema - mais uma coisa
pra falhar silenciosamente num Windows sem isso) nem Mermaid via JavaScript
injetado (mesma classe de fragilidade dos scripts de rolagem/foco já usados
em outras páginas, mas sem necessidade aqui, já que o diagrama é estático).
HTML/CSS puro roda 100% offline, sem dependência nova, e herda a mesma
paleta/fonte do resto do app em vez de parecer um diagrama genérico colado
por cima.
"""

from __future__ import annotations

import streamlit as st

from ui.components import render_header

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
    """
    colunas_html = []
    for titulo_ramo, passos in ramos:
        passos_html = "".join(
            f"""
            <div class="sobre-fluxo-passo">
                <div class="sobre-fluxo-numero">{numero}</div>
                <div class="sobre-fluxo-texto"><strong>{titulo}</strong>{f"<br>{texto}" if texto else ""}</div>
            </div>
            """
            for numero, titulo, texto in passos
        )
        colunas_html.append(
            f"""
            <div class="sobre-fluxo-ramo">
                <div class="sobre-fluxo-ramo-titulo">{titulo_ramo}</div>
                {passos_html}
            </div>
            """
        )
    st.markdown(
        f'<div class="sobre-fluxo-bifurcacao">{"".join(colunas_html)}</div>',
        unsafe_allow_html=True,
    )


def _callout(texto: str) -> None:
    st.markdown(f'<div class="sobre-callout">{texto}</div>', unsafe_allow_html=True)


def _catalogo_categoria(titulo: str, cartoes: list[tuple[str, str]]) -> None:
    """Um grupo de "cartões" de gráfico (título + descrição de uma linha), organizados em grade - ver `_sec_catalogo_graficos`."""
    cartoes_html = "".join(
        f"""
        <div class="sobre-catalogo-card">
            <div class="sobre-catalogo-card-titulo">{titulo_cartao}</div>
            <div class="sobre-catalogo-card-desc">{desc_cartao}</div>
        </div>
        """
        for titulo_cartao, desc_cartao in cartoes
    )
    st.markdown(
        f"""
        <div class="sobre-catalogo-categoria">{titulo}</div>
        <div class="sobre-catalogo-grade">{cartoes_html}</div>
        """,
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
        subtitulo="Como o Refuturiza QA funciona, do login até o relatório em PDF.",
    )

    _sec_visao_geral()

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

    with st.expander("⚙️ Administração (só para o admin)"):
        _sec_administracao()

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption(
        "Esta página é só informativa - não lê nem altera nenhum dado do arquivo importado ou da "
        "sua sessão."
    )
