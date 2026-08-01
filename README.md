# Refuturiza QA — Painel de Indicadores de Qualidade

Aplicação web (Streamlit) que transforma work items do Azure DevOps — importados manualmente em CSV/TXT ou buscados direto pela API — em um painel de indicadores e gráficos interativos sobre o trabalho de QA: volume de testes, bugs em aberto, backlog envelhecido, fluxo no board Kanban e ritmo de trabalho por responsável e por projeto.

Acesso multiusuário com login, controle de quem pode ver o quê e um fluxo de solicitação de acesso auto-atendido (sem precisar de e-mail ou processo externo).

## Índice

- [Visão geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
  - [Login e controle de acesso](#login-e-controle-de-acesso)
  - [Importação de dados](#importação-de-dados)
  - [Mapeamento de colunas](#mapeamento-de-colunas)
  - [Filtros do dashboard](#filtros-do-dashboard)
  - [Indicadores e gráficos](#indicadores-e-gráficos)
  - [Construtor de gráfico personalizado](#construtor-de-gráfico-personalizado)
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
3. **Confirmar o mapeamento de colunas** e navegar pelo dashboard, com filtros e mais de quinze indicadores/gráficos prontos.

## Funcionalidades

### Login e controle de acesso

- Autenticação multiusuário via [`streamlit-authenticator`](https://github.com/mkhorasani/Streamlit-Authenticator), com sessão persistida em cookie assinado — um F5 na página não exige login de novo, dentro do prazo configurado.
- A sessão é encerrada automaticamente quando a aba/janela do navegador é realmente fechada (não só recarregada), mesmo em navegadores que mantêm o processo rodando em segundo plano.
- Quem não tem conta pode clicar em **"Solicitar acesso"** e preencher nome, e-mail e motivo — a solicitação fica registrada num banco de dados (Turso) e só é visível para o administrador dentro do próprio app. Não há envio de e-mail nem integração externa.
- **Painel Administrativo** (visível só para o usuário `admin`): lista as solicitações por status (Pendentes, Já criadas, Revogadas, Rejeitadas), com ações de aprovar/rejeitar/revogar/recuperar/excluir, exclusão em massa e um diagnóstico de conexão com o banco de dados.
- A criação de conta em si continua manual, por decisão de projeto: o administrador gera o hash da senha (`scripts/gerar_hash_senha.py`) e adiciona o usuário em `auth/users.yaml`, depois marca a solicitação como "criada" no painel — o painel documenta e organiza os pedidos, mas não cria contas sozinho.

### Importação de dados

Duas formas de trazer os dados para o app, ambas alimentando o mesmo pipeline de indicadores:

- **Upload manual** de um arquivo `.csv`/`.txt` (até 20MB), com detecção automática de encoding e delimitador (vírgula, ponto e vírgula, tabulação ou pipe), remoção de linhas/colunas vazias e mensagens de erro amigáveis quando o arquivo não pode ser interpretado.
- **Busca automática no Azure DevOps**, direto pela API REST, sem precisar exportar/importar CSV manualmente:
  - Cada usuário informa o **próprio Personal Access Token (PAT)** — nunca salvo em disco/Secrets, fica só na memória da sessão do navegador e some ao sair. Isso dá rastreabilidade real: o log de acesso do Azure DevOps mostra o usuário dono do PAT, não uma conta de serviço compartilhada.
  - Seleção em cascata: organização → projeto → um ou mais **Area Paths** (times/módulos, opcional, com multiseleção) → query já salva no Azure DevOps.
  - Um item de teste sem coluna de board própria (comum em Test Cases, que vivem dentro de Test Plans/Suites) herda a coluna do item pai vinculado, quando existir — para não perder a visão de fluxo desses itens no gráfico de board.
  - Mensagens de erro específicas para PAT inválido/expirado, falta de permissão, organização/projeto/query não encontrados, e bloqueios de rede/Conditional Access no Azure AD da organização.

### Mapeamento de colunas

Como a estrutura do arquivo pode variar, o app tenta identificar sozinho qual coluna representa cada campo canônico (Projeto/Area Path, Status, Data Planejada, Data de Execução, Data de Criação, Tipo de Teste, Responsável/Executor, Caso de Teste/ID, Severidade/Prioridade, Coluna do Board) por correspondência de palavras-chave, com suporte a termos em português e inglês (exports do Azure DevOps costumam vir em inglês mesmo em organizações que operam em português).

O mapeamento sugerido é sempre exibido para confirmação/ajuste manual antes de qualquer gráfico ser gerado — nunca é aplicado silenciosamente. Também é possível anexar **campos personalizados** (qualquer outra coluna do arquivo, com um rótulo livre), disponíveis no filtro e no construtor de gráfico personalizado.

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
- **Distribuição por Coluna do Board (Kanban)** e **Area Path × Coluna do Board** — usando a ordem real do fluxo (Backlog → ... → Finalizado) e excluindo por padrão os itens sem coluna atribuída ("Não atribuído(a)"), com um detalhamento à parte de quem são esses itens, por tipo.
- **Volume de Testes por Responsável** — quem fez quanto, com opção de abrir por Projeto (barra empilhada).
- **Volume por Responsável ao Longo do Tempo** — ritmo semanal de cada pessoa (não diário, para não confundir variação real de ritmo com o padrão de dia da semana), limitado às 8 pessoas de maior volume para manter o gráfico legível.
- **Distribuição por Severidade/Prioridade**.
- **Tabela de dados detalhados** (filtrados) com exportação para CSV.

Praticamente todo gráfico permite escolher o tipo de visualização (Barras, Barras Horizontais, Pizza, Rosca, Linha, Área, Treemap, Pareto, Radar preenchido — conforme fizer sentido para os dados daquele indicador). A paleta de cores foi desenhada especificamente para que categorias vizinhas num mesmo gráfico nunca fiquem com tons parecidos, mesmo em gráficos com poucas categorias.

### Construtor de gráfico personalizado

Para perguntas que não têm um gráfico fixo pronto: escolha livremente a coluna do eixo X, uma coluna opcional para agrupar/colorir, a métrica (contagem de registros ou soma de uma coluna numérica) e o tipo de gráfico — usando qualquer campo mapeado, personalizado ou bruto do arquivo importado.

### Painel administrativo

Descrito acima, em [Login e controle de acesso](#login-e-controle-de-acesso).

## Estrutura do projeto

```
app.py                       # ponto de entrada / roteamento de páginas
auth/
  auth_manager.py            # autenticação (login, sessão, logout)
  users.yaml                 # credenciais dos usuários (não versionar em texto puro sem cuidado)
core/
  analytics.py               # regras de negócio: cálculo de todos os indicadores/gráficos
  azure_devops_client.py     # cliente da API REST do Azure DevOps
  column_mapper.py           # detecção automática de colunas + normalização de valores
  data_loader.py             # leitura/parse de CSV/TXT (encoding, delimitador, limpeza)
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
  gerar_hash_senha.py        # utilitário de linha de comando para gerar hash de senha (bcrypt)
requirements.txt
```

## Stack técnica

| Camada | Tecnologia |
| --- | --- |
| Interface / servidor web | [Streamlit](https://streamlit.io/) |
| Autenticação | streamlit-authenticator + bcrypt |
| Manipulação de dados | pandas |
| Gráficos | Plotly Express / Plotly Graph Objects |
| Detecção de encoding | chardet |
| Configuração de usuários | PyYAML |
| Integração com Azure DevOps | requests (API REST, sem SDK) |
| Banco de dados (solicitações de acesso) | Turso (SQLite via HTTP), acessado com `requests` puro |
| Hospedagem | Streamlit Community Cloud |

Ver `requirements.txt` para as versões mínimas exigidas de cada dependência.

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

## Configuração (secrets)

Em produção (Streamlit Community Cloud), configurar em **Settings → Secrets**; localmente, em `.streamlit/secrets.toml` (nunca commitado no Git):

```toml
[auth]
cookie_key = "uma-chave-secreta-longa-e-aleatoria"

[turso]
database_url = "https://SEU-BANCO-SEUUSUARIO.turso.io"
auth_token = "SEU_TOKEN_DE_AUTENTICACAO_TURSO"
```

- `auth.cookie_key` assina o cookie de sessão de login — é o segredo mais sensível do app; sem ele configurado em produção, o app usa o valor de `auth/users.yaml` como fallback (aceitável só em desenvolvimento local).
- `turso.*` é exigido apenas para o fluxo de solicitação de acesso (botão "Solicitar acesso" na tela de login e o Painel Administrativo). Sem essa configuração, o restante do app funciona normalmente — só esse fluxo específico fica indisponível, com uma mensagem de erro clara em vez de travar a aplicação.
- O Personal Access Token do Azure DevOps **não é** um secret da aplicação — cada usuário cola o próprio PAT dentro do app, na tela de importação, e ele nunca é persistido.

## Gestão de usuários

A criação de contas é manual, por decisão de projeto (sem processo automatizado de cadastro):

1. A pessoa solicita acesso pela tela de login (nome, e-mail, motivo).
2. O administrador revisa a solicitação no Painel Administrativo.
3. Aprovando, o administrador gera o hash da senha com `scripts/gerar_hash_senha.py` e adiciona o usuário em `auth/users.yaml` (formato padrão do `streamlit-authenticator`: credenciais, nome do cookie, chave, validade em dias, e-mails pré-autorizados).
4. O administrador marca a solicitação como "criada" no painel, para sair da lista de pendentes.

Revogar acesso segue o caminho inverso: remover/desabilitar o usuário em `auth/users.yaml` e marcar a solicitação como "revogada" no painel (o painel registra o histórico; a revogação de acesso real sempre acontece no arquivo de credenciais).

## Deploy

Hospedado no **Streamlit Community Cloud**, apontando para este repositório. Qualquer alteração enviada ao branch de produção é publicada automaticamente. Os Secrets de produção (`cookie_key`, credenciais do Turso) são configurados direto no painel do Streamlit Community Cloud — nunca no código versionado.

## Segurança e privacidade

- Senhas de usuários são armazenadas com hash (bcrypt) em `auth/users.yaml`, nunca em texto puro.
- O PAT do Azure DevOps de cada usuário nunca é salvo em disco, banco de dados ou Secrets — vive só na memória da sessão do navegador enquanto o usuário está logado.
- As solicitações de acesso não disparam e-mail nem qualquer notificação externa — ficam visíveis só para quem acessa o Painel Administrativo dentro do próprio app.
- A sessão de login é encerrada automaticamente ao fechar de verdade a aba/janela do navegador (não sobrevive além de um F5 dentro do prazo configurado).

## Limitações conhecidas

- A criação/remoção de contas continua manual (edição de `auth/users.yaml`); o app organiza e documenta as solicitações, mas não provisiona usuários sozinho.
- O painel administrativo hoje reconhece um único usuário (`admin`) como administrador — dar esse acesso a mais pessoas exige alterar `ui/pages/admin_page.py`.
- Indicadores que dependem de um campo específico (datas, Severidade, Coluna do Board etc.) só aparecem quando esse campo está mapeado nos dados importados — não há como calculá-los sem a informação correspondente no arquivo/consulta de origem.
