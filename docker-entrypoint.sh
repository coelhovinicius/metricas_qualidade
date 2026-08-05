#!/usr/bin/env bash
# Ponto de entrada do container (ver Dockerfile). Duas responsabilidades:
#
# 1) Reconstituir .streamlit/secrets.toml a partir de UMA variável de
#    ambiente só (SECRETS_TOML), contendo o conteúdo inteiro do arquivo TOML
#    (o mesmo bloco [auth]/[turso] descrito no README.md, seção
#    "Configuração (secrets)"). Isso existe porque a maioria dos serviços de
#    hospedagem (Hugging Face Spaces, Render, etc.) só oferece "variáveis de
#    ambiente" simples (chave=valor), não um jeito nativo de subir um arquivo
#    TOML com seções aninhadas como o Streamlit espera - então, em vez de
#    reescrever a autenticação do app pra usar só variáveis soltas, é mais
#    simples (e não exige tocar em nenhum código) colar o TOML inteiro como
#    valor de uma única variável de ambiente, e este script grava esse valor
#    no arquivo que o app já sabe ler (auth/auth_manager.py já verifica
#    st.secrets normalmente).
#
# 2) Iniciar o Streamlit ouvindo na porta certa (a maioria dos serviços
#    informa a porta via variável de ambiente PORT; se não informar, usa 7860
#    - a porta padrão esperada pelo Hugging Face Spaces).
set -e

mkdir -p .streamlit
if [ -n "${SECRETS_TOML:-}" ]; then
    printf '%s' "$SECRETS_TOML" > .streamlit/secrets.toml
fi

exec streamlit run app.py \
    --server.port="${PORT:-7860}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
