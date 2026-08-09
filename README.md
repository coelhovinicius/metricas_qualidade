# Refuturiza QA — Painel de Indicadores de Qualidade

Aplicação web (Streamlit) que transforma work items do Azure DevOps — importados manualmente em CSV/TXT, buscados direto pela API, ou buscados de uma pasta compartilhada no Google Drive — em um painel de indicadores e gráficos interativos sobre o trabalho de QA: volume de testes, bugs em aberto, backlog envelhecido, fluxo no board Kanban, ritmo por sprint e ritmo de trabalho por responsável e por projeto. Também gera um relatório completo em PDF, pronto para anexar num e-mail ou guardar como registro de um período.

Acesso multiusuário com login, controle de quem pode ver o quê e um fluxo de solicitação de acesso auto-atendido (sem precisar de e-mail ou processo externo).

> Procurando um passo a passo de uso (sem código)? Veja **[GUIA_ADMIN.md](GUIA_ADMIN.md)** (administrador) e **[GUIA_CONVIDADO.md](GUIA_CONVIDADO.md)** (usuário comum) — o mesmo conteúdo do guia do usuário também está disponível dentro do próprio app, em **Sobre o App**, com um PDF pronto para baixar e repassar. Para configurar a query certa no Azure DevOps, veja **[Guia - Como Montar a Query no Azure DevOps.md](Guia%20-%20Como%20Montar%20a%20Query%20no%20Azure%20DevOps.md)**; para configurar a busca no Google Drive, **[Configurar Google Drive.md](Configurar%20Google%20Drive.md)**. Este README é a documentação técnica de arquitetura do projeto; para um mergulho ainda mais detalhado em cada linguagem/ferramenta/biblioteca usada e como cada uma se encaixa, veja **[DOCUMENTACAO_TECNICA.md](DOCUMENTACAO_TECNICA.md)**.

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
  - [Sobre o App e Guia do Usuário](#sobre-o-app-e-guia-do-usuário)
    - [Mantendo o fluxograma em dia](#mantendo-o-fluxograma-em-dia)
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
2. **Importar dados** — enviando um arquivo exportado do Azure DevOps, buscando direto da API com um Personal Access Token pessoal, ou buscando um `.csv` já deixado numa pasta própria do Google Drive.
3. **Confirmar o mapeamento de colunas** e navegar pelo dashboard, com filtros, mais de vinte indicadores/gráficos prontos e um relatório em PDF de tudo isso, com um clique.

## Funcionalidades

### Login e controle de acesso

- Autenticação multiusuário via [`streamlit-authenticator`](https://github.com/mkhorasani/Streamlit-Authenticator), com sessão persistida em cookie assinado — um F5 na página não exige login de novo, dentro do prazo configurado.
- A sessão é encerrada automaticamente quando a aba/janela do navegador é realmente fechada (não só recarregada), mesmo em navegadores que mantêm o processo rodando em segundo plano.
- Quem não tem conta pode clicar em **"Solicitar acesso"** e preencher nome, e-mail e motivo — a solicitação fica registrada num banco de dados (Turso) e só é visível para o administrador dentro do próprio app. Não há envio de e-mail nem integração externa.
- **Painel Administrativo** (visível só para o usuário `admin`): lista as solicitações por status (Pendentes, Já criadas, Revogadas, Rejeitadas), com ações de aprovar/rejeitar/revogar/recuperar/excluir, exclusão em massa, logs do sistema, diagnóstico de conexão com o banco de dados e mais — ver [Painel administrativo](#painel-administrativo) abaixo.
- A criação de conta em si continua manual, por decisão de projeto: o administrador gera o hash da senha (`scripts/gerar_hash_senha.py`) e adiciona o usuário nos Secrets do Streamlit, depois marca a solicitação como "criada" no painel — o painel documenta e organiza os pedidos, mas não cria contas sozinho.

### Importação de dados

Três formas de trazer os dados para o app, todas alimentando o mesmo pipeline de indicadores:

- **Upload manual** de um arquivo `.csv`/`.txt` (até 20MB), com detecção automática de encoding e delimitador (vírgula, ponto e vírgula, tabulação ou pipe), remoção de linhas/colunas vazias e mensagens de erro amigáveis quando o arquivo não pode ser interpretado.
- **Busca automática no Azure DevOps**, direto pela API REST, sem precisar exportar/importar CSV manualmente:
  - Cada usuário informa o **próprio Personal Access Token (PAT)** — nunca salvo em disco/Secrets, fica só na memória da sessão do navegador e some ao sair. Isso dá rastreabilidade real: o log de acesso do Azure DevOps mostra o usuário dono do PAT, não uma conta de serviço compartilhada.
  - Seleção em cascata: organização → projeto → um ou mais **Area Paths** (times/módulos, opcional, com multiseleção) → query já salva no Azure DevOps.
  - A cada busca, o app confere quem é o dono real do PAT (direto na API do Azure DevOps) e compara com quem está logado — se os nomes não baterem, o log correspondente é marcado como "POSSÍVEL ANOMALIA" para o admin conferir (não bloqueia a busca).
  - Um item de teste sem coluna de board própria (comum em Test Cases, que vivem dentro de Test Plans/Suites) herda a coluna do item pai vinculado, quando existir — para não perder a visão de fluxo desses itens no gráfico de board.
  - É o único caminho que traz **Prioridade Dentro do Board** e **Severidade Calculada** (posição relativa dentro da coluna) — dependem de um campo (Stack Rank/Backlog Priority) que o Azure DevOps não expõe em CSV manual, em nenhuma configuração de query.
  - Mensagens de erro específicas para PAT inválido/expirado, falta de permissão, organização/projeto/query não encontrados, e bloqueios de rede/Conditional Access no Azure AD da organização.
- **Busca automática no Google Drive**, de um arquivo `.csv` já deixado numa pasta:
  - Usa uma **Conta de Serviço** do Google (credencial "robô", sem tela de login pessoal), configurada uma única vez pelo administrador — ver **[Configurar Google Drive.md](Configurar%20Google%20Drive.md)** para o passo a passo completo.
  - Diferente do PAT (pessoal, um por usuário), a credencial da conta de serviço é **uma só, compartilhada por todo mundo logado**. O que É individual é a **pasta**: cada usuário compartilha e configura a própria pasta raiz do Drive (guardada por usuário em `core/config_app.py`) — ninguém depende do administrador para trocar de pasta, e ninguém enxerga a pasta configurada por outra pessoa.
  - Permite navegar por subpastas dentro da pasta raiz configurada, com um botão de atualizar lista (a pasta pode mudar por fora do app a qualquer momento).
  - Enquanto a credencial da conta de serviço não estiver configurada pelo administrador, esta opção mostra um aviso e fica indisponível — os outros dois caminhos continuam funcionando normalmente.

### Mapeamento de colunas

Como a estrutura do arquivo pode variar, o app tenta identificar sozinho qual coluna representa cada campo canônico (Projeto, Status, Data Planejada, Data de Execução, Data de Criação, Tipo de Teste, Responsável/Executor, **Criado por** — reserva do Responsável, ver abaixo —, Caso de Teste/ID, Severidade/Prioridade, Coluna do Board, **Sprint** — a partir de "Iteration Path", ver o guia de queries — e, só em dados vindos do Azure DevOps por PAT, Prioridade dentro do Board) por correspondência de palavras-chave, com suporte a termos em português e inglês (exports do Azure DevOps costumam vir em inglês mesmo em organizações que operam em português).

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
- **Backlog Aberto** — idade média/mediana dos itens ainda abertos, e quantos estão parados há mais de 90/180/365 dias, mais um gráfico de bolha (Volume × Idade × Risco).
- **Planejamento vs. Testes Efetivados**.
- **Sprints — Itens Concluídos** e **Volume por Responsável ao Longo do Tempo**, quando a coluna Sprint está mapeada.
- **Testes por Projeto** e **Ranking de Bugs por Projeto**.
- **Distribuição por Tipo de Teste**, com exclusão configurável de tipos "contêiner" (Test Plan, Test Suite) que não representam um item de teste individual.
- **Taxa de Sucesso por Projeto**.
- **Tendência ao Longo do Tempo** (volume semanal, opcionalmente por Status).
- **Bugs Abertos vs. Solucionados ao longo do tempo** — acumulado semanal, com opção de marcar quais colunas do board estão "fora do controle da QA" (aguardando validação externa), para não penalizar o time por uma espera que não é dele.
- **Distribuição por Severidade/Prioridade**.
- **Distribuição por Coluna do Board (Kanban)** e **Area Path × Coluna do Board** — usando a ordem real do fluxo (Backlog → ... → Finalizado) e excluindo por padrão os itens sem coluna atribuída ("Não atribuído(a)"), com um detalhamento à parte de quem são esses itens, por tipo.
- **Prioridade Dentro do Board** e **Severidade Calculada** — só disponíveis com dados vindos da busca automática por PAT (ver [Importação de dados](#importação-de-dados)).
- **Volume de Testes por Responsável** — quem fez quanto, com opção de abrir por Projeto (barra empilhada).
- **Volume por Responsável ao Longo do Tempo** — ritmo semanal de cada pessoa (não diário, para não confundir variação real de ritmo com o padrão de dia da semana), limitado às 8 pessoas de maior volume para manter o gráfico legível.
- **Carga de Risco por Responsável** — mapa de calor Responsável × Severidade, para identificar quem segura os itens mais críticos, não só quem tem mais itens.
- **Tabela de dados detalhados** (filtrados) com exportação para CSV.

Praticamente todo gráfico permite escolher o tipo de visualização (Barras, Barras Horizontais, Pizza, Rosca, Linha, Área, Treemap, Pareto, Funil, Mapa de Calor, Radar preenchido — conforme fizer sentido para os dados daquele indicador). A paleta de cores foi desenhada especificamente para que categorias vizinhas num mesmo gráfico nunca fiquem com tons parecidos, mesmo em gráficos com poucas categorias.

### Construtor de gráfico personalizado

Para perguntas que não têm um gráfico fixo pronto: escolha livremente a coluna do eixo X, uma coluna opcional para agrupar/colorir, a métrica (contagem de registros ou soma de uma coluna numérica) e o tipo de gráfico — usando qualquer campo mapeado, personalizado ou bruto do arquivo importado.

### Relatório completo em PDF

Ao final do dashboard, o botão **"Gerar PDF do relatório"** monta um PDF com os KPIs e todos os gráficos visíveis na tela naquele momento — respeitando os mesmos filtros (Período/Projeto/Tipos de Teste/Status) e o mesmo tipo de gráfico escolhido em cada seção, inclusive o gráfico personalizado, se algum já tiver sido gerado. Conteúdo dentro de um expansor recolhido (ex.: a tabela de dados detalhados) não entra no PDF — só o que já está visível por padrão.

Detalhes técnicos relevantes:

- Cada gráfico Plotly é rasterizado como imagem PNG via [`kaleido`](https://github.com/plotly/Kaleido) (versão `>=1.0`; ver comentário em `requirements.txt` sobre por que não pode ser a versão `0.2.1`) e o PDF em si é montado com [`reportlab`](https://www.reportlab.com/opensource/) (`core/pdf_report.py`).
- O `kaleido>=1.0` não vem com um navegador embutido: procura um Chrome/Chromium/Edge/Brave já instalado no sistema, e só baixa um "Chrome for Testing" próprio se não achar nenhum. No Streamlit Community Cloud, isso depende do pacote `chromium` do `packages.txt` (ver [Deploy](#deploy)) — sem ele, o navegador baixado sozinho não consegue nem abrir, por faltar bibliotecas do sistema no container.
- Se a geração falhar (ex.: sem navegador disponível e sem acesso à internet para baixar um), o app mostra uma mensagem de erro amigável em vez de travar — o resto do dashboard continua funcionando normalmente.

### Painel administrativo

Visível só para o usuário `admin` (menu lateral → "⚙️ Administração"). Dois blocos de configuração de topo, seguidos de quatro abas:

- **Diagnóstico da conexão com o banco de dados (Turso)** — testa, sob demanda, se o app consegue falar com o banco onde ficam solicitações, logs e configurações.
- **Código de acesso ao conteúdo administrativo de "Sobre o App"** — define (ou desativa) um código que, repassado por fora do app a quem o administrador escolher, libera a visão do conteúdo administrativo dentro de "Sobre o App" para pessoas que não são o admin (ver [Sobre o App e Guia do Usuário](#sobre-o-app-e-guia-do-usuário)).
- **📋 Solicitações de Acesso** — pendentes/já criadas/revogadas/rejeitadas, com ações de aprovar/rejeitar/revogar/reverter/recuperar/excluir (individual ou em massa), cada uma atrás de um modal de confirmação.
- **🗒️ Logs do Sistema** — três categorias (Ações no Painel, Erros Técnicos, Login/Acessos), com seletor de quantidade, modo "com detalhes" e limpeza de entradas antigas por número de dias.
- **📁 Google Drive** — status da credencial da conta de serviço (configurada nos Secrets/arquivo local, nunca pela tela) e um botão de testar conexão. A pasta em si é configurada por cada usuário, não aqui (ver [Importação de dados](#importação-de-dados)).
- **📘 Guia do Usuário** — dois blocos, cada um com o mesmo padrão (botão manual + indicador ✅/⚠️ de "alteração pendente" por hash do conteúdo, sem regenerar nada sozinho): (1) gera/atualiza o PDF do "Guia Completo do Usuário"; (2) gera/atualiza as duas imagens do "Fluxograma completo do app" (retângulos + setas). Os dois com um clique, sem precisar de terminal — ver próxima seção.

### Sobre o App e Guia do Usuário

Página **"ℹ️ Sobre o App"**, visível para **qualquer pessoa logada** (não só o admin) — objetivo declarado: ajudar qualquer usuário a entender o app inteiro, inclusive o que existe do lado da Administração, mesmo sem ter acesso a ela.

- Visão geral do fluxo principal e um **fluxograma completo**, em duas versões complementares: (1) cartões em HTML/CSS puro, com descrição de cada passo, sem dependência de Graphviz/Mermaid; e (2) uma **imagem** (retângulos + setas, no estilo tradicional de diagrama de fluxo), gerada com Graphviz e servida já pronta (ver [Mantendo o fluxograma em dia](#mantendo-o-fluxograma-em-dia) logo abaixo sobre como atualizá-la). As duas mostram as mesmas duas trilhas que rodam em paralelo — quem usa o app no dia a dia, e quem administra — e onde uma trava a outra.
- **Segregação de conteúdo por papel**: a trilha "quem administra" do fluxograma (nas duas versões, cartões e imagem) e a seção "Administração" ficam resumidas/escondidas por padrão para quem não é o admin. Quem administra pode liberar um código de acesso (ver [Painel administrativo](#painel-administrativo)) para desbloquear esse conteúdo, só na sessão de quem digitar o código certo — não é uma segunda camada de autenticação real, é um seletor de conteúdo informativo.
- Cada imagem também tem um botão **"⬇️ Baixar este fluxograma (imagem)"**, logo abaixo dela, na própria tela.
- **Guia Completo do Usuário**: o mesmo conteúdo de `GUIA_CONVIDADO.md`/`GUIA_ADMIN.md`, incluindo como gerar um PAT do Azure DevOps e quais colunas configurar na query, disponível na própria tela e como **PDF para baixar** (gerado por `core/gerador_guia_pdf.py`, ver [Painel administrativo](#painel-administrativo)). De propósito, sem nenhuma menção ao nome do produto/marca dentro desse PDF — como ele pode ser baixado e repassado livremente por qualquer usuário, o conteúdo evita depender de estar sempre associado a um nome específico.
- Catálogo dos gráficos disponíveis, agrupados por tema.

#### Mantendo o fluxograma em dia

Diferente dos cartões de texto (que são código Python puro e aparecem sempre atualizados sozinhos), a **imagem** do fluxograma é gerada à parte e servida já pronta — então, sempre que um fluxo do app mudar de verdade (etapa nova, tela removida, caminho de importação novo, responsabilidade que passou a ser de outra trilha etc.), a imagem só reflete isso depois de ser regenerada. Dois jeitos de fazer isso, ambos produzindo o mesmo resultado (mesma função, `core/gerador_fluxograma.py`):

**Caminho recomendado — pelo próprio app, sem terminal:** Administração → aba "📘 Guia do Usuário" → seção "🗺️ Fluxograma completo do app (imagem)" → botão **"🔄 Gerar/Atualizar fluxograma agora"**. Grava as duas imagens (completa e trancada) direto no banco de dados (Turso) — já valendo pra todo mundo em "Sobre o App", na hora, sem precisar de redeploy. Um indicador (✅/⚠️) avisa quando o desenho do fluxo no código mudou desde a última geração, comparando um hash do conteúdo — mesmo padrão já usado pelo PDF do Guia do Usuário, ver acima. Esse é o caminho pensado pro dia a dia: exige que o ambiente tenha o Graphviz disponível, e por isso `graphviz` está no `requirements.txt` e no `packages.txt` (ver [Deploy](#deploy)) — já configurado, não precisa instalar nada à parte para usar o botão.

**Caminho alternativo — localmente, por linha de comando:** útil pra quem quer conferir a imagem antes de publicar, ou prefere manter `assets/fluxograma_completo.png`/`assets/fluxograma_publico.png` do repositório sempre iguais ao que está em produção (o botão acima não mexe nesses arquivos — só no banco de dados):

```
pip install graphviz          # binding Python (já é dependência do projeto)
# e o binário do sistema (só na sua máquina, nunca precisa em produção):
#   Ubuntu/Debian: sudo apt install graphviz
#   macOS:         brew install graphviz
#   Windows:       https://graphviz.org/download/
python scripts/gerar_fluxograma_diagrama.py
```

Isso sobrescreve as duas imagens em `assets/`. Depois de editar o desenho do fluxo (as caixas e setas de cada trilha ficam em `_montar_trilha_usuario`, `_montar_trilha_admin_completa` e `_montar_trilha_admin_trancada`, dentro de `core/gerador_fluxograma.py`), confira visualmente e faça commit + push das duas imagens.

Se preferir não mexer em nada disso manualmente, também dá pra pedir para a IA (Claude) fazer esse passo a passo — só apontar o que mudou no fluxo do app.

## Estrutura do projeto

```
app.py                       # ponto de entrada / roteamento de páginas
auth/
  auth_manager.py            # autenticação (login, sessão, logout)
  users.yaml                 # fallback local de credenciais - NÃO commitado (ver .gitignore)
core/
  analytics.py                # regras de negócio: cálculo de todos os indicadores/gráficos
  azure_devops_client.py      # cliente da API REST do Azure DevOps
  column_mapper.py            # detecção automática de colunas + normalização de valores
  config_app.py                # configuração genérica (Turso, chave/valor): pasta do Drive por
                                # usuário, PDF do guia + hash, fluxograma (imagem) + hash,
                                # código de acesso ao conteúdo admin
  data_loader.py               # leitura/parse de CSV/TXT (encoding, delimitador, limpeza)
  fuso_horario.py              # conversão de datas/horas para o fuso de Brasília
  gerador_fluxograma.py        # monta (em memória, Graphviz) as duas imagens do fluxograma completo
  gerador_guia_pdf.py          # monta (em memória) o PDF do Guia Completo do Usuário
  google_drive_client.py       # cliente da API do Google Drive (conta de serviço)
  logs_sistema.py              # logs de auditoria/erros/acessos (tabela no Turso)
  pdf_report.py                 # geração do relatório completo em PDF (kaleido + reportlab)
  solicitacoes_conta.py        # CRUD das solicitações de acesso (tabela no Turso)
  turso_client.py              # cliente HTTP minimalista para o banco Turso
ui/
  components.py                # componentes reutilizáveis (cabeçalho, overlay de loading, botão anti-clique-duplo...)
  theme.py                     # cores, paletas e CSS global
  pages/
    login_page.py
    upload_page.py
    dashboard_page.py
    admin_page.py
    sobre_page.py               # página "Sobre o App" + Guia do Usuário (ver README, seção própria)
utils/
  session.py                    # inicialização/limpeza centralizada do session_state
assets/                        # logotipos, imagens (inclusive as duas do fluxograma) e o PDF padrão do Guia do Usuário
  fluxograma_completo.png                # fluxograma em imagem, com as duas trilhas (ver scripts/gerar_fluxograma_diagrama.py)
  fluxograma_publico.png                 # mesma imagem, sem a trilha administrativa (para quem não desbloqueou)
scripts/
  gerar_hash_senha.py                    # gera o hash bcrypt de uma senha nova
  gerar_guia_usuario_pdf.py              # gera o PDF do Guia do Usuário localmente (ver core/gerador_guia_pdf.py)
  gerar_fluxograma_diagrama.py           # gera as duas imagens do fluxograma (Graphviz) - ver "Mantendo o fluxograma em dia"
  migrar_credenciais_para_secrets.py     # converte auth/users.yaml existente no bloco TOML dos Secrets
gerar_roi_pdf.py              # utilitário avulso de geração de PDF (ver o próprio arquivo)
Dockerfile / docker-entrypoint.sh / .dockerignore   # hospedagem alternativa via Docker (ver FALLBACK_DEPLOY.md)
.gitignore                    # exclui auth/users.yaml, .streamlit/secrets.toml e core/google_drive_credentials.json do controle de versão
packages.txt                  # pacotes de sistema (apt) exigidos no Streamlit Community Cloud
requirements.txt
README.md                     # este arquivo (documentação técnica de arquitetura)
DOCUMENTACAO_TECNICA.md       # documentação técnica detalhada: cada linguagem/ferramenta/biblioteca, para que serve e onde é usada
GUIA_ADMIN.md                 # passo a passo de uso para o administrador
GUIA_CONVIDADO.md             # passo a passo de uso para o usuário comum
Guia - Como Montar a Query no Azure DevOps.md   # como configurar a query para todos os gráficos funcionarem
Configurar Google Drive.md    # passo a passo (administrador) para ativar a busca no Google Drive
FALLBACK_DEPLOY.md            # hospedagem alternativa (Docker) caso o Streamlit Community Cloud fique indisponível
```

## Stack técnica

| Camada | Tecnologia |
| --- | --- |
| Interface / servidor web | [Streamlit](https://streamlit.io/) |
| Autenticação | streamlit-authenticator + bcrypt |
| Manipulação de dados | pandas |
| Gráficos | Plotly Express / Plotly Graph Objects |
| Relatório do dashboard em PDF | kaleido (rasterização dos gráficos) + reportlab (montagem do PDF) |
| Guia do Usuário em PDF | reportlab (mesma biblioteca, uso independente - ver `core/gerador_guia_pdf.py`) |
| Fluxograma completo (imagem) | Graphviz (binding Python `graphviz` + binário `dot` do sistema - ver `core/gerador_fluxograma.py`) |
| Detecção de encoding | chardet |
| Configuração de usuários (fallback local) | PyYAML |
| Integração com Azure DevOps | requests (API REST, sem SDK) |
| Integração com Google Drive | google-api-python-client + google-auth (conta de serviço) |
| Banco de dados (solicitações, logs, configuração) | Turso (SQLite via HTTP), acessado com `requests` puro |
| Fuso horário | zoneinfo (biblioteca padrão do Python) |
| Hospedagem principal | Streamlit Community Cloud |
| Hospedagem alternativa (fallback) | Docker, em Hugging Face Spaces ou Render (ver `FALLBACK_DEPLOY.md`) |

Ver `requirements.txt` para as versões exigidas de cada dependência. **`streamlit` e `starlette` são travados numa versão exata** (não `>=`) — ver o comentário no topo do arquivo: uma combinação incompatível entre essas duas bibliotecas já derrubou a aplicação inteira em produção (erro `TypeError: GZipResponder.__init__() missing 1 required keyword-only argument: 'thread_minimum_size'`), então não altere essas duas linhas sem testar a combinação antes.

Para uma explicação detalhada — o que cada linguagem/ferramenta/biblioteca faz, por que ela foi escolhida e exatamente onde/quando/como ela é usada dentro do app — veja **[DOCUMENTACAO_TECNICA.md](DOCUMENTACAO_TECNICA.md)**.

## Como rodar localmente

Passo a passo pensado para quem nunca rodou este projeto antes, mesmo sem muita familiaridade com linha de comando.

**Pré-requisitos** (instale antes de começar, se ainda não tiver):

1. **Git** — para baixar (clonar) o código. [git-scm.com/downloads](https://git-scm.com/downloads).
2. **Python 3.11 ou mais recente** — na instalação do Windows, marque a opção **"Add Python to PATH"**. [python.org/downloads](https://python.org/downloads).

Depois de instalar os dois, confirme no terminal (PowerShell, no Windows):

```powershell
git --version
python --version
```

Se algum comando der erro de "não reconhecido", reinstale marcando a opção de adicionar ao PATH (Python) ou reabra o terminal depois de instalar.

**Passo a passo**:

```powershell
# 1. Baixar o código (troque pela URL real do repositório)
git clone https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git
cd SEU-REPOSITORIO

# 2. Criar e ativar um ambiente virtual (isola as dependências deste
#    projeto do resto do seu computador - recomendado, não obrigatório)
python -m venv venv
venv\Scripts\activate
# no Linux/macOS, o comando de ativar é: source venv/bin/activate

# 3. Instalar as dependências do projeto
pip install -r requirements.txt

# 4. Rodar a aplicação
python -m streamlit run app.py
```

O terminal mostra uma URL (normalmente `http://localhost:8501`) — abra no navegador. Se o navegador não abrir sozinho, copie e cole a URL manualmente.

**Sem nenhuma configuração extra** (Secrets/`.streamlit/secrets.toml`), o app já roda localmente usando os valores de fallback definidos em `auth/users.yaml` para login. Três coisas dependem de configuração adicional para funcionar (o resto do app funciona normalmente sem elas — ver [Configuração (secrets)](#configuração-secrets)):

- **Busca automática no Azure DevOps** — não depende de nenhum secret do projeto; cada usuário cola o próprio PAT na tela.
- **Busca automática no Google Drive** — depende da credencial da conta de serviço (`[google_drive]` nos Secrets, ou `core/google_drive_credentials.json` local) — ver **[Configurar Google Drive.md](Configurar%20Google%20Drive.md)**.
- **Solicitação de acesso, Painel Administrativo, Guia do Usuário em PDF gerado pelo app** — dependem da seção `[turso]` (banco de dados).

O relatório em PDF do dashboard também funciona localmente sem nenhuma configuração extra — o Windows costuma já ter algum navegador instalado (Edge, Chrome), que o `kaleido` encontra sozinho; se não encontrar, baixa um "Chrome for Testing" próprio na primeira geração (só precisa de acesso à internet nesse momento).

## Configuração (secrets)

Em produção (Streamlit Community Cloud), configurar em **Settings → Secrets**; localmente, em `.streamlit/secrets.toml` (nunca commitado no Git — ver `.gitignore`):

```toml
[auth.cookie]
name = "app_cookie"
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

# Opcional - só necessário para a busca automática no Google Drive (ver
# "Configurar Google Drive.md" para o passo a passo completo de como gerar
# estes valores).
[google_drive]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "..."
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```

- **`[auth]`** contém a base de usuários inteira (credenciais + config do cookie + e-mails pré-autorizados) — é a fonte de credenciais preferida (ver [Gestão de usuários](#gestão-de-usuários)). O `auth/users.yaml` local continua existindo como fallback só para rodar sem configurar Secrets (ex.: primeira vez clonando o projeto) — nesse caso funciona exatamente como antes, só que **sem essa fonte nunca ser commitada**. Se quiser manter só a `cookie_key` nos Secrets (formato antigo/mínimo) e o resto no arquivo local, isso também continua funcionando — `auth/auth_manager.py` aceita as duas formas.
- `turso.*` é exigido para o fluxo de solicitação de acesso, o Painel Administrativo, e para o Guia do Usuário em PDF ser gerado/persistido pelo próprio app. Sem essa configuração, o restante do app funciona normalmente — só esses fluxos específicos ficam indisponíveis, com uma mensagem de erro clara em vez de travar a aplicação.
- `[google_drive]` é exigido só para a opção "Buscar arquivo no Google Drive" na importação — ver **[Configurar Google Drive.md](Configurar%20Google%20Drive.md)**. Localmente, pode ficar num arquivo `core/google_drive_credentials.json` em vez de nos Secrets (nunca commitado — ver `.gitignore`).
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

Hospedado no **Streamlit Community Cloud**, apontando para este repositório. Qualquer alteração enviada ao branch de produção é publicada automaticamente (ou após clicar em "Reboot app" no painel do Streamlit Cloud, quando a alteração exige reinstalar dependências). Os Secrets de produção (base de usuários completa em `[auth]`, credenciais do Turso, credencial do Google Drive) são configurados direto no painel do Streamlit Community Cloud — nunca no código versionado.

Dois arquivos controlam o ambiente de execução no Streamlit Community Cloud, além do código:

- **`requirements.txt`** — dependências Python. `streamlit` e `starlette` estão travados numa versão exata específica de propósito (ver [Stack técnica](#stack-técnica)) — evite trocar por `>=` sem testar a combinação primeiro.
- **`packages.txt`** — dependências de sistema (`apt-get install`), duas linhas: `chromium` (necessário para o relatório em PDF funcionar em produção: garante as bibliotecas de sistema — `libnss3`, `libgtk-3-0`, `libasound2` etc. — que qualquer Chrome/Chromium precisa para conseguir abrir dentro do container do Streamlit Cloud; sem isso, o navegador que o `kaleido` baixa sozinho até é baixado com sucesso, mas falha ao iniciar, "The browser seemed to close immediately after starting") e `graphviz` (o binário `dot`, necessário para o botão "🔄 Gerar/Atualizar fluxograma agora" em Administração — ver [Mantendo o fluxograma em dia](#mantendo-o-fluxograma-em-dia)). Qualquer alteração neste arquivo exige um rebuild completo do ambiente (reboot manual do app pelo painel do Streamlit Cloud costuma ser necessário).

**Hospedagem alternativa**: se o Streamlit Community Cloud ficar indisponível, este mesmo app pode rodar via Docker (mesmo código, sem alterações) em serviços como Hugging Face Spaces ou Render — ver **[FALLBACK_DEPLOY.md](FALLBACK_DEPLOY.md)** para o passo a passo completo.

Se o repositório for **público**, isso é ainda mais importante: qualquer arquivo commitado é visível para qualquer pessoa, inclusive em commits antigos. Este projeto foi ajustado para não depender de nenhum arquivo sensível versionado (ver seções acima) — mas vale conferir a visibilidade do repositório em GitHub → Settings → Danger Zone, e considerar torná-lo privado se ele guardar qualquer histórico de commit anterior a esse ajuste.

## Segurança e privacidade

- Senhas de usuários são armazenadas com hash (bcrypt), nunca em texto puro, e vivem nos Secrets do Streamlit — não no repositório Git (ver [Gestão de usuários](#gestão-de-usuários)).
- O PAT do Azure DevOps de cada usuário nunca é salvo em disco, banco de dados ou Secrets — vive só na memória da sessão do navegador enquanto o usuário está logado.
- A credencial da conta de serviço do Google Drive fica só nos Secrets do Streamlit (produção) ou num arquivo local ignorado pelo Git — nunca é colada ou exibida pela tela do app; é uma credencial única, compartilhada por todo mundo logado, mas cada usuário só enxerga/configura a própria pasta.
- O "código de acesso ao conteúdo administrativo de Sobre o App" (ver [Sobre o App e Guia do Usuário](#sobre-o-app-e-guia-do-usuário)) **não é** uma segunda camada de autenticação de verdade — é só um seletor de conteúdo informativo, guardado como configuração comum no mesmo banco de dados. Não use esse código para proteger nada que exija segurança real.
- O PDF do Guia do Usuário, disponível para qualquer pessoa logada baixar e repassar, é escrito de propósito sem nenhum dado específico deste ambiente (nenhuma credencial, nenhum e-mail de conta de serviço real, nenhuma URL de organização) — onde um valor real ajudaria, o texto orienta a pessoa a conferir a própria tela do app em vez de embutir um valor fixo.
- As solicitações de acesso não disparam e-mail nem qualquer notificação externa — ficam visíveis só para quem acessa o Painel Administrativo dentro do próprio app.
- A sessão de login é encerrada automaticamente ao fechar de verdade a aba/janela do navegador (não sobrevive além de um F5 dentro do prazo configurado).
- Se o repositório já foi público em algum momento com `auth/users.yaml` commitado, trate os hashes de senha expostos naquele período como potencialmente comprometidos (mesmo com bcrypt, um hash exposto pode ser atacado offline) — o ideal é tornar o repositório privado e, quando possível, trocar as senhas dos usuários que estavam naquele arquivo.

## Limitações conhecidas

- A criação/remoção de contas continua manual (edição dos Secrets, com `scripts/gerar_hash_senha.py` para gerar o hash); o app organiza e documenta as solicitações, mas não provisiona usuários sozinho.
- O painel administrativo hoje reconhece um único usuário (`admin`) como administrador de verdade — dar esse acesso a mais pessoas exige alterar `ui/pages/admin_page.py`. O "código de acesso ao conteúdo administrativo de Sobre o App" é uma forma de compartilhar só a *informação* sobre os fluxos de admin com outras pessoas, sem dar a elas acesso real ao Painel Administrativo.
- Indicadores que dependem de um campo específico (datas, Severidade, Coluna do Board, Sprint etc.) só aparecem quando esse campo está mapeado nos dados importados — não há como calculá-los sem a informação correspondente no arquivo/consulta de origem.
- A geração do relatório em PDF do dashboard depende de conseguir abrir um navegador Chrome/Chromium no ambiente onde o app está rodando (local ou Streamlit Community Cloud) — em ambientes de execução muito restritos/minimalistas sem o `packages.txt` correspondente, essa funcionalidade específica pode falhar (com uma mensagem de erro clara), mesmo com o resto do dashboard funcionando normalmente.
- O Google Drive permite hoje uma pasta raiz por usuário (não múltiplas pastas raiz por pessoa) — nada impede, porém, que essa pasta raiz seja uma pasta "guarda-chuva" com subpastas por projeto/time dentro dela, já que a navegação do app permite entrar em subpastas livremente.
