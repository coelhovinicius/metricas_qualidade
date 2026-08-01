# Refuturiza QA — Dashboard de Métricas de QA

## O que é

Um dashboard interno (construído em Python/Streamlit, hospedado no Streamlit Community Cloud e acessível por link de navegador, sem instalação) que transforma os work items do Azure DevOps do time de QA em indicadores visuais prontos para análise — substituindo a conferência manual de planilhas exportadas.

## Problema que resolve

Antes do app, entender o panorama real do trabalho de QA (volume de testes, bugs em aberto, backlog envelhecendo, ritmo de cada pessoa/projeto) dependia de exportar dados do Azure DevOps e montar tabelas/gráficos manualmente a cada consulta — processo repetitivo, sujeito a erro e sem padronização entre times. O dashboard centraliza isso: os mesmos dados brutos do Azure DevOps viram, de forma automática e padronizada, um conjunto de indicadores prontos para qualquer pessoa da empresa consultar.

## Como os dados entram no app

- **Upload manual**: arquivo .csv/.txt exportado do Azure DevOps.
- **Busca automática via API**: conecta direto no Azure DevOps (com um Personal Access Token pessoal, nunca salvo em disco) e traz os work items de uma query já salva — escolhendo organização, projeto e, opcionalmente, um ou mais Area Paths (times/módulos) ao mesmo tempo.
- **Mapeamento automático de colunas**: o app tenta identificar sozinho qual coluna do arquivo representa Projeto, Status, datas (planejada/execução/criação), Tipo de Teste, Responsável, Severidade e Coluna do Board (Kanban) — sempre com uma tela de confirmação antes de gerar qualquer gráfico, para nunca montar um indicador em cima de um mapeamento errado.

## Principais indicadores e gráficos disponíveis

- Indicadores gerais (total de registros, taxa de sucesso quando aplicável)
- Distribuição de Status e cruzamento Area Path × Status
- Backlog aberto: idade média/mediana e quantos itens estão parados há mais de 90/180/365 dias
- Planejado vs. Efetivado
- Testes por Projeto e Ranking de Bugs por Projeto
- Distribuição por Tipo de Teste (Bug, Test Case etc.)
- Taxa de Sucesso por Projeto
- Tendência ao longo do tempo (semanal)
- Bugs Abertos vs. Solucionados ao longo do tempo, descontando tempo de espera fora do controle da QA (ex.: aguardando validação de outro time)
- Distribuição por Coluna do Board (Kanban) e cruzamento Area Path × Coluna do Board — mostra onde estão os gargalos do fluxo
- **Volume de Testes por Responsável** — quem está fazendo quanto, com a opção de abrir por Projeto
- **Volume por Responsável ao Longo do Tempo** — ritmo semanal de cada pessoa, para enxergar sobrecarga, ociosidade ou queda de ritmo do time
- Distribuição por Severidade/Prioridade
- Construtor de gráfico personalizado, para perguntas ad-hoc que não têm um gráfico fixo pronto

Todos os gráficos têm filtros por período, Projeto, Tipo de Teste e Status na barra lateral, aplicados automaticamente ao painel inteiro.

## Para quem é

- **Liderança de QA**: acompanhamento do dia a dia do time, identificação de gargalos no board e de backlog envelhecendo.
- **Liderança de TI/diretoria**: visão executiva do volume de trabalho da área, ritmo ao longo do tempo e distribuição de carga entre pessoas e projetos — sem precisar pedir relatório manual.

## Destaques técnicos

- Construído em Python (Streamlit + Pandas + Plotly), com paleta de cores própria desenhada para nunca repetir tons parecidos entre categorias vizinhas de um mesmo gráfico.
- Tolerante a dados incompletos: qualquer indicador que dependa de um campo não mapeado no arquivo simplesmente não aparece, em vez de quebrar o painel.
- Evolução contínua: o app já passou por rodadas de ajuste fino (paleta de cores, seleção de múltiplos Area Paths na importação, substituição de indicadores pouco acionáveis por outros mais direto ao ponto, como o de volume por responsável) com base no uso real do time.