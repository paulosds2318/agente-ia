# API HTTP

Todas as respostas de erro usam o formato `{"erro": "mensagem"}`.

As rotas privadas exigem cookie de sessão. Operações de escrita também exigem o
cabeçalho `X-CSRF-Token`, obtido em `POST /login`, `POST /cadastro` ou `GET /sessao`.

## Autenticação

- `POST /cadastro`: cria uma conta conforme `ALLOW_REGISTRATION`.
- `POST /login`: inicia uma sessão.
- `GET /sessao`: retorna usuário e token CSRF.
- `POST /logout`: encerra a sessão.

Todos os recursos são filtrados pelo proprietário autenticado.

## Operação

- `GET /saude`: informa disponibilidade e configuração pública sem expor segredos.

## Conversas

- `GET /conversas`: lista conversas.
- `POST /conversas`: cria uma conversa.
- `GET /conversas/<id>/mensagens`: retorna histórico, arquivo e modelo ativos.
- `DELETE /conversas/<id>`: exclui conversa e artefatos associados.

## Chat

### `POST /perguntar`

```json
{
  "conversa_id": 1,
  "mensagem": "Resuma esta base"
}
```

Pode responder com `429` quando a cota Gemini for atingida, `503` para chave inválida e `504` em timeout.

### `POST /mensagens/<id>/tentar-novamente`

Repete o processamento de uma mensagem do usuário que falhou.

## Arquivos

### `POST /upload`

`multipart/form-data` com `conversa_id` e `arquivo`. Aceita `.csv` e `.xlsx`.

## Treinamento

### `POST /treinar`

```json
{
  "conversa_id": 1,
  "alvo": "comprou"
}
```

Retorna `202` e um `tarefa_id`.

### `GET /tarefas/<id>`

Retorna `status`, `progresso`, `resultado` ou `erro`.

### `DELETE /tarefas/<id>`

Solicita o cancelamento de uma tarefa pendente ou em processamento.

## Previsão

### `POST /prever`

`multipart/form-data` com `conversa_id` e `arquivo`. A nova base deve conter as colunas usadas pelo modelo.

### `GET /previsoes/<token>`

Baixa o CSV produzido pela previsão.
