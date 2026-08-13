# Política de segurança

## Escopo

O Atlas foi projetado para uso local por uma pessoa. Não exponha diretamente o servidor Flask à internet sem autenticação, TLS, controle de acesso, servidor WSGI e revisão de segurança.

## Proteção de dados

- Nunca publique `.env`, `instance/` ou `uploads/`.
- Use somente bases autorizadas e observe a legislação aplicável.
- Exclua conversas quando os dados não forem mais necessários.
- Não use dados pessoais reais em testes ou issues públicas.
- Revogue imediatamente uma chave publicada acidentalmente.

## Relato de vulnerabilidades

## Defesas disponíveis

- autenticação opcional por `ATLAS_ACCESS_TOKEN`;
- limitação de requisições por endereço;
- Content Security Policy e cabeçalhos restritivos;
- expiração automática dos CSVs de previsão;
- envio de amostras categóricas à IA desativado por padrão;
- logs sem conteúdo de planilhas ou credenciais.

O token local é uma proteção simples, não um sistema completo de autorização.

Não abra uma issue pública contendo credenciais, dados pessoais ou detalhes exploráveis. Entre em contato privadamente com o mantenedor do repositório.

## Produção

Antes de uso multiusuário, implemente autenticação, autorização por proprietário, CSRF, rate limiting, auditoria, criptografia adequada, armazenamento externo de tarefas e backups protegidos.

