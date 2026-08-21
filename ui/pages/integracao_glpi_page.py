"""
Página de Integração GLPI x Azure DevOps.

Acesso restrito: administradores do painel, mais quem for autorizado via
tabela `usuarios_autorizados_glpi_qa` (gerenciada em Admin -> Integração GLPI).

Fluxo por aba (Chamados / Problemas):
1. Buscar itens ativos no GLPI (`listar_chamados_ativos` / `listar_problemas_ativos`).
2. Buscar itens já existentes no board de destino no Azure DevOps
   (`listar_itens_existentes_no_board`), usado para dois níveis de deduplicação:
   a) Título EXATO ("Chamado {id}"/"Problema {id}") - já foi integrado antes,
      ponto final, não é oferecido de novo.
   b) Conteúdo PARECIDO (via difflib, sem IA - decisão explícita, já que só
      existem dois boards) - sinaliza uma possível duplicata mesmo com
      título/ID diferente.
      - Em CHAMADOS isso é só informativo: pode haver, legitimamente, mais de
        um chamado sobre o mesmo bug/erro/gap/falha - todos devem poder subir.
        A deduplicação real de Chamados continua sendo o título exato (ID do
        chamado no GLPI).
      - Em PROBLEMAS isso é tratado como duplicata real: o GLPI não deveria
        ter dois Problemas sobre o mesmo assunto. Uma linha com conteúdo
        parecido já nasce com "Integrar?" desmarcado e um aviso visível, mas
        a linha nunca é escondida e o checkbox continua editável - controle
        total é sempre do usuário.
3. Grid editável (`st.data_editor`) para revisar/confirmar responsável e
   decidir, linha a linha, o que efetivamente integrar.
4. Botão "Integrar selecionados" cria os Work Items faltantes no Azure DevOps.
"""

from __future__ import annotations

import difflib
import re

import pandas as pd
import streamlit as st

from auth.auth_manager import AuthManager
from core.azure_devops_client import (
    AzureDevOpsError,
    ItemExistenteBoard,
    criar_work_item,
    listar_area_paths,
    listar_itens_existentes_no_board,
    listar_projetos,
    listar_tipos_work_item,
)
from core.glpi_client import (
    ROTULOS_TIPO_CHAMADO,
    ROTULOS_URGENCIA,
    ChamadoGlpi,
    GlpiError,
    ProblemaGlpi,
    listar_chamados_ativos,
    listar_problemas_ativos,
)
from core.logs_sistema import TIPO_ERRO, TIPO_PAINEL, registrar_log
from core.turso_client import TursoError
from core.usuarios_autorizados_glpi import usuario_esta_na_lista
from ui.busca_azure_devops import ORGANIZACOES_SUGERIDAS
from ui.components import action_button, finish_action, loading_overlay, render_header
from ui.pages.admin_page import usuario_e_admin


TAG_SUSTENTACAO = "Sustentação"

# Acima de que taxa de similaridade (difflib.SequenceMatcher, de 0 a 1) duas
# descrições são consideradas "conteúdo parecido". Comparação puramente
# textual, sem IA/LLM - decisão explícita, já que só existem dois boards.
#
# 0.6 é um ponto de partida deliberadamente sensível (mais fácil de dar
# "falso positivo" do que de deixar passar uma duplicata de verdade), porque
# o custo dos dois erros é bem diferente aqui:
#   - Falso positivo: a linha nasce desmarcada à toa. Custo baixo - o
#     usuário só marca a caixa manualmente (controle total, nunca é bloqueio).
#   - Falso negativo: dois Problemas iguais sobem sem aviso nenhum. Isso é
#     exatamente o que o usuário pediu para NUNCA acontecer ("não ter
#     duplicações de jeito nenhum").
# Ajuste este valor depois de ver duplicatas reais do GLPI - texto duplicado
# de verdade raramente fica muito abaixo disso, mas vale calibrar com casos
# reais assim que o acesso ao GLPI estiver liberado.
LIMIAR_SIMILARIDADE_CONTEUDO = 0.6

_REGEX_TAG_HTML = re.compile(r"<[^>]+>")


def usuario_pode_acessar(username: str) -> bool:
    """True se o usuário pode ver/usar esta página: admin, ou autorizado explicitamente."""
    if not username:
        return False
    if usuario_e_admin(username):
        return True
    try:
        return usuario_esta_na_lista(username)
    except TursoError:
        return False


# ---------------------------------------------------------------------------
# Deduplicação por conteúdo (difflib - sem IA, ver LIMIAR_SIMILARIDADE_CONTEUDO)
# ---------------------------------------------------------------------------


