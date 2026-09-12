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

