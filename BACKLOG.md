# 📋 Backlog de Tarefas — Autenticação

Este documento centraliza as tarefas planejadas para o módulo de **Autenticação** do ThothSCV AI.

---

## 🔴 Prioridade 1 (P1): Autenticação Real com Provedores Sociais (OAuth 2.0)

Substituir os mocks locais de desenvolvimento pelas integrações oficiais completas com Google e LinkedIn.

### 1.1 Conexão Real com Google OAuth 2.0
- [x] **Configuração no Google Cloud Console:**
  - [x] Criar/vincular projeto no Google Cloud Console.
  - [x] Configurar Tela de Consentimento OAuth (nome da aplicação, logo e e-mail de contato).
  - [x] Gerar credenciais: `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`.
  - [x] Cadastrar URI de redirecionamento autorizada: `http://localhost:8000/auth/callback/google`.
- [x] **Implementação no Backend:**
  - [x] Configurar carregamento das credenciais em `Settings` (`app/core/config.py`).
  - [x] Implementar rota de redirecionamento `GET /auth/login/google` para a tela de login do Google.
  - [x] Implementar rota de callback `GET /auth/callback/google`.
  - [x] Troca segura de `code` por tokens oficiais junto ao endpoint do Google (`https://oauth2.googleapis.com/token`).
  - [x] Extração de perfil real do usuário (`email`, `full_name`, `picture_url` e `sub`).
  - [x] Persistência no banco relacional e emissão de cookie seguro de sessão `session_token`.
- [x] **Garantia de Qualidade:**
  - [x] Testes automatizados de integração cobrindo fluxos felizes e exceções de autorização.
  - [x] 100% de cobertura de código mantida.

---

### 1.2 Conexão Real com LinkedIn OAuth 2.0
- [ ] **Configuração no LinkedIn Developer Portal:**
  - [ ] Criar aplicativo no portal de desenvolvedores do LinkedIn.
  - [ ] Habilitar o produto *"Sign In with LinkedIn using OpenID Connect"*.
  - [ ] Gerar `LINKEDIN_CLIENT_ID` e `LINKEDIN_CLIENT_SECRET`.
  - [ ] Cadastrar URI de redirecionamento autorizada: `http://localhost:8000/auth/callback/linkedin`.
- [ ] **Implementação no Backend:**
  - [ ] Adicionar variáveis de ambiente e configurações no backend.
  - [ ] Implementar rotas `GET /auth/login/linkedin` e `GET /auth/callback/linkedin`.
  - [ ] Troca de código de autorização e consulta aos dados do perfil via endpoint `/v2/userinfo`.
  - [ ] Persistência de usuário e emissão de cookie de sessão.
- [ ] **Garantia de Qualidade:**
  - [ ] Testes automatizados cobrindo autenticação com sucesso e tratamento de recusa de acesso.

---

## 🟡 Prioridade 2 (P2): Autenticação Tradicional (E-mail & Senha) e Recuperação

Permitir acesso para usuários que optem por não utilizar contas de redes sociais.

### 2.1 Cadastro & Login com E-mail e Senha
- [ ] Hashing seguro de senhas com algoritmo criptográfico robusto (`bcrypt` ou `argon2`).
- [ ] Validação rigorosa de formato de e-mail e regras de força de senha.
- [ ] Telas e formulários integrados ao modal com validação inline.

### 2.2 Recuperação de Senha via E-mail
- [ ] Criação de porta abstrata `EmailPort` e adaptador `SmtpEmailAdapter` (Gmail SMTP / transacional).
- [ ] Geração de tokens efêmeros seguros com tempo de expiração (30 min).
- [ ] Template HTML responsivo de e-mail com a identidade ThothSCV.
- [ ] Rota e tela para redefinição de senha (`/auth/reset-password?token=...`).