def _texto_para_comparacao(html_ou_texto: str | None) -> str:
    """Remove tags HTML e normaliza espaços/caixa - usado só para comparar conteúdo, nunca exibido."""
    sem_tags = _REGEX_TAG_HTML.sub(" ", html_ou_texto or "")
    return " ".join(sem_tags.lower().split())


def _conteudo_comparavel_chamado(chamado: ChamadoGlpi) -> str:
    # Propositalmente SÓ a descrição crua do GLPI - título/categoria não
    # entram aqui porque o título muda por definição (é "Chamado {id}", o ID
    # é sempre diferente) e isso, sozinho, já derrubaria a taxa de
    # similaridade mesmo entre dois chamados sobre o mesmo bug. Ver também
    # `_conteudo_existente_apos_metadados`, que faz o mesmo recorte do lado
    # do item já existente no Azure, para a comparação ficar simétrica.
    return _texto_para_comparacao(chamado.descricao_html)


def _conteudo_comparavel_problema(problema: ProblemaGlpi) -> str:
    partes = [
        problema.descricao_html or "",
        problema.causa_raiz_html or "",
        problema.analise_html or "",
        problema.tratamento_html or "",
    ]
    return _texto_para_comparacao(" ".join(p for p in partes if p))


def _conteudo_existente_apos_metadados(item: ItemExistenteBoard) -> str:
    """
    A descrição gravada no Azure DevOps por esta integração (ver
    `_montar_descricao_chamado`/`_montar_descricao_problema`) sempre começa
    com um bloco de metadados (link para o GLPI, status, datas, solicitante,
    técnico) seguido de um "<hr/>", e só depois vem o conteúdo original do
    GLPI. Cortamos tudo antes do primeiro "<hr/>" para comparar conteúdo com
    conteúdo - sem isso, duas datas ou dois técnicos diferentes (comuns
    mesmo entre chamados/problemas genuinamente duplicados) derrubariam a
    taxa de similaridade por um motivo que nada tem a ver com o assunto
    tratado. Itens sem "<hr/>" (ex.: criados manualmente antes desta
    integração existir) entram inteiros na comparação, por segurança.
    """
    html = item.descricao_html or ""
    partes = html.split("<hr/>", 1)
    return partes[1] if len(partes) == 2 else html


def _encontrar_conteudo_parecido(
    texto_novo: str, itens_existentes: list[ItemExistenteBoard]
) -> tuple[ItemExistenteBoard, float] | None:
    """
    Compara `texto_novo` (já normalizado, ver `_conteudo_comparavel_chamado`/
    `_conteudo_comparavel_problema`) contra o conteúdo (pós-metadados) de
    cada item já existente no board, via `difflib.SequenceMatcher`. Devolve
    (o `ItemExistenteBoard` mais parecido, taxa de similaridade) quando a
    melhor taxa encontrada atinge/supera `LIMIAR_SIMILARIDADE_CONTEUDO`;
    devolve `None` caso contrário. Devolver o item inteiro (não só o título)
    permite à grade (`_renderizar_aba`) mostrar também um resumo do que já
    existe no Azure, não só o título e a porcentagem.
    """
    if not texto_novo:
        return None
    melhor: tuple[ItemExistenteBoard, float] | None = None
    for item in itens_existentes:
        texto_existente = _texto_para_comparacao(_conteudo_existente_apos_metadados(item))
        if not texto_existente:
            continue
        taxa = difflib.SequenceMatcher(None, texto_novo, texto_existente).ratio()
        if taxa >= LIMIAR_SIMILARIDADE_CONTEUDO and (melhor is None or taxa > melhor[1]):
            melhor = (item, taxa)
    return melhor


# ---------------------------------------------------------------------------
# Resumos para EXIBIÇÃO na grade (diferente do texto de comparação acima:
# aqui preservamos maiúsculas/pontuação e cortamos num tamanho legível -
# nunca são usados para decidir nada, só para o usuário ler "do que se
# trata" sem precisar abrir o GLPI ou o Azure DevOps em outra aba).
# ---------------------------------------------------------------------------

_TAMANHO_RESUMO = 220


def _resumo_para_exibicao(html_ou_texto: str | None, tamanho: int = _TAMANHO_RESUMO) -> str:
    sem_tags = _REGEX_TAG_HTML.sub(" ", html_ou_texto or "")
    texto = " ".join(sem_tags.split())
    if not texto:
        return ""
    if len(texto) <= tamanho:
        return texto
    return texto[:tamanho].rstrip() + "…"


