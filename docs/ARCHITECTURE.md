# Arquitetura

## Visão geral

```text
Navegador
   │ HTTP/JSON
   ▼
Flask ─────────────── Gemini API
   │
   ├── SQLite: conversas, mensagens, arquivos, modelos e tarefas
   ├── uploads/: bases tabulares
   ├── instance/modelos/: pipelines joblib
   └── instance/previsoes/: resultados CSV
```

## Componentes

### Núcleo modular

- `atlas/config.py`: configuração tipada e limites operacionais.
- `atlas/ai.py`: integração lazy com Gemini.
- `atlas/security.py`: rate limiting local e cabeçalhos HTTP.
- `app.py`: composição Flask, rotas e orquestração.

### Interface

`templates/index.html` contém a estrutura e o cliente JavaScript. `static/style.css` implementa layout responsivo e temas.

### Persistência

O SQLite é criado automaticamente em `instance/conversas.db`. As tabelas são inicializadas e migradas de forma incremental na inicialização.

- `conversas`: agrupador principal.
- `mensagens`: histórico e estado da resposta.
- `arquivos`: metadados e caminho da base ativa.
- `modelos`: artefato e métricas do melhor pipeline.
- `tarefas`: progresso do treinamento assíncrono.
- `usuarios`: identidades e hashes de senha.
- `previsoes`: downloads privados com proprietário e expiração.

Conversas pertencem a um usuário; arquivos, mensagens, modelos e tarefas herdam
esse isolamento. Na migração, a primeira conta assume as conversas legadas.

### Machine learning

O pipeline usa `ColumnTransformer` para:

- imputar números pela mediana;
- padronizar números;
- imputar categorias pelo valor mais frequente;
- aplicar one-hot encoding com categorias desconhecidas toleradas.

Identificadores textuais de alta cardinalidade são descartados. O melhor pipeline é escolhido pela pontuação F1 ponderada ou R² e salvo com `joblib`.

### Concorrência

O treinamento usa `ThreadPoolExecutor` com dois workers. O navegador consulta `/tarefas/<id>` até conclusão. Para produção distribuída, substitua-o por Celery, RQ ou serviço equivalente.

## Limites

As tarefas ficam persistidas no SQLite. Tarefas interrompidas são retomadas na
inicialização e podem ser canceladas pela API. O melhor algoritmo é escolhido
pela validação cruzada; o conjunto de teste fica reservado para apresentação.
O resultado registra baseline, versões, possíveis sinais de vazamento e
importância dos atributos quando disponível.

- Upload HTTP: 10 MB.
- Base processada: até 1 milhão de linhas e 1.000 colunas.
- Mensagem: 3.000 caracteres.
- Histórico enviado à IA: últimas 12 mensagens.

## Render

No Render, `ATLAS_DATA_DIR=/var/data` direciona banco, uploads, modelos e previsões
ao disco persistente. Gunicorn executa um worker com quatro threads e recebe tráfego
em `0.0.0.0:$PORT`. `ProxyFix` confia em um nível do proxy do Render para reconhecer
HTTPS e o endereço do cliente. O health check público usa `/saude`.

## Evolução recomendada

Separar `app.py` em blueprints e serviços, introduzir autenticação, mover tarefas para uma fila persistente e usar PostgreSQL/armazenamento de objetos em implantação multiusuário.
