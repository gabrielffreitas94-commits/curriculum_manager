---
name: hexagonal-fastapi-backend
description: Diretrizes de arquitetura hexagonal, injeção de dependências e design de APIs com FastAPI e Pydantic v2.
---

# Skill: Hexagonal FastAPI Backend

Esta skill orienta a construção de serviços backend seguindo o padrão Hexagonal (Ports & Adapters) com FastAPI e Pydantic v2 no ThothCVs AI.

## Diretrizes de Estrutura

1. **`app/ports/`**: Define interfaces abstratas (`abc.ABC`) para cada ponto de contato externo (DB, IA, Storage, Auth, Notificações, Documentos).
2. **`app/adapters/`**: Implementações concretas das interfaces. Nunca importe adapters dentro de `domain` ou `ports`.
3. **`app/domain/`**: Entidades de negócio puras e regras invariantes.
4. **`app/services/`**: Casos de uso orquestrando domínio e portas.
5. **`app/api/v1/`**: Controladores HTTP enxutos que apenas recebem a requisição, validam via Pydantic, invocam o caso de uso e retornam a resposta.

## Padrão de Injeção de Dependências

```python
from fastapi import APIRouter, Depends
from app.ports.resume import ResumePort
from app.core.dependencies import get_resume_service

router = APIRouter(prefix="/resumes", tags=["Resumes"])

@router.post("/generate", response_model=ResumeResponseSchema)
async def generate_resume(
    payload: GenerateResumeRequestSchema,
    service: ResumePort = Depends(get_resume_service),
    current_user: User = Depends(get_current_user)
) -> ResumeResponseSchema:
    return await service.generate(user_id=current_user.id, payload=payload)
```