def _resumo_novo_chamado(chamado: ChamadoGlpi) -> str:
    """Resumo do chamado NOVO, direto do GLPI - mesma fonte usada na descrição do Work Item."""
    return _resumo_para_exibicao(chamado.descricao_html)


def _resumo_novo_problema(problema: ProblemaGlpi) -> str:
    """Resumo do problema NOVO, direto do GLPI (descrição + causa raiz + análise + tratamento)."""
    partes = [
        problema.descricao_html or "",
        problema.causa_raiz_html or "",
        problema.analise_html or "",
        problema.tratamento_html or "",
    ]
    return _resumo_para_exibicao(" ".join(p for p in partes if p))


def _resumo_existente_azure(item: ItemExistenteBoard) -> str:
    """Resumo do item que JÁ EXISTE no Azure DevOps (sem o bloco de metadados - ver `_conteudo_existente_apos_metadados`)."""
    return _resumo_para_exibicao(_conteudo_existente_apos_metadados(item))


# ---------------------------------------------------------------------------
# Montagem das descrições - o título é só um título, o contexto vai na
# descrição do Work Item (link para o GLPI + campos relevantes por tipo).
# ---------------------------------------------------------------------------


def _linha_campo(rotulo: str, valor: str | None) -> str:
    if not valor:
        return ""
    return f"<p><strong>{rotulo}:</strong> {valor}</p>"


def _montar_descricao_chamado(chamado: ChamadoGlpi) -> str:
    tipo_rotulo = ROTULOS_TIPO_CHAMADO.get(chamado.tipo, str(chamado.tipo)) if chamado.tipo else None
    urgencia_rotulo = ROTULOS_URGENCIA.get(chamado.urgencia, str(chamado.urgencia)) if chamado.urgencia else None
    partes = [
        f'<p><a href="{chamado.link}" target="_blank">Ver chamado {chamado.id} no GLPI</a></p>',
        _linha_campo("Status", chamado.status_rotulo),
        _linha_campo("Tipo", tipo_rotulo),
        _linha_campo("Categoria", chamado.categoria),
        _linha_campo("Urgência", urgencia_rotulo),
        _linha_campo("Aberto em", chamado.data_abertura),
        _linha_campo("Solicitante", chamado.solicitante_nome),
        _linha_campo("Técnico atribuído (GLPI)", chamado.tecnico_nome),
        "<hr/>",
        chamado.descricao_html or "<p><em>Sem descrição no GLPI.</em></p>",
    ]
    return "".join(p for p in partes if p)


def _montar_descricao_problema(problema: ProblemaGlpi) -> str:
    partes = [
        f'<p><a href="{problema.link}" target="_blank">Ver problema {problema.id} no GLPI</a></p>',
        _linha_campo("Status", problema.status_rotulo),
        _linha_campo("Aberto em", problema.data_abertura),
        _linha_campo("Técnico atribuído (GLPI)", problema.tecnico_nome),
        "<hr/>",
        problema.descricao_html or "<p><em>Sem descrição no GLPI.</em></p>",
    ]
    if problema.causa_raiz_html:
        partes.append("<p><strong>Causa raiz:</strong></p>")
        partes.append(problema.causa_raiz_html)
    if problema.analise_html:
        partes.append("<p><strong>Análise:</strong></p>")
        partes.append(problema.analise_html)
    if problema.tratamento_html:
        partes.append("<p><strong>Tratamento:</strong></p>")
        partes.append(problema.tratamento_html)
    return "".join(p for p in partes if p)


# ---------------------------------------------------------------------------
# Modo teste - dados 100% fictícios (GLPI e Azure), nenhuma chamada de rede.
#
# Serve para visualizar a tela e a lógica de deduplicação por conteúdo antes
# de ter acesso Super-Admin no GLPI (ou antes de ter um board/sandbox real no
# Azure DevOps para testar). Enquanto este modo estiver ligado, a criação de
# Work Items fica desativada - nenhum dado fictício é gravado em lugar
# nenhum. Os exemplos abaixo foram montados de propósito para exercitar os
# três cenários de deduplicação:
#   - "Chamado 9003" já existe no board fictício -> título exato, não é
#     oferecido de novo (comportamento inalterado).
#   - "Chamado 9001" e "Chamado 9002" têm conteúdo parecido com um item
#     fictício já existente ("Chamado 8888") mas são chamados DIFERENTES -
#     em Chamados isso é só informativo, os dois continuam marcados para
#     subir (pode haver mais de um chamado sobre o mesmo bug).
#   - "Problema 501" tem conteúdo parecido com "Problema 777", já existente
#     - em Problemas isso é tratado como duplicata real, então nasce
#     desmarcado com aviso.
# ---------------------------------------------------------------------------


