# ThothCVs AI - Gestão Inteligente de Currículos & ATS Pessoal

> **ThothCVs AI** é uma plataforma moderna e completa para gestão de carreira, síntese direcionada de currículos otimizados para sistemas ATS (Applicant Tracking Systems) e acompanhamento proativo de candidaturas em modelo de ATS Pessoal.

---

## 🚀 Principais Capacidades

1. **Dossiê Profissional (Master CV)**:
   - Repositório centralizado de dados pessoais, experiências, competências, formação, certificações e links.
   - Suporte a multi-idiomas nativo (`pt-BR`, `pt-PT`, `en-US`, `en-GB`, `es-ES`) e formatação uniforme de datas (mês/ano).

2. **Motor de IA & Pipeline Anti-Alucinação (Grounding Audit)**:
   - Integração com Google Gemini (`gemini-2.5-flash`) via SDK `google-genai` com Structured Outputs.
   - Auditoria estrita em 4 estágios: validação de entidades, cálculo de score de confiança (Grounding Trust Score), identificação de termos não fundamentados e auto-poda (*auto-pruning*).
   - Zero invenções: garantia matemática de que métricas, empresas ou cargos não existentes no dossiê jamais serão inseridos.

3. **Correspondência Semântica & Análise ATS (Vector Match Engine)**:
   - Cálculo ponderado de aderência (70% competências mandatórias, 30% desejáveis).
   - Identificação de lacunas de compatibilidade e recomendações de palavras-chave ATS.

4. **Renderização Determinística de Documentos (PDF & DOCX)**:
   - Exportação em **PDF** diagramado via HTML5/Jinja2 e WeasyPrint com regras estritas de quebra de página (`page-break-inside: avoid`).
   - Exportação em **DOCX** single-column nativo com `python-docx` para total compatibilidade com leitores de ATS legados.

5. **ATS Pessoal & Ciclo de Vida de Candidaturas (Kanban)**:
   - Acompanhamento das etapas: *Enviada*, *Triagem/RH*, *Entrevistas*, *Proposta*, *Não Selecionado*.
   - Detector de estagnação: sinaliza automaticamente candidaturas paradas há mais de 7 dias sem contato.
   - Métricas analíticas agregadas: taxa de conversão para entrevistas, taxa de ofertas e score médio de compatibilidade.

6. **Sistema de Notificações & Robô Proativo**:
   - Agendamento de alertas e lembretes de follow-up.
   - Disparo de varredura proativa de vagas esquecidas para evitar perda de oportunidades.

7. **Interface Acessível Next.js 15 (WCAG 2.1 AA)**:
   - Desenvolvida com Next.js 15 (App Router), Tailwind CSS e Lucide Icons.
   - Conformidade estrita WCAG: foco por teclado, modais acessíveis (*focus trap* e *Escape*), links de salto (*skip-to-content*), e independência de cor (status com ícone + cor + texto).

8. **Observabilidade & Rastreabilidade Distribuída de Ponta a Ponta**:
   - Logging estruturado com `structlog` agnóstico e adaptador nativo para Google Cloud Logging / Cloud Trace.
   - Rastreamento ponta a ponta com propagação contínua de `X-Correlation-ID` do frontend Next.js 15 aos serviços de backend FastAPI.
   - Telemetria de LLM Ops (latência, consumo de tokens, modelo e score de veracidade anti-alucinação).
   - Higienização automática e estrita de PII e segredos (tokens Bearer, senhas e API keys).
   - Error Boundaries acessíveis (Next.js 15 App Router) com exibição e cópia assistida de ID de Suporte para SRE.

---

## 🛠️ Arquitetura do Sistema

O sistema foi projetado sob os princípios de **Arquitetura Hexagonal (Ports & Adapters)** e **Clean Architecture**:

```
backend/
├── app/
│   ├── adapters/          # Implementações concretas (Gemini, WeasyPrint, DOCX, Firebase, GCP Logging)
│   ├── api/v1/            # Controllers FastAPI, rotas e dependências
│   │   └── schemas/       # Contratos Pydantic v2
│   ├── core/              # Configurações, banco assíncrono, i18n, criptografia, logging, telemetry e correlation
│   ├── domain/            # Modelos relacionais SQLAlchemy 2.0
│   ├── ports/             # Interfaces abstratas (AI, Documentos, Autenticação)
│   ├── services/          # Casos de uso e orquestração de negócio
│   └── templates/         # Templates Jinja2 para renderização de currículos
└── tests/                 # Suíte automatizada de testes unitários e de integração (216 testes)

frontend/
├── src/
│   ├── app/               # Next.js 15 App Router (layout, page, error boundaries)
│   ├── components/        # Componentes acessíveis Radix/Tailwind (Kanban, Drawer, Viewer, Modais)
│   ├── lib/               # Cliente HTTP ApiClient (com correlation ID) e módulo de telemetria
│   └── test/              # Suíte de testes unitários e componentes Vitest (123 testes)
```

---

## 📋 Pré-requisitos & Instalação

### Backend (Python 3.13 + UV)

1. Instale o gerenciador `uv`:
   ```bash
   pip install uv
   ```

2. Navegue até a pasta `backend/` e sincronize as dependências:
   ```bash
   cd backend
   uv sync
   ```

3. Configure o arquivo de ambiente `.env` (baseado em `.env.example`):
   ```env
   GEMINI_API_KEY="sua_chave_gemini"
   DATABASE_URL="sqlite+aiosqlite:///./thothcvs.db"
   AES_ENCRYPTION_KEY="sua_chave_secreta_32_bytes_para_aes_gcm"
   ```

4. Execute as migrations do Alembic:
   ```bash
   uv run alembic upgrade head
   ```

5. Inicie a API FastAPI:
   ```bash
   uv run uvicorn app.main:app --reload --port 8000
   ```

### Frontend (Next.js 15 + Node.js 22)

1. Navegue até a pasta `frontend/`:
   ```bash
   cd frontend
   npm install
   ```

2. Inicie o servidor de desenvolvimento:
   ```bash
   npm run dev
   ```

3. Para compilar a versão de produção:
   ```bash
   npm run build
   ```

---

## 🧪 Qualidade de Código & CI/CD Quality Gates

O projeto adota uma política rigorosa de **Test-Driven Development (TDD)**, tipagem estrita e **Quality Gates automatizados** no GitHub Actions:

```bash
# Backend: Testes com 100% de cobertura obrigatória
uv run pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=100

# Backend: Verificação estática de tipos e linter
uv run mypy app
uv run ruff check .
uv run ruff format --check .

# Frontend: Testes unitários com 100% de cobertura de linhas
npm run test:coverage

# Frontend: Linter e compilação de produção
npm run lint
npm run build

# Quality Gates de CI/CD
python scripts/check_hexagonal_architecture.py
python scripts/check_security_guardrails.py
```

- **Cobertura de Testes Backend:** 216 testes passando com 100.00% de cobertura em 50 arquivos.
- **Cobertura de Testes Frontend:** 123 testes passando com 100.00% de cobertura de linhas em 12 suítes.
- **Tipagem Mypy & TypeScript:** 0 erros de tipagem.
- **AST Architecture Gate:** 100% de conformidade com os limites da Arquitetura Hexagonal.
- **Security Anti-Regression Gate:** 100% blindado contra regressão em testes de segurança protegidos.

---

## 📄 Licença

Distribuído sob a licença MIT. Consulte o arquivo `LICENSE` para mais detalhes.
