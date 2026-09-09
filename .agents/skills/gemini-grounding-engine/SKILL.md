---
name: gemini-grounding-engine
description: Padrões de integração com o Google Gemini API via SDK google-genai, Structured Outputs e validação anti-alucinação.
---

# Skill: Gemini Grounding Engine & Anti-Alucinação

Esta skill orienta a integração com a API do Google Gemini, garantindo conformidade com a proposta de valor do ThothCVs AI: **veracidade factual absoluta**.

## Pipeline em 4 Estágios

1. **Estágio 1 (Job Parsing):** `gemini-1.5-flash` decompõe a vaga em requisitos mandatórios e desejáveis.
2. **Estágio 2 (Grounding Context):** Injeção fechada e restritiva apenas dos fatos reais do usuário cadastrados no PostgreSQL.
3. **Estágio 3 (Constrained Generation):** Uso de **Structured Outputs** nativo do Gemini (`response_mime_type="application/json"`) associado ao modelo Pydantic `FullGeneratedResumePayload`.
4. **Estágio 4 (Auditoria Algorítmica):** Validador pós-geração em Python puro que confere similaridade de empresas/cargos, realiza interseção estrita das skills e valida métricas numéricas contra o banco.