def _gerar_chamados_teste() -> list[ChamadoGlpi]:
    link_base = "https://suporte.refuturiza.com.br/front/ticket.form.php?id="
    return [
        ChamadoGlpi(
            id=9001,
            titulo="Chamado 9001",
            descricao_html="<p>Usuário relata tela branca ao tentar logar no portal, após clicar em Entrar.</p>",
            status=2,
            tipo=1,
            categoria="Login / Acesso",
            urgencia=4,
            data_abertura="21/08/2026 09:14:00",
            solicitante_nome="Maria Souza",
            solicitante_email="maria.souza@refuturiza.com.br",
            tecnico_nome="João Pereira",
            tecnico_email="joao.pereira@refuturiza.com.br",
            link=f"{link_base}9001",
        ),
        ChamadoGlpi(
            id=9002,
            titulo="Chamado 9002",
            descricao_html="<p>Login trava em tela branca depois que o usuário clica em Entrar no portal.</p>",
            status=1,
            tipo=1,
            categoria="Login / Acesso",
            urgencia=3,
            data_abertura="21/08/2026 10:02:00",
            solicitante_nome="Carlos Lima",
            solicitante_email="carlos.lima@refuturiza.com.br",
            tecnico_nome=None,
            tecnico_email=None,
            link=f"{link_base}9002",
        ),
        ChamadoGlpi(
            id=9003,
            titulo="Chamado 9003",
            descricao_html="<p>Solicitação de acesso ao módulo financeiro para o novo colaborador do setor.</p>",
            status=4,
            tipo=2,
            categoria="Acessos",
            urgencia=2,
            data_abertura="20/08/2026 16:40:00",
            solicitante_nome="Ana Paula",
            solicitante_email="ana.paula@refuturiza.com.br",
            tecnico_nome="João Pereira",
            tecnico_email="joao.pereira@refuturiza.com.br",
            link=f"{link_base}9003",
        ),
        ChamadoGlpi(
            id=9004,
            titulo="Chamado 9004",
            descricao_html="<p>Relatório de vendas do mês não está exportando em PDF, trava em 90%.</p>",
            status=1,
            tipo=1,
            categoria="Relatórios",
            urgencia=3,
            data_abertura="21/08/2026 11:30:00",
            solicitante_nome="Roberto Alves",
            solicitante_email="roberto.alves@refuturiza.com.br",
            tecnico_nome=None,
            tecnico_email=None,
            link=f"{link_base}9004",
        ),
    ]


def _gerar_problemas_teste() -> list[ProblemaGlpi]:
    link_base = "https://suporte.refuturiza.com.br/front/problem.form.php?id="
    return [
        ProblemaGlpi(
            id=501,
            titulo="Problema 501",
            descricao_html="<p>Falha recorrente de autenticação via SSO, atingindo múltiplos usuários ao mesmo tempo.</p>",
            status=2,
            causa_raiz_html=None,
            analise_html="<p>Em investigação junto ao provedor de identidade.</p>",
            tratamento_html=None,
            data_abertura="20/08/2026 08:00:00",
            tecnico_nome="João Pereira",
            tecnico_email="joao.pereira@refuturiza.com.br",
            link=f"{link_base}501",
        ),
        ProblemaGlpi(
            id=502,
            titulo="Problema 502",
            descricao_html="<p>Geração de relatórios consolidados está expirando por timeout no fim do dia.</p>",
            status=1,
            causa_raiz_html=None,
            analise_html=None,
            tratamento_html=None,
            data_abertura="21/08/2026 07:45:00",
            tecnico_nome=None,
            tecnico_email=None,
            link=f"{link_base}502",
        ),
    ]


def _gerar_itens_existentes_teste(aba_key: str) -> list[ItemExistenteBoard]:
    if aba_key == "chamados":
        return [
            ItemExistenteBoard(
                titulo="Chamado 8888",
                descricao_html="<p>Usuário relatou tela branca ao tentar fazer login no portal ao clicar em Entrar.</p>",
            ),
            ItemExistenteBoard(
                titulo="Chamado 9003",
                descricao_html="<p>Solicitação de acesso ao módulo financeiro para o novo colaborador do setor.</p>",
            ),
        ]
    return [
        ItemExistenteBoard(
            titulo="Problema 777",
            descricao_html="<p>Instabilidade recorrente na autenticação via SSO afetando múltiplos usuários simultaneamente.</p>",
        ),
    ]


# ---------------------------------------------------------------------------
# Seletor de destino no Azure DevOps (PAT -> Organização -> Projeto ->
# Area Path -> Tipo de Work Item) + walkthrough do PAT de leitura E escrita.
# ---------------------------------------------------------------------------


def _explicar_pat_leitura_e_escrita() -> None:
    """
    Walkthrough completo, passo a passo, para gerar um PAT com escopo
    Work Items -> Read & Write.

    Usado SÓ nesta página (Integração GLPI). As demais áreas do app
    (Importar Dados, Scrum & Sprints etc.) continuam com suas próprias
    instruções, mais curtas, em `ui/busca_azure_devops.py` - aquele texto não
    é alterado por este aqui: esta tela cria Work Items (grava), as outras só
    leem, por isso os PATs e as instruções são propositalmente segregados.
    """
    with st.expander(
        "📘 Como gerar o PAT com permissão de leitura E escrita (passo a passo)",
        expanded=False,
    ):
        st.markdown(
            """
Esta tela **cria** Work Items no Azure DevOps (não só lê). Por isso, o PAT usado
aqui precisa do escopo **Work Items → Read & Write** — diferente das outras áreas
do painel (Importar Dados, Scrum & Sprints etc.), que só pedem leitura.

O PAT nunca é salvo em disco nem nos Secrets do Streamlit — ele fica só na
memória desta sessão do navegador e some ao sair.

**Passo a passo:**

1. Acesse **dev.azure.com** e faça login com a conta que tem acesso à
   organização do Azure DevOps que você vai usar aqui.
2. Clique no ícone do seu perfil (canto superior direito) e escolha
   **"Personal Access Tokens"**. Se preferir, vá direto pela URL, trocando
   `SUAORGANIZACAO` pelo nome da sua organização:
   `https://dev.azure.com/SUAORGANIZACAO/_usersSettings/tokens`
3. Clique em **"+ New Token"**.
4. Dê um nome que ajude a identificar depois (ex.: `Integracao GLPI - Leitura e Escrita`).
5. Em **Organization**, confirme que está selecionada a organização correta
   (a mesma que você vai escolher no seletor logo abaixo).
6. Em **Expiration**, escolha uma validade (ex.: 30 ou 90 dias). Quando o
   token expirar, basta gerar um novo e colar aqui de novo — nada mais no
   painel precisa mudar.
7. Em **Scopes**, clique em **"Custom defined"** (⚠️ não use "Full access").
8. Na lista de escopos, procure **"Work Items"** e selecione **"Read & Write"**
   (⚠️ não escolha só "Read" — sem o "Write" a criação dos itens vai falhar
   com erro de permissão).
9. Clique em **"Create"**.
10. **Copie o token imediatamente** — o Azure DevOps mostra o valor só uma
    única vez. Se perder, é preciso gerar um novo token do zero.
11. Cole o token no campo abaixo. Ele fica só nesta sessão do seu navegador.
            """
        )


