# Política de segurança

## Escopo

O Atlas não possui autenticação. Use-o localmente ou em rede privada confiável e não o exponha diretamente à internet.

## Proteção de dados

- Nunca publique `.env`, `instance/` ou `uploads/`.
- Use somente bases autorizadas e observe a legislação aplicável.
- Exclua conversas quando os dados não forem mais necessários.
- Não use dados pessoais reais em testes ou issues públicas.
- Revogue imediatamente uma chave publicada acidentalmente.

## Relato de vulnerabilidades

## Defesas disponíveis

- limitação de requisições por endereço;
- Content Security Policy e cabeçalhos restritivos;
- expiração automática dos CSVs de previsão;
- envio de amostras categóricas à IA desativado por padrão;
- logs sem conteúdo de planilhas ou credenciais.

No Render, nunca copie a chave Gemini
para `render.yaml`; configure-a como secret no Dashboard. O disco persistente mantém
dados entre deploys, portanto aplique também backups e uma política de retenção.

Não abra uma issue pública contendo credenciais, dados pessoais ou detalhes exploráveis. Entre em contato privadamente com o mantenedor do repositório.

## Produção

Antes de uso público, implemente autenticação e autorização, além de TLS, rate limiting compartilhado, auditoria, armazenamento externo de tarefas e backups protegidos.
