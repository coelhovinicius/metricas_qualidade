"""
Cliente para a API REST do GLPI (`/apirest.php`), usado pela Integração GLPI
x Azure DevOps (ver `ui/pages/integracao_glpi_page.py`).

⚠️ AVISO IMPORTANTE SOBRE O ESTADO DESTE ARQUIVO: escrito ANTES de haver
acesso de Super-Admin liberado no GLPI da empresa (pré-requisito para sequer
ativar a API REST lá - ver Configurar → Geral → API), então nada aqui foi
testado contra uma instância real ainda. Os endpoints/nomes de campo usados
seguem a documentação PADRÃO da API REST do GLPI (a mesma em qualquer
instalação não customizada por plugin), mas o primeiro passo assim que o
acesso sair é validar cada função abaixo contra o GLPI de verdade e ajustar
o que precisar - em especial os nomes de campo específicos de Problema
(`cause`/`impact`/`symptom`) e a forma de descobrir o técnico
atribuído/solução (ver comentários pontuais abaixo).

Arquitetura de credenciais (token fixo em Secrets - decisão já tomada, ao
contrário do PAT do Azure DevOps que é por usuário): como esta área é
restrita a um grupo pequeno de pessoas autorizadas (ver
`core/usuarios_autorizados_glpi.py`) e o objetivo é só LER chamados/problemas
(não fazer nada em nome de uma pessoa específica), não há necessidade de um
token por pessoa - um único App-Token + User-Token, guardados nos Secrets do
Streamlit, servem para qualquer pessoa autorizada.

Configuração esperada em `st.secrets` (nunca no código/Git):

    [glpi]
    url_base = "https://suporte.refuturiza.com.br"
    app_token = "SEU_APP_TOKEN"
    user_token = "SEU_USER_TOKEN"

Ver Configurar → Geral → API (App-Token) e Preferências → "Chaves de acesso
remoto" → API token (User-Token) dentro do próprio GLPI para gerar os dois.

Status ativos vs. finalizados (Chamados e Problemas usam a mesma escala
padrão do GLPI - `CommonITILObject::status`):
    1 = Novo
    2 = Em atendimento (atribuído)
    3 = Em atendimento (planejado)
    4 = Pendente
    5 = Solucionado
    6 = Fechado
"Ativo" = status NÃO em {5, 6} (Solucionado/Fechado) - ver `STATUS_FINALIZADOS`
abaixo. Se a instância de vocês tiver status customizados além destes 6
(GLPI permite isso via plugins de status), essa lista é o primeiro lugar a
ajustar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests
import streamlit as st

TIMEOUT_SEGUNDOS = 30
TAMANHO_PAGINA = 250  # itens por página ao paginar /Ticket ou /Problem

STATUS_FINALIZADOS = {5, 6}  # Solucionado, Fechado - ver docstring do módulo

ROTULOS_STATUS = {
    1: "Novo",
    2: "Em atendimento (atribuído)",
    3: "Em atendimento (planejado)",
    4: "Pendente",
    5: "Solucionado",
    6: "Fechado",
}

# Escala padrão de urgência/prioridade do GLPI (1 a 5) - mesmos rótulos em
# qualquer instalação não customizada.
ROTULOS_URGENCIA = {1: "Muito baixa", 2: "Baixa", 3: "Média", 4: "Alta", 5: "Muito alta"}

ROTULOS_TIPO_CHAMADO = {1: "Incidente", 2: "Requisição/Solicitação"}

# Tipo de vínculo em Ticket_User/Problem_User - 1 = Solicitante, 2 = Atribuído,
# 3 = Observador. Usado por `_buscar_pessoa_vinculada` abaixo.
_TIPO_VINCULO_SOLICITANTE = 1
_TIPO_VINCULO_ATRIBUIDO = 2


class GlpiError(Exception):
    """Erro amigável de configuração/comunicação com a API do GLPI."""


@dataclass
class ChamadoGlpi:
    id: int
    titulo: str
    descricao_html: str
    status: int
    tipo: Optional[int]
    categoria: Optional[str]
    urgencia: Optional[int]
    data_abertura: Optional[str]
    solicitante_nome: Optional[str]
    solicitante_email: Optional[str]
    tecnico_nome: Optional[str]
    tecnico_email: Optional[str]
    link: str

    @property
    def status_rotulo(self) -> str:
        return ROTULOS_STATUS.get(self.status, f"Status {self.status}")


@dataclass
class ProblemaGlpi:
    id: int
    titulo: str
    descricao_html: str
    status: int
    causa_raiz_html: Optional[str]
    analise_html: Optional[str]  # campo "impact" do GLPI - ver nota em `_montar_problema`
    tratamento_html: Optional[str]
    data_abertura: Optional[str]
    tecnico_nome: Optional[str]
    tecnico_email: Optional[str]
    link: str

    @property
    def status_rotulo(self) -> str:
        return ROTULOS_STATUS.get(self.status, f"Status {self.status}")


def _configuracao() -> tuple[str, str, str]:
    try:
        secao = st.secrets.get("glpi")
    except Exception:
        secao = None
    if not secao or not secao.get("url_base") or not secao.get("app_token") or not secao.get("user_token"):
        raise GlpiError(
            "A integração com o GLPI ainda não está configurada. Adicione a seção [glpi] "
            "(url_base, app_token, user_token) nos Secrets do Streamlit."
        )
    url_base = secao["url_base"].rstrip("/")
    return url_base, secao["app_token"], secao["user_token"]


def _tratar_erro_http(resposta: requests.Response, contexto: str) -> None:
    if resposta.status_code == 401:
        raise GlpiError(
            f"O GLPI recusou a autenticação ({contexto}) - confira o App-Token e o User-Token "
            "configurados nos Secrets, e se a API REST está ativada em Configurar → Geral → API."
        )
    if resposta.status_code == 400:
        raise GlpiError(f"O GLPI recusou a requisição ({contexto}, HTTP 400): {resposta.text[:300]}")
    if not resposta.ok:
        raise GlpiError(f"O GLPI retornou um erro inesperado ({contexto}, HTTP {resposta.status_code}): {resposta.text[:300]}")


def iniciar_sessao(url_base: str, app_token: str, user_token: str) -> str:
    """Abre uma sessão na API do GLPI e devolve o Session-Token (initSession)."""
    try:
        resposta = requests.get(
            f"{url_base}/apirest.php/initSession",
            headers={"App-Token": app_token, "Authorization": f"user_token {user_token}"},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException as exc:
        raise GlpiError(f"Não foi possível conectar ao GLPI ({url_base}): {exc}") from exc
    _tratar_erro_http(resposta, "initSession")
    try:
        return resposta.json()["session_token"]
    except (ValueError, KeyError) as exc:
        raise GlpiError("O GLPI respondeu, mas sem um 'session_token' reconhecível.") from exc


def encerrar_sessao(url_base: str, app_token: str, session_token: str) -> None:
    """Fecha a sessão aberta por `iniciar_sessao` (best-effort - nunca levanta exceção)."""
    try:
        requests.get(
            f"{url_base}/apirest.php/killSession",
            headers={"App-Token": app_token, "Session-Token": session_token},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except requests.RequestException:
        pass


def testar_conexao() -> None:
    """Levanta `GlpiError` se a configuração/conexão estiver com problema (usado no painel admin)."""
    url_base, app_token, user_token = _configuracao()
    session_token = iniciar_sessao(url_base, app_token, user_token)
    encerrar_sessao(url_base, app_token, session_token)


def _cabecalhos(app_token: str, session_token: str) -> dict:
    return {"App-Token": app_token, "Session-Token": session_token}


def _paginar_itens(url_base: str, itemtype: str, headers: dict) -> list[dict]:
    """
    Busca TODOS os itens de um tipo (`Ticket` ou `Problem`), paginando em
    blocos de `TAMANHO_PAGINA` até a API devolver menos itens do que o
    pedido (sinal de que chegou na última página). `expand_dropdowns=true`
    faz campos do tipo dropdown/árvore (ex.: `itilcategories_id`) virem já
    como texto legível, em vez de um ID numérico cru.
    """
    itens: list[dict] = []
    inicio = 0
    while True:
        try:
            resposta = requests.get(
                f"{url_base}/apirest.php/{itemtype}",
                headers=headers,
                params={
                    "range": f"{inicio}-{inicio + TAMANHO_PAGINA - 1}",
                    "expand_dropdowns": "true",
                },
                timeout=TIMEOUT_SEGUNDOS,
            )
        except requests.RequestException as exc:
            raise GlpiError(f"Não foi possível buscar {itemtype} no GLPI: {exc}") from exc
        _tratar_erro_http(resposta, f"listar {itemtype}")
        try:
            pagina = resposta.json()
        except ValueError as exc:
            raise GlpiError(f"O GLPI respondeu, mas o conteúdo de {itemtype} não é um JSON válido.") from exc
        if not isinstance(pagina, list):
            # A API devolve um dict (não uma lista) quando não há nenhum item
            # do tipo - trata como página vazia em vez de erro.
            break
        itens.extend(pagina)
        if len(pagina) < TAMANHO_PAGINA:
            break
        inicio += TAMANHO_PAGINA
    return itens


def _buscar_pessoa_vinculada(
    url_base: str, itemtype: str, item_id: int, headers: dict, tipo_vinculo: int
) -> tuple[Optional[str], Optional[str]]:
    """
    Busca o nome/e-mail da pessoa vinculada a um Chamado/Problema com um tipo
    de vínculo específico (1=Solicitante, 2=Atribuído) - no GLPI, essas
    ligações vivem numa tabela própria (`Ticket_User`/`Problem_User`), não
    como um campo direto no item.

    ⚠️ Não testado contra uma instância real ainda (ver aviso no topo do
    arquivo) - a existência do sub-recurso `/{itemtype}/{id}/{itemtype}_User`
    é o comportamento padrão documentado da API REST do GLPI, mas vale
    confirmar assim que houver acesso de verdade.

    Melhor esforço: qualquer falha aqui devolve `(None, None)` em vez de
    propagar erro - não vale a pena travar a listagem inteira de chamados
    só porque não achou o responsável de UM deles.
    """
    try:
        resposta = requests.get(
            f"{url_base}/apirest.php/{itemtype}/{item_id}/{itemtype}_User",
            headers=headers,
            timeout=TIMEOUT_SEGUNDOS,
        )
        if not resposta.ok:
            return None, None
        vinculos = resposta.json()
        if not isinstance(vinculos, list):
            return None, None
        for vinculo in vinculos:
            if vinculo.get("type") == tipo_vinculo:
                nome = vinculo.get("alternative_email") or vinculo.get("users_id")
                # `use_notification`/`alternative_email` cobre solicitante
                # anônimo; o caminho comum é o campo do usuário vinculado
                # devolver nome/e-mail diretamente quando expandido - como
                # este endpoint não aceita `expand_dropdowns`, o valor pode
                # vir só como ID numérico em instalações mais antigas. Ver
                # aviso do módulo: ajustar aqui após testar ao vivo.
                email = vinculo.get("alternative_email")
                return (str(nome) if nome else None), email
    except (requests.RequestException, ValueError):
        pass
    return None, None


def _montar_chamado(url_base: str, item: dict, headers: dict) -> ChamadoGlpi:
    tecnico_nome, tecnico_email = _buscar_pessoa_vinculada(
        url_base, "Ticket", item["id"], headers, _TIPO_VINCULO_ATRIBUIDO
    )
    solicitante_nome, solicitante_email = _buscar_pessoa_vinculada(
        url_base, "Ticket", item["id"], headers, _TIPO_VINCULO_SOLICITANTE
    )
    return ChamadoGlpi(
        id=item["id"],
        titulo=item.get("name") or f"Chamado {item['id']}",
        descricao_html=item.get("content") or "",
        status=int(item.get("status", 0)),
        tipo=item.get("type"),
        categoria=item.get("itilcategories_id") or None,
        urgencia=item.get("urgency"),
        data_abertura=item.get("date"),
        solicitante_nome=solicitante_nome,
        solicitante_email=solicitante_email,
        tecnico_nome=tecnico_nome,
        tecnico_email=tecnico_email,
        link=f"{url_base}/front/ticket.form.php?id={item['id']}",
    )


def _montar_problema(url_base: str, item: dict, headers: dict) -> ProblemaGlpi:
    tecnico_nome, tecnico_email = _buscar_pessoa_vinculada(
        url_base, "Problem", item["id"], headers, _TIPO_VINCULO_ATRIBUIDO
    )
    return ProblemaGlpi(
        id=item["id"],
        titulo=item.get("name") or f"Problema {item['id']}",
        descricao_html=item.get("content") or "",
        status=int(item.get("status", 0)),
        # Nomes de campo padrão do GLPI para a análise de Problema (ITIL) -
        # "cause" (causa raiz), "impact" (análise/impacto), "symptom"
        # (sintoma). ⚠️ Confirmar contra a API real assim que possível (ver
        # aviso no topo do arquivo) - se algum vier vazio/ausente aqui, o
        # bloco de contexto da descrição simplesmente omite esse campo, sem
        # quebrar a integração.
        causa_raiz_html=item.get("cause") or None,
        analise_html=item.get("impact") or None,
        tratamento_html=item.get("symptom") or None,
        data_abertura=item.get("date"),
        tecnico_nome=tecnico_nome,
        tecnico_email=tecnico_email,
        link=f"{url_base}/front/problem.form.php?id={item['id']}",
    )


def listar_chamados_ativos() -> list[ChamadoGlpi]:
    """
    Lista todos os Chamados (Tickets) com status ainda ATIVO (não
    Solucionado/Fechado - ver `STATUS_FINALIZADOS`). Abre e fecha a própria
    sessão internamente. Levanta `GlpiError` em caso de falha de
    configuração/comunicação.
    """
    url_base, app_token, user_token = _configuracao()
    session_token = iniciar_sessao(url_base, app_token, user_token)
    try:
        headers = _cabecalhos(app_token, session_token)
        itens = _paginar_itens(url_base, "Ticket", headers)
        ativos = [item for item in itens if int(item.get("status", 0)) not in STATUS_FINALIZADOS]
        return [_montar_chamado(url_base, item, headers) for item in ativos]
    finally:
        encerrar_sessao(url_base, app_token, session_token)


def listar_problemas_ativos() -> list[ProblemaGlpi]:
    """Mesma lógica de `listar_chamados_ativos`, para Problemas (Problem)."""
    url_base, app_token, user_token = _configuracao()
    session_token = iniciar_sessao(url_base, app_token, user_token)
    try:
        headers = _cabecalhos(app_token, session_token)
        itens = _paginar_itens(url_base, "Problem", headers)
        ativos = [item for item in itens if int(item.get("status", 0)) not in STATUS_FINALIZADOS]
        return [_montar_problema(url_base, item, headers) for item in ativos]
    finally:
        encerrar_sessao(url_base, app_token, session_token)