def _selecionar_destino_azure(namespace: str, rotulo_board: str):
    """
    Seletor em cascata PAT -> Organização -> Projeto -> Area Path -> Tipo de
    Work Item, namespaced em `st.session_state` por `namespace` (para não
    conflitar entre as abas Chamados x Problemas). Devolve
    (organizacao, projeto, area_path, tipo_wi, pat), ou `None` se algo faltar.

    Layout "zigue-zague": cada etapa ocupa uma coluna, alternando 1ª/2ª
    coluna a cada nova etapa (PAT -> coluna 1 da linha 1, Organização ->
    coluna 2 da linha 1, Projeto -> coluna 1 da linha 2, e assim por diante),
    em vez de uma etapa por linha inteira. Como cada etapa só aparece depois
    que a anterior tem um valor válido (é uma cascata), o zigue-zague vai se
    preenchendo progressivamente conforme o usuário completa cada campo.
    """
    _explicar_pat_leitura_e_escrita()

    linha1_col1, linha1_col2 = st.columns(2)
    with linha1_col1:
        pat = st.text_input(
            "Personal Access Token (PAT) com escopo Work Items (Read & Write)",
            type="password",
            key=f"{namespace}_pat",
            help="Veja o passo a passo acima para gerar este token.",
        )
    if not pat:
        st.info("Informe o PAT acima para carregar organizações, projetos e area paths.")
        return None

    with linha1_col2:
        organizacao = st.selectbox("Organização", options=ORGANIZACOES_SUGERIDAS, key=f"{namespace}_organizacao")
    if not organizacao:
        return None

    try:
        projetos = listar_projetos(organizacao, pat)
    except AzureDevOpsError as exc:
        st.error(f"Não foi possível carregar os projetos: {exc}")
        return None
    if not projetos:
        st.warning("Nenhum projeto encontrado para esta organização/PAT.")
        return None

    linha2_col1, linha2_col2 = st.columns(2)
    with linha2_col1:
        projeto = st.selectbox("Projeto", options=[p.nome for p in projetos], key=f"{namespace}_projeto")
    if not projeto:
        return None

    try:
        area_paths = listar_area_paths(organizacao, projeto, pat)
    except AzureDevOpsError as exc:
        st.error(f"Não foi possível carregar os Area Paths: {exc}")
        return None
    if not area_paths:
        st.warning("Nenhum Area Path encontrado para este projeto.")
        return None

    with linha2_col2:
        area_path = st.selectbox(
            f"Area Path (board de {rotulo_board})", options=area_paths, key=f"{namespace}_area_path"
        )
    if not area_path:
        return None

    try:
        tipos_wi = listar_tipos_work_item(organizacao, projeto, pat)
    except AzureDevOpsError as exc:
        st.error(f"Não foi possível carregar os tipos de Work Item: {exc}")
        return None
    if not tipos_wi:
        st.warning("Nenhum tipo de Work Item encontrado para este projeto.")
        return None

    linha3_col1, _linha3_col2 = st.columns(2)
    indice_padrao = tipos_wi.index("User Story") if "User Story" in tipos_wi else 0
    with linha3_col1:
        tipo_wi = st.selectbox(
            "Tipo de Work Item a ser criado",
            options=tipos_wi,
            index=indice_padrao,
            key=f"{namespace}_tipo_wi",
            help="Convenção atual do time é 'User Story' - confirme com a gerência se isso mudar no futuro.",
        )
    if not tipo_wi:
        return None

    return organizacao, projeto, area_path, tipo_wi, pat


# ---------------------------------------------------------------------------
# Aba (Chamados ou Problemas): buscar -> revisar/confirmar -> integrar.
# ---------------------------------------------------------------------------


