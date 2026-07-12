# Refuturiza · Painel de Indicadores de Qualidade de Testes

Aplicação Streamlit para importar arquivos de execução de testes (`.csv`/`.txt`)
e gerar automaticamente indicadores e gráficos interativos de qualidade.

## Funcionalidades

- **Login multiusuário** com sessão **persistida em cookie** (sobrevive a F5/refresh
  por até 7 dias, configurável).
- **Importação de CSV/TXT** com detecção automática de encoding e delimitador.
- **Detecção automática das colunas** (Projeto, Status, Datas, Bug, Responsável,
  Severidade etc.), com tela de confirmação/ajuste antes de gerar os indicadores —
  já que a estrutura do arquivo pode variar.
- **Indicadores calculados automaticamente:**
  - Volumetria total de testes;
  - Quantidade que passou / não passou (e taxa de sucesso);
  - Planejamento vs. Testes Efetivamente Realizados;
  - Testes por Projeto;
  - Ranking de Bugs por Projeto;
  - Taxa de sucesso por projeto;
  - Tendência temporal de execução;
  - Testes por responsável;
  - Distribuição por severidade/prioridade.
- **Gráficos interativos** (Plotly: zoom, hover, pan) com **seletor de tipo de
  gráfico** (barras/pizza/linha) e **filtros** de projeto e status na barra lateral.
- **Overlay de carregamento** ("Carregando, aguarde...") que escurece a tela e
  bloqueia interação durante processamento.
- **Proteção contra múltiplos cliques**: botões se desabilitam automaticamente
  após o primeiro clique até a operação terminar.
- Tema visual aplicado via `.streamlit/config.toml` (identidade Refuturiza).

## Estrutura do projeto

```
refuturiza_qa/
├── app.py                      # Ponto de entrada / roteamento de páginas
├── requirements.txt
├── .streamlit/
│   └── config.toml             # Tema visual (fornecido)
├── assets/                     # Logotipo e símbolo Refuturiza
├── auth/
│   ├── users.yaml              # Credenciais dos usuários (hashes de senha)
│   └── auth_manager.py         # Login + sessão persistida em cookie
├── core/                       # Regras de negócio (sem dependência de UI)
│   ├── data_loader.py          # Leitura de CSV/TXT com autodetecção
│   ├── column_mapper.py        # Detecção automática do papel das colunas
│   └── analytics.py            # Cálculo dos indicadores
├── ui/
│   ├── theme.py                 # Cores e CSS customizado
│   ├── components.py            # Overlay de loading, botão anti-duplo-clique, KPI cards
│   └── pages/
│       ├── login_page.py
│       ├── upload_page.py
│       └── dashboard_page.py
├── utils/
│   └── session.py               # Inicialização do st.session_state
├── scripts/
│   └── gerar_hash_senha.py      # Utilitário para gerar hash de senha
└── sample_data/
    └── exemplo_testes.csv       # Arquivo de exemplo para testar a aplicação
```

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configurando os usuários

O arquivo `auth/users.yaml` já vem com dois usuários de exemplo:

| Usuário       | Senha (exemplo)     |
|---------------|----------------------|
| `admin`       | `Refuturiza@2025`    |
| `qa.analista` | `Qualidade@2025`     |

**Antes de usar em produção**, gere novos hashes de senha com:

```bash
python scripts/gerar_hash_senha.py
```

Cole o hash gerado no campo `password` do usuário correspondente em
`auth/users.yaml`. Você também pode adicionar novos usuários seguindo o
mesmo padrão do arquivo, e deve trocar a chave `cookie.key` por um valor
aleatório e secreto antes de publicar a aplicação.

## Solução de problemas

**Erro `Failed building wheel for pillow` / `RequiredDependencyException: zlib` no Windows:**
Isso acontece quando o Python instalado é muito recente (ex: 3.14) e a versão do
Streamlit fixada no `requirements.txt` obriga a usar uma versão antiga do
`pillow` que ainda não tem wheel pré-compilada para essa versão do Python —
então o pip tenta compilar do zero e falha por falta do `zlib`. Duas soluções:

1. **Recomendado:** use Python **3.11 ou 3.12** para este projeto (versões
   com suporte maduro em todo o ecossistema de dados — Streamlit, pandas,
   pyarrow, pillow). Crie o ambiente virtual com essa versão, ex:
   `py -3.12 -m venv .venv`.
2. Ou mantenha o Python atual e deixe o `pip` escolher a versão mais recente
   do Streamlit (já feito neste `requirements.txt`, sem pin de versão exata),
   o que libera uma versão do `pillow` com wheel pronta.

Se o erro persistir, rode `pip install --upgrade pip` antes de instalar os
requirements — versões antigas do pip às vezes não escolhem a wheel certa.

**Erro `AttributeError: module 'streamlit_authenticator' has no attribute 'Hasher'`
ao rodar `gerar_hash_senha.py`:**
Isso acontece se a versão instalada do `streamlit-authenticator` for diferente
da 0.3.2 (essa lib muda a API de geração de hash entre versões). Duas soluções:
1. Reinstale com a versão travada: `pip install -r requirements.txt --force-reinstall streamlit-authenticator==0.3.2`;
2. Ou simplesmente use a versão mais recente do `requirements.txt` deste
   projeto — o script `gerar_hash_senha.py` já foi atualizado para gerar o
   hash usando a biblioteca `bcrypt` diretamente, sem depender dessa API
   instável, então não deve mais ocorrer.

## Rodando a aplicação

```bash
streamlit run app.py
```

Acesse `http://localhost:8501`, faça login e importe o arquivo
`sample_data/exemplo_testes.csv` para ver a aplicação funcionando com dados
de exemplo (ou envie seu próprio arquivo de execução de testes).

## Adicionando novos indicadores

Toda a lógica de cálculo fica isolada em `core/analytics.py`, sem nenhuma
dependência do Streamlit — cada função recebe o DataFrame já tratado e o
mapeamento de colunas, e devolve um DataFrame pronto para plotagem. Para
adicionar uma nova métrica:

1. Crie uma função em `core/analytics.py` que retorne um DataFrame (ou `None`
   quando os dados necessários não existirem no arquivo importado);
2. Chame essa função em `ui/pages/dashboard_page.py` e renderize com
   `_plotar(...)`, seguindo o padrão das seções já existentes.

## Observações técnicas

- A detecção de colunas é heurística (por palavras-chave). Por isso a
  aplicação sempre exibe uma tela de confirmação antes de gerar os gráficos,
  para evitar que uma detecção incorreta gere indicadores enganosos.
- O overlay de carregamento e o bloqueio de botões cobrem tanto a importação
  do arquivo quanto a confirmação do mapeamento — as duas operações que
  disparam processamento mais pesado na aplicação.
