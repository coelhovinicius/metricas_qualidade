# Guia do Usuário — Refuturiza QA

Este guia é para quem usa o painel como **usuário comum** (sem acesso ao Painel Administrativo, que é exclusivo do administrador). Ele cobre desde pedir acesso, até importar dados, navegar pelo dashboard e gerar o relatório em PDF.

> 💡 Esse mesmo conteúdo também está disponível **dentro do próprio app**, na página **"ℹ️ Sobre o App"** (visível para qualquer pessoa logada) — incluindo um PDF prontinho para baixar e repassar para outra pessoa nova, com passo a passo de como gerar um PAT do Azure DevOps e montar a query certa.

## Sumário

1. [Ainda não tenho uma conta](#1-ainda-não-tenho-uma-conta)
2. [Como entrar (login)](#2-como-entrar-login)
3. [Navegação geral](#3-navegação-geral)
4. [Importar dados](#4-importar-dados)
5. [Confirmar o mapeamento de colunas](#5-confirmar-o-mapeamento-de-colunas)
6. [Usando o dashboard](#6-usando-o-dashboard)
7. [Construtor de gráfico personalizado](#7-construtor-de-gráfico-personalizado)
8. [Gerar o relatório em PDF](#8-gerar-o-relatório-em-pdf)
9. ["Nova Análise" e "Sair"](#9-nova-análise-e-sair)
10. [Perguntas frequentes](#10-perguntas-frequentes)

---

## 1. Ainda não tenho uma conta

Na tela inicial (a mesma tela de login), abaixo dos campos de usuário e senha, há o botão **Solicitar acesso**. Clique nele e preencha:

- **Nome completo**
- **E-mail**
- **Motivo do acesso** (ex.: "faço parte do time de QA do projeto X")

Clique em **Confirmar**. Você verá uma mensagem confirmando que a solicitação foi registrada. A partir daí, o pedido fica visível só para o administrador, que vai analisar e criar sua conta — não existe envio automático de e-mail nesse processo, então o aviso de "conta pronta" precisa vir do próprio administrador, por fora do app. Se já existir uma solicitação pendente com o mesmo e-mail, uma nova tentativa é bloqueada até a primeira ser analisada.

Depois que sua conta for criada, volte a essa mesma tela para fazer login normalmente (próxima seção).

## 2. Como entrar (login)

1. Abra o link do painel no navegador. Você verá a tela **"Acesso ao Painel de Qualidade"**.
2. Digite o **Usuário** e a **Senha** que o administrador te passou e clique em **Entrar**.
3. Se usuário/senha estiverem incorretos, uma mensagem de erro aparece — confira com o administrador se os dados estão certos.
4. Depois de logar, um F5 (recarregar a página) **não** pede login de novo por um tempo — sua sessão fica salva num cookie do navegador daquele computador. Fechar a aba/janela de verdade (ou clicar em **Sair**) encerra a sessão.

## 3. Navegação geral

Depois de logado, a barra lateral esquerda mostra quatro botões:

- **📥 Importar Dados** — tela inicial, para trazer um arquivo de testes para dentro do app.
- **📊 Indicadores** — o dashboard em si, com todos os gráficos.
- **🏃 Scrum & Sprints** — área dedicada a indicadores de fluxo, ritmo de entrega e trabalho em andamento (WIP), pensada para observabilidade de Scrum/Sprints. Visível para qualquer pessoa logada, sem precisar de acesso administrativo.
- **ℹ️ Sobre o App** — uma explicação visual (com fluxograma) de como o app inteiro funciona, incluindo um resumo do que existe do lado da Administração — mesmo você não tendo acesso a ela — e o Guia Completo do Usuário para baixar em PDF.

O botão da página em que você está fica destacado em laranja. Mais abaixo na barra lateral aparece o botão **🔄 Nova Análise** (só depois de você já ter importado algum arquivo) e, por último, **Sair**.

## 4. Importar dados

Clique em **📥 Importar Dados** na barra lateral (é para onde você já cai depois de logar, na primeira vez). Há três formas de trazer dados, escolhidas no seletor **"Como deseja importar os dados?"** no topo da página:

### Opção A — Enviar arquivo (.csv/.txt)

1. Deixe selecionada a opção **"Enviar arquivo (.csv/.txt)"**.
2. Clique na área de upload e escolha um arquivo `.csv` ou `.txt` do seu computador (limite de 20MB) — normalmente um export do Azure DevOps.
3. Clique em **Processar arquivo**.
4. O app detecta sozinho a codificação e o separador de colunas do arquivo. Se ele não conseguir interpretar o arquivo, uma mensagem de erro explica o motivo (ex.: arquivo vazio, ou linhas com quantidades diferentes de colunas) — nesse caso, confira o arquivo de origem e tente de novo.

### Opção B — Buscar automaticamente do Azure DevOps

Se você já tem um Personal Access Token (PAT) pessoal do Azure DevOps, pode pular o passo de exportar/importar CSV manualmente:

1. Selecione **"Buscar automaticamente do Azure DevOps"**.
2. Cole o seu **PAT pessoal** no campo indicado. Para gerar um token novo: em `dev.azure.com`, clique na sua foto de perfil → **Personal Access Tokens** → **New Token**, com escopo **"Work Items (Read)"**. Esse token é **seu**, individual — nunca é salvo em disco nem enviado para os administradores do app, fica só na memória da sua sessão do navegador enquanto você está usando o app, e some quando você sai.
3. Escolha a **Organização** e clique em **Carregar organização**.
4. Escolha o **Projeto** — os passos seguintes carregam sozinhos assim que você escolhe o projeto.
5. (Opcional) Selecione um ou mais **Area Path(s) do Board no Projeto**, se quiser restringir a busca a times/módulos específicos. Deixe em branco para trazer tudo que a query já retorna.
6. Escolha uma **Query salva no Azure DevOps** já existente (no seletor). Se a query que você precisa ainda não existe, use **Criar nova query ↗** (abre o Azure DevOps numa aba nova) e depois **🔄 Atualizar lista** aqui para ela aparecer.
7. Clique em **Baixar relatório atualizado**.

Se algo der errado (token inválido/expirado, sem permissão, organização/projeto/query não encontrados), a mensagem de erro explica a causa provável. Esta é a única forma de importação que traz os gráficos **"Prioridade Dentro do Board"** e **"Severidade Calculada"**, que dependem de um campo indisponível em CSV manual.

### Opção C — Buscar arquivo no Google Drive

Uma alternativa ao upload manual, para quem já tem o hábito de exportar e guardar o `.csv` numa pasta do Google Drive:

1. Selecione **"Buscar arquivo no Google Drive"**.
2. Se for a primeira vez, copie o e-mail da conta de serviço mostrado na própria tela e compartilhe a sua pasta do Drive com esse e-mail (permissão de Leitor), depois cole o link/ID dessa pasta e clique em **Salvar minha pasta**. O app testa o acesso antes de salvar — fica guardado pra você, uma vez só; da próxima vez, o app já vai direto para a sua pasta.
3. Navegue até o arquivo (é possível entrar em subpastas) e escolha o `.csv`.
4. Clique em **Importar arquivo selecionado**.

Se aparecer um aviso de que "a conta de serviço do Google Drive ainda não foi configurada", isso não depende de você — peça para a pessoa administradora configurar (Administração → Google Drive) antes. Enquanto isso, use "Enviar arquivo" normalmente. A pasta que você configura é só sua — ninguém mais enxerga qual pasta você escolheu, e você não depende do administrador para trocar de pasta depois da primeira vez.

## 5. Confirmar o mapeamento de colunas

Depois de importar (por qualquer uma das três formas), a página mostra:

1. Uma confirmação de sucesso, com nome do arquivo, quantidade de linhas/colunas e a codificação/delimitador detectados.
2. Um expansor **"Prévia dos dados importados"** com as 20 primeiras linhas — útil para conferir se o arquivo leu certo antes de seguir.
3. A seção **"Confirme o mapeamento automático de colunas"**: o app tenta adivinhar sozinho qual coluna do seu arquivo representa cada campo (Projeto, Status, Data Planejada, Data de Execução, Data de Criação, Tipos de Teste, Responsável/Executor, Criado por, Caso de Teste/ID, Severidade/Prioridade, Coluna do Board, **Sprint**). Confira cada campo e ajuste manualmente qualquer um que não bateu, usando os seletores. Campos deixados como **"— não mapeado —"** simplesmente fazem os gráficos que dependem deles não aparecerem — não trava o app, então não se preocupe em preencher tudo se algum campo não existe no seu arquivo.
4. (Opcional) **Campos personalizados**: se o seu arquivo tem alguma coluna útil que não se encaixa nos campos fixos acima (ex.: Cliente, Ambiente), clique em **+ Adicionar campo personalizado**, dê um nome livre para ela e escolha a coluna correspondente. Esses campos ficam disponíveis depois no construtor de gráfico personalizado.
5. Clique em **Confirmar mapeamento e gerar indicadores** para ir direto ao dashboard.

> 💡 Se algum gráfico que você esperava ver não aparecer, o motivo mais comum é uma coluna não configurada na query do Azure DevOps (ela só vem no CSV se estiver marcada em "Column Options" da sua query salva) — veja o guia **"Como Montar a Query no Azure DevOps"** (disponível na página "Sobre o App", em PDF) para a lista completa de colunas recomendadas.

## 6. Usando o dashboard

Ao confirmar o mapeamento, você cai direto na página **📊 Indicadores**. A barra lateral ganha, no topo, os filtros — eles se aplicam a **todo** o dashboard de uma vez:

- **Período** — datas "De"/"Até". Ajuste as datas e clique em **Confirmar intervalo** para aplicar (mudar a data sozinha, sem clicar no botão, ainda não altera o dashboard).
- **Filtros** — Projeto, Tipos de Teste e Status, todos como caixas de seleção múltipla, com tudo marcado por padrão (ou seja: sem filtro nenhum aplicado até você desmarcar algo).

No corpo da página, de cima para baixo, você encontra:

- **Cartões de KPI** no topo — números-resumo. Se o seu arquivo usa um vocabulário de status reconhecível como Passou/Falhou (comum em planilhas de execução de teste tradicionais), aparecem volumetria total, quantidade que passou, que não passou e a taxa de sucesso. Se o vocabulário for de fluxo de trabalho (comum em exports crus do Azure DevOps, ex.: New/Active/Closed), aparecem volumetria total, o status mais frequente e quantos status distintos existem.
- Uma sequência de gráficos — a lista abaixo — cada um com seu próprio seletor **"Tipo de gráfico"** no canto (Barras, Barras Horizontais, Pizza, Rosca, Linha, Área, Treemap, Pareto, Funil, Mapa de Calor, Radar preenchido — as opções variam conforme o gráfico, só aparecem os tipos que fazem sentido para aquele dado). Alguns gráficos têm filtros extras próprios, só deles (ex.: excluir tipos "contêiner" como Test Plan/Test Suite na Distribuição por Tipo de Teste, ou marcar quais colunas do board estão "fora do controle da QA" em Bugs Abertos vs. Solucionados).
- Um expansor **"Ver dados detalhados (filtrados)"** ao final de tudo, com a tabela completa dos dados já filtrados e um botão para exportar em CSV.

Os gráficos disponíveis (cada um só aparece se os campos de que ele depende estiverem mapeados) são:

- **Distribuição de Status** (ou "Passou vs. Não Passou")
- **Area Path × Status**
- **Backlog Aberto** — idade dos itens ainda abertos, com destaque para quantos estão parados há mais de 90/180/365 dias, e um gráfico de bolha (Volume × Idade × Risco).
- **Planejamento vs. Testes Efetivados**
- **Sprints — Itens Concluídos** e **Volume por Responsável ao Longo do Tempo** (semanal) — dependem da coluna Sprint mapeada.
- **Testes por Projeto**
- **Ranking de Bugs por Projeto**
- **Distribuição por Tipo de Teste**
- **Taxa de Sucesso por Projeto**
- **Tendência ao Longo do Tempo**
- **Bugs Abertos vs. Solucionados**
- **Distribuição por Severidade/Prioridade**
- **Distribuição por Coluna do Board (Kanban)**
- **Area Path × Coluna do Board**
- **Prioridade Dentro do Board** e **Severidade Calculada** — só aparecem com dados vindos da busca automática por PAT (Opção B da seção 4), mesmo que a query esteja configurada certinho.
- **Volume de Testes por Responsável**
- **Carga de Risco por Responsável** — mapa de calor Responsável × Severidade.

Se algum desses não aparecer para você, normalmente é porque o campo do qual ele depende não foi mapeado no seu arquivo — volte em "Importar Dados" para conferir, se achar que deveria estar disponível.

## 7. Construtor de gráfico personalizado

Mais abaixo no dashboard, a seção **"Monte seu gráfico personalizado"** deixa você montar um gráfico do zero, para perguntas que não têm um gráfico fixo pronto entre os da lista acima:

1. **Eixo / Categoria (X)** — a coluna que vira as categorias do gráfico.
2. **Agrupar por (opcional)** — uma segunda coluna, para dividir/colorir por grupo (ex.: "Projeto por Status").
3. **Métrica** — contar registros, ou somar uma coluna numérica.
4. **Coluna numérica** — só aparece se você escolher "Soma de coluna numérica" no passo anterior.
5. **Tipo de gráfico**.

Clique em **Gerar gráfico**. Ele fica salvo na tela e é recalculado automaticamente se você mudar os filtros da barra lateral depois — não precisa gerar de novo toda vez.

## 8. Gerar o relatório em PDF

No final da página do dashboard, a seção **"Relatório completo em PDF"** tem o botão **📄 Gerar PDF do relatório**. Ele monta um PDF com os KPIs e todos os gráficos que estão visíveis na tela naquele momento — com os mesmos filtros que você aplicou e o mesmo tipo de gráfico escolhido em cada seção (inclusive o gráfico personalizado, se você já tiver gerado um).

- Pode levar até um minuto (cada gráfico é desenhado individualmente) — é normal a tela ficar bloqueada com um aviso de carregamento durante esse tempo.
- Se você mudar algum filtro depois de gerar o PDF, clique no botão de novo para atualizar — o arquivo já baixado não se atualiza sozinho.
- Assim que pronto, aparece o botão **⬇️ Baixar PDF gerado**.
- Conteúdo dentro de um expansor recolhido (como a tabela de dados detalhados) não entra no PDF — só o que já está visível na tela por padrão.
- Numa situação rara de falha (geralmente por indisponibilidade momentânea do ambiente), uma mensagem de erro explica o problema — o resto do dashboard continua funcionando normalmente, e você pode tentar gerar de novo.

## 9. "Nova Análise" e "Sair"

- **🔄 Nova Análise** (barra lateral, aparece só depois de você já ter processado um arquivo) — limpa o arquivo importado e todos os indicadores/gráficos/filtros gerados a partir dele (inclusive o gráfico personalizado que você montou, se algum), para você processar um arquivo novo sem precisar dar F5. Pede confirmação antes de aplicar, porque não tem como desfazer. Sua sessão continua logada, e a organização/projeto/query do Azure DevOps já configurados (se você usa a busca automática) não são apagados.
- **Sair** (final da barra lateral) — encerra sua sessão de verdade. Use sempre que terminar de usar o painel num computador que não é só seu.

## 10. Perguntas frequentes

**Esqueci minha senha.**
Fale com o administrador do sistema — a redefinição de senha é feita por ele, não existe um "esqueci minha senha" automático dentro do app.

**Um gráfico que eu esperava ver não aparece.**
Ele depende de um campo que não foi mapeado no seu arquivo (ex.: sem uma coluna reconhecida como "Coluna do Board", os gráficos de board simplesmente não aparecem) — ou, no caso de "Prioridade Dentro do Board"/"Severidade Calculada", só está disponível vindo da busca automática por PAT, nunca de CSV manual/Google Drive. Volte em "Importar Dados" e confira/ajuste o mapeamento — ou aceite que aquele indicador não se aplica aos dados que você importou.

**Meu Personal Access Token do Azure DevOps é seguro para usar aqui?**
Sim — ele nunca é salvo em disco, banco de dados ou nas configurações do app. Fica só na memória da sua sessão do navegador enquanto você está logado e usando a busca automática, e desaparece quando você sai ou fecha a aba de verdade.

**E o link/ID da minha pasta do Google Drive?**
Fica guardado só para você (associado ao seu usuário), não é compartilhado com mais ninguém que usa o app — nem o administrador vê qual pasta você escolheu, só a credencial da conta de serviço em si é dele.

**Preciso pedir acesso de novo se meu login parar de funcionar?**
Não necessariamente — primeiro confirme com o administrador se sua conta ainda existe/está ativa. Só peça uma solicitação nova se realmente não tiver mais conta.

**Vejo só duas opções na barra lateral (Importar Dados / Indicadores), sem "Sobre o App". É normal?**
Não — "ℹ️ Sobre o App" deveria aparecer para qualquer pessoa logada, incluindo você. Se ela não aparecer, avise o administrador. Já o "⚙️ Administração" (uma quarta opção) é mesmo visível só para o usuário administrador do sistema.
