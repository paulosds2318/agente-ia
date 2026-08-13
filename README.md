# Atlas — Agente de Dados

Aplicação web Flask para conversar com uma IA sobre bases tabulares, diagnosticar qualidade de dados, treinar modelos de machine learning e gerar previsões em lote. Pode ser executada localmente ou publicada no Render.

## Funcionalidades

- Chat com Gemini 3.5 Flash Lite e histórico em SQLite.
- Conversas, planilhas e modelos isolados por sessão.
- Upload de CSV e XLSX com diagnóstico automático.
- Detecção automática de classificação ou regressão.
- Preparação de valores ausentes, números e categorias.
- Comparação entre modelos com validação cruzada.
- Treinamento em segundo plano com indicador de progresso.
- Persistência dos modelos com `joblib`.
- Previsão em lote e download em CSV.
- Tema claro/escuro e interface responsiva.

## Requisitos

- Python 3.11 ou superior.
- Uma chave da API Gemini.

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite `.env` e informe sua chave:

```env
GEMINI_API_KEY=sua_chave_aqui
FLASK_DEBUG=false
```

Execute:

```powershell
python app.py
```

Acesse `http://127.0.0.1:5000`.

## Publicação no Render

O repositório inclui um Blueprint em `render.yaml`. Para publicar:

1. Envie o projeto para um repositório no GitHub.
2. No Render, escolha **New > Blueprint**.
3. Selecione o repositório e mantenha `render.yaml` como Blueprint Path.
4. Configure `GEMINI_API_KEY` como variável de ambiente secreta.
5. Crie o serviço e aguarde o status **Live**.

O Render instala as dependências e inicia a aplicação com:

```text
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

No plano gratuito, o serviço pode adormecer após um período sem acessos. O primeiro acesso seguinte pode demorar enquanto a instância reinicia.

## Como usar

1. Crie ou abra uma conversa.
2. Envie uma planilha CSV ou XLSX de até 10 MB.
3. Consulte o relatório de qualidade ou faça perguntas no chat.
4. Escolha a coluna que deseja prever.
5. Aguarde a comparação dos modelos.
6. Envie outra planilha com as mesmas colunas para gerar previsões.

## Machine learning

Para classificação, o Atlas compara regressão logística e floresta aleatória. Para regressão, compara regressão linear e floresta aleatória. A avaliação inclui divisão treino/teste e validação cruzada.

As métricas não garantem desempenho em produção. Verifique qualidade, representatividade, vazamento de dados e impacto das previsões antes de tomar decisões reais.

## Dados locais

Dados privados não são versionados:

- `.env`: credenciais locais.
- `instance/`: banco, modelos e previsões.
- `uploads/`: planilhas enviadas.
- `.venv/`: ambiente Python.

Excluir uma conversa também remove seus arquivos e modelos associados.

## Testes

```powershell
python -m unittest discover -s tests -v
```

Os testes cobrem histórico, isolamento de arquivos, validação, treinamento e previsão.

## Estrutura

```text
.
├── app.py                 # Aplicação Flask, persistência e ML
├── main.py                # Cliente de terminal experimental
├── render.yaml            # Blueprint de publicação no Render
├── .python-version        # Versão do Python usada no deploy
├── requirements.txt       # Dependências Python
├── static/style.css       # Estilos da interface
├── templates/index.html   # Interface e JavaScript
├── tests/test_app.py      # Testes automatizados
└── docs/                  # Documentação técnica
```

Consulte [Arquitetura](docs/ARCHITECTURE.md), [API](docs/API.md), [Segurança](SECURITY.md) e [Contribuição](CONTRIBUTING.md).

## Limitações atuais

- Projetado para uso experimental e sem autenticação de usuários.
- SQLite e executor em memória não são indicados para múltiplas instâncias.
- Tarefas em andamento não sobrevivem ao reinício do processo.
- No plano gratuito do Render, SQLite, uploads e modelos ficam em armazenamento efêmero e podem ser perdidos após reinícios ou novos deploys.
- A disponibilidade do chat depende da cota da API Gemini.

## Licença

Nenhuma licença foi definida. Até que uma licença seja adicionada, permanecem reservados os direitos autorais do projeto.

