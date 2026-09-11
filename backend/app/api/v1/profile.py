"""Rotas da API para gerenciamento do Repositório Profissional (Dossiê).

Implementa operações completas de CRUD para experiências, formações,
certificações, projetos, competências e agregação do dossiê sob /api/v1/profile.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.api.v1.schemas.profile import (
    CertificationCreateRequest,
    CertificationResponse,
    CertificationUpdateRequest,
    EducationCreateRequest,
    EducationResponse,
    EducationUpdateRequest,
    ExperienceCreateRequest,
    ExperienceResponse,
    ExperienceUpdateRequest,
    FullDossierResponse,
    LanguageCreateRequest,
    LanguageResponse,
    LanguageUpdateRequest,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    SkillCreateRequest,
    SkillResponse,
    SkillUpdateRequest,
)
from app.core.database import get_db_session
from app.domain.models import User
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/profile", tags=["Repositório Profissional (Dossiê)"])


def get_profile_service(db: AsyncSession = Depends(get_db_session)) -> ProfileService:
    """Fábrica de injeção de dependência para o serviço de perfil."""
    return ProfileService(db=db)


# ==================== EXPERIÊNCIAS ====================
@router.post(
    "/experiences",
    response_model=ExperienceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra nova experiência profissional",
)
async def create_experience(
    body: ExperienceCreateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.create_experience(user_id=current_user.id, data=body.model_dump())


@router.get(
    "/experiences",
    response_model=list[ExperienceResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista experiências profissionais do usuário",
)
async def list_experiences(
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.list_experiences(user_id=current_user.id)


@router.get(
    "/experiences/{experience_id}",
    response_model=ExperienceResponse,
    status_code=status.HTTP_200_OK,
    summary="Recupera experiência por ID",
)
async def get_experience(
    experience_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    item = await service.get_experience(user_id=current_user.id, experience_id=experience_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiência não encontrada.",
        )
    return item


@router.put(
    "/experiences/{experience_id}",
    response_model=ExperienceResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza experiência profissional existente",
)
async def update_experience(
    experience_id: uuid.UUID,
    body: ExperienceUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    updated = await service.update_experience(
        user_id=current_user.id,
        experience_id=experience_id,
        data=body.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiência não encontrada.",
        )
    return updated


@router.delete(
    "/experiences/{experience_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclusão lógica (soft delete) da experiência",
)
async def delete_experience(
    experience_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> None:
    deleted = await service.delete_experience(user_id=current_user.id, experience_id=experience_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiência não encontrada.",
        )


# ==================== FORMAÇÃO ACADÊMICA ====================
@router.post(
    "/educations",
    response_model=EducationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra formação acadêmica",
)
async def create_education(
    body: EducationCreateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.create_education(user_id=current_user.id, data=body.model_dump())


@router.get(
    "/educations",
    response_model=list[EducationResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista formações acadêmicas",
)
async def list_educations(
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.list_educations(user_id=current_user.id)


@router.put(
    "/educations/{education_id}",
    response_model=EducationResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza formação acadêmica",
)
async def update_education(
    education_id: uuid.UUID,
    body: EducationUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    updated = await service.update_education(
        user_id=current_user.id,
        education_id=education_id,
        data=body.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formação acadêmica não encontrada.",
        )
    return updated


@router.delete(
    "/educations/{education_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui formação acadêmica",
)
async def delete_education(
    education_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> None:
    deleted = await service.delete_education(user_id=current_user.id, education_id=education_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Formação acadêmica não encontrada.",
        )


# ==================== CERTIFICAÇÕES ====================
@router.post(
    "/certifications",
    response_model=CertificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra certificação técnica",
)
async def create_certification(
    body: CertificationCreateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.create_certification(user_id=current_user.id, data=body.model_dump())


@router.get(
    "/certifications",
    response_model=list[CertificationResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista certificações técnicas",
)
async def list_certifications(
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.list_certifications(user_id=current_user.id)


@router.put(
    "/certifications/{certification_id}",
    response_model=CertificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza certificação técnica",
)
async def update_certification(
    certification_id: uuid.UUID,
    body: CertificationUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    updated = await service.update_certification(
        user_id=current_user.id,
        certification_id=certification_id,
        data=body.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificação não encontrada.",
        )
    return updated


@router.delete(
    "/certifications/{certification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui certificação técnica",
)
async def delete_certification(
    certification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> None:
    deleted = await service.delete_certification(
        user_id=current_user.id, certification_id=certification_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificação não encontrada.",
        )


# ==================== PROJETOS ====================
@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra projeto ou portfólio",
)
async def create_project(
    body: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.create_project(user_id=current_user.id, data=body.model_dump())


@router.get(
    "/projects",
    response_model=list[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista projetos do usuário",
)
async def list_projects(
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.list_projects(user_id=current_user.id)


@router.put(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza projeto existente",
)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    updated = await service.update_project(
        user_id=current_user.id,
        project_id=project_id,
        data=body.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto não encontrado.",
        )
    return updated


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui projeto do usuário",
)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> None:
    deleted = await service.delete_project(user_id=current_user.id, project_id=project_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Projeto não encontrado.",
        )


# ==================== COMPETÊNCIAS (SKILLS) ====================
@router.post(
    "/skills",
    response_model=SkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra competência técnica",
)
async def create_skill(
    body: SkillCreateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.create_skill(user_id=current_user.id, data=body.model_dump())


@router.get(
    "/skills",
    response_model=list[SkillResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista competências com filtro opcional por categoria",
)
async def list_skills(
    category: str | None = Query(default=None, description="Filtro opcional por categoria"),
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.list_skills(user_id=current_user.id, category=category)


@router.put(
    "/skills/{skill_id}",
    response_model=SkillResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza competência existente",
)
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    updated = await service.update_skill(
        user_id=current_user.id,
        skill_id=skill_id,
        data=body.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Competência não encontrada.",
        )
    return updated


@router.delete(
    "/skills/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui competência do usuário",
)
async def delete_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> None:
    deleted = await service.delete_skill(user_id=current_user.id, skill_id=skill_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Competência não encontrada.",
        )


# ==================== IDIOMAS ====================
@router.post(
    "/languages",
    response_model=LanguageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra idioma e nível de proficiência",
)
async def create_language(
    body: LanguageCreateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.create_language(user_id=current_user.id, data=body.model_dump())


@router.get(
    "/languages",
    response_model=list[LanguageResponse],
    status_code=status.HTTP_200_OK,
    summary="Lista idiomas dominados pelo usuário",
)
async def list_languages(
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.list_languages(user_id=current_user.id)


@router.put(
    "/languages/{language_id}",
    response_model=LanguageResponse,
    status_code=status.HTTP_200_OK,
    summary="Atualiza nível de idioma",
)
async def update_language(
    language_id: uuid.UUID,
    body: LanguageUpdateRequest,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    updated = await service.update_language(
        user_id=current_user.id,
        language_id=language_id,
        data=body.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Idioma não encontrado.",
        )
    return updated


@router.delete(
    "/languages/{language_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Exclui idioma do usuário",
)
async def delete_language(
    language_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> None:
    deleted = await service.delete_language(user_id=current_user.id, language_id=language_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Idioma não encontrado.",
        )


# ==================== DOSSIÊ COMPLETO ====================
@router.get(
    "/full",
    response_model=FullDossierResponse,
    status_code=status.HTTP_200_OK,
    summary="Consulta agregada de todo o dossiê profissional",
    description=(
        "Retorna todas as experiências, formações, certificações, "
        "projetos, skills e idiomas do usuário ativo."
    ),
)
@router.get(
    "/dossier",
    response_model=FullDossierResponse,
    status_code=status.HTTP_200_OK,
    summary="Alias para consulta agregada do dossiê profissional",
)
async def get_full_dossier(
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> Any:
    return await service.get_full_dossier(user_id=current_user.id)
