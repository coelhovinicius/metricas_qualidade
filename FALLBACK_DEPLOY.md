# Fallback de hospedagem gratuita (enquanto o Streamlit Community Cloud está instável)

Este guia existe porque o Streamlit Community Cloud ficou travado em
"Spinning up manager process..." em todos os apps da conta, sem incidente
declarado na página de status deles. Os arquivos deste guia (`Dockerfile`,
`docker-entrypoint.sh`, `.dockerignore`, `README_HUGGINGFACE_SPACE.md`)
rodam o **mesmo app, sem nenhuma mudança de código**, dentro de um container
Docker — o que permite hospedar em qualquer serviço que aceite Docker,
independente do Streamlit Cloud.

**Recomendação: Hugging Face Spaces** (opção 1 abaixo) — gratuito de verdade
(sem cartão de crédito), sem limite de horas por mês, e só "dorme" depois de
48h sem acesso (bem mais folgado que outras opções gratuitas). Leva uns 10-15
minutos pra colocar no ar. Render (opção 2) é uma alternativa igualmente boa
se preferir o fluxo "conectar direto no GitHub".

Nenhuma das opções abaixo mexe no que já está configurado no Streamlit Cloud
— são ambientes paralelos e independentes. Quando o Streamlit Cloud voltar ao
normal, você pode voltar a usá-lo, manter os dois, ou desligar o fallback.

---

## Opção 1 — Hugging Face Spaces (recomendado)

1. Crie uma conta gratuita em [huggingface.co](https://huggingface.co/join) (se ainda não tiver uma) — só e-mail e senha, sem cartão.
2. Clique em **New Space** (canto superior direito → ícone de perfil → *New Space*, ou vá direto em [huggingface.co/new-space](https://huggingface.co/new-space)).
3. Preencha:
   - **Space name**: ex. `refuturiza-qa` (vira parte da URL pública).
   - **License**: pode deixar a padrão, ou "None".
   - **Select the Space SDK**: escolha **Docker** → template **Blank**.
   - **Space hardware**: deixe a opção gratuita (**CPU basic · Free**).
   - **Visibility**: **Private** (recomendado, já que este é um painel interno com login) ou Public, se preferir.
4. Clique em **Create Space**. Você cai numa tela com instruções de `git clone`/`git push` para esse novo repositório.
5. No seu computador, dentro da pasta do projeto (a mesma onde está o `app.py`), suba os arquivos para esse novo repositório do Space:
   ```powershell
   git remote add space https://huggingface.co/spaces/SEU-USUARIO/refuturiza-qa
   ```
   (troque `SEU-USUARIO`/`refuturiza-qa` pelo que apareceu na tela de criação do Space — o Hugging Face vai pedir login/token na primeira vez; use um **Access Token** gerado em Settings → Access Tokens, com permissão de escrita, no lugar da senha.)
6. **Renomeie** `README_HUGGINGFACE_SPACE.md` para `README.md` **só nesta cópia local antes de enviar pro Space** (esse repositório é separado do seu GitHub — não afeta o README do projeto principal):
   ```powershell
   copy README.md README_GITHUB_BACKUP.md
   copy README_HUGGINGFACE_SPACE.md README.md
   ```
7. Envie tudo para o Space:
   ```powershell
   git add -A
   git commit -m "Deploy de fallback no Hugging Face Spaces"
   git push space main
   ```
   (se o branch local não se chamar `main`, ajuste o comando, ex. `git push space master:main`.)
8. Assim que o push terminar, o Hugging Face começa a construir a imagem Docker sozinho — acompanhe em **Settings → (nome do Space)** ou na própria página do Space, aba **Logs**. A primeira build demora alguns minutos (instala o Chromium etc.).
9. **Configure os Secrets antes de abrir o app** (senão o login não funciona): na página do Space, vá em **Settings → Variables and secrets → New secret**. Crie um secret chamado exatamente `SECRETS_TOML`, e cole nele o **conteúdo inteiro** do seu `.streamlit/secrets.toml` (o mesmo bloco `[auth...]`/`[turso...]` que você já usa no Streamlit Cloud — copie e cole igual, com todas as linhas). Salve.
10. Reinicie o Space (**Settings → Factory reboot**, ou basta esperar o build inicial terminar se o secret já foi configurado antes). O app fica disponível em `https://huggingface.co/spaces/SEU-USUARIO/refuturiza-qa` (ou embutido na própria página do Space).

**Depois que voltar a funcionar**, restaure o `README.md` original localmente (`copy README_GITHUB_BACKUP.md README.md`) antes de continuar trabalhando no repositório do GitHub, para não misturar os dois.

## Opção 2 — Render (alternativa)

1. Crie uma conta gratuita em [render.com](https://render.com) (dá pra entrar direto com o GitHub).
2. **New → Web Service**, conecte sua conta do GitHub e selecione o repositório deste projeto.
3. Configuração do serviço:
   - **Runtime**: **Docker** (o Render detecta o `Dockerfile` automaticamente).
   - **Instance Type**: **Free**.
4. Em **Environment Variables**, adicione uma variável `SECRETS_TOML` com o conteúdo inteiro do seu `.streamlit/secrets.toml` colado como valor (mesma ideia do passo 9 da Opção 1).
5. Clique em **Create Web Service**. O Render clona o repositório, builda a imagem Docker (instala o Chromium etc.) e sobe o app sozinho — acompanhe pela aba **Logs**.
6. Fica disponível numa URL do tipo `https://refuturiza-qa.onrender.com`.

Diferença prática para o dia a dia: o plano gratuito do Render "dorme" depois de **15 minutos sem acesso** (o Hugging Face aguenta 48h), e tem um teto de 750 horas grátis por mês na conta inteira — mais que suficiente para um app só, mas vale saber que existe esse teto.

---

## Por que isso funciona sem mudar nada no código

- O `Dockerfile` instala o Chromium via `apt-get`, exatamente como o `packages.txt` já faz no Streamlit Cloud — resolve a mesma necessidade do relatório em PDF.
- `requirements.txt` é o mesmo, com as mesmas versões travadas de `streamlit`/`starlette` já testadas.
- A única diferença é *como* os Secrets chegam até o app: no Streamlit Cloud eles vêm de `st.secrets` configurado pelo próprio painel deles; aqui, o `docker-entrypoint.sh` grava o mesmo conteúdo num arquivo `.streamlit/secrets.toml` dentro do container, a partir da variável de ambiente `SECRETS_TOML` — o `auth/auth_manager.py` não percebe diferença nenhuma, lê do mesmo jeito de sempre.
