"""Testes unitários diretos para os endpoints de rotas (users.py, notifications.py, resumes.py).

Garante 100% de cobertura nos métodos e retornos de respostas de streaming, fábricas
e atualização de preferências.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request

from app.api.v1.notifications import (
    get_notification_service,
    get_unread_count,
    list_notifications,
    mark_all_as_read,
    mark_as_read,
    scan_follow_ups,
)
from app.api.v1.resumes import (
    analyze_job,
    copilot_chat,
    export_resume_docx,
    export_resume_pdf,
    generate_resume,
    get_resume_service,
    ingest_job_from_document,
    ingest_job_from_url,
    list_prompt_skills,
    match_preview,
)
from app.api.v1.schemas.notification import UnreadCountResponse
from app.api.v1.schemas.resume import (
    CopilotChatRequest,
    CopilotMessageSchema,
    JobAnalyzeRequest,
    JobUrlIngestRequest,
    MatchPreviewRequest,
    ResumeGenerateRequest,
)
from app.api.v1.schemas.user import UserSettingsUpdateRequest
from app.api.v1.users import get_my_settings, update_my_settings
from app.domain.models import PromptSkill, User


@pytest.fixture
def mock_user() -> User:
    user = User(
        id=uuid.uuid4(),
        firebase_uid="uid_router_123",
        email="router@test.com",
        full_name="Router User",
        is_active=True,
    )
    user.settings = None
    return user


@pytest.mark.asyncio
async def test_users_router_direct(mock_user: User) -> None:
    """Valida todos os endpoints de users.py diretamente."""
    # 1. get_my_settings com settings = None
    settings_resp1 = await get_my_settings(current_user=mock_user)
    assert settings_resp1.has_gemini_key is False
    assert settings_resp1.preferred_language == "pt-BR"

    # 3. update_my_settings quando settings é None (criação sob demanda)
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    body_create = UserSettingsUpdateRequest(
        gemini_api_key="AIzaSyTestDirectKey123",
        preferred_language="en-US",
        email_notifications_enabled=False,
        in_app_notifications_enabled=False,
        default_prompt_skill_id=uuid.uuid4(),
    )
    res_up1 = await update_my_settings(body=body_create, current_user=mock_user, db=db)
    assert res_up1.has_gemini_key is True
    assert res_up1.preferred_language == "en-US"
    assert res_up1.email_notifications_enabled is False
    assert res_up1.in_app_notifications_enabled is False

    # 4. update_my_settings limpando a chave com string vazia
    body_clear = UserSettingsUpdateRequest(gemini_api_key="   ")
    res_up2 = await update_my_settings(body=body_clear, current_user=mock_user, db=db)
    assert res_up2.has_gemini_key is False


@pytest.mark.asyncio
async def test_notifications_router_direct(mock_user: User) -> None:
    """Valida todos os endpoints de notifications.py diretamente."""
    service = MagicMock()
    db = MagicMock()

    # Factory
    factory_service = get_notification_service(db=db)
    assert factory_service is not None

    # list_notifications
    service.list_notifications = AsyncMock(return_value=[])
    res_list = await list_notifications(unread_only=True, current_user=mock_user, service=service)
    assert res_list == []

    # get_unread_count
    service.get_unread_count = AsyncMock(return_value=5)
    res_count = await get_unread_count(current_user=mock_user, service=service)
    assert isinstance(res_count, UnreadCountResponse)
    assert res_count.unread_count == 5

    # mark_as_read
    notif_id = uuid.uuid4()
    service.mark_as_read = AsyncMock(return_value={"id": notif_id, "is_read": True})
    res_read = await mark_as_read(notification_id=notif_id, current_user=mock_user, service=service)
    assert res_read["is_read"] is True

    # mark_all_as_read
    service.mark_all_as_read = AsyncMock(return_value=3)
    res_all = await mark_all_as_read(current_user=mock_user, service=service)
    assert res_all.updated_count == 3

    # scan_follow_ups
    service.scan_and_generate_follow_ups = AsyncMock(return_value=2)
    res_scan = await scan_follow_ups(current_user=mock_user, service=service)
    assert res_scan.created_count == 2


@pytest.mark.asyncio
async def test_resumes_router_direct(mock_user: User) -> None:
    """Valida todos os endpoints de resumes.py diretamente."""
    db = MagicMock()
    resume_service = MagicMock()
    doc_service = MagicMock()

    # Factory
    assert get_resume_service(db=db) is not None

    desc = "Descrição da oportunidade profissional com requisitos para teste."
    mock_request = MagicMock(spec=Request)
    mock_request.client = MagicMock(host="127.0.0.1")

    # analyze_job
    resume_service.analyze_job = AsyncMock(return_value={"job_title": "Dev"})
    res_an = await analyze_job(
        request=mock_request,
        body=JobAnalyzeRequest(job_description=desc),
        current_user=mock_user,
        service=resume_service,
    )
    assert res_an == {"job_title": "Dev"}

    # match_preview
    resume_service.match_preview = AsyncMock(return_value={"match_percentage": 90.0})
    res_mp = await match_preview(
        request=mock_request,
        body=MatchPreviewRequest(job_description=desc),
        current_user=mock_user,
        service=resume_service,
    )
    assert res_mp == {"match_percentage": 90.0}

    # generate_resume
    resume_service.generate_resume = AsyncMock(return_value={"resume_id": uuid.uuid4()})
    res_gen = await generate_resume(
        request=mock_request,
        body=ResumeGenerateRequest(job_description=desc),
        current_user=mock_user,
        service=resume_service,
    )
    assert "resume_id" in res_gen

    # export_resume_pdf
    rid = uuid.uuid4()
    doc_service.export_pdf = AsyncMock(return_value=(b"%PDF-1.4", "cv.pdf"))
    pdf_resp = await export_resume_pdf(resume_id=rid, current_user=mock_user, service=doc_service)
    assert pdf_resp.status_code == 200
    assert pdf_resp.media_type == "application/pdf"
    assert pdf_resp.body == b"%PDF-1.4"

    # export_resume_docx
    doc_service.export_docx = AsyncMock(return_value=(b"PK\x03\x04", "cv.docx"))
    docx_resp = await export_resume_docx(resume_id=rid, current_user=mock_user, service=doc_service)
    assert docx_resp.status_code == 200
    assert "openxmlformats" in docx_resp.media_type
    assert docx_resp.body == b"PK\x03\x04"

    # list_prompt_skills
    prompt_service = MagicMock()
    mock_skill = PromptSkill(
        id=uuid.uuid4(),
        slug="google-xyz",
        name="Google XYZ",
        description="Fórmula de impacto",
        category="methodology",
        system_prompt="Instruções",
        default_language="pt-BR",
        is_system_default=True,
    )
    prompt_service.list_active_skills = AsyncMock(return_value=[mock_skill])
    skills_resp = await list_prompt_skills(current_user=mock_user, service=prompt_service)
    assert len(skills_resp) == 1
    assert skills_resp[0].slug == "google-xyz"

    # ingest_job_from_url
    ingest_service = MagicMock()
    ingest_service.extract_text_from_url = AsyncMock(return_value="Conteúdo da vaga extraído.")
    url_resp = await ingest_job_from_url(
        body=JobUrlIngestRequest(url="https://jobs.example.com/123"),
        current_user=mock_user,
        service=ingest_service,
    )
    assert url_resp.source_type == "url"
    assert url_resp.job_description == "Conteúdo da vaga extraído."

    # ingest_job_from_document
    ingest_service.extract_text_from_document = MagicMock(return_value="Texto do documento PDF.")
    mock_upload = MagicMock()
    mock_upload.filename = "vaga.pdf"
    mock_upload.read = AsyncMock(return_value=b"%PDF-1.4 mock")
    doc_ingest_resp = await ingest_job_from_document(
        file=mock_upload,
        current_user=mock_user,
        service=ingest_service,
    )
    assert doc_ingest_resp.source_type == "document"
    assert doc_ingest_resp.job_description == "Texto do documento PDF."

    # copilot_chat
    copilot_service = MagicMock()
    copilot_service.chat = AsyncMock(return_value="Sugestão de tailoring do Copilot.")
    copilot_resp = await copilot_chat(
        body=CopilotChatRequest(
            job_description=desc,
            prompt_skill_slug="google-xyz",
            messages=[CopilotMessageSchema(role="user", content="Como destacar meus resultados?")],
        ),
        current_user=mock_user,
        service=copilot_service,
    )
    assert copilot_resp.reply == "Sugestão de tailoring do Copilot."
