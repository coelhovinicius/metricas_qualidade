"""
Botao "Analisar com IA": aciona, sob demanda, uma analise por IA de UM
grafico especifico com os dados que estao na tela naquele momento (ja
considerando filtros aplicados) - ver `core/n8n_client.py` para o cliente
HTTP que fala com o fluxo n8n configurado pelo usuario.

Piloto em dois graficos por enquanto (ver `docs/` ou o commit que introduziu
este arquivo): Backlog Aberto (Dashboard) e Itens Concluidos por Sprint
(Scrum & Sprints) - `renderizar_botao_analise_ia` foi pensado para ser
chamado por qualquer secao de grafico, bastando uma `chave` unica por
grafico (usada tanto para o botao quanto para guardar o resultado da analise
em `st.session_state`, para ele sobreviver a reruns ate ser limpo).
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import streamlit as st

from core.logs_sistema import TIPO_PAINEL, registrar_log
from core.n8n_client import N8nError, analisar_grafico
from ui.components import action_button, finish_action, loading_overlay
from ui.filtros_dashboard import resumir_filtros_ativos

_PREFIXO_CHAVE_RESULTADO = "__analise_ia_resultado__"
_PREFIXO_CHAVE_ERRO = "__analise_ia_erro__"

_COLUNA_RESPONSAVEL = "Responsável"


def _anonimizar_responsaveis(
    dados: pd.DataFrame, contexto_extra: Optional[dict[str, Any]]
) -> tuple[pd.DataFrame, Optional[dict[str, Any]]]:
    """
    Troca nomes reais de Responsável/Executor por rótulos genéricos
    ("Colaborador 1", "Colaborador 2", ...) antes de mandar pra IA - pedido
    explícito do usuário: a análise por IA nunca deve citar ninguém pelo
    nome, nem pra elogiar nem pra apontar risco, então nem mandamos o nome
    real pra fora do app. O gráfico na TELA continua mostrando os nomes reais
    normalmente - só o que viaja pro fluxo n8n/IA é anonimizado.

    Usa o MESMO mapeamento em `dados` e em qualquer lista dentro de
    `contexto_extra` que também tenha a coluna "Responsável" (ex.: itens
    concluídos recentemente, em `scrum_page.py`), pra IA conseguir cruzar as
    duas informações sem saber quem é quem de verdade.
    """
    if dados is None or _COLUNA_RESPONSAVEL not in dados.columns:
        return dados, contexto_extra

    # Reúne, numa única passada, todos os nomes reais que aparecem tanto em
    # `dados` quanto nas listas de `contexto_extra` - assim ninguém fica sem
    # rótulo (o que forçaria um "Colaborador (outro)" genérico e perderia
    # distinção entre pessoas).
    ordem: list[str] = []

    def _registrar(nome: object) -> None:
        texto = str(nome)
        if texto not in ordem:
            ordem.append(texto)

    for nome in dados[_COLUNA_RESPONSAVEL].tolist():
        _registrar(nome)
    if contexto_extra:
        for valor in contexto_extra.values():
            if isinstance(valor, list):
                for item in valor:
                    if isinstance(item, dict) and _COLUNA_RESPONSAVEL in item:
                        _registrar(item[_COLUNA_RESPONSAVEL])

    mapa = {nome: f"Colaborador {indice + 1}" for indice, nome in enumerate(ordem)}

    dados_anonimo = dados.copy()
    dados_anonimo[_COLUNA_RESPONSAVEL] = dados_anonimo[_COLUNA_RESPONSAVEL].astype(str).map(mapa)

    contexto_anonimo = contexto_extra
    if contexto_extra:
        contexto_anonimo = {}
        for chave_ctx, valor in contexto_extra.items():
            if isinstance(valor, list):
                contexto_anonimo[chave_ctx] = [
                    {**item, _COLUNA_RESPONSAVEL: mapa[str(item[_COLUNA_RESPONSAVEL])]}
                    if isinstance(item, dict) and _COLUNA_RESPONSAVEL in item
                    else item
                    for item in valor
                ]
            else:
                contexto_anonimo[chave_ctx] = valor

    return dados_anonimo, contexto_anonimo


def renderizar_botao_analise_ia(
    *,
    chave: str,
    titulo: str,
    descricao: str,
    tipo_grafico: str,
    dados: pd.DataFrame,
    contexto_extra: Optional[dict[str, Any]] = None,
    nome_usuario: Optional[str] = None,
) -> None:
    """
    Desenha o botao "🤖 Analisar com IA" para um grafico, e - depois que uma
    analise ja foi gerada - o texto da analise junto com um botao para
    limpa-la. `chave` precisa ser unica por grafico na pagina (ex.:
    "dashboard_backlog_bolha", "scrum_sprint_velocidade").

    `dados` deve ser o DataFrame ja filtrado, exatamente como usado para
    montar o grafico exibido - e enviado inteiro (convertido para
    lista de dicts) ao fluxo n8n configurado, para a analise ser a mais
    completa possivel (decisao explicita do usuario: priorizar qualidade da
    analise sobre economizar tamanho do envio).
    """
    chave_resultado = f"{_PREFIXO_CHAVE_RESULTADO}{chave}"
    chave_erro = f"{_PREFIXO_CHAVE_ERRO}{chave}"
    chave_botao = f"btn_analise_ia_{chave}"

    if action_button("🤖 Analisar com IA", key=chave_botao, type="secondary"):
        with loading_overlay("Analisando o grafico com IA, aguarde..."):
            try:
                dados_anonimos, contexto_extra_anonimo = _anonimizar_responsaveis(dados, contexto_extra)

                contexto: dict[str, Any] = {
                    "filtros_ativos": resumir_filtros_ativos(),
                    "total_linhas": int(len(dados)),
                }
                if contexto_extra_anonimo:
                    contexto.update(contexto_extra_anonimo)

                texto_analise = analisar_grafico(
                    titulo=titulo,
                    descricao=descricao,
                    tipo_grafico=tipo_grafico,
                    dados=dados_anonimos.to_dict(orient="records"),
                    contexto=contexto,
                )
                st.session_state[chave_resultado] = texto_analise
                st.session_state[chave_erro] = None
                registrar_log(TIPO_PAINEL, nome_usuario, f"Analise por IA gerada - {titulo}")
            except N8nError as erro:
                st.session_state[chave_resultado] = None
                st.session_state[chave_erro] = str(erro)
        finish_action(chave_botao)
        st.rerun()

    erro_atual = st.session_state.get(chave_erro)
    if erro_atual:
        st.error(erro_atual)

    resultado_atual = st.session_state.get(chave_resultado)
    if resultado_atual:
        with st.container(border=True):
            st.markdown("**🤖 Analise por IA**")
            st.markdown(resultado_atual)
            if st.button("Limpar analise", key=f"btn_limpar_analise_ia_{chave}"):
                st.session_state[chave_resultado] = None
                st.session_state[chave_erro] = None
                st.rerun()
