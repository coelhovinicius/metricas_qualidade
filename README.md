# Refuturiza QA — Painel de Indicadores de Qualidade

Aplicação web (Streamlit) que transforma work items do Azure DevOps — importados manualmente em CSV/TXT ou buscados direto pela API — em um painel de indicadores e gráficos interativos sobre o trabalho de QA: volume de testes, bugs em aberto, backlog envelhecido, fluxo no board Kanban e ritmo de trabalho por responsável e por projeto. Também gera um relatório completo em PDF, pronto para anexar num e-mail ou guardar como registro de um período.

Acesso multiusuário com login, controle de quem pode ver o quê e um fluxo de solicitação de acesso auto-atendido (sem precisar de e-mail ou processo externo).

> Procurando um passo a passo de uso (sem código)? Veja **[GUIA_ADMIN.md](GUIA_ADMIN.md)** (administrador) e **[GUIA_CONVIDADO.md](GUIA_CONVIDADO.md)** (usuário comum). Este README é a documentação técnica do projeto.

## Índice

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
  - [Login e controle de acesso](#login-e-controle-de-acesso)
  - [Importação de dados](#importação-de-dados)
  - [Mapeamento de colunas](#mapeamento-de-colunas)
  - [Filtros do dashboard](#filtros-do-dashboard)
  - [Indicadores e gráficos](#indicadores-e-gráficos)
  - [Construtor de gráfico personalizado](#construtor-de-gráfico-personalizado)
  - [Relatório completo em PDF](#relatório-completo-em-pdf)
  - [Painel administrativo](#painel-administrativo)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Stack técnica](#stack-técnica)
- [Como rodar localmente](#como-rodar-localmente)
- [Configuração (secrets)](#configuração-secrets)
- [Gestão de usuários](#gestão-de-usuários)
- [Deploy](#deploy)
- [Segurança e privacidade](#segurança-e-privacidade)
- [Limitações conhecidas](#limitações-conhecidas)

## Visão geral

Antes deste app, entender o panorama real do trabalho de QA dependia de exportar dados do Azure DevOps e montar tabelas/gráficos manualmente a cada consulta. O painel centraliza isso: os mesmos dados brutos viram, de forma automática e padronizada, um conjunto de indicadores prontos — acessíveis por link de navegador, sem instalação, para qualquer pessoa autorizada da empresa.

Fluxo de uso, em três passos:

1. **Login** com usuário e senha (ou solicitação de acesso, se ainda não tiver conta).
2. **Importar dados** — enviando um arquivo exportado do Azure DevOps, ou buscando direto da API com um Personal Access Token pessoal.
3. **Confirmar o mapeamento de colunas** e navegar pelo dashboard, com filtros, mais de quinze indicadores/gráficos prontos e um relatório em PDF de tudo isso, com um clique.

## Funcionalidades

### Login e controle de acesso

- Autenticação multiusuário via [`streamlit-authenticator`](https://github.com/mkhorasani/Streamlit-Authenticator), com sessão persistida em cookie assinado — um F5 na página não exige login de novo, dentro do prazo configurado.
- A sessão é encerrada automaticamente quando a aba/janela do navegador é realmente fechada (não só recarregada), mesmo em navegadores que mantêm o processo rodando em segundo plano.
- Quem não tem conta pode clicar em **"Solicitar acesso"** e preencher nome, e-mail e motivo — a solicitação fica registrada num banco de dados (Turso) e só é visível para o administrador dentro do próprio app. Não há envio de e-mail nem integração externa.
- **Painel Administrativo** (visível só para o usuário `admin`): lista as solicitações por status (Pendentes, Já criadas, Revogadas, Rejeitadas), com ações de aprovar/rejeitar/revogar/recuperar/excluir, exclusão em massa e um diagnóstico de conexão com o banco de dados.
- A criação de conta em si continua manual, por decisão de projeto: o administrador gera o hash da senha (`scripts/gerar_hash_senha.py`) e adiciona o usuário nos Secrets do Streamlit, depois marca a solicitação como "criada" no painel — o painel documenta e organiza os pedidos, mas não cria contas sozinho.

### Importação de dados

Duas formas de trazer os dados para o app, ambas alimentando o mesmo pipeline de indicadores:

- **Upload manual** de um arquivo `.csv`/`.txt` (até 20MB), com detecção automática de encoding e delimitador (vírgula, ponto e vírgula, tabulação ou pipe), remoção de linhas/colunas vazias e mensagens de erro amigáveis quando o arquivo não pode ser interpretado.
- **Busca automática no Azure DevOps**, direto pela API REST, sem precisar exportar/importar CSV manualmente:
  - Cada usuário informa o **próprio Personal Access Token (PAT)** — nunca salvo em disco/Secrets, fica só na memória da sessão do navegador e some ao sair. Isso dá rastreabilidade real: o log de acesso do Azure DevOps mostra o usuário dono do PAT, não uma conta de serviço compartilhada.
  - Seleção em cascata: organização → projeto → um ou mais **Area Paths** (times/módulos, opcional, com multiseleção) → query já salva no Azure DevOps.
  - Um item de teste sem coluna de board própria (comum em Test Cases, que vivem dentro de Test Plans/Suites) herda a coluna do item pai vinculado, quando existir — para não perder a visão de fluxo desses itens no gráfico de board.
  - Mensagens de erro específicas para PAT inválido/expirado, falta de permissão, organização/projeto/query não encontrados, e bloqueios de rede/Conditional Access no Azure AD da organização.

### Mapeamento de colunas

Como a estrutura do arquivo pode variar, o app tenta identificar sozinho qual coluna representa cada campo canônico (Projeto, Status, Data Planejada, Data de Execução, Data de Criação, Tipo de Teste, Responsável/Executor, **Criado por** — reserva do Responsável, ver abaixo —, Caso de Teste/ID, Severidade/Prioridade, Coluna do Board) por correspondência de palavras-chave, com suporte a termos em português e inglês (exports do Azure DevOps costumam vir em inglês mesmo em organizações que operam em português).

O mapeamento sugerido é sempre exibido para confirmação/ajuste manual antes de qualquer gráfico ser gerado — nunca é aplicado silenciosamente. Também é possível anexar **campos personalizados** (qualquer outra coluna do arquivo, com um rótulo livre), disponíveis no filtro e no construtor de gráfico personalizado.

O campo **Criado por** é uma reserva do Responsável: quando uma linha não tem Responsável preenchido, mas tem um valor em Criado por, esse valor é usado no lugar — só nesse caso; um Responsável já preenchido nunca é sobrescrito. Isso reduz a quantidade de itens que caem em "Não atribuído(a)" no gráfico **Volume de Testes por Responsável** quando o arquivo de origem tem uma coluna de autor/criador mais completa que a de responsável/atribuído.

Campos não mapeados simplesmente fazem os indicadores que dependem deles não aparecerem — o dashboard nunca quebra por falta de uma coluna.

### Filtros do dashboard

Aplicados a todo o painel, na barra lateral:

- **Período** (data inicial/final, com valor padrão do último mês até a data de hoje, dentro dos limites reais do arquivo).
- **Projeto** (multiseleção, todos marcados por padrão).
- **Tipos de Teste** (multiseleção).
- **Status** (multiseleção).

### Indicadores e gráficos

- **KPIs no topo**: volumetria total, e — quando o vocabulário de Status do arquivo é reconhecido como Passou/Falhou/Planejado — passaram, não passaram e taxa de sucesso; caso contrário, status mais frequente e quantidade de status distintos.
- **Distribuição de Status** (ou "Passou vs. Não Passou", quando aplicável).
- **Area Path × Status** — cruzamento que evita misturar vocabulários diferentes de Status quando times/processos distintos estão selecionados ao mesmo tempo.
- **Backlog Aberto** — idade média/mediana dos itens ainda abertos, e quantos estão parados há mais de 90/180/365 dias.
- **Planejamento vs. Testes Efetivados**.
- **Testes por Projeto** e **Ranking de Bugs por Projeto**.
- **Distribuição por Tipo de Teste**, com exclusão configurável de tipos "contêiner" (Test Plan, Test Suite) que não representam um item de teste individual.
- **Taxa de Sucesso por Projeto**.
- **Tendência ao Longo do Tempo** (volume semanal, opcionalmente por Status).
- **Bugs Abertos vs. Solucionados ao longo do tempo** — acumulado semanal, com opção de marcar quais colunas do board estão "fora do controle da QA" (aguardando validação externa), para não penalizar o time por uma espera que não é dele.
- **Distribuição por Severidade/Prioridade**.
- **Distribuição por Coluna do Board (Kanban)** e **Area Path × Coluna do Board** — usando a ordem real do fluxo (Backlog → ... → Finalizado) e excluindo por padrão os itens sem coluna atribuída ("Não atribuído(a)"), com um detalhamento à parte de quem são esses itens, por tipo.
- **Volume de Testes por Responsável** — quem fez quanto, com opção de abrir por Projeto (barra empilhada).
- **Volume por Responsável ao Longo do Tempo** — ritmo semanal de cada pessoa (não diário, para não confundir variação real de ritmo com o padrão de dia da semana), limitado às 8 pessoas de maior volume para manter o gráfico legível.
- **Tabela de dados detalhados** (filtrados) com exportação para CSV.

Praticamente todo gráfico permite escolher o tipo de visualização (Barras, Barras Horizontais, Pizza, Rosca, Linha, Área, Treemap, Pareto, Radar preenchido — conforme fizer sentido para os dados daquele indicador). A paleta de cores foi desenhada especificamente para que categorias vizinhas num mesmo gráfico nunca fiquem com tons parecidos, mesmo em gráficos com poucas categorias.

### Construtor de gráfico personalizado

Para perguntas que não têm um gráfico fixo pronto: escolha livremente a coluna do eixo X, uma coluna opcional para agrupar/colorir, a métrica (contagem de registros ou soma de uma coluna numérica) e o tipo de gráfico — usando qualquer campo mapeado, personalizado ou bruto do arquivo importado.

### Relatório completo em PDF

Ao final do dashboard, o botão **"Gerar PDF do relatório"** monta um PDF com os KPIs e todos os gráficos visíveis na tela naquele momento — respeitando os mesmos filtros (Período/Projeto/Tipos de Teste/Status) e o mesmo tipo de gráfico escolhido em cada seção, inclusive o gráfico personalizado, se algum já tiver sido gerado. Conteúdo dentro de um expansor recolhido (ex.: a tabela de dados detalhados) não entra no PDF — só o que já está visível por padrão.

Detalhes técnicos relevantes:

- Cada gráfico Plotly é rasterizado como imagem PNG via [`kaleido`](https://github.com/plotly/Kaleido) (versão `>=1.0`; ver comentário em `requirements.txt` sobre por que não pode ser a versão `0.2.1`) e o PDF em si é montado com [`reportlab`](https://www.reportlab.com/opensource/).
- O `kaleido>=1.0` não vem com um navegador embutido: procura um Chrome/Chromium/Edge/Brave já instalado no sistema, e só baixa um "Chrome for Testing" próprio se não achar nenhum. No Streamlit Community Cloud, isso depende do pacote `chromium` do `packages.txt` (ver [Deploy](#deploy)) — sem ele, o navegador baixado sozinho não consegue nem abrir, por faltar bibliotecas do sistema no container.
- Se a geração falhar (ex.: sem navegador disponível e sem acesso à internet para baixar um), o app mostra uma mensagem de erro amigável em vez de travar — o resto do dashboard continua funcionando normalmente.

### Painel administrativo

Descrito acima, em [Login e controle de acesso](#login-e-controle-de-acesso).

## Estrutura do projeto

```
app.py                       # ponto de entrada / roteamento de páginas
auth/
  auth_manager.py            # autenticação (login, sessão, logout)
  users.yaml                 # fallback local de credenciais - NÃO commitado (ver .gitignore)
core/
  analytics.py               # regras de negócio: cálculo de todos os indicadores/gráficos
  azure_devops_client.py     # cliente da API REST do Azure DevOps
  column_mapper.py           # detecção automática de colunas + normalização de valores
  data_loader.py             # leitura/parse de CSV/TXT (encoding, delimitador, limpeza)
  pdf_report.py               # geração do relatório completo em PDF (kaleido + reportlab)
  solicitacoes_conta.py      # CRUD das solicitações de acesso (tabela no Turso)
  turso_client.py            # cliente HTTP minimalista para o banco Turso
ui/
  components.py              # componentes reutilizáveis (cabeçalho, overlay de loading, KPI card...)
  theme.py                   # cores, paletas e CSS global
  pages/
    login_page.py
    upload_page.py
    dashboard_page.py
    admin_page.py
utils/
  session.py                 # inicialização/limpeza centralizada do session_state
assets/                      # logotipos e imagens (logo_refuturiza.png, simbolo_refuturiza.png)
scripts/
  gerar_hash_senha.py                   # gera o hash bcrypt de uma senha nova
  migrar_credenciais_para_secrets.py    # converte auth/users.yaml existente no bloco TOML dos Secrets
.gitignore                   # exclui auth/users.yaml e .streamlit/secrets.toml do controle de versão
packages.txt                 # pacotes de sistema (apt) exigidos no Streamlit Community Cloud
requirements.txt
README.md                    # este arquivo (documentação técnica)
GUIA_ADMIN.md                # passo a passo de uso para o administrador
GUIA_CONVIDADO.md            # passo a passo de uso para o usuário comum
```

## Stack técnica

| Camada | Tecnologia |
| --- | --- |
| Interface / servidor web | [Streamlit](https://streamlit.io/) |
| Autenticação | streamlit-authenticator + bcrypt |
| Manipulação de dados | pandas |
| Gráficos | Plotly Express / Plotly Graph Objects |
| Relatório em PDF | kaleido (rasterização dos gráficos) + reportlab (montagem do PDF) |
| Detecção de encoding | chardet |
| Configuração de usuários | PyYAML |
| Integração com Azure DevOps | requests (API REST, sem SDK) |
| Banco de dados (solicitações de acesso) | Turso (SQLite via HTTP), acessado com `requests` puro |
| Hospedagem | Streamlit Community Cloud |

Ver `requirements.txt` para as versões exigidas de cada dependência. **`streamlit` e `starlette` são travados numa versão exata** (não `>=`) — ver o comentário no topo do arquivo: uma combinação incompatível entre essas duas bibliotecas já derrubou a aplicação inteira em produção (erro `TypeError: GZipResponder.__init__() missing 1 required keyword-only argument: 'thread_minimum_size'`), então não altere essas duas linhas sem testar a combinação antes.

## Como rodar localmente

```powershell
# 1. Criar e ativar um ambiente virtual (opcional, mas recomendado)
python -m venv venv
venv\Scripts\activate

# 2. Instalar as dependências
pip install -r requirements.txt

# 3. Rodar a aplicação
python -m streamlit run app.py
```

A aplicação abre em `http://localhost:8501`. Sem os Secrets configurados (passo abaixo), o app ainda roda localmente, usando os valores de fallback definidos em `auth/users.yaml` — mas a busca automática no Azure DevOps e o registro de solicitações de acesso (que depende do Turso) não vão funcionar sem a configuração correspondente.

O relatório em PDF também funciona localmente sem nenhuma configuração extra — o Windows costuma já ter algum navegador instalado (Edge, Chrome), que o `kaleido` encontra sozinho; se não encontrar, baixa um "Chrome for Testing" próprio na primeira geração (só precisa de acesso à internet nesse momento).

## Configuração (secrets)

Em produção (Streamlit Community Cloud), configurar em **Settings → Secrets**; localmente, em `.streamlit/secrets.toml` (nunca commitado no Git — ver `.gitignore`):

```toml
[auth.cookie]
name = "refu_cookie"
key = "uma-chave-secreta-longa-e-aleatoria"
expiry_days = 30

[auth.preauthorized]
emails = []

[auth.credentials.usernames.admin]
email = "admin@empresa.com"
name = "Nome Completo"
password = "$2b$12$hash-bcrypt-da-senha-aqui"

# repita [auth.credentials.usernames.<usuario>] para cada conta

[turso]
database_url = "https://SEU-BANCO-SEUUSUARIO.turso.io"
auth_token = "SEU_TOKEN_DE_AUTENTICACAO_TURSO"
```

- **`[auth]`** contém a base de usuários inteira (credenciais + config do cookie + e-mails pré-autorizados) — é a fonte de credenciais preferida (ver [Gestão de usuários](#gestão-de-usuários)). O `auth/users.yaml` local continua existindo como fallback só para rodar sem configurar Secrets (ex.: primeira vez clonando o projeto) — nesse caso funciona exatamente como antes, só que **sem essa fonte nunca ser commitada**. Se quiser manter só a `cookie_key` nos Secrets (formato antigo/mínimo) e o resto no arquivo local, isso também continua funcionando — `auth/auth_manager.py` aceita as duas formas.
- `turso.*` é exigido apenas para o fluxo de solicitação de acesso (botão "Solicitar acesso" na tela de login e o Painel Administrativo). Sem essa configuração, o restante do app funciona normalmente — só esse fluxo específico fica indisponível, com uma mensagem de erro clara em vez de travar a aplicação.
- O Personal Access Token do Azure DevOps **não é** um secret da aplicação — cada usuário cola o próprio PAT dentro do app, na tela de importação, e ele nunca é persistido.

Para converter um `auth/users.yaml` já existente no bloco `[auth.*]` acima sem digitar hash de senha manualmente, rode localmente:

```powershell
python scripts\migrar_credenciais_para_secrets.py
```

O script só lê o arquivo local e imprime o bloco TOML no terminal — nada é enviado pela rede; copie a saída e cole no `secrets.toml`.

## Gestão de usuários

**As credenciais de usuário (incluindo hash de senha) vivem nos Secrets do Streamlit, nunca no repositório Git.** `auth/users.yaml` é só um fallback de desenvolvimento local e **não deve ser commitado** (está no `.gitignore`) — ver [Configuração (secrets)](#configuração-secrets) para o porquê e como migrar um arquivo já existente.

Criação de conta, passo a passo:

1. A pessoa solicita acesso pela tela de login (nome, e-mail, motivo).
2. O administrador revisa a solicitação no Painel Administrativo.
3. Aprovando, o administrador gera o hash da senha com `scripts/gerar_hash_senha.py` e adiciona o usuário na seção `[auth.credentials.usernames.<usuario>]` dos Secrets (local **e** do Streamlit Community Cloud, se a conta precisa valer em produção).
4. O administrador marca a solicitação como "criada" no painel, para sair da lista de pendentes.

Revogar acesso segue o caminho inverso: remover o usuário dos Secrets (e do `auth/users.yaml` local, se ele também estiver lá) e marcar a solicitação como "revogada" no painel (o painel registra o histórico; a revogação de acesso real sempre acontece na fonte de credenciais).

Veja o passo a passo detalhado, com prints/descrição de tela, em **[GUIA_ADMIN.md](GUIA_ADMIN.md)**.

## Deploy

Hospedado no **Streamlit Community Cloud**, apontando para este repositório. Qualquer alteração enviada ao branch de produção é publicada automaticamente (ou após clicar em "Reboot app" no painel do Streamlit Cloud, quando a alteração exige reinstalar dependências). Os Secrets de produção (base de usuários completa em `[auth]`, credenciais do Turso) são configurados direto no painel do Streamlit Community Cloud — nunca no código versionado.

Dois arquivos controlam o ambiente de execução no Streamlit Community Cloud, além do código:

- **`requirements.txt`** — dependências Python. `streamlit` e `starlette` estão travados numa versão exata específica de propósito (ver [Stack técnica](#stack-técnica)) — evite trocar por `>=` sem testar a combinação primeiro.
- **`packages.txt`** — dependências de sistema (`apt-get install`), hoje só com uma linha, `chromium`. Necessário para o relatório em PDF funcionar em produção: garante as bibliotecas de sistema (`libnss3`, `libgtk-3-0`, `libasound2` etc.) que qualquer Chrome/Chromium precisa para conseguir abrir dentro do container do Streamlit Cloud — sem isso, o navegador que o `kaleido` baixa sozinho até é baixado com sucesso, mas falha ao iniciar ("The browser seemed to close immediately after starting"). Qualquer alteração neste arquivo exige um rebuild completo do ambiente (reboot manual do app pelo painel do Streamlit Cloud costuma ser necessário).

Se o repositório for **público**, isso é ainda mais importante: qualquer arquivo commitado é visível para qualquer pessoa, inclusive em commits antigos. Este projeto foi ajustado para não depender de nenhum arquivo sensível versionado (ver seções acima) — mas vale conferir a visibilidade do repositório em GitHub → Settings → Danger Zone, e considerar torná-lo privado se ele guardar qualquer histórico de commit anterior a esse ajuste.

## Segurança e privacidade

- Senhas de usuários são armazenadas com hash (bcrypt), nunca em texto puro, e vivem nos Secrets do Streamlit — não no repositório Git (ver [Gestão de usuários](#gestão-de-usuários)).
- O PAT do Azure DevOps de cada usuário nunca é salvo em disco, banco de dados ou Secrets — vive só na memória da sessão do navegador enquanto o usuário está logado.
- As solicitações de acesso não disparam e-mail nem qualquer notificação externa — ficam visíveis só para quem acessa o Painel Administrativo dentro do próprio app.
- A sessão de login é encerrada automaticamente ao fechar de verdade a aba/janela do navegador (não sobrevive além de um F5 dentro do prazo configurado).
- Se o repositório já foi público em algum momento com `auth/users.yaml` commitado, trate os hashes de senha expostos naquele período como potencialmente comprometidos (mesmo com bcrypt, um hash exposto pode ser atacado offline) — o ideal é tornar o repositório privado e, quando possível, trocar as senhas dos usuários que estavam naquele arquivo.

## Limitações conhecidas

- A criação/remoção de contas continua manual (edição dos Secrets, com `scripts/gerar_hash_senha.py` para gerar o hash); o app organiza e documenta as solicitações, mas não provisiona usuários sozinho.
- O painel administrativo hoje reconhece um único usuário (`admin`) como administrador — dar esse acesso a mais pessoas exige alterar `ui/pages/admin_page.py`.
- Indicadores que dependem de um campo específico (datas, Severidade, Coluna do Board etc.) só aparecem quando esse campo está mapeado nos dados importados — não há como calculá-los sem a informação correspondente no arquivo/consulta de origem.
- A geração do relatório em PDF depende de conseguir abrir um navegador Chrome/Chromium no ambiente onde o app está rodando (local ou Streamlit Community Cloud) — em ambientes de execução muito restritos/minimalistas sem o `packages.txt` correspondente, essa funcionalidade específica pode falhar (com uma mensagem de erro clara), mesmo com o resto do dashboard funcionando normalmente.
