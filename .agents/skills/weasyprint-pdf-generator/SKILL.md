---
name: weasyprint-pdf-generator
description: Geração determinística de currículos em PDF e DOCX via WeasyPrint, templates Jinja2 e tipografia amigável para ATS.
---

# Skill: WeasyPrint PDF & DOCX Generator

Esta skill orienta a criação e renderização de currículos com layout milimétrico e fidelidade vetorial.

## Diretrizes de Renderização

1. **HTML Semântico:** Templates Jinja2 usando tags estruturadas (`<header>`, `<main>`, `<section>`, `<h1>`, `<h2>`, `<ul>`, `<li>`).
2. **CSS Paged Media (`@page`):**
   - Configurar margens adequadas (ex: `margin: 15mm 12mm`).
   - Evitar quebras de página desagradáveis com `break-inside: avoid` em blocos de experiências.
3. **Formatação de Datas:**
   - Datas sempre formatadas exclusivamente em **Mês/Ano** (`MM/yyyy` ou `MMM yyyy`) de acordo com o `LocaleMetadata`.
