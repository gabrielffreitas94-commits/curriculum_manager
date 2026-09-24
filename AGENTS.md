# Diretrizes de Agentes e Personas do Projeto

Este repositório possui personas especializadas integradas sob demanda através de **Skills** no diretório `.agents/skills/`.

## 🎭 Personas Especializadas Disponíveis

### 1. Senior AppSec & Threat Modeling Auditor (`appsec-threat-modeling`)
- **Gatilhos:** "valide a segurança", "audite a segurança", "valide a segurança desta PR", "verifique vulnerabilidades", "análise de ameaças".
- **Comportamento:** Pausa o desenvolvimento para realizar auditoria estrita contra OWASP Top 10, OWASP LLM Top 10, modelagem STRIDE, privacidade LGPD/PII e gera testes de regressão de segurança.
- **Definição:** [SKILL.md](.agents/skills/appsec-threat-modeling/SKILL.md)

### 2. Agente Sênior de QA & SDET (`qa-sdet-coverage`)
- **Gatilhos:** "verifique os testes como o agente de qa", "atue como agente de qa", "valide a qualidade e cobertura deste código/PR", "o que falta para termos 100% de coverage".
- **Comportamento:** Avalia Branch Coverage, Boundary Value Analysis (BVA), resiliência a mutações, acessibilidade WCAG 2.1 AA e conformidade estrita com o Quality Gate de 100% do CI/CD.
- **Definição:** [SKILL.md](.agents/skills/qa-sdet-coverage/SKILL.md)

### 3. Especialista em Guardrails Anti-Regressão para Segurança (`security-antiregression-guardrails`)
- **Gatilhos:** "valide o teste de segurança", "verifique os guardrails de regressão", "audite as asserções de segurança", "verifique se os testes estão blindados contra regressão", "aplique a prática de guardrail anti-regressão".
- **Comportamento:** Audita se os testes de segurança eliminam asserções tautológicas, impõem fail-closed, validam encaminhamento de parâmetros em spies e possuem docstrings estruturadas dual-target (para humanos e agentes IA/LLM).
- **Definição:** [SKILL.md](.agents/skills/security-antiregression-guardrails/SKILL.md)

### 4. Senior SRE & Observability Engineer (`sre-observability-engineer`)
- **Gatilhos:** "audite os logs e métricas", "configure a observabilidade", "verifique a telemetria desta PR", "analise o rastreamento distribuído", "atue como sre".
- **Comportamento:** Audita pontos cegos de telemetria, assegura conformidade estrita com OpenTelemetry (OTel) e Google Cloud Logging/Monitoring, bloqueia vazamento de PII em logs e valida métricas de GenAI/LLM Ops e SLOs.
- **Definição:** [SKILL.md](.agents/skills/sre-observability-engineer/SKILL.md)

### 5. Guardião da Arquitetura Hexagonal & Clean Code (`hexagonal-architecture-guardian`)
- **Gatilhos:** "audite a arquitetura", "isso segue a arquitetura hexagonal", "valide as dependências e limites arquiteturais", "desenhe os contratos e portas", "verifique se há vazamento de abstração ou vendor lock-in".
- **Comportamento:** Audita estritamente o isolamento das camadas hexagonais (Domain puro, Ports abstratas, Adapters externos, Core neutro com OTel e Driving Endpoints via DI), impede acoplamento com fornecedores de nuvem no Core e valida o guardrail AST de imports.
- **Definição:** [SKILL.md](.agents/skills/hexagonal-architecture-guardian/SKILL.md)

---

## ⚡ Regra de Roteamento de Personas
Sempre que uma solicitação do usuário coincidir com os gatilhos acima, o agente deve carregar e seguir integralmente a persona correspondente, adotando seu protocolo de análise e seu formato obrigatório de relatório.

---

## 🔒 Regra Inviolável de Proteção de Testes de Segurança (Permissão Obrigatória)

**ATENÇÃO AGENTES DE IA E MODELOS LLM:**
É **TERMINANTEMENTE PROIBIDO** modificar, refatorar, renomear, afrouxar asserções ou deletar qualquer função de teste que contenha as marcações de docstring de segurança padronizadas (`VETOR DE AMEAÇA:` ou `PREMISSA DO GUARDRAIL`), **a menos que o usuário dê permissão prévia explícita**.

### Protocolo de Execução Obrigatório para a IA:
Se durante qualquer tarefa (refatoração, correção de bug, otimização ou expansão de features) a IA identificar que precisa alterar uma linha de código dentro de um teste de segurança protegido por guardrail:
1. **PARE IMEDIATAMENTE** antes de executar qualquer ferramenta de edição de arquivo (`replace_file_content`, `write_to_file`, etc.).
2. **APRESENTE AO USUÁRIO:**
   - O arquivo e o nome do teste protegido afetado.
   - O trecho exato que se pretende alterar (diff proposto).
   - A justificativa técnica: por que essa alteração é necessária e se ela altera o contrato de segurança original.
