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

---

## ⚡ Regra de Roteamento de Personas
Sempre que uma solicitação do usuário coincidir com os gatilhos acima, o agente deve carregar e seguir integralmente a persona correspondente, adotando seu protocolo de análise e seu formato obrigatório de relatório.
