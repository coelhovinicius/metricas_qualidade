# Guia do Administrador — Indicadores - QA

Este guia é para quem faz login como **administrador** (usuário `admin`). Ele cobre tudo que um usuário comum já pode fazer (importar dados, navegar pelo dashboard, gerar PDF) **e** as funções extras que só o administrador enxerga: o Painel Administrativo completo.

Se você só precisa saber como usar o dashboard no dia a dia (sem as funções de administração), o **[GUIA_CONVIDADO.md](GUIA_CONVIDADO.md)** cobre a mesma parte de uso, de forma um pouco mais enxuta. Esse mesmo conteúdo de uso comum também está disponível dentro do próprio app, em **"ℹ️ Sobre o App"**.

## Sumário

1. [Como entrar (login)](#1-como-entrar-login)
2. [Navegação geral](#2-navegação-geral)
3. [Painel Administrativo — visão geral](#3-painel-administrativo-visão-geral)
4. [Diagnóstico de conexão e código de acesso ao conteúdo admin](#4-diagnóstico-de-conexão-e-código-de-acesso-ao-conteúdo-admin)
5. [Aba: Solicitações de Acesso](#5-aba-solicitações-de-acesso)
6. [Criando uma conta de verdade](#6-criando-uma-conta-de-verdade)
7. [Aba: Logs do Sistema](#7-aba-logs-do-sistema)
8. [Aba: Google Drive](#8-aba-google-drive)
9. [Aba: Guia do Usuário](#9-aba-guia-do-usuário)
10. [Importar dados](#10-importar-dados)
11. [Confirmar o mapeamento de colunas](#11-confirmar-o-mapeamento-de-colunas)
12. [Usando o dashboard](#12-usando-o-dashboard)
13. [Analisar um gráfico com IA (configuração e uso)](#13-analisar-um-gráfico-com-ia-configuração-e-uso)
14. [Construtor de gráfico personalizado](#14-construtor-de-gráfico-personalizado)
15. [Gerar o relatório em PDF](#15-gerar-o-relatório-em-pdf)
16. ["Nova Análise" e "Sair"](#16-nova-análise-e-sair)
17. [Perguntas frequentes](#17-perguntas-frequentes)

---

## 1. Como entrar (login)

1. Abra o link do painel no navegador. Você verá a tela **"Acesso ao Painel de Qualidade"**, com os campos **Usuário** e **Senha**.
2. Digite suas credenciais e clique em **Entrar**.
3. Se usuário/senha estiverem incorretos, uma mensagem de erro aparece e você pode tentar de novo.
4. Depois de logar, um F5 (recarregar a página) **não** pede login de novo por um tempo — sua sessão fica salva num cookie do navegador. Só fechar a aba/janela de verdade (ou clicar em **Sair**) encerra a sessão.

> Não confunda com o botão **"Solicitar acesso"**, que existe nessa mesma tela — ele é para quem **ainda não tem conta**. Como administrador, você já tem a sua.

## 2. Navegação geral

Depois de logado, a barra lateral esquerda mostra cinco botões (você é a única pessoa que vê o penúltimo):

- **📥 Importar Dados** — tela inicial, para trazer um arquivo de testes para dentro do app.
- **📊 Indicadores** — o dashboard em si, com todos os gráficos.
- **🏃 Scrum & Sprints** — área dedicada a indicadores de fluxo, ritmo de entrega e trabalho em andamento (WIP), pensada para observabilidade de Scrum/Sprints. Visível para qualquer pessoa logada, não só para admin.
- **⚙️ Administração** — o Painel Administrativo (só admin).
- **ℹ️ Sobre o App** — a mesma explicação visual que qualquer usuário vê, mais um resumo do que existe do lado da Administração (para você, sempre expandido; para quem não é admin, escondido por padrão — ver seção 4).

O botão da página em que você está fica destacado em laranja. Mais abaixo na barra lateral aparece o botão **🔄 Nova Análise** (só depois de já ter importado algum arquivo) e, por último, **Sair**.

## 3. Painel Administrativo — visão geral

Clique em **⚙️ Administração** na barra lateral. A tela é organizada em dois blocos de configuração no topo (fora de qualquer aba) e quatro abas logo abaixo:

- **Diagnóstico da conexão com o banco de dados (Turso)** e **Código de acesso ao conteúdo administrativo de "Sobre o App"** — ver seção 4.
- **📋 Solicitações de Acesso** — ver seção 5.
- **🗒️ Logs do Sistema** — ver seção 7.
- **📁 Google Drive** — ver seção 8.
- **📘 Guia do Usuário** — ver seção 9.

## 4. Diagnóstico de conexão e código de acesso ao conteúdo admin

Dois expansores no topo da página, fechados por padrão:

### Diagnóstico da conexão com o banco de dados (Turso)

Clique nele e depois em **Testar conexão** se alguma ação do painel estiver dando erro — ele confirma se o app consegue falar com o banco onde ficam solicitações, logs e configurações. Se a conexão falhar, a mensagem de erro explica o motivo (normalmente configuração de Secrets, não algo que você resolve clicando em botões).

### Código de acesso ao conteúdo administrativo de "Sobre o App"

A página "Sobre o App" (visível a qualquer pessoa logada) descreve os fluxos de administração — mas, por padrão, essa parte fica **escondida** para quem não é você. Aqui você define um código de texto livre (ex.: `qa2026`) e o repassa, por fora do app (chat, e-mail, verbalmente), só para quem você quiser que enxergue esse conteúdo. A pessoa digita esse código na própria tela dela e desbloqueia, só para a sessão de navegador dela.

- Deixar o campo em branco e salvar **desativa** o desbloqueio para todo mundo (volta a ficar visível só para você).
- Isso **não é** uma segunda senha de login — não dá acesso ao Painel Administrativo de verdade, só à descrição textual/fluxograma de como ele funciona.

**Sobre a imagem do fluxograma:** além dos cartões de texto, "Sobre o App" também mostra uma imagem do fluxo completo (retângulos + setas). Essa imagem **não se atualiza sozinha** quando algo no fluxo do app muda — precisa ser regenerada, com um clique em Administração → aba "📘 Guia do Usuário" → "🔄 Gerar/Atualizar fluxograma agora" (ver seção 9). Se você notar a imagem desatualizada em relação ao que o app realmente faz, é por isso.

## 5. Aba: Solicitações de Acesso

A aba mostra quatro grupos, cada um numa seção própria:

### Pendentes

Toda solicitação nova cai aqui primeiro. Cada cartão mostra nome, e-mail, data/hora do pedido (em horário de Brasília) e o motivo escrito pela pessoa. Duas ações por cartão:

- **✅ Marcar como criada** — use depois de já ter criado a conta de verdade (veja a seção [6. Criando uma conta de verdade](#6-criando-uma-conta-de-verdade) abaixo). Um modal de confirmação aparece antes de aplicar; confirme só depois de a conta já existir mesmo, porque este botão **não cria a conta sozinho** — só move o cartão para "Já criadas".
- **❌ Rejeitar** — para pedidos que você decidiu não atender. A pessoa não recebe nenhuma notificação automática (não há envio de e-mail); se quiser avisá-la, o contato precisa ser feito por fora do app. O cartão vai para "Rejeitadas".

### Já criadas (dentro de um expansor)

Lista de contas que você já confirmou como criadas. Cada cartão tem o botão:

- **🚫 Revogar acesso** — marca o cartão como revogado aqui no painel. **Isso não desliga a conta de verdade sozinho** — depois de clicar e confirmar, lembre-se de também remover (ou trocar a senha de) o usuário nos Secrets do Streamlit, como descrito na seção 6. Se o e-mail da solicitação estiver na lista de e-mails protegidos (configurada no código, `EMAILS_PROTEGIDOS_DE_REVOGACAO` em `ui/pages/admin_page.py`), o botão não aparece — é uma proteção para você nunca revogar o próprio acesso sem querer.

### Revogadas (dentro de um expansor)

- **↩️ Reverter revogação** — manda o cartão de volta para "Pendentes" (não direto para "Já criadas"), para você reconfirmar que a conta foi mesmo recriada antes de marcar como criada de novo.
- **🗑️ Excluir** — apaga o registro dessa solicitação de vez (não afeta o acesso real de ninguém, só o histórico do painel).
- Use as caixinhas de seleção ao lado de cada cartão (ou **Selecionar todas**) para excluir várias solicitações revogadas de uma vez, com o botão **🗑️ Excluir selecionadas** que aparece assim que algo é marcado.

### Rejeitadas (dentro de um expansor)

- **♻️ Recuperar** — manda o cartão de volta para "Pendentes", caso a rejeição tenha sido engano.
- **🗑️ Excluir** — mesma lógica das revogadas: apaga o registro, sem afetar acesso real. Também com seleção em massa.

Toda ação (criar, rejeitar, revogar, reverter, recuperar, excluir) abre um modal de confirmação com um aviso do que vai acontecer antes de aplicar de verdade — nada muda com um clique só.

## 6. Criando uma conta de verdade

O Painel Administrativo **organiza e documenta** os pedidos de acesso, mas a criação da conta em si é manual, feita fora da tela do app (isso é intencional — mantém as senhas fora do código e do banco de solicitações). Passo a passo:

1. No terminal, com o ambiente do projeto ativo, gere o hash da senha da pessoa:
   ```powershell
   python scripts\gerar_hash_senha.py
   ```
   Siga as instruções que aparecerem no terminal para informar a senha desejada; o script devolve um hash (começando com `$2b$...`) — essa é a forma segura de guardar a senha, nunca em texto puro.
2. Adicione a pessoa nos **Secrets do Streamlit** (Settings → Secrets, no painel do Streamlit Community Cloud, **e** no seu `.streamlit/secrets.toml` local, se também usa o app localmente), dentro do bloco `[auth.credentials.usernames]`:
   ```toml
   [auth.credentials.usernames.nome_de_usuario]
   email = "pessoa@empresa.com"
   name = "Nome Completo da Pessoa"
   password = "$2b$12$hash-gerado-no-passo-anterior"
   ```
3. Salve os Secrets. No Streamlit Community Cloud, isso já reinicia o app sozinho com a conta nova disponível.
4. Volte ao Painel Administrativo, na solicitação correspondente em "Pendentes", e clique em **✅ Marcar como criada**.

Para revogar acesso, o caminho é o inverso: remova (ou renomeie) o bloco `[auth.credentials.usernames.<usuario>]` dessa pessoa nos Secrets, salve, e marque a solicitação como revogada no painel (seção 5).

## 7. Aba: Logs do Sistema

Três sub-abas, uma por categoria:

- **🗂️ Ações no Painel** — tudo que um administrador faz nas solicitações de conta (criar, rejeitar, revogar, reverter, recuperar, excluir), mais os downloads via PAT do Azure DevOps — incluindo um alerta de **"POSSÍVEL ANOMALIA"** quando o dono real do PAT (confirmado direto na API do Azure DevOps) não bate com quem está logado no app.
- **⚠️ Erros Técnicos** — falhas capturadas durante o uso do app (ex.: falha ao buscar do Azure DevOps, erro inesperado em alguma página), já abrindo em modo "com detalhes" (traceback completo) por padrão — útil para diagnosticar problemas sem depender só da mensagem amigável que apareceu para quem estava usando.
- **🔑 Login/Acessos** — toda tentativa de entrar no app, com sucesso ou não.

Em cada sub-aba: seletor de quantas entradas mostrar, toggle "Ver com detalhes" (mostra cada entrada num cartão com o texto completo, sem cortar), botão **🔄 Atualizar**, e uma seção **"Limpar entradas antigas"** (apaga por número de dias, com um total de quantas foram removidas ao final).

## 8. Aba: Google Drive

Diagnóstico da conta de serviço usada na busca de arquivo no Google Drive — em duas colunas lado a lado:

- **Esquerda**: status da credencial (e-mail da conta de serviço, se configurada) — é esse e-mail que cada usuário precisa compartilhar (permissão de Leitor) com a própria pasta do Drive.
- **Direita**: botão **Testar conexão**, para confirmar rapidamente que a credencial continua funcionando.

Não existe mais uma "pasta raiz" única configurada aqui: desde que a credencial existe, cada usuário guarda a PRÓPRIA pasta direto na tela Importar Dados, sem depender de você para trocar. Se a credencial ainda não estiver configurada, siga o passo a passo completo em **[Configurar Google Drive.md](Configurar%20Google%20Drive.md)** — é feito nos Secrets do Streamlit (produção) ou num arquivo local, nunca colado pela tela do app.

## 9. Aba: Guia do Usuário

Gera (ou atualiza) o PDF **"Guia Completo do Usuário"** — o mesmo oferecido para download em "Sobre o App", para qualquer pessoa logada — direto pelo navegador, sem precisar de terminal nem VSCode.

- Um indicador no topo mostra **✅ "Atualizado - sem alterações pendentes"** ou **⚠️ "Há alterações no conteúdo do guia que ainda não foram enviadas para o PDF"** — comparando o conteúdo do guia no código com o que foi usado na última geração. Isso não acontece sozinho: é só um aviso; a atualização em si continua manual.
- Clique em **🔄 Gerar/Atualizar PDF agora** para gerar uma versão nova a partir do conteúdo atual. O resultado é salvo no banco de dados (Turso) — é o que garante que a versão nova fica disponível para todo mundo imediatamente, e sobrevive a reinícios/redeploys do Streamlit Community Cloud (cujo disco é temporário).
- Depois de gerar, aparece também um botão opcional **"⬇️ Baixar esta versão para manter o assets/ do repositório em dia"** — útil só se você quiser manter o arquivo `.pdf` versionado no Git igual ao que está no ar (não afeta o que os usuários recebem, que já está atualizado assim que você clica em "Gerar/Atualizar").

> Esse PDF é escrito de propósito sem nenhuma menção ao nome do produto/marca e sem nenhum dado específico deste ambiente (credenciais, e-mails reais, URLs de organização) — como ele pode ser baixado e repassado livremente por qualquer usuário logado, o conteúdo evita depender de informação sensível ou de um nome específico.

**Logo abaixo, um segundo bloco separado por uma linha divisória: "🗺️ Fluxograma completo do app (imagem)"** — mesma lógica do PDF acima, mas para as duas imagens (retângulos + setas) do "Fluxograma completo do app" mostrado em "Sobre o App" (a completa e a trancada, para quem não desbloqueou o conteúdo administrativo).

- Mesmo indicador ✅/⚠️, comparando o desenho do fluxo no código com a última geração.
- Clique em **🔄 Gerar/Atualizar fluxograma agora** para gerar as duas versões de uma vez e salvar no banco de dados (Turso) — disponível para todo mundo em "Sobre o App" imediatamente.
- Depois de gerar, as duas imagens aparecem lado a lado na tela, cada uma com um botão opcional de download (mesmo propósito do botão do PDF: manter os arquivos `assets/fluxograma_completo.png`/`assets/fluxograma_publico.png` do repositório em dia, se você quiser).
- Só os cartões de TEXTO do resto de "Sobre o App" (inclusive os da própria seção "Fluxograma completo do app") não precisam desse botão — já são código, aparecem sempre atualizados sozinhos.

## 10. Importar dados

Clique em **📥 Importar Dados** na barra lateral. Há três formas de trazer dados, escolhidas no seletor **"Como deseja importar os dados?"** no topo da página:

### Opção A — Enviar arquivo (.csv/.txt)

1. Deixe selecionada a opção **"Enviar arquivo (.csv/.txt)"**.
2. Clique na área de upload e escolha um arquivo `.csv` ou `.txt` do seu computador (limite de 20MB).
3. Clique em **Processar arquivo**.
4. O app detecta sozinho a codificação e o separador de colunas do arquivo — se ele não conseguir interpretar o arquivo, uma mensagem de erro explica o motivo (ex.: arquivo vazio, ou linhas com quantidades diferentes de colunas).

### Opção B — Buscar automaticamente do Azure DevOps

1. Selecione **"Buscar automaticamente do Azure DevOps"**.
2. Cole o seu **Personal Access Token (PAT)** pessoal no campo indicado. Para gerar um: em `dev.azure.com`, clique na sua foto de perfil → **Personal Access Tokens** → **New Token**, com escopo **"Work Items (Read)"**. O token fica só na memória da sua sessão do navegador — nunca é salvo em disco nem nos Secrets, e some quando você sai.
3. Escolha a **Organização** e clique em **Carregar organização**.
4. Escolha o **Projeto** — os passos seguintes (Area Paths e Queries) carregam sozinhos assim que você escolhe o projeto.
5. (Opcional) Selecione um ou mais **Area Path(s) do Board no Projeto** para restringir a busca a times/módulos específicos. Deixe em branco para não aplicar esse filtro extra.
6. Escolha uma **Query salva no Azure DevOps** já existente. Se a query que você precisa ainda não existe, use o botão **Criar nova query ↗** (abre o Azure DevOps numa aba nova) e depois **🔄 Atualizar lista** aqui para ela aparecer no seletor.
7. Clique em **Baixar relatório atualizado**.

Se algo der errado (PAT inválido/expirado, sem permissão, organização/projeto/query não encontrados, bloqueio de rede), a mensagem de erro explica a causa provável. É a única forma de importação que traz os gráficos **"Prioridade Dentro do Board"** e **"Severidade Calculada"**.

### Opção C — Buscar arquivo no Google Drive

1. Selecione **"Buscar arquivo no Google Drive"** (precisa da credencial configurada — seção 8).
2. Se ainda não tiver uma pasta configurada, copie o e-mail da conta de serviço mostrado na tela, compartilhe sua pasta do Drive com ele (Leitor), cole o link/ID da pasta e clique em **Salvar minha pasta**.
3. Navegue até o arquivo (é possível entrar em subpastas) e escolha o `.csv`.
4. Clique em **Importar arquivo selecionado**.

## 11. Confirmar o mapeamento de colunas

Depois de importar (por qualquer uma das três formas), a página mostra:

1. Uma confirmação de sucesso com o nome do arquivo, quantidade de linhas/colunas e a codificação/delimitador detectados.
2. Um expansor **"Prévia dos dados importados"**, com as 20 primeiras linhas — útil para conferir se leu tudo certo antes de seguir.
3. A seção **"Confirme o mapeamento automático de colunas"**: o app já tenta adivinhar sozinho qual coluna do seu arquivo representa cada campo (Projeto, Status, Data Planejada, Data de Execução, Data de Criação, Tipos de Teste, Responsável/Executor, Criado por, Caso de Teste/ID, Severidade/Prioridade, Coluna do Board, **Sprint**). Confira cada campo e ajuste manualmente qualquer um que não bateu, usando os seletores. Campos deixados como **"— não mapeado —"** simplesmente fazem os gráficos que dependem deles não aparecerem — não trava o app.
4. (Opcional) **Campos personalizados**: relacione qualquer outra coluna do seu arquivo (que não se encaixa nos campos fixos acima) a um nome livre, clicando em **+ Adicionar campo personalizado**. Esses campos ficam disponíveis depois no construtor de gráfico personalizado.
5. Clique em **Confirmar mapeamento e gerar indicadores** para ir direto ao dashboard.

Veja **[Guia - Como Montar a Query no Azure DevOps.md](Guia%20-%20Como%20Montar%20a%20Query%20no%20Azure%20DevOps.md)** para a lista completa de colunas recomendadas a configurar na query (vale para as opções A e C — a B já traz tudo sozinha).

## 12. Usando o dashboard

Ao confirmar o mapeamento, você cai direto na página **📊 Indicadores**. A barra lateral ganha, no topo, os filtros:

- **Período** — datas "De"/"Até"; ajuste e clique em **Confirmar intervalo** para aplicar.
- **Filtros** — Projeto, Tipos de Teste e Status, todos como caixas de seleção múltipla (multiseleção), com tudo marcado por padrão.

No corpo da página, de cima para baixo:

- **Cartões de KPI** no topo — números-resumo (volumetria total e, dependendo do vocabulário de status do seu arquivo, taxa de sucesso ou os status mais comuns).
- Uma sequência de gráficos, cada um com seu próprio seletor **"Tipo de gráfico"** (Barras, Barras Horizontais, Pizza, Rosca, Linha, Área, Treemap, Pareto, Funil, Mapa de Calor, Radar preenchido — as opções variam conforme o gráfico) e, em alguns casos, filtros extras próprios daquele gráfico.
- Um expansor **"Ver dados detalhados (filtrados)"** ao final, com a tabela completa e um botão para exportar em CSV.

Os gráficos disponíveis (aparecem ou não dependendo de quais campos você mapeou) são: Distribuição de Status, Area Path × Status, Backlog Aberto (com gráfico de bolha Volume × Idade × Risco), Planejamento vs. Testes Efetivados, Sprints — Itens Concluídos, Testes por Projeto, Ranking de Bugs por Projeto, Distribuição por Tipo de Teste, Taxa de Sucesso por Projeto, Tendência ao Longo do Tempo, Bugs Abertos vs. Solucionados, Distribuição por Severidade/Prioridade, Distribuição por Coluna do Board, Area Path × Coluna do Board, Prioridade Dentro do Board *, Severidade Calculada *, Volume de Testes por Responsável, Volume por Responsável ao Longo do Tempo e Carga de Risco por Responsável.

<small>* Só com dados vindos da busca automática por PAT (Opção B da seção 10).</small>

## 13. Analisar um gráfico com IA (configuração e uso)

Logo abaixo de praticamente todo gráfico (Dashboard e Scrum & Sprints) existe um botão **🤖 Analisar com IA**, que gera um texto explicando o que os dados daquele gráfico mostram, pontos de atenção e uma sugestão prática — considerando os filtros já aplicados na tela. O uso é igual para qualquer pessoa logada (ver seção 12); esta seção cobre a parte que só diz respeito a você, como administrador: como habilitar o recurso.

### Como funciona por baixo dos panos

O app **não fala direto com nenhuma API de IA** (OpenAI, Gemini etc.) — ele só envia os dados do gráfico (já filtrados como estão na tela) para um **webhook** que você configura, e devolve o texto que essa automação responder. Qual modelo de IA é usado, qual o prompt exato, e qualquer chave de API de IA em si são responsabilidade inteiramente dessa automação externa, não deste app — o app não sabe (e não precisa saber) o que acontece do outro lado do webhook.

### Habilitando o recurso

Sem nenhuma configuração, o botão **"Analisar com IA" simplesmente não aparece** em nenhum gráfico — não trava nem exibe erro, só fica indisponível, igual às outras integrações opcionais deste app (Google Drive, por exemplo). Para habilitar, adicione a seção `[n8n]` nos **Secrets do Streamlit** (produção) ou no seu `.streamlit/secrets.toml` local:

```toml
[n8n]
webhook_url = "https://SEU-WEBHOOK.exemplo.com/webhook/analise-grafico"
auth_token = "TOKEN_OPCIONAL_SE_O_WEBHOOK_EXIGIR_AUTENTICACAO"
```

- **`webhook_url`** — a URL que recebe os dados do gráfico (POST, corpo JSON) e devolve o texto da análise. É o único campo obrigatório.
- **`auth_token`** — opcional; se preenchido, é enviado como `Authorization: Bearer <auth_token>` em cada chamada. Deixe de fora se o seu webhook não exigir autenticação (ou usar outro mecanismo, como um segredo já embutido na própria URL).
- A montagem da automação em si (qual serviço recebe o webhook, qual modelo de IA usar, o prompt, eventuais múltiplos provedores de IA como reserva um do outro) é decidida e mantida inteiramente por você, fora deste app — não há nenhuma tela dentro do painel para isso.

### Privacidade dos dados enviados

- Cada clique em "Analisar com IA" envia só os dados **daquele gráfico específico**, já filtrados como estão na tela naquele momento — não o arquivo inteiro importado.
- Em qualquer gráfico com uma coluna de Responsável, os **nomes reais nunca são enviados** para o webhook — o app troca cada nome por um rótulo genérico ("Colaborador 1", "Colaborador 2"...) antes de montar a requisição, sempre o mesmo rótulo para a mesma pessoa dentro de uma mesma análise. O gráfico na tela continua mostrando os nomes reais normalmente; só o que viaja para fora do app é anonimizado.
- Cada análise gerada com sucesso fica registrada em Administração → Logs do Sistema → "🗂️ Ações no Painel" (quem pediu, qual gráfico) — mas se algo der errado (webhook fora do ar, resposta num formato inesperado, tempo de espera esgotado — até cerca de 75 segundos), a pessoa usando o app só vê uma mensagem de erro amigável na hora; nada é registrado nos Logs do Sistema por essa falha específica.

## 14. Construtor de gráfico personalizado

Mais abaixo no dashboard, a seção **"Monte seu gráfico personalizado"** deixa você montar um gráfico do zero, para perguntas que não têm um gráfico fixo pronto:

1. **Eixo / Categoria (X)** — a coluna que vai virar as categorias do gráfico.
2. **Agrupar por (opcional)** — uma segunda coluna, para dividir/colorir por grupo (ex.: "Projeto por Status").
3. **Métrica** — contar registros, ou somar uma coluna numérica.
4. **Coluna numérica** — só aparece se você escolher "Soma de coluna numérica" acima.
5. **Tipo de gráfico**.

Clique em **Gerar gráfico**. O gráfico gerado também é recalculado automaticamente se você mudar os filtros da barra lateral depois.

## 15. Gerar o relatório em PDF

No final da página do dashboard, a seção **"Relatório completo em PDF"** tem o botão **📄 Gerar PDF do relatório**. Ele monta um PDF com os KPIs e todos os gráficos visíveis na tela naquele momento — com os mesmos filtros aplicados e o mesmo tipo de gráfico escolhido em cada seção (inclusive o gráfico personalizado, se você já tiver gerado um).

- Pode levar até um minuto (cada gráfico é desenhado individualmente); a primeira vez que alguém gera um PDF numa instalação nova pode demorar mais ainda, se o app precisar baixar um navegador dedicado para essa etapa.
- Se você mudar algum filtro depois de gerar o PDF, clique no botão de novo para atualizar — o PDF não se atualiza sozinho.
- Assim que pronto, aparece o botão **⬇️ Baixar PDF gerado**.
- Conteúdo dentro de um expansor recolhido (como a tabela de dados detalhados) não entra no PDF.
- Se a geração falhar (situação rara, geralmente falta de navegador disponível no ambiente), uma mensagem de erro explica o motivo — o resto do dashboard continua funcionando normalmente.

## 16. "Nova Análise" e "Sair"

- **🔄 Nova Análise** (barra lateral, aparece só depois de já ter processado um arquivo) — limpa o arquivo importado e todos os indicadores/gráficos/filtros gerados a partir dele (inclusive o gráfico personalizado), para você importar um arquivo novo sem precisar dar F5. Pede confirmação antes de aplicar. Sua sessão continua logada, e a organização/projeto/query do Azure DevOps já configurados (se você usa a busca automática) não são apagados.
- **Sair** (final da barra lateral) — encerra sua sessão de verdade.

## 17. Perguntas frequentes

**Um gráfico não aparece no dashboard. Por quê?**
Ele depende de um campo que não foi mapeado no seu arquivo (ex.: sem "Coluna do Board" mapeada, os gráficos de board não aparecem), ou é um dos dois gráficos exclusivos da busca por PAT. Volte em "Importar Dados" e confira o mapeamento, ou aceite que aquele indicador simplesmente não se aplica a esse arquivo.

**Uma solicitação de acesso ficou "presa" em Pendentes por engano.**
Você pode simplesmente ignorá-la até decidir, ou rejeitá-la (ela pode ser "Recuperada" depois, se mudar de ideia).

**Marquei "Marcar como criada" sem ter criado a conta de verdade.**
Volte à seção "Já criadas", não tem um caminho direto de "desfazer" para essa lista específica — a forma prática é revogar (o que move para "Revogadas") e depois "Reverter revogação" (volta para "Pendentes"), aí sim criar a conta de verdade e marcar como criada novamente.

**Posso dar acesso ao Painel Administrativo para mais alguém?**
Hoje o painel reconhece só o usuário `admin` como administrador de verdade — é uma constante no código (`USUARIO_ADMIN` em `ui/pages/admin_page.py`). Ampliar isso é uma alteração de código, não uma configuração dentro do app. Se você só quer que outra pessoa entenda como a Administração funciona (sem dar acesso real a ela), use o "Código de acesso ao conteúdo administrativo de Sobre o App" (seção 4).

**Esqueci o código de acesso ao conteúdo administrativo de "Sobre o App".**
Sem problema — volte na seção 4, o código atual aparece na tela para você reler ou trocar a qualquer momento.

**O botão "Analisar com IA" não aparece em nenhum gráfico.**
Confirme se a seção `[n8n]` (pelo menos `webhook_url`) está configurada nos Secrets (ver seção 13) — sem ela, o botão simplesmente não aparece em lugar nenhum, para ninguém, mesmo você.

**A análise por IA respondeu, mas sem texto reconhecível (ou com erro).**
A mensagem de erro mostrada inclui um trecho do corpo bruto que o webhook devolveu — normalmente aponta se o problema é formato de resposta inesperado, credencial de algum provedor de IA configurado na sua automação, ou timeout (o app espera até cerca de 75 segundos). Como o app não sabe o que acontece do lado de dentro do webhook (seção 13), o diagnóstico mais detalhado precisa ser feito direto na sua automação.
