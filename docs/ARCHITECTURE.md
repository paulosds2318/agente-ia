Exit code: 0
Wall time: 0.3 seconds
Output:
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

### Interface

`templates/index.html` contém a estrutura e o cliente JavaScript. `static/style.css` implementa layout responsivo e temas.

### Persistência

O SQLite é criado automaticamente em `instance/conversas.db`. As tabelas são inicializadas e migradas de forma incremental na inicialização.

- `conversas`: agrupador principal.
- `mensagens`: histórico e estado da resposta.
- `arquivos`: metadados e caminho da base ativa.
- `modelos`: artefato e métricas do melhor pipeline.
- `tarefas`: progresso do treinamento assíncrono.

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

- Upload HTTP: 10 MB.
- Base processada: até 1 milhão de linhas e 1.000 colunas.
- Mensagem: 3.000 caracteres.
- Histórico enviado à IA: últimas 12 mensagens.

## Evolução recomendada

Separar `app.py` em blueprints e serviços, introduzir autenticação, mover tarefas para uma fila persistente e usar PostgreSQL/armazenamento de objetos em implantação multiusuário.

