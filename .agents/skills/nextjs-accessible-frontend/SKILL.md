---
name: nextjs-accessible-frontend
description: Desenvolvimento do frontend Next.js 15 (App Router) com Tailwind CSS, shadcn/ui e conformidade estrita WCAG 2.1 AA.
---

# Skill: Next.js Accessible Frontend (a11y)

Esta skill orienta o desenvolvimento da interface web do ThothCVs AI, focando em performance, estética limpa e acessibilidade universal.

## Regras de Acessibilidade (WCAG 2.1 AA)

1. **Radix UI Primitives:** Modais e popovers devem prender o foco (`focus trap`) e responder a `Escape`.
2. **Navegação por Teclado:** O Kanban de candidaturas e formulários de vaga devem ser 100% navegáveis por teclado (`Tab`, `Espaço`, `Enter`, `Setas`).
3. **Independência de Cor:** Requisitos da vaga devem apresentar cor + ícone semântico + texto textual explícito.
4. **TSDoc Obrigatório:** Todo componente deve documentar suas props e comportamento acessível via anotações `@a11y`.
