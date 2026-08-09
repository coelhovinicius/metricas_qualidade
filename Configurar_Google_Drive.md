# Configurar a busca de arquivo no Google Drive

Guia passo a passo para deixar a opção **"Buscar arquivo no Google Drive"** (tela Importar Dados) funcionando. Você só precisa fazer isso **uma vez**. Depois de pronto, qualquer pessoa logada no app já consegue usar a busca — só o administrador precisa mexer nestas configurações.

O app usa uma **Conta de Serviço** do Google (uma credencial "robô", sem tela de login) para enxergar a pasta do Drive que você escolher compartilhar com ela. Nenhuma senha ou login pessoal do Google é usado nesse processo.

---

## Parte 1 — Criar a Conta de Serviço no Google Cloud

1. Acesse [console.cloud.google.com](https://console.cloud.google.com) e faça login com sua conta Google normal (a mesma que você já usa, por exemplo, para a chave de API do Gemini que você mencionou usar no n8n).

2. **Crie um projeto novo** (ou reaproveite um que já tenha) — menu no topo da página, ao lado do logo do Google Cloud → "Novo Projeto". Dê um nome como `refuturiza-qa-drive`. Não precisa de faturamento/cartão de crédito para isso — a API do Drive tem uso gratuito de sobra para este caso.

3. Com o projeto selecionado, vá em **"APIs e Serviços" → "Biblioteca"** (menu ☰ à esquerda), procure por **"Google Drive API"** e clique em **"Ativar"**.

4. Vá em **"APIs e Serviços" → "Credenciais"** (mesmo menu ☰).

5. Clique em **"+ Criar Credenciais" → "Conta de serviço"**.

6. Preencha:
   - **Nome da conta de serviço**: algo como `qa-app-drive-reader`.
   - **ID**: é preenchido sozinho a partir do nome — pode deixar como está.
   - Clique em **"Criar e continuar"**.
   - Na etapa de "Conceder acesso" (papel/role), pode **pular** — não precisa dar nenhum papel de projeto para esta conta de serviço, já que o acesso de verdade vai ser dado depois, diretamente na pasta do Drive (Parte 3).
   - Clique em **"Concluído"**.

7. Você volta para a lista de credenciais. Clique na conta de serviço que acabou de criar (aparece na seção "Contas de serviço").

8. Vá na aba **"Chaves"** → **"Adicionar chave" → "Criar nova chave"**.

9. Escolha o formato **JSON** e clique em **"Criar"**. Um arquivo `.json` é baixado automaticamente para o seu computador (algo como `refuturiza-qa-drive-xxxxxxxxxxxx.json`).

   ⚠️ **Este arquivo é uma credencial sensível** — quem tiver esse arquivo consegue acessar tudo que a conta de serviço tiver permissão para ver no Drive. Guarde-o num lugar seguro e **nunca** o envie por e-mail, chat ou o suba para o GitHub.

10. Ainda na página da conta de serviço, copie o **e-mail** dela (algo como `qa-app-drive-reader@refuturiza-qa-drive.iam.gserviceaccount.com`) — você vai precisar dele na Parte 3.

---

## Parte 2 — Configurar a credencial no app

Você tem duas opções, dependendo de onde está rodando o app:

### Opção A — Produção (Streamlit Community Cloud, o link https://quality-assurance-metrics.streamlit.app)

1. Abra o arquivo JSON baixado no passo 9 acima com um editor de texto qualquer (Bloco de Notas serve). Ele tem esta cara:

   ```json
   {
     "type": "service_account",
     "project_id": "refuturiza-qa-drive",
     "private_key_id": "abcd1234...",
     "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQ...\n-----END PRIVATE KEY-----\n",
     "client_email": "qa-app-drive-reader@refuturiza-qa-drive.iam.gserviceaccount.com",
     "client_id": "123456789...",
     "auth_uri": "https://accounts.google.com/o/oauth2/auth",
     "token_uri": "https://oauth2.googleapis.com/token",
     "auth_provider_x509_cert_url": "...",
     "client_x509_cert_url": "...",
     "universe_domain": "googleapis.com"
   }
   ```

2. No painel do Streamlit Community Cloud, entre no seu app → **⚙️ Settings → Secrets**.

3. **Adicione** (não substitua o que já existe — os blocos `[auth]` e `[turso]` continuam lá) o seguinte bloco, um `[google_drive]` com os MESMOS campos do JSON, valor por valor:

   ```toml
   [google_drive]
   type = "service_account"
   project_id = "refuturiza-qa-drive"
   private_key_id = "abcd1234..."
   private_key = "-----BEGIN PRIVATE KEY-----\nMIIEvQ...\n-----END PRIVATE KEY-----\n"
   client_email = "qa-app-drive-reader@refuturiza-qa-drive.iam.gserviceaccount.com"
   client_id = "123456789..."
   auth_uri = "https://accounts.google.com/o/oauth2/auth"
   token_uri = "https://oauth2.googleapis.com/token"
   auth_provider_x509_cert_url = "..."
   client_x509_cert_url = "..."
   universe_domain = "googleapis.com"
   ```

   **Atenção especial ao campo `private_key`**: ele tem várias linhas no JSON original, mas no JSON elas já vêm representadas como `\n` dentro de uma única linha de texto (entre aspas) — é exatamente esse formato de uma linha só, com os `\n` literais (a barra invertida seguida de "n", não uma quebra de linha de verdade), que deve ser colado no TOML dos Secrets também. Ou seja: **copie o valor do campo `private_key` direto do JSON, entre aspas duplas, sem reformatar nada** — não tente "arrumar" as quebras de linha manualmente, o formato do JSON já é o que o TOML precisa.

4. Clique em **"Save"**. O Streamlit Community Cloud reinicia o app sozinho em alguns segundos.

### Opção B — Rodando localmente (na sua máquina)

1. Copie o arquivo JSON baixado no passo 9 para dentro da pasta do projeto, em:

   ```
   core/google_drive_credentials.json
   ```

2. Pronto — não precisa editar nenhum outro arquivo. Esse caminho já é ignorado pelo Git (foi adicionado ao `.gitignore` junto com esta funcionalidade), então ele nunca vai parar sendo commitado sem querer.

Se você roda o app tanto localmente quanto em produção, repita as duas opções — cada ambiente lê a credencial do seu próprio lugar (Secrets em produção, arquivo local no seu computador), então uma configuração não interfere na outra.

---

## Parte 3 — Compartilhar a pasta do Drive com a conta de serviço

1. No Google Drive, crie (ou escolha) a pasta que vai reunir os arquivos `.csv` exportados de queries do Azure DevOps (pode ter subpastas dentro dela também — a busca no app deixa navegar por elas).

2. Clique com o botão direito na pasta → **"Compartilhar"**.

3. Cole o **e-mail da conta de serviço** que você copiou no passo 10 da Parte 1 (algo como `qa-app-drive-reader@refuturiza-qa-drive.iam.gserviceaccount.com`).

4. Defina a permissão como **"Leitor"** (é tudo que o app precisa — ele só lê arquivos, nunca escreve nada na pasta).

5. Desmarque a opção de notificar por e-mail, se aparecer (a conta de serviço não lê e-mail) e clique em **"Enviar"** ou **"Compartilhar"**.

6. Copie o **link da pasta** (botão direito → "Copiar link", ou pegue direto da barra de endereço do navegador com a pasta aberta) — algo como:

   ```
   https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz1234567
   ```

---

## Parte 4 — Configurar a pasta raiz dentro do app

1. Faça login no app como `admin` e vá em **Administração → aba "📁 Google Drive"**.

2. Confira se o e-mail da conta de serviço aparece em verde no topo da tela (confirma que a credencial da Parte 2 foi lida com sucesso). Se aparecer um aviso amarelo em vez disso, revise a Parte 2 — o app ainda não está enxergando a credencial.

3. No campo **"Link ou ID da pasta raiz"**, cole o link copiado no passo 6 da Parte 3 (o link inteiro funciona — o app extrai o ID sozinho).

4. Clique em **"Salvar pasta raiz"**. O app testa o acesso na hora, antes de salvar — se a pasta não tiver sido compartilhada corretamente (Parte 3), você vai ver uma mensagem de erro explicando o motivo, e a pasta NÃO é salva até você corrigir.

5. Se der tudo certo, a pasta raiz configurada aparece na tela, e a opção **"Buscar arquivo no Google Drive"** já fica disponível para todo mundo, na tela **Importar Dados**.

Você pode usar o botão **"Testar conexão"** a qualquer momento depois disso, para confirmar rapidamente que tudo continua funcionando (por exemplo, depois de trocar a pasta compartilhada, ou se desconfiar de algum problema).

---

## Perguntas frequentes

**Preciso repetir isso toda vez que quiser trocar a pasta usada?**
Não — só a Parte 4 (colar o novo link/ID em Administração → Google Drive → "Salvar pasta raiz"). As Partes 1-3 são feitas uma única vez (ou quando a pasta compartilhada mudar de dono/local).

**Cada pessoa que usa o app precisa da própria credencial?**
Não — ao contrário do PAT do Azure DevOps (que é pessoal, um por usuário), a conta de serviço do Google Drive é **uma só, compartilhada por todo mundo que já está logado no app**. Quem administra o Google Drive decide quais pastas ficam visíveis, compartilhando (ou não) com essa única conta de serviço.

**A chave JSON expira?**
Não tem prazo de validade automático, mas pode ser revogada/apagada a qualquer momento no Google Cloud Console (Credenciais → conta de serviço → aba Chaves → excluir a chave). Se isso acontecer sem querer, basta gerar uma chave nova (repita o passo 8 da Parte 1) e atualizar a credencial (Parte 2).

**Posso usar mais de uma pasta raiz diferente (por exemplo, uma por projeto)?**
Hoje o app permite configurar uma pasta raiz por vez (compartilhada por todos que usam o app) — mas nada impede que essa pasta raiz seja uma pasta "guarda-chuva" com subpastas por projeto/time dentro dela, já que a navegação do app permite entrar em subpastas livremente.
