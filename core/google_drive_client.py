"""
Cliente para explorar uma pasta (e subpastas) do Google Drive compartilhada
com a conta de serviço do app, e baixar um arquivo .csv de dentro dela -
alternativa a enviar o arquivo manualmente, ou à busca automática no Azure
DevOps (ver `ui/pages/upload_page.py`, opção "Buscar arquivo no Google
Drive").

Arquitetura de credenciais (diferente do PAT do Azure DevOps): aqui é UMA
conta de serviço só, compartilhada por todo mundo que usa o app - faz
sentido porque o Drive já tem seu próprio controle de acesso por pasta
(quem administra o Google Drive decide com quem compartilhar a pasta), e
qualquer pessoa que já está logada neste app, pelas credenciais de login já
controladas por quem administra o sistema, é alguém autorizado a ver esses
dados. Não faz sentido pedir um "PAT" por pessoa aqui como é feito com o
Azure DevOps.

De onde vem a credencial (a chave JSON da conta de serviço, baixada do
Google Cloud Console):
    Prioridade 1 - Secrets do Streamlit (`st.secrets["google_drive"]`), com
    os MESMOS campos do arquivo JSON baixado do Google Cloud Console
    (type, project_id, private_key_id, private_key, client_email, ...) -
    caminho usado em produção (Streamlit Community Cloud).

    Prioridade 2 (fallback) - arquivo local `core/google_drive_credentials.json`
    (a própria chave JSON baixada do Google Cloud Console, sem nenhuma
    conversão), usado só pra rodar localmente sem configurar Secrets antes.
    NÃO deve ser commitado no Git (ver .gitignore).

Veja o passo a passo completo de como criar a conta de serviço, gerar essa
credencial, e compartilhar a pasta do Drive com ela, no guia entregue junto
com este recurso ("Configurar Google Drive.md").
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

_ESCOPOS = ["https://www.googleapis.com/auth/drive.readonly"]
_MIME_TYPE_PASTA = "application/vnd.google-apps.folder"
_MIME_TYPE_PLANILHA_GOOGLE = "application/vnd.google-apps.spreadsheet"

CREDENCIAIS_LOCAIS_PATH = Path(__file__).parent / "google_drive_credentials.json"


class GoogleDriveError(Exception):
    """Erro amigável de configuração/comunicação com o Google Drive."""


@dataclass
class ConteudoPasta:
    subpastas: list[dict]  # [{"id": ..., "nome": ...}, ...], ordenado por nome
    arquivos_csv: list[dict]  # [{"id": ..., "nome": ...}, ...], ordenado por nome


def _secrets_para_dict(valor: Any) -> Any:
    """
    Mesma conversão de `auth/auth_manager.py::_secrets_para_dict` (duplicada
    aqui, em vez de importada, pra não criar uma dependência de `core/` em
    cima de `auth/` só por causa de um helper de 4 linhas): `st.secrets` não
    devolve um `dict` "de verdade" em nenhum nível - devolve um tipo próprio
    do Streamlit, parecido com dict mas que a lib do Google (que espera um
    dict nativo pra montar as credenciais) pode não aceitar sem essa
    conversão.
    """
    if hasattr(valor, "items"):
        return {chave: _secrets_para_dict(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_secrets_para_dict(item) for item in valor]
    return valor


def _info_credenciais() -> dict:
    try:
        secao = st.secrets.get("google_drive")
    except Exception:
        # st.secrets pode levantar exceção quando não existe secrets.toml
        # configurado - mesmo comportamento já tratado em auth_manager.py/turso_client.py.
        secao = None
    if secao and secao.get("private_key"):
        return _secrets_para_dict(secao)

    if CREDENCIAIS_LOCAIS_PATH.exists():
        try:
            return json.loads(CREDENCIAIS_LOCAIS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise GoogleDriveError(
                f"O arquivo {CREDENCIAIS_LOCAIS_PATH.name} existe, mas não pôde ser lido como "
                f"JSON válido: {exc}"
            ) from exc

    raise GoogleDriveError(
        "A conta de serviço do Google Drive ainda não está configurada. Peça para o "
        "administrador configurar em Administração → Google Drive."
    )


def email_conta_servico() -> Optional[str]:
    """
    Devolve o e-mail da conta de serviço configurada, ou `None` se não
    houver nenhuma credencial configurada ainda - NUNCA levanta erro (é só
    um dado auxiliar pra exibir no painel Administração, pra quem for
    compartilhar a pasta do Drive saber com qual e-mail compartilhar).
    """
    try:
        return _info_credenciais().get("client_email")
    except GoogleDriveError:
        return None


def _credenciais() -> service_account.Credentials:
    info = _info_credenciais()
    try:
        return service_account.Credentials.from_service_account_info(info, scopes=_ESCOPOS)
    except (ValueError, KeyError) as exc:
        raise GoogleDriveError(
            "A credencial da conta de serviço do Google Drive está incompleta ou mal formatada. "
            "Confira a seção [google_drive] nos Secrets do Streamlit (ou o arquivo "
            f"{CREDENCIAIS_LOCAIS_PATH.name}, se estiver rodando localmente) - compare campo a "
            "campo com o JSON original baixado do Google Cloud Console."
        ) from exc


def _servico():
    # `cache_discovery=False`: evita o cache de arquivo que a biblioteca do
    # Google tenta usar por padrão (pra guardar a "descrição" da API) - em
    # ambientes com sistema de arquivos restrito/somente leitura (caso do
    # Streamlit Community Cloud), isso gera avisos no log sem quebrar nada,
    # mas é desnecessário aqui (a API do Drive não muda a cada execução).
    return build("drive", "v3", credentials=_credenciais(), cache_discovery=False)


def _mensagem_amigavel_http_error(exc: HttpError, contexto_pasta: bool = False) -> str:
    status = exc.resp.status if exc.resp is not None else None
    if status == 404:
        return (
            "Pasta não encontrada (404) - confira se o ID/link da pasta configurado em "
            "Administração → Google Drive está correto."
            if contexto_pasta
            else "Arquivo não encontrado (404) no Google Drive - pode ter sido movido ou "
            "apagado desde a última vez que a lista foi carregada. Clique em \"Atualizar "
            "lista\" e tente de novo."
        )
    if status == 403:
        return (
            "Acesso negado (403) - a pasta não está compartilhada com a conta de serviço do "
            "app, ou o compartilhamento foi removido. Compartilhe a pasta (Compartilhar → "
            "colar o e-mail da conta de serviço, permissão de Leitor) - o e-mail exato "
            "aparece em Administração → Google Drive."
            if contexto_pasta
            else "A conta de serviço não tem permissão para acessar este arquivo (403)."
        )
    if status == 401:
        return (
            "Credencial da conta de serviço inválida, corrompida ou expirada (401). Gere uma "
            "nova chave no Google Cloud Console e atualize os Secrets."
        )
    return f"O Google Drive retornou um erro inesperado ({status}): {exc}"


def testar_conexao(pasta_raiz_id: Optional[str] = None) -> None:
    """
    Levanta `GoogleDriveError` se a credencial (e, opcionalmente, o acesso à
    pasta configurada) estiverem com problema - usado no painel
    Administração → Google Drive, botão "Testar conexão".
    """
    servico = _servico()
    try:
        servico.about().get(fields="user").execute()
    except HttpError as exc:
        raise GoogleDriveError(_mensagem_amigavel_http_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - erro de rede/transporte, não HttpError
        raise GoogleDriveError(f"Não foi possível conectar ao Google Drive: {exc}") from exc

    if pasta_raiz_id:
        try:
            servico.files().get(
                fileId=pasta_raiz_id, fields="id, name, mimeType", supportsAllDrives=True
            ).execute()
        except HttpError as exc:
            raise GoogleDriveError(_mensagem_amigavel_http_error(exc, contexto_pasta=True)) from exc


def listar_pastas_e_arquivos_csv(pasta_id: str) -> ConteudoPasta:
    """
    Lista o conteúdo IMEDIATO (não recursivo) de uma pasta do Drive,
    separado em subpastas e arquivos .csv - usado pra montar a navegação em
    Importar Dados → "Buscar arquivo no Google Drive" (ver `ui/pages/upload_page.py`).
    Qualquer outro tipo de arquivo (planilha nativa do Google não nomeada
    ".csv", PDF, imagem etc.) fica de fora da lista de propósito - só .csv é
    um formato que este app sabe importar.
    """
    servico = _servico()
    query = f"'{pasta_id}' in parents and trashed = false"
    try:
        resposta = servico.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            orderBy="name",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
    except HttpError as exc:
        raise GoogleDriveError(_mensagem_amigavel_http_error(exc, contexto_pasta=True)) from exc
    except Exception as exc:  # noqa: BLE001
        raise GoogleDriveError(f"Não foi possível listar o conteúdo da pasta no Google Drive: {exc}") from exc

    itens = resposta.get("files", [])
    subpastas = sorted(
        (
            {"id": item["id"], "nome": item["name"]}
            for item in itens
            if item.get("mimeType") == _MIME_TYPE_PASTA
        ),
        key=lambda item: item["nome"].lower(),
    )
    arquivos_csv = sorted(
        (
            {"id": item["id"], "nome": item["name"]}
            for item in itens
            if item.get("mimeType") != _MIME_TYPE_PASTA and item["name"].lower().endswith(".csv")
        ),
        key=lambda item: item["nome"].lower(),
    )
    return ConteudoPasta(subpastas=subpastas, arquivos_csv=arquivos_csv)


def baixar_arquivo_csv(arquivo_id: str) -> bytes:
    """
    Baixa o conteúdo bruto (bytes) de um arquivo do Drive pelo `id`. Trata
    dois casos: um arquivo .csv de verdade (a forma esperada - alguém
    baixou o resultado de uma query do Azure DevOps e colocou a pasta como
    está) usa download direto; se o arquivo, por engano, foi salvo/
    convertido como Planilha Google (Google Sheets) em vez de um .csv de
    verdade, exporta como .csv em vez de tentar um download direto (que
    falharia - arquivos nativos do Google não têm bytes "próprios" pra
    baixar, só exportação).
    """
    servico = _servico()
    try:
        metadados = servico.files().get(
            fileId=arquivo_id, fields="mimeType", supportsAllDrives=True
        ).execute()
        eh_planilha_google = metadados.get("mimeType") == _MIME_TYPE_PLANILHA_GOOGLE
        if eh_planilha_google:
            requisicao = servico.files().export_media(fileId=arquivo_id, mimeType="text/csv")
        else:
            requisicao = servico.files().get_media(fileId=arquivo_id, supportsAllDrives=True)

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, requisicao)
        concluido = False
        while not concluido:
            _, concluido = downloader.next_chunk()
        return buffer.getvalue()
    except HttpError as exc:
        raise GoogleDriveError(_mensagem_amigavel_http_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise GoogleDriveError(f"Não foi possível baixar o arquivo do Google Drive: {exc}") from exc


_PADRAO_ID_PASTA_DRIVE = re.compile(r"(?:/folders/|[?&]id=)([a-zA-Z0-9_-]{10,})")


def extrair_id_pasta_do_link(texto: str) -> str:
    """
    Aceita tanto o ID puro da pasta quanto o link completo copiado do
    navegador (ex.: "https://drive.google.com/drive/folders/ID?usp=sharing")
    e devolve só o ID - usado em Administração → Google Drive, pra quem for
    configurar não precisar extrair o ID manualmente do link.
    """
    texto = texto.strip()
    casamento = _PADRAO_ID_PASTA_DRIVE.search(texto)
    return casamento.group(1) if casamento else texto