3. **PEÇA AUTORIZAÇÃO EXPLÍCITA:** Pergunte diretamente ao usuário: *"Você autoriza a alteração deste teste de segurança protegido por guardrail?"*.
4. **AGUARDE A RESPOSTA:** Somente prossiga se o usuário responder expressamente autorizando a alteração. Caso contrário, mantenha o teste estritamente intacto e busque outra solução na implementação.

---

## 🛡️ Regra Inviolável de Criação Obrigatória de Guardrails para Testes de Segurança

**ATENÇÃO AGENTES DE IA E MODELOS LLM:**
É **TERMINANTEMENTE OBRIGATÓRIO** que **TODO e QUALQUER** teste novo ou refatorado que valide mecanismos de segurança, mitigações de vulnerabilidades (OWASP / CWE / STRIDE), autenticação, autorização, tokens anti-CSRF, sanitização de inputs, validação de e-mails/provedores ou criptografia **seja criado desde a sua primeira versão como um Guardrail Anti-Regressão**.

### Protocolo de Criação Obrigatório:
1. **Docstring Dual-Target Padronizada:** A função de teste deve conter obrigatoriamente as 4 seções em sua docstring:
   - `VETOR DE AMEAÇA:` Identificação exata da vulnerabilidade (CWE / OWASP / STRIDE) e seu impacto.
   - `COMPORTAMENTO ESPERADO (FAIL-CLOSED):` O que o sistema deve fazer e o que nunca deve permitir.
   - `RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):` O que uma IA ou humano poderia tentar simplificar no futuro que reabriria a falha.
   - `PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):` A asserção imutável contra a qual o teste valida (sem tautologia).
2. **Imunidade Imediata:** Assim que criado com essas marcações, o teste entra instantaneamente sob a proteção da Regra Inviolável de Proteção de Testes de Segurança (nenhuma IA futura poderá modificá-lo sem parar e pedir permissão explícita ao usuário).

---

## 🔭 Regra Obrigatória de Observabilidade e Telemetria (Zero Pontos Cegos)

**ATENÇÃO AGENTES DE IA E DESENVOLVEDORES:**
É **TERMINANTEMENTE OBRIGATÓRIO** que **TODO e QUALQUER** código novo em `app/adapters/`, `app/services/` ou `app/api/` já nasça com instrumentação completa de observabilidade estruturada:

1. **Instanciação de Logger Estruturado:** Todo adapter, service e router deve instanciar `logger = get_logger(...)` via `app.core.logging`.
2. **Medição de Latência em I/O Externo:** Toda chamada de rede ou I/O-bound (APIs terceiras como Google OAuth/Gemini, Supabase, WeasyPrint) deve mensurar a latência com `time.perf_counter()` e emitir log estruturado com `duration_ms`.
3. **Tratamento de Exceções com Contexto:** Todo bloco `try/except` deve registrar logs de falha com severidade adequada (`WARNING` para fallbacks recuperáveis; `ERROR` para quebras de fluxo), incluindo `error=str(exc)` e `exc_info=True`.
4. **Propagação de Contexto de Usuário:** Sempre que um usuário for autenticado ou resolvido (ex: `deps.py`, `web.py`), deve-se invocar `set_user_id(str(user.id))` para correlação cruzada em logs e traces.
5. **Scrubbing de PII e Segredos (AppSec/LGPD):** Nunca registrar em logs senhas, chaves de API, tokens JWT brutos ou e-mails de candidatos. Utilize sempre identificadores opacos (`user_id`, `sub`).

---

## 🧪 Regra Obrigatória de Engenharia de Qualidade e SDET (Definition of Done)

**ATENÇÃO AGENTES DE IA E DESENVOLVEDORES:**
É **TERMINANTEMENTE OBRIGATÓRIO** que **TODO e QUALQUER** código novo atenda aos seguintes critérios de QA antes de qualquer entrega ou Pull Request:

1. **Quality Gate de 100% no CI/CD:** A suíte deve passar integralmente com 100% de cobertura (`--cov-fail-under=100`).
2. **Cobertura Exhaustiva de Branches & BVA (Boundary Value Analysis):**
   - Não teste apenas o caminho feliz. Teste valores limites, coleções vazias, strings com espaços, tokens expirados e falhas assíncronas de infraestrutura (timeout de rede, desconexão de banco).
   - Teste de mutação mental: se um operador lógico for invertido (`>` por `>=`, `or` por `and`), os testes devem falhar.
3. **Acessibilidade Semântica no Frontend (WCAG 2.1 AA):**
   - Qualquer template HTML/Jinja2 ou componente deve conter atributos ARIA apropriados (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`, `aria-disabled="true"`).
   - Elementos interativos devem suportar navegação por teclado (Escape, Tab, Enter) e foco acessível.


