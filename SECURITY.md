# Política de segurança

## Escopo

O Atlas possui login e isolamento por proprietário, mas não deve ser exposto diretamente à internet sem TLS, servidor WSGI e revisão de infraestrutura.

## Proteção de dados

- Nunca publique `.env`, `instance/` ou `uploads/`.
- Use somente bases autorizadas e observe a legislação aplicável.
- Exclua conversas quando os dados não forem mais necessários.
- Não use dados pessoais reais em testes ou issues públicas.
- Revogue imediatamente uma chave publicada acidentalmente.

## Relato de vulnerabilidades

## Defesas disponíveis

- login com senha armazenada por hash e sessões HttpOnly;
- autorização por proprietário em conversas, tarefas e previsões;
- proteção CSRF em operações de escrita;
- limitação de requisições por endereço;
- Content Security Policy e cabeçalhos restritivos;
- expiração automática dos CSVs de previsão;
- envio de amostras categóricas à IA desativado por padrão;
- logs sem conteúdo de planilhas ou credenciais.

Use `ATLAS_SECRET_KEY` persistente e aleatória. Em HTTPS, configure `SESSION_COOKIE_SECURE=true`.

No Render, esses valores são definidos pelo Blueprint. Nunca copie a chave Gemini
para `render.yaml`; configure-a como secret no Dashboard. O disco persistente mantém
dados entre deploys, portanto aplique também backups e uma política de retenção.

Não abra uma issue pública contendo credenciais, dados pessoais ou detalhes exploráveis. Entre em contato privadamente com o mantenedor do repositório.

## Produção

Antes de uso público, adicione TLS, rate limiting compartilhado, auditoria, armazenamento externo de tarefas e backups protegidos.