def _renderizar_aba(aba_key: str, rotulo_plural: str, rotulo_singular: str) -> None:
    st.subheader(rotulo_plural)
    st.caption(
        f"Busca {rotulo_plural.lower()} ativos no GLPI, compara com o que já existe no "
        f"board escolhido no Azure DevOps e permite integrar só o que você confirmar."
    )

    modo_teste = st.checkbox(
        "🧪 Usar dados fictícios (modo teste - GLPI e Azure simulados, nenhuma chamada de rede)",
        key=f"glpi_{aba_key}_modo_teste",
        help=(
            "Mostra a tela e a lógica de deduplicação funcionando com exemplos prontos, sem "
            "precisar de PAT nem de acesso ao GLPI ainda. Enquanto este modo estiver ligado, o "
            "botão de integrar fica desativado - nenhum dado fictício é gravado em lugar nenhum."
        ),
    )

    organizacao = projeto = area_path = tipo_wi = pat = None
    if not modo_teste:
        destino = _selecionar_destino_azure(namespace=f"glpi_{aba_key}", rotulo_board=rotulo_plural)
        if destino is None:
            return
        organizacao, projeto, area_path, tipo_wi, pat = destino

    chave_itens = f"glpi_{aba_key}_itens"
    chave_existentes = f"glpi_{aba_key}_existentes"

    rotulo_botao_buscar = (
        "🧪 Gerar dados de teste" if modo_teste else f"🔄 Buscar {rotulo_plural.lower()} ativos no GLPI"
    )
    if st.button(rotulo_botao_buscar, key=f"glpi_{aba_key}_buscar"):
        if modo_teste:
            itens_glpi = _gerar_chamados_teste() if aba_key == "chamados" else _gerar_problemas_teste()
            itens_existentes = _gerar_itens_existentes_teste(aba_key)
        else:
            with loading_overlay(
                f"Buscando {rotulo_plural.lower()} no GLPI e itens já existentes no Azure DevOps..."
            ):
                try:
                    itens_glpi = listar_chamados_ativos() if aba_key == "chamados" else listar_problemas_ativos()
                    itens_existentes = listar_itens_existentes_no_board(organizacao, projeto, area_path, pat)
                except (GlpiError, AzureDevOpsError) as exc:
                    st.error(f"Erro ao buscar dados: {exc}")
                    return
        st.session_state[chave_itens] = itens_glpi
        st.session_state[chave_existentes] = itens_existentes

    itens_glpi = st.session_state.get(chave_itens)
    itens_existentes = st.session_state.get(chave_existentes)

    if itens_glpi is None or itens_existentes is None:
        return

    if not itens_glpi:
        st.info(f"Nenhum {rotulo_singular.lower()} ativo encontrado no GLPI.")
        return

    titulos_existentes = {i.titulo for i in itens_existentes}
    existentes_por_titulo = {i.titulo: i for i in itens_existentes}

    st.caption(
        "🆕 = dado novo, vindo do GLPI (o que seria criado no Azure DevOps)  ·  "
        "☁️ = dado que já existe hoje no board do Azure DevOps (só para comparação, nada aqui é gravado)."
    )

    linhas = []
    for item in itens_glpi:
        titulo_esperado = f"{rotulo_singular} {item.id}"
        ja_no_azure = titulo_esperado in titulos_existentes

        texto_comparavel = (
            _conteudo_comparavel_chamado(item) if aba_key == "chamados" else _conteudo_comparavel_problema(item)
        )
        parecido = _encontrar_conteudo_parecido(texto_comparavel, itens_existentes)

        if ja_no_azure:
            integrar_padrao = False
        elif aba_key == "problemas" and parecido is not None:
            # Problemas: conteúdo parecido é tratado como duplicata real - a
            # linha nasce desmarcada, com aviso visível, mas continua
            # editável (controle total é sempre do usuário).
            integrar_padrao = False
        else:
            # Chamados: conteúdo parecido é só informativo. Pode haver,
            # legitimamente, vários chamados sobre o mesmo bug/erro - todos
            # devem poder subir; a deduplicação real aqui é o título exato
            # (ID do chamado no GLPI), não o conteúdo.
            integrar_padrao = True

        conteudo_parecido_rotulo = ""
        item_existente_relacionado = None
        if parecido is not None:
            item_existente_relacionado, taxa = parecido
            conteudo_parecido_rotulo = f"{item_existente_relacionado.titulo} ({taxa:.0%})"
        if item_existente_relacionado is None and ja_no_azure:
            item_existente_relacionado = existentes_por_titulo.get(titulo_esperado)

        resumo_glpi = _resumo_novo_chamado(item) if aba_key == "chamados" else _resumo_novo_problema(item)
        resumo_azure = _resumo_existente_azure(item_existente_relacionado) if item_existente_relacionado else ""

        linhas.append(
            {
                "Integrar?": integrar_padrao,
                "Já no Azure": ja_no_azure,
                "ID": item.id,
                "Título no GLPI": item.titulo,
                "Status": item.status_rotulo,
                "Resumo (GLPI)": resumo_glpi,
                "Conteúdo parecido com": conteudo_parecido_rotulo,
                "Resumo (Azure)": resumo_azure,
                "Responsável (e-mail no Azure DevOps)": item.tecnico_email or "",
            }
        )

    df = pd.DataFrame(linhas)

    if aba_key == "problemas" and (df["Conteúdo parecido com"] != "").any():
        st.warning(
            "⚠️ Alguns problemas têm conteúdo parecido com um item que já existe no board. "
            "O GLPI não deveria ter dois Problemas sobre o mesmo assunto — por isso essas "
            "linhas já nascem com 'Integrar?' desmarcado. Confira as colunas ☁️ para comparar "
            "e marque manualmente se, mesmo assim, quiser integrar."
        )

    df_editado = st.data_editor(
        df,
        key=f"glpi_{aba_key}_grid",
        hide_index=True,
        use_container_width=True,
        disabled=[
            "Já no Azure",
            "ID",
            "Título no GLPI",
            "Status",
            "Resumo (GLPI)",
            "Conteúdo parecido com",
            "Resumo (Azure)",
        ],
        column_config={
            "Integrar?": st.column_config.CheckboxColumn("Integrar?"),
            "Já no Azure": st.column_config.CheckboxColumn("☁️ Já no Azure"),
            "ID": st.column_config.NumberColumn("🆕 ID"),
            "Título no GLPI": st.column_config.TextColumn("🆕 Título no GLPI"),
            "Status": st.column_config.TextColumn("🆕 Status (GLPI)"),
            "Resumo (GLPI)": st.column_config.TextColumn(
                "🆕 Resumo (GLPI)",
                width="large",
                help="Trecho da descrição do chamado/problema, direto do GLPI - o que viraria a descrição do Work Item.",
            ),
            "Conteúdo parecido com": st.column_config.TextColumn(
                "☁️ Parecido com (Azure)",
                help="Título e % de similaridade do item já existente no board mais parecido, se houver.",
            ),
            "Resumo (Azure)": st.column_config.TextColumn(
                "☁️ Resumo do item já existente (Azure)",
                width="large",
                help="Trecho do conteúdo do item já existente no board (o mesmo item da coluna anterior), para comparar lado a lado.",
            ),
            "Responsável (e-mail no Azure DevOps)": st.column_config.TextColumn(
                "Responsável (e-mail no Azure DevOps)"
            ),
        },
    )

    selecionados = df_editado[df_editado["Integrar?"]]
    st.caption(f"{len(selecionados)} de {len(df_editado)} selecionado(s) para integração.")

    if modo_teste:
        st.info(
            "🧪 Modo teste ativo: a criação de Work Items está desativada para não gravar dados "
            "fictícios em nenhum board real. Desmarque o modo teste e informe PAT, Organização, "
            "Projeto e Area Path quando quiser integrar de verdade."
        )
        return

    chave_integrar = f"glpi_{aba_key}_integrar"
    # `action_button` (não `st.button`) de propósito: esta é a única ação
    # desta tela que GRAVA de verdade no Azure DevOps (cria Work Items). Um
    # clique duplo com `st.button` comum poderia disparar a criação dos
    # mesmos itens duas vezes antes da primeira leva terminar - exatamente o
    # tipo de duplicata que toda a lógica de deduplicação desta página existe
    # pra evitar. Mesmo padrão já usado em `ui/pages/admin_page.py` para
    # qualquer ação que grava/altera algo.
    if action_button("🚀 Integrar selecionados", key=chave_integrar, disabled=selecionados.empty):
        itens_por_id = {item.id: item for item in itens_glpi}
        sucesso = []
        falha = []
        usuario_atual = AuthManager.current_username()
        with loading_overlay("Criando Work Items no Azure DevOps..."):
            for _, linha in selecionados.iterrows():
                item = itens_por_id[linha["ID"]]
                titulo = f"{rotulo_singular} {item.id}"
                descricao = (
                    _montar_descricao_chamado(item) if aba_key == "chamados" else _montar_descricao_problema(item)
                )
                email_responsavel = (linha["Responsável (e-mail no Azure DevOps)"] or "").strip() or None
                try:
                    resultado = criar_work_item(
                        organization=organizacao,
                        project=projeto,
                        area_path=area_path,
                        work_item_type=tipo_wi,
                        title=titulo,
                        description_html=descricao,
                        tags=[TAG_SUSTENTACAO],
                        pat=pat,
                        assigned_to_email=email_responsavel,
                    )
                    sucesso.append((titulo, resultado))
                    registrar_log(
                        TIPO_PAINEL, usuario_atual,
                        f"Criou o Work Item '{titulo}' a partir do GLPI ({rotulo_plural}) -> {resultado.url_html}",
                    )
                except AzureDevOpsError as exc:
                    falha.append((titulo, str(exc)))
                    registrar_log(
                        TIPO_ERRO, usuario_atual,
                        f"Falha ao integrar '{titulo}' do GLPI ({rotulo_plural}): {exc}",
                    )
        finish_action(chave_integrar)

        if sucesso:
            st.success(f"{len(sucesso)} item(ns) criado(s) com sucesso:")
            for titulo, resultado in sucesso:
                aviso_atribuicao = (
                    ""
                    if resultado.atribuicao_aplicada
                    else " (⚠️ criado sem atribuição - e-mail não encontrado no Azure DevOps)"
                )
                st.markdown(f"- [{titulo}]({resultado.url_html}){aviso_atribuicao}")
        if falha:
            st.error(f"{len(falha)} item(ns) com falha:")
            for titulo, erro in falha:
                st.markdown(f"- {titulo}: {erro}")

        st.session_state.pop(chave_itens, None)
        st.session_state.pop(chave_existentes, None)
        st.rerun()


def render_integracao_glpi_page() -> None:
    render_header(
        titulo="🔗 Integração GLPI x Azure DevOps",
        subtitulo="Transforma chamados e problemas ativos do GLPI em Work Items no Azure DevOps.",
    )

    aba_chamados, aba_problemas = st.tabs(["🎫 Chamados", "❗ Problemas"])
    with aba_chamados:
        _renderizar_aba("chamados", "Chamados", "Chamado")
    with aba_problemas:
        _renderizar_aba("problemas", "Problemas", "Problema")
