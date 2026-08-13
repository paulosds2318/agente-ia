# Como contribuir

## Preparação

1. Crie um ambiente virtual.
2. Instale `requirements.txt`.
3. Copie `.env.example` para `.env`.
4. Nunca inclua credenciais ou dados reais em commits.

## Fluxo sugerido

1. Crie uma branch curta e descritiva.
2. Faça alterações pequenas e focadas.
3. Adicione ou atualize testes.
4. Execute `python -m unittest discover -s tests -v`.
5. Abra um pull request explicando comportamento, validação e riscos.

## Estilo

- Use UTF-8 e nomes claros.
- Mantenha mensagens exibidas ao usuário em português.
- Não use dados pessoais nos testes.
- Preserve compatibilidade das migrações SQLite existentes.
- Trate caminhos de arquivos como entrada não confiável.

## Commits

Prefira mensagens no imperativo, por exemplo:

```text
Adiciona exportação das previsões
Corrige isolamento de arquivos por conversa
```

