---
name: i18n-locale-engine
description: Arquitetura de internacionalização multilíngue, manifesto LocaleRegistry e injeção dialetal para o Gemini.
---

# Skill: i18n Locale Engine

Esta skill orienta a gestão de idiomas e convenções regionais no ThothCVs AI.

## Idiomas Nativos
- `pt-BR` (Português Brasil)
- `pt-PT` (Português Portugal)
- `en-US` (English United States)
- `en-GB` (English United Kingdom)
- `es-ES` (Español)

## Diretrizes de Implementação
1. **Desacoplamento:** O idioma da UI é independente do idioma de geração do currículo.
2. **Manifesto Central:** Toda adição de novo idioma deve ser feita no `LocaleRegistry`, sem modificar lógica de negócio.
3. **Datas:** Mês e Ano exclusivamente, formatados conforme o locale.
