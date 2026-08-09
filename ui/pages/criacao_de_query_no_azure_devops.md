# Guia — Como montar a query no Azure DevOps para o app funcionar 100%

Este guia é para quem vai trazer dados para o app **sem usar a busca automática por PAT** — ou seja, os dois caminhos que dependem de um arquivo `.csv` exportado manualmente do Azure DevOps:

- **"Enviar arquivo (.csv/.txt)"** (upload direto do computador), e
- **"Buscar arquivo no Google Drive"** (mesmo arquivo `.csv`, só que buscado de uma pasta do Drive em vez do computador).

Os dois processam o **mesmo tipo de arquivo**, da **mesma forma** — então este guia vale igualmente para os dois. Se você usa a busca automática por PAT, pode pular este guia: ela já traz tudo sozinha, sem depender de como a query está configurada (ver aviso no fim).

---

## Por que isso importa

O app tenta reconhecer sozinho, pelo **nome de cada coluna do seu CSV**, qual campo é qual (Projeto, Status, Responsável, Sprint, etc.) — mas só consegue reconhecer uma coluna que **existe** no arquivo. E o arquivo `.csv` exportado do Azure DevOps só traz as colunas que a **sua query** está configurada para exibir. Se uma coluna não estiver configurada lá, ela simplesmente não vem no arquivo — e aquele indicador específico do app fica vazio ou incompleto, mesmo que o dado exista no Azure DevOps.

A solução é simples: configurar a query **uma vez** com todas as colunas recomendadas abaixo, salvar, e reexportar sempre que precisar de dados atualizados.

---

## Passo a passo: adicionando colunas à sua query

1. No Azure DevOps, abra a query (**Boards → Queries**, ou o link direto da sua query salva).
2. Nos resultados da query, clique no ícone de engrenagem/colunas (**"Column Options"** ou "Opções de coluna") — geralmente no canto superior direito da grade de resultados.
3. Na caixa de busca, digite o nome do campo (veja a tabela abaixo) e clique em **"Add"**/"Adicionar" para colocá-lo na lista de colunas exibidas.
4. Repita para cada campo da tabela que fizer sentido para o seu processo.
5. Clique em **OK/Aplicar**, depois em **Save** (salvar a query) para não precisar refazer isso da próxima vez.
6. Para gerar o arquivo: nos resultados da query, use o botão **"Export to CSV"** (ou "Exportar para CSV") na barra de ferramentas.

---

## Tabela de colunas recomendadas

| Adicione esta coluna na query | Vira, no app | Alimenta |
|---|---|---|
| **ID** | Caso de Teste / ID | Identificação de cada item; sempre disponível. |
| **Work Item Type** | Tipos de Teste | Distribuição por Tipo de Teste, exclusão de "contêineres" (Test Plan/Test Suite). |
| **State** | Status | Quase todos os gráficos de qualidade/status. |
| **Area Path** | Projeto | Todos os gráficos "por Projeto". |
| **Assigned To** | Responsável / Executor | Volume por Responsável, Carga de Risco por Responsável. |
| **Created By** | Autor / Criado por | Reserva para Responsável quando "Assigned To" está vazio. |
| **Created Date** | Data de Criação | Tendência ao longo do tempo, backlog/tempo parado. |
| **Severity** (ou **Priority**) | Severidade / Prioridade | Distribuição por Severidade/Prioridade (cores fixas: Critical/High/Medium/Low). |
| **Board Column** | Coluna do Board (Kanban) | Distribuição por Coluna do Board, Area Path × Coluna do Board, Funil. |
| **Iteration Path** ⚠️ | Sprint | Sprints — Itens Concluídos, Volume por Responsável ao Longo do Tempo. |
| **Tags** | (sem campo fixo) | Não vira nenhum indicador pronto sozinho, mas fica disponível como opção no "gráfico personalizado" (junto com qualquer outra coluna extra que sobrar no arquivo). |

⚠️ **Atenção ao nome exato:** é **Iteration Path**, não **Iteration ID** — são campos diferentes (Iteration Path é o texto "Projeto\Sprint 24"; Iteration ID é só um número interno sem uso no app). Se por engano só o Iteration ID for adicionado, o app pode tentar usá-lo como Sprint mesmo assim e os gráficos mostrarão números em vez do nome da sprint — dá para perceber e corrigir na tela de confirmação de mapeamento, mas o certo já de início é usar Iteration Path.

⚠️ **Board Column nem sempre aparece na lista de colunas disponíveis** para adicionar, dependendo do processo/template do seu projeto no Azure DevOps (Agile, Scrum, Basic, CMMI) — se não encontrar "Board Column" na busca do Column Options, esse indicador específico (Distribuição por Coluna do Board) simplesmente fica indisponível para arquivos exportados manualmente; o resto do app continua funcionando normalmente.

Campos de **data planejada** e **data de execução** (usados em "Planejamento vs. Testes Efetivados") não têm um nome padrão único no Azure DevOps — geralmente são campos personalizados, específicos de cada processo/time. Se o seu time tiver um campo assim, dê à coluna um nome que contenha uma destas frases (o app ignora acento/maiúscula, mas precisa da frase, não só um pedaço da palavra):

- **Data planejada**: "Data Planejada", "Planejamento", "Data Prevista", "Previsto", ou começando com "Data Plan".
- **Data de execução**: "Data Execução"/"Data de Execução", "Data Teste", "Executado em", "Data Real", ou "Data Efetiva".

---

## O que NÃO dá para trazer via CSV manual (mesmo configurando tudo certo)

Dois indicadores do app — **"Prioridade Dentro do Board"** e **"Severidade Calculada (posição no board)"** — dependem de um campo (Stack Rank/Backlog Priority) que o Azure DevOps **não deixa adicionar como coluna de query nem aparece no CSV exportado**, em nenhuma configuração. Esse campo só é alcançável pela API, ou seja, **só a busca automática por PAT** traz esses dois gráficos. Se algum usuário precisar deles, oriente a usar "Buscar Query no Azure DevOps" (com o próprio PAT pessoal) em vez do CSV.

---

## Resumo rápido (para colar num aviso ou apresentar rapidinho)

Antes de exportar o CSV da sua query no Azure DevOps, confirme que estas colunas estão marcadas em **Column Options**:

`ID` · `Work Item Type` · `State` · `Area Path` · `Assigned To` · `Created By` · `Created Date` · `Severity` (ou `Priority`) · `Board Column` · **`Iteration Path`** (não Iteration ID)

Depois: **Export to CSV** → suba esse arquivo (upload direto, ou deixe na sua pasta do Google Drive) no app normalmente.

Se quiser os gráficos de "Prioridade/Severidade por posição no Board", use a busca automática por PAT em vez do CSV.

---

## Não precisa se preocupar com…

- **Codificação e separador do CSV** (vírgula, ponto e vírgula, acentuação): o app detecta sozinho.
- **Ordem das colunas**: não importa a ordem, só se elas existem.
- **Nome exato "perfeito"** de cada coluna: o app reconhece por palavras-chave (ex.: tanto "Status" quanto "Situação" funcionam para o campo Status) — e mesmo se a sugestão automática vier errada, a tela de confirmação de mapeamento deixa corrigir manualmente antes de gerar os indicadores, então nada quebra de forma silenciosa.