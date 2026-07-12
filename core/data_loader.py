"""
Carregamento de arquivos CSV/TXT enviados pelo usuário.

Faz detecção automática de:
    - Codificação (encoding) do arquivo;
    - Delimitador de colunas (`,` `;` `\\t` `|`);
    - Linhas totalmente vazias e colunas "Unnamed" residuais.

Levanta `DataLoadError` com mensagens amigáveis quando o arquivo não pode
ser interpretado, para serem exibidas diretamente na interface.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import IO

import chardet
import pandas as pd

EXTENSOES_SUPORTADAS = ("csv", "txt")
DELIMITADORES_CANDIDATOS = [",", ";", "\t", "|"]


class DataLoadError(Exception):
    """Erro amigável de leitura/parse do arquivo importado."""


@dataclass
class ResultadoCarga:
    dataframe: pd.DataFrame
    encoding_detectado: str
    delimitador_detectado: str
    nome_arquivo: str
    total_linhas: int
    total_colunas: int


def _detectar_encoding(raw_bytes: bytes) -> str:
    amostra = raw_bytes[:200_000]
    resultado = chardet.detect(amostra)
    encoding = (resultado.get("encoding") or "utf-8").lower()
    # Normaliza apelidos comuns para nomes aceitos pelo pandas/python
    mapa_normalizacao = {"ascii": "utf-8", "windows-1252": "cp1252"}
    return mapa_normalizacao.get(encoding, encoding)


def _detectar_delimitador(texto_amostra: str) -> str:
    try:
        dialeto = csv.Sniffer().sniff(texto_amostra, delimiters="".join(DELIMITADORES_CANDIDATOS))
        return dialeto.delimiter
    except csv.Error:
        # Fallback: conta ocorrências de cada delimitador candidato na primeira linha
        primeira_linha = texto_amostra.splitlines()[0] if texto_amostra else ""
        contagens = {delim: primeira_linha.count(delim) for delim in DELIMITADORES_CANDIDATOS}
        melhor_delimitador = max(contagens, key=contagens.get)
        return melhor_delimitador if contagens[melhor_delimitador] > 0 else ","


def _limpar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Remove linhas e colunas 100% vazias
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")
    # Normaliza nomes de coluna (remove espaços extras)
    df.columns = [str(coluna).strip() for coluna in df.columns]
    # Remove colunas fantasma geradas por delimitadores no fim da linha
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed(:.*)?$", na=False)]
    # Remove espaços extras em colunas de texto
    colunas_texto = df.select_dtypes(include="object").columns
    for coluna in colunas_texto:
        df[coluna] = df[coluna].astype(str).str.strip()
    return df.reset_index(drop=True)


def validar_extensao(nome_arquivo: str) -> None:
    extensao = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
    if extensao not in EXTENSOES_SUPORTADAS:
        raise DataLoadError(
            f"Extensão '.{extensao}' não suportada. Envie um arquivo .csv ou .txt."
        )


def carregar_arquivo(arquivo: IO[bytes], nome_arquivo: str) -> ResultadoCarga:
    """
    Lê um arquivo CSV/TXT enviado via `st.file_uploader`, detectando
    automaticamente encoding e delimitador.
    """
    validar_extensao(nome_arquivo)

    raw_bytes = arquivo.read()
    if not raw_bytes:
        raise DataLoadError("O arquivo enviado está vazio.")

    encoding = _detectar_encoding(raw_bytes)

    try:
        texto = raw_bytes.decode(encoding, errors="strict")
    except (UnicodeDecodeError, LookupError):
        # Fallback seguro caso a detecção de encoding falhe
        encoding = "latin-1"
        texto = raw_bytes.decode(encoding, errors="replace")

    amostra = "\n".join(texto.splitlines()[:20])
    delimitador = _detectar_delimitador(amostra)

    try:
        df = pd.read_csv(
            io.StringIO(texto),
            sep=delimitador,
            engine="python",
            on_bad_lines="skip",
        )
    except Exception as exc:  # noqa: BLE001 - queremos capturar qualquer falha de parse
        raise DataLoadError(
            "Não foi possível interpretar o arquivo. Verifique se ele está "
            "bem formado (mesma quantidade de colunas em todas as linhas)."
        ) from exc

    if df.empty or df.shape[1] == 0:
        raise DataLoadError("O arquivo foi lido, mas nenhuma coluna/linha válida foi encontrada.")

    df = _limpar_dataframe(df)

    return ResultadoCarga(
        dataframe=df,
        encoding_detectado=encoding,
        delimitador_detectado=delimitador,
        nome_arquivo=nome_arquivo,
        total_linhas=df.shape[0],
        total_colunas=df.shape[1],
    )
