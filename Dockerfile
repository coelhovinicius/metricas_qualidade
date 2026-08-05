# Dockerfile de FALLBACK — usado para rodar este app fora do Streamlit
# Community Cloud (Hugging Face Spaces, Render, ou qualquer outro serviço que
# aceite um container Docker), enquanto o Streamlit Community Cloud estiver
# instável. Ver FALLBACK_DEPLOY.md para o passo a passo completo.
#
# Mesmo raciocínio do packages.txt usado no Streamlit Cloud: o relatório em
# PDF (core/pdf_report.py) precisa de um Chrome/Chromium instalado no sistema
# para o kaleido rasterizar os gráficos - por isso o apt-get install chromium
# abaixo, igual ao packages.txt.

FROM python:3.11-slim

# Testado nesta combinação exata (streamlit==1.61.1 / starlette==1.3.1) antes
# de qualquer entrega - ver comentário em requirements.txt sobre por que essas
# duas versões são travadas.
WORKDIR /app

# chromium: necessário para o relatório em PDF (kaleido). ca-certificates:
# necessário para chamadas HTTPS (Azure DevOps, Turso) funcionarem direito.
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

# 7860 é a porta padrão esperada pelo Hugging Face Spaces (SDK Docker) - ver
# app_port no README_HUGGINGFACE_SPACE.md. Outros serviços (ex.: Render)
# normalmente informam a porta certa pela variável de ambiente PORT em tempo
# de execução, que o docker-entrypoint.sh já lê (com 7860 como padrão).
ENV PORT=7860
EXPOSE 7860

ENTRYPOINT ["./docker-entrypoint.sh"]
