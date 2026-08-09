# Documentação Técnica — Arquitetura, Linguagens e Ferramentas

Este documento explica, em detalhe, **tudo que é usado para montar e fazer funcionar este aplicativo**: cada linguagem, biblioteca, serviço externo e metodologia, para que serve, e como/quando/onde ela entra em ação dentro do código. É complementar ao [README.md](README.md) (que foca em funcionalidades e como rodar o projeto) — aqui o foco é a arquitetura por trás de cada peça.

**Nota sobre segurança**: este documento pode ser lido por qualquer pessoa com acesso ao repositório, então ele nunca contém credenciais reais, e-mails de conta de serviço reais, URLs de organização/banco de dados reais, ou qualquer outro dado específico deste ambiente. Onde um exemplo concreto ajuda a explicar algo, ele usa valores fictícios/genéricos, no mesmo espírito do restante da documentação deste projeto (ver [Segurança e privacidade](README.md#segurança-e-privacidade) no README). De propósito, este documento também evita usar o nome comercial do produto — refere-se a ele só como "o app"/"o projeto".

## Sumário

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [Linguagem e runtime](#2-linguagem-e-runtime)
3. [Camada de interface: Streamlit](#3-camada-de-interface-streamlit)
4. [Autenticação e sessão](#4-autenticação-e-sessão)
5. [Manipulação de dados: pandas](#5-manipulação-de-dados-pandas)
6. [Visualização: Plotly](#6-visualização-plotly)
7. [Importação de dados — três fontes](#7-importação-de-dados-três-fontes)
8. [Detecção e mapeamento de colunas](#8-detecção-e-mapeamento-de-colunas)
9. [Regras de negócio (indicadores e gráficos)](#9-regras-de-negócio-indicadores-e-gráficos)
10. [Geração de PDF](#10-geração-de-pdf)
11. [Banco de dados: Turso](#11-banco-de-dados-turso)
12. [Fuso horário](#12-fuso-horário)
13. [Hospedagem e deploy](#13-hospedagem-e-deploy)
14. [Segurança — visão consolidada](#14-segurança-visão-consolidada)
15. [Convenções e padrões de código](#15-convenções-e-padrões-de-código)
16. [Mapa de arquivos](#16-mapa-de-arquivos)
17. [Glossário](#17-glossário)

---

## 1. Visão geral da arquitetura

O app é uma aplicação web escrita inteiramente em **Python**, sem front-end separado (sem React/Vue/HTML manual) — a interface inteira é gerada pelo próprio [Streamlit](#3-camada-de-interface-streamlit), um framework que transforma um script Python comum numa página web interativa, redesenhando a tela do zero a cada interação do usuário (um clique, uma digitação, etc.) — esse modelo de execução ("rerun completo do script a cada interação") é a peça mais importante para entender como o restante do código é organizado, especialmente o uso extensivo de `st.session_state` (ver seção 3).

Camadas do projeto, de fora para dentro:

- **`app.py`** — ponto de entrada único. Decide se mostra a tela de login ou o app autenticado, monta o menu lateral, e roteia para a página certa.
- **`ui/`** — camada de apresentação: uma página por tela (`ui/pages/*.py`), mais componentes reutilizáveis (`ui/components.py`) e o tema visual/CSS (`ui/theme.py`). Só esta camada importa `streamlit`.
- **`core/`** — regras de negócio, puras (a maioria dos módulos aqui não sabe que existe uma interface por cima — só recebe dados, processa, devolve resultado ou levanta um erro com mensagem amigável). É a camada testável/reaproveitável.
- **`auth/`** — autenticação e sessão.
- **`utils/`** — utilitários transversais (hoje, só inicialização/limpeza do `st.session_state`).
- **Serviços externos**: um banco de dados (Turso), duas APIs de terceiros (Azure DevOps, Google Drive) — nenhum obrigatório para o app subir; cada ausência de configuração desliga só a funcionalidade correspondente, com uma mensagem clara, sem derrubar o resto.

Não há back-end/API separado: o próprio processo Streamlit atende requisições HTTP do navegador (usa o servidor web embutido do Streamlit, hoje baseado em Starlette/Tornado internamente) e executa a lógica de negócio no mesmo processo, síncrono. Não há fila de tarefas, worker separado, nem cache distribuído — para a escala de uma ferramenta interna de equipe, a simplicidade de um único processo foi a escolha deliberada.

## 2. Linguagem e runtime

**Python 3** (nenhuma versão mínima é imposta explicitamente no código, mas bibliotecas usadas como `zoneinfo` requerem Python 3.9+; recomendado 3.11+). Todo o código — interface, regras de negócio, scripts de linha de comando — é Python; não há nenhuma linha de JavaScript escrita à mão no projeto (o pouco de HTML/CSS que existe é para estilizar componentes do Streamlit, não para lógica de aplicação — ver seção 3).

Gerenciamento de dependências via `pip` + `requirements.txt` (sem Poetry/pipenv) — lista simples de pacotes com versão mínima ou travada, comentada linha a linha explicando o porquê de cada uma (ver `requirements.txt` no repositório, é praticamente um mini-changelog de decisões técnicas).

## 3. Camada de interface: Streamlit

[Streamlit](https://streamlit.io/) é o framework que gera toda a interface web a partir de chamadas Python (`st.markdown(...)`, `st.button(...)`, `st.dataframe(...)` etc.) — sem escrever HTML/JS manualmente para os elementos padrão. Pontos centrais de como ele é usado aqui:

- **Modelo de execução**: a cada interação do usuário (clique, digitação confirmada, seleção), o Streamlit executa o script **inteiro de novo**, do topo. Isso significa que nenhuma variável Python comum "sobrevive" entre interações — só o que está guardado em `st.session_state` (um dicionário persistente entre execuções, por sessão de navegador) continua existindo. `utils/session.py` centraliza toda a inicialização dessas chaves (`CHAVES_PADRAO`) e as funções de limpeza (`resetar_dados_importados`, `resetar_para_nova_analise` etc.), para não espalhar `if "x" not in st.session_state` por todo o código.
- **Roteamento**: não existe roteador de verdade (nem URLs por página) — `app.py` guarda a página atual em `st.session_state["pagina_atual"]` e decide, com um `if/elif`, qual função `render_*_page()` chamar. Trocar de página é só mudar essa chave e forçar um novo rerun (`st.rerun()`).
- **Componentes próprios** (`ui/components.py`): `render_header` (cabeçalho com logo), `loading_overlay` (bloqueia a tela com um spinner enquanto uma operação está em andamento), `action_button` (um `st.button` que se desabilita sozinho depois do primeiro clique, para não disparar duas vezes a mesma ação enquanto a primeira ainda está processando — sempre usado em par com `finish_action`, chamado ao final da operação), `kpi_card`/`render_kpi_row` (cartões numéricos estilizados).
- **HTML/CSS customizado**: para elementos que o Streamlit não oferece prontos (cabeçalho com logo, cartões de KPI, os diagramas de fluxo em "Sobre o App", badges de status), o código usa `st.markdown(..., unsafe_allow_html=True)` com classes CSS próprias, todas centralizadas em `ui/theme.py` (injetadas uma vez, via `injetar_css_global()`, no início de `app.py`). Os fluxogramas da página "Sobre o App" são desenhados assim, de propósito, em vez de usar uma biblioteca de diagramas (Graphviz exigiria o binário `dot` instalado no sistema; Mermaid via JavaScript injetado teria a mesma fragilidade de outros truques de JS já usados no projeto) — HTML/CSS puro roda em qualquer lugar, sem dependência nova, e herda a paleta/fonte do resto do app.
- **Diálogos modais** (`@st.dialog(...)`) — usados para toda confirmação de ação destrutiva ou irreversível (revogar acesso, excluir solicitação, nova análise), sempre com um resumo do que vai acontecer antes de aplicar de verdade.
- **`st.secrets`** — mecanismo nativo do Streamlit para configuração sensível (ver seção 4 e 14): lido em produção do painel do Streamlit Community Cloud, e localmente de `.streamlit/secrets.toml` (nunca commitado).

## 4. Autenticação e sessão

- **[`streamlit-authenticator`](https://github.com/mkhorasani/Streamlit-Authenticator)** cuida do formulário de login, da comparação de senha e da emissão/validação de um cookie de sessão assinado — encapsulado em `auth/auth_manager.py` (classe `AuthManager`). O cookie guarda quem está logado por um número configurável de dias (`expiry_days`), então um F5 não pede login de novo dentro desse prazo.
- **[`bcrypt`](https://pypi.org/project/bcrypt/)** é o algoritmo de hash de senha usado por baixo do `streamlit-authenticator` — senhas nunca são guardadas em texto puro; `scripts/gerar_hash_senha.py` é a ferramenta de linha de comando que gera esse hash na hora de criar uma conta nova.
- **Fonte de credenciais**: a lista de usuários/senhas (hash)/config de cookie vem de `st.secrets["auth"]` em produção; localmente, se os Secrets não estiverem configurados, cai para um arquivo `auth/users.yaml` (lido via **[`PyYAML`](https://pyyaml.org/)**) — esse arquivo nunca deve ser commitado (está no `.gitignore`) por guardar hash de senha.
- **Encerramento de sessão ao fechar a aba**: além do botão "Sair", existe um mecanismo em `auth/auth_manager.py` que detecta o fechamento real do navegador (não um F5) via um pequeno script injetado com `st.components.v1.html(...)` (a única forma de rodar JavaScript de verdade no Streamlit — `st.markdown` com `unsafe_allow_html=True` não executa `<script>`, por sanitização do próprio framework) — o mesmo mecanismo de "rodar JS de verdade" é reaproveitado em `ui/components.py::rolar_para_topo` para rolar a página programaticamente.
- **PAT do Azure DevOps não é autenticação da aplicação** — é uma credencial pessoal de terceiros que cada usuário cola manualmente na tela de importação, guardada só em `st.session_state` (memória do processo, nunca disco/banco) e usada só para chamadas à API do Azure DevOps.

## 5. Manipulação de dados: pandas

**[`pandas`](https://pandas.pydata.org/)** é a estrutura de dados central do app — qualquer arquivo importado (CSV/TXT, resposta da API do Azure DevOps, CSV baixado do Google Drive) é convertido, o quanto antes, para um `pandas.DataFrame`, e todo o resto do pipeline (mapeamento de colunas, cálculo de indicadores, filtros, construção de gráficos, geração de PDF) opera sobre esse `DataFrame` com as ferramentas padrão do pandas (`.groupby`, `.pivot_table`, `.merge`, seleção booleana, etc.). `core/analytics.py` (mais de 1400 linhas) é o módulo com a maior concentração de código pandas do projeto — cada gráfico do dashboard corresponde a uma função ali (ver seção 9).

## 6. Visualização: Plotly

**[Plotly](https://plotly.com/python/)** (`plotly.express` para os casos simples, `plotly.graph_objects` para composições mais finas) gera todos os gráficos interativos do dashboard — zoom, hover com detalhe, exportação de imagem pelo próprio menu do gráfico, tudo isso vem de graça do Plotly, sem código adicional. Cada seção de gráfico do dashboard (`ui/pages/dashboard_page.py`) tem um seletor de "Tipo de gráfico" que decide qual função Plotly chamar (barras, pizza, linha, treemap, funil, mapa de calor, radar, etc.) sobre os mesmos dados já calculados por `core/analytics.py`. A paleta de cores usada nos gráficos é definida uma vez em `ui/theme.py`, desenhada para que categorias vizinhas num mesmo gráfico nunca fiquem com tons parecidos.

## 7. Importação de dados — três fontes

### 7.1 Upload manual (`core/data_loader.py`)

Recebe um arquivo `.csv`/`.txt` (via `st.file_uploader`) e faz, nesta ordem: detecção de **encoding** com **[`chardet`](https://pypi.org/project/chardet/)** (analisa os primeiros 200KB do arquivo e sugere a codificação mais provável, com um fallback para `latin-1` se a decodificação falhar), detecção de **delimitador** com `csv.Sniffer` (biblioteca padrão do Python, com um fallback manual que conta ocorrências de cada delimitador candidato na primeira linha, caso o `Sniffer` não consiga decidir), leitura com `pandas.read_csv` (usando `engine="python"` e `on_bad_lines="skip"`, para tolerar linhas malformadas em vez de travar o processo inteiro), e uma limpeza final (remove linhas/colunas 100% vazias, remove colunas "Unnamed" residuais de delimitadores sobrando no fim da linha, remove espaços extras de células de texto).

### 7.2 Busca automática no Azure DevOps (`core/azure_devops_client.py`)

Cliente HTTP escrito à mão com **[`requests`](https://requests.readthedocs.io/)** puro (sem SDK oficial da Microsoft) contra a **API REST do Azure DevOps**. Autenticação via **PAT (Personal Access Token)**, enviado como Basic Auth (usuário vazio, senha = o token) em todas as chamadas. Fluxo:

1. `obter_identidade_autenticada` — confirma quem é o dono real do token (usado depois para o alerta de "possível anomalia" se o nome não bater com quem está logado no app).
2. `listar_projetos` / `listar_area_paths` / `listar_queries` — alimentam os seletores em cascata da tela de importação.
3. `buscar_work_items_da_query` — dado o ID de uma query salva, primeiro busca a lista de IDs de work items (`_buscar_ids_da_query`), depois busca os campos de cada um **em lotes** (`_buscar_campos_em_lotes` — a API do Azure DevOps tem limite de itens por chamada, então IDs grandes demais são divididos em múltiplas requisições), e monta o `DataFrame` final (`_montar_dataframe`).
4. `_completar_board_column_via_item_pai` — um item sem "Board Column" própria (comum em Test Cases, que vivem dentro de Test Plans/Suites) herda a coluna do item pai vinculado, quando existe, para não perder a visão de fluxo desses itens no gráfico de board.

Diferente das outras duas fontes, esta sempre traz um conjunto **fixo** de campos (`CAMPOS_API_PARA_COLUNA`), incluindo dois campos (Stack Rank/Backlog Priority, usados pelos gráficos "Prioridade Dentro do Board"/"Severidade Calculada") que a interface web do Azure DevOps não permite exportar em nenhuma configuração de query — por isso esses dois gráficos só existem vindo por este caminho.

### 7.3 Busca no Google Drive (`core/google_drive_client.py`)

Usa **[`google-api-python-client`](https://github.com/googleapis/google-api-python-client)** + **[`google-auth`](https://github.com/googleapis/google-auth-library-python)** para falar com a **API do Google Drive**, autenticado por uma **Conta de Serviço** (uma credencial "robô" — arquivo JSON com uma chave privada, sem tela de login interativa; ver `Configurar Google Drive.md` para o passo a passo de criação). A credencial é lida de `st.secrets["google_drive"]` em produção, ou de um arquivo local `core/google_drive_credentials.json` (nunca versionado). Funções principais: `listar_pastas_e_arquivos_csv` (lista o conteúdo de uma pasta, separando subpastas de arquivos `.csv`), `baixar_arquivo_csv` (baixa os bytes de um arquivo específico), `extrair_id_pasta_do_link` (aceita tanto a URL completa quanto só o ID da pasta, colados pelo usuário), `testar_conexao` (usado tanto no diagnóstico do admin quanto na hora de salvar a pasta de cada usuário, para confirmar acesso antes de gravar).

A pasta em si é uma configuração **por usuário**, não da aplicação — guardada no banco de dados (ver seção 11) com uma chave por `nome_usuario`, para que cada pessoa logada configure e enxergue só a própria pasta.

## 8. Detecção e mapeamento de colunas

`core/column_mapper.py` resolve o problema de "a mesma informação pode vir com nomes de coluna diferentes em cada exportação" (`"Status"` vs. `"Situação"` vs. `"State"`, por exemplo). O algoritmo, em `detectar_mapeamento`:

1. Normaliza todo nome de coluna (minúsculas, sem acento — via `unicodedata.normalize("NFKD", ...)`).
2. Para cada campo canônico (Projeto, Status, Sprint, etc.), tenta casar contra uma lista de palavras-chave (`PALAVRAS_CHAVE`, incluindo termos em português e inglês).
3. Palavras com 4+ caracteres casam como **substring** em qualquer lugar do nome da coluna normalizado; palavras mais curtas (ex.: "id") só casam como **token isolado** (usando uma quebra por `re.split(r"[^a-z0-9]+", ...)`), para evitar falso positivo tipo "id" dentro de "validado".
4. Cada campo processado usa uma coluna só uma vez (`colunas_ja_usadas`) — evita duas colunas semânticas diferentes caindo na mesma coluna de origem.
5. Ordem de processamento importa: `prioridade_board` é resolvido antes de `severidade` de propósito, porque a palavra-chave "prioridade" apareceria nos dois, e a coluna mais específica (posição no board) precisa ser reconhecida primeiro.

O resultado nunca é aplicado silenciosamente — sempre passa por uma tela de confirmação onde o usuário pode corrigir qualquer campo manualmente antes de qualquer gráfico ser gerado.

## 9. Regras de negócio (indicadores e gráficos)

`core/analytics.py` é o módulo mais extenso do projeto — cada indicador do dashboard corresponde a uma ou mais funções aqui, todas puras (recebem um `DataFrame` já mapeado e devolvem outro `DataFrame`/estrutura pronta para plotar, sem tocar em `st.session_state` nem em interface). Alguns exemplos do tipo de lógica concentrada aqui: `preparar_dados` (aplica o mapeamento, converte tipos, resolve o fallback "Criado por" quando "Responsável" está vazio), `calcular_backlog_aberto`/`ranking_itens_mais_antigos_abertos` (idade dos itens ainda em aberto), `itens_concluidos_por_sprint` (agrupa por Sprint/Iteration Path em ordem cronológica aproximada), `severidade_calculada_por_posicao`/`ranking_prioridade_board` (só para dados vindos do PAT — usam a posição relativa do item dentro da coluna do board como proxy de severidade/prioridade), `bugs_abertos_vs_solucionados` (acumulado semanal, com suporte a marcar colunas do board como "fora do controle da QA"), `construir_grafico_personalizado` (motor genérico por trás do "Monte seu gráfico personalizado" — eixo, agrupamento e métrica escolhidos livremente pelo usuário).

## 10. Geração de PDF

Duas gerações de PDF completamente independentes no projeto, ambas usando **[`reportlab`](https://www.reportlab.com/opensource/)** (biblioteca Python para montar documentos PDF programaticamente, via API "Platypus": `SimpleDocTemplate`, `Paragraph`, `Table`, `TableStyle`, `Spacer`, `PageBreak` etc.):

- **Relatório do dashboard** (`core/pdf_report.py`) — monta um PDF com os KPIs e todos os gráficos visíveis na tela. Como o Plotly desenha gráficos interativos (HTML/JS), eles precisam ser convertidos para imagem estática antes de entrar num PDF — isso é feito por **[`kaleido`](https://github.com/plotly/Kaleido)** (`fig.to_image(format="png", ...)`), que por trás das cortinas abre um navegador Chrome/Chromium sem interface (headless) para renderizar e capturar cada gráfico como PNG. A versão usada (`>=1.0`) não vem com navegador embutido — ela procura um Chrome/Chromium/Edge/Brave já instalado no sistema, e só baixa um binário próprio ("Chrome for Testing") se não achar nenhum.
- **Guia Completo do Usuário** (`core/gerador_guia_pdf.py`) — mesma biblioteca (reportlab), uso completamente independente: monta um PDF só de texto/tabelas/passos numerados (sem nenhum gráfico Plotly, então não depende de `kaleido`/Chrome), com o conteúdo de onboarding do usuário. Gerado em memória (`io.BytesIO`, sem tocar em disco) pela função `gerar_pdf_bytes()`, reaproveitada tanto pelo botão de Administração quanto pelo script de linha de comando `scripts/gerar_guia_usuario_pdf.py`.

## 11. Banco de dados: Turso

**[Turso](https://turso.tech/)** é um serviço de **SQLite hospedado**, acessado aqui por uma **API HTTP simples** (`core/turso_client.py`, usando só `requests` — sem driver/SDK nativo), no formato "pipeline" documentado pela Turso: cada chamada envia um comando SQL e recebe de volta linhas em JSON. Essa escolha (HTTP puro, sem SDK) evita instalar um driver de banco compilado, o que simplifica o deploy no Streamlit Community Cloud.

Três usos, todos no mesmo banco, cada um com sua própria tabela criada sozinha na primeira vez que é necessária (`CREATE TABLE IF NOT EXISTS`):

- **`solicitacoes_conta_qa`** (`core/solicitacoes_conta.py`) — os pedidos de acesso feitos na tela de login (nome, e-mail, justificativa, status: pendente/criada/rejeitada/revogada).
- **`logs_sistema_qa`** (`core/logs_sistema.py`) — três categorias de log (ações no painel administrativo, erros técnicos capturados, tentativas de login), sempre com gravação "best-effort": se o banco estiver indisponível no momento, a linha de log é perdida silenciosamente em vez de travar a ação real que estava sendo registrada.
- **`configuracoes_app_qa`** (`core/config_app.py`) — uma tabela chave/valor genérica, reaproveitada para tudo que precisa ser configurável em tempo de execução sem mexer em Secrets: a pasta do Google Drive de cada usuário (uma chave por `nome_usuario`), o PDF do Guia do Usuário inteiro (codificado em base64 num valor de texto) mais um hash do conteúdo (para detectar quando o PDF salvo ficou desatualizado em relação ao código), e o código de acesso que libera o conteúdo administrativo na página "Sobre o App" para quem não é o admin.

Sem a seção `[turso]` configurada nos Secrets, essas três áreas ficam indisponíveis (com mensagem de erro clara) — o resto do app (login local via `auth/users.yaml`, importação, dashboard) funciona normalmente sem depender do banco.

## 12. Fuso horário

`core/fuso_horario.py` centraliza a conversão para o horário de Brasília (`America/Sao_Paulo`, UTC-3 fixo — sem horário de verão desde 2019) usando **`zoneinfo`** (biblioteca padrão do Python, sem dependência externa). Existe porque três fontes de data/hora do projeto usam fusos diferentes por padrão: `datetime.now()` do Python usa o fuso do servidor onde o app está rodando (não é garantido ser o do Brasil), a API do Azure DevOps devolve tudo em UTC, e o SQLite/Turso grava `datetime('now')` sempre em UTC. Duas funções: `formatar_data_hora_brasil` (para timestamps, com conversão de fuso) e `formatar_data_brasil` (para datas puras, sem horário — sem conversão de fuso, para não arriscar mudar o dia por causa do deslocamento).

## 13. Hospedagem e deploy

- **Principal: [Streamlit Community Cloud](https://streamlit.io/cloud)** — hospedagem gratuita oficial do Streamlit, publica automaticamente a partir do repositório Git. Dois arquivos controlam o ambiente além do código: `requirements.txt` (dependências Python) e `packages.txt` (dependências de sistema via `apt-get` — hoje só `chromium`, necessário para o `kaleido` conseguir abrir um navegador dentro do container minimalista do Streamlit Cloud).
- **Alternativa (fallback): Docker**, documentado em `FALLBACK_DEPLOY.md` — o mesmo código, sem nenhuma alteração, roda dentro de um container Docker (`Dockerfile`/`docker-entrypoint.sh`/`.dockerignore`), hospedável em **Hugging Face Spaces** (recomendado — gratuito, sem limite de horas) ou **Render**. A única diferença prática é como os Secrets chegam ao app: em vez do painel do Streamlit Cloud, uma variável de ambiente `SECRETS_TOML` é gravada pelo `docker-entrypoint.sh` num arquivo `.streamlit/secrets.toml` dentro do container, no início da execução — o restante do código não percebe diferença nenhuma.

## 14. Segurança — visão consolidada

Resumo transversal (cada ponto já é mencionado, com mais contexto, na seção correspondente acima e no [README](README.md#segurança-e-privacidade)):

- **Senhas** de usuários: hash bcrypt, nunca texto puro, vivem nos Secrets do Streamlit (nunca no Git).
- **PAT do Azure DevOps**: nunca persistido (nem disco, nem banco, nem Secrets) — só memória de sessão, por usuário, some ao sair.
- **Credencial de conta de serviço do Google Drive**: só nos Secrets/arquivo local ignorado pelo Git — nunca passa pela tela do app. É compartilhada (uma só para todo o app), mas a pasta configurada por cada usuário é individual e privada dele.
- **Código de acesso ao conteúdo administrativo de "Sobre o App"**: deliberadamente **não** é uma segunda camada de autenticação — é só um seletor de conteúdo informativo, guardado como configuração comum. Não protege nenhuma ação real, só a visibilidade de um texto explicativo.
- **PDF do Guia do Usuário**: por ser baixável livremente por qualquer pessoa logada (para poder ser repassado a qualquer usuário novo), o conteúdo é escrito sem nenhum dado específico deste ambiente — nenhuma credencial, nenhum e-mail de conta de serviço real, nenhuma URL de organização, e sem o nome comercial do produto.
- **Logs e solicitações de acesso**: visíveis só dentro do Painel Administrativo, sem nenhum envio automático (e-mail, webhook) para fora do app.
- **Erros não tratados**: capturados centralmente em `app.py` (`try/except` ao redor da renderização de cada página) — o usuário final vê uma mensagem genérica, o traceback completo vai só para o log técnico (visível ao admin).

## 15. Convenções e padrões de código

- **Nomenclatura em português** em quase todo o código (funções, variáveis, comentários) — só nomes de bibliotecas/APIs externas e alguns termos técnicos sem tradução natural (`session_state`, `DataFrame`) ficam em inglês.
- **Funções "privadas"** de cada módulo começam com `_` (convenção do Python, não impõe restrição de verdade, mas sinaliza "não chame isso de fora deste arquivo").
- **Erros com mensagem amigável**: cada camada externa (banco, APIs, leitura de arquivo) tem sua própria exceção customizada (`TursoError`, `AzureDevOpsError`, `GoogleDriveError`, `DataLoadError`) com mensagem já pronta para mostrar na tela — o código de interface nunca precisa formatar um erro técnico cru para o usuário.
- **`action_button` + `finish_action`** (`ui/components.py`): padrão usado em toda ação que dispara uma chamada de rede/banco, para impedir duplo clique/duplo envio.
- **`@st.dialog`**: toda ação destrutiva ou irreversível passa por um modal de confirmação antes de aplicar.
- **Docstrings extensas**: os módulos deste projeto tendem a explicar **por que** uma decisão foi tomada (não só o quê o código faz) diretamente no docstring da função/módulo — decisões de design, bugs específicos já enfrentados e evitados, e trade-offs considerados ficam documentados no próprio código-fonte, para quem for mexer depois não repetir um erro já resolvido.

## 16. Mapa de arquivos

Ver [Estrutura do projeto](README.md#estrutura-do-projeto) no README para a árvore completa de arquivos comentada.

## 17. Glossário

- **PAT (Personal Access Token)**: um token de acesso pessoal, gerado pelo próprio usuário no Azure DevOps, que funciona como uma senha temporária e restrita (só leitura de work items, neste caso) para uma aplicação acessar uma API em nome dele, sem usar a senha de verdade.
- **Conta de serviço (service account)**: um tipo de credencial do Google Cloud que representa uma "identidade robô" (não uma pessoa) — usada aqui para o app conseguir ler arquivos do Google Drive sem depender do login pessoal de ninguém.
- **Work item**: o termo do Azure DevOps para qualquer item rastreável (caso de teste, bug, tarefa, etc.).
- **Area Path**: campo hierárquico do Azure DevOps usado para organizar work items por projeto/time/módulo (ex.: `Produto\Módulo\Time`).
- **Iteration Path**: campo do Azure DevOps que representa a sprint/iteração de um work item — é o campo mapeado como "Sprint" neste app.
- **Board Column**: a coluna do quadro Kanban em que um work item está no momento (ex.: "A Fazer", "Em Progresso", "Concluído").
- **Session state**: o mecanismo do Streamlit para guardar dados entre uma interação e outra do usuário, já que o script inteiro é reexecutado a cada interação (ver seção 3).
- **Hash (de senha, ou de conteúdo)**: uma transformação matemática que converte um dado (uma senha, um texto) num valor de tamanho fixo, difícil de reverter — usada aqui tanto para nunca guardar senha em texto puro (bcrypt) quanto para detectar se o conteúdo do Guia do Usuário mudou desde a última vez que o PDF foi gerado (SHA-256, ver `core/gerador_guia_pdf.py::hash_conteudo_atual`).
