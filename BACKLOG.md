# 📋 Backlog de Tarefas — ThothSCV AI

Este documento centraliza as tarefas planejadas, melhorias e evolução contínua da plataforma **ThothSCV AI**, priorizadas por impacto e ordem de desenvolvimento.

---

## 🚦 Legenda de Status
- 🔴 **Prioridade 1 (P1):** Crítico / Próximo foco de desenvolvimento imediato.
- 🟡 **Prioridade 2 (P2):** Importante / Planejado para curto e médio prazo.
- 🟢 **Prioridade 3 (P3):** Melhorias contínuas, novas funcionalidades e expansões futuras.

| Ícone | Significado |
| :---: | :--- |
| ⏳ | **Pendente / A Fazer** |
| 🚧 | **Em Progresso** |
| ✅ | **Concluído** |

---

## 🔴 Prioridade 1 (P1): Autenticação Real & Provedores OAuth

O foco imediato é substituir os mocks de desenvolvimento pelas integrações reais de login social.

### 1.1 Conexão Real com Google OAuth 2.0
- [ ] **Configuração no Google Cloud Console:**
  - [ ] Criar projeto no Google Cloud / Firebase Auth (ou utilizar existente).
  - [ ] Configurar Tela de Consentimento OAuth (nome do app, logo, e-mails de suporte).
  - [ ] Gerar credenciais: `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`.
  - [ ] Cadastrar URI autorizada de redirecionamento: `http://localhost:8000/auth/callback/google` (e domínio de produção).
- [ ] **Implementação no Backend:**
  - [ ] Adicionar variáveis no `.env` e carregamento em `Settings` (`app/core/config.py`).
  - [ ] Criar rota de redirecionamento para o Google: `GET /auth/login/google`.
  - [ ] Criar rota de callback: `GET /auth/callback/google`.
  - [ ] Troca segura do `code` de autorização por tokens oficiais junto ao endpoint do Google (`https://oauth2.googleapis.com/token`).
  - [ ] Extração dos dados reais do usuário: `email`, `full_name`, `picture_url` e `sub` (Google ID).
  - [ ] Sincronização com o banco relacional e emissão do cookie HTTP-only `session_token`.
- [ ] **Garantia de Qualidade & Testes:**
  - [ ] Testes automatizados com mocks de rede simulando respostas oficiais da API do Google.
  - [ ] 100% de cobertura de código mantida.

---

### 1.2 Conexão Real com LinkedIn OAuth 2.0
- [ ] **Configuração no LinkedIn Developer Portal:**
  - [ ] Criar app no portal de desenvolvedores do LinkedIn.
  - [ ] Adicionar produto *"Sign In with LinkedIn using OpenID Connect"*.
  - [ ] Gerar `LINKEDIN_CLIENT_ID` e `LINKEDIN_CLIENT_SECRET`.
  - [ ] Configurar URI de retorno autorizada: `http://localhost:8000/auth/callback/linkedin`.
- [ ] **Implementação no Backend:**
  - [ ] Configurar variáveis no `app/core/config.py` e `.env`.
  - [ ] Implementar rotas `GET /auth/login/linkedin` e `GET /auth/callback/linkedin`.
  - [ ] Troca de código de autorização e consulta ao endpoint OpenID `/v2/userinfo`.
  - [ ] Persistência de dados cadastrais e foto de perfil.
- [ ] **Garantia de Qualidade & Testes:**
  - [ ] Testes de integração cobrindo fluxos felizes e de erro (usuário cancelou consentimento, token inválido).

---

## 🟡 Prioridade 2 (P2): Autenticação Clássica (E-mail/Senha) e Recuperação

Evolução futura para permitir contas sem vínculo com redes sociais.

### 2.1 Cadastro & Login Tradicional (E-mail & Senha)
- [ ] Hashing seguro de senhas com algoritmo robusto (`bcrypt` ou `argon2`).
- [ ] Validação de formato de e-mail e regras de força de senha (mínimo 8 dígitos, caractere especial).
- [ ] Formulário de login e cadastro integrado ao modal HTMX sem recarregar a página.

### 2.2 Recuperação de Senha via E-mail Transacional
- [ ] **Arquitetura Hexagonal de E-mail:**
  - [ ] Criar `EmailPort` abstrata em `app/ports/email_port.py`.
  - [ ] Criar adaptador `SmtpEmailAdapter` em `app/adapters/smtp_email_adapter.py` com suporte a Gmail SMTP e provedores transacionais (Resend/Brevo).
- [ ] **Segurança de Tokens:**
  - [ ] Gerador de tokens efêmeros via JWT (30 minutos de validade com claim de propósito restrito).
- [ ] **Templates & Páginas:**
  - [ ] Template HTML responsivo em Jinja2 com identidade visual ThothSCV.
  - [ ] Página/modal para digitação e confirmação de nova senha (`/auth/reset-password?token=...`).

---

## 🟢 Prioridade 3 (P3): Funcionalidades de Carreira e ATS

### 3.1 Dossiê Profissional (Master CV)
- [ ] Tela de gerenciamento do perfil do candidato (experiências, formação, skills).
- [ ] Importação de currículo existente via PDF/DOCX (extração inicial).

### 3.2 ATS Pessoal & Gestão de Candidaturas
- [ ] Quadro Kanban de vagas aplicadas (*Enviada*, *Entrevistas*, *Proposta*).
- [ ] Sistema de alerta de estagnação (> 7 dias sem contato).

### 3.3 Motor de IA (Gemini Grounding & Exportação)
- [ ] Tela de submissão de descrição de vaga (Job Description).
- [ ] Análise de match e aderência ATS.
- [ ] Geração de currículo customizado e exportação em PDF (WeasyPrint) e DOCX.
