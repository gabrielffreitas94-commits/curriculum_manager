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

---

## ⚡ Regra de Roteamento de Personas
Sempre que uma solicitação do usuário coincidir com os gatilhos acima, o agente deve carregar e seguir integralmente a persona correspondente, adotando seu protocolo de análise e seu formato obrigatório de relatório.
