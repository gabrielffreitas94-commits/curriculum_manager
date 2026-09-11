"""Testes de integração para a gestão do Repositório Profissional (Dossiê).

Valida operações completas de CRUD, isolamento de tenant (multi-tenancy),
ordenação manual, soft delete e agregação completa do perfil.
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.ports.auth_port import AuthUser

USER_A_AUTH = AuthUser(
    uid="firebase_user_a",
    email="user_a@thothcvs.ai",
    full_name="Alice Candidate",
)

USER_B_AUTH = AuthUser(
    uid="firebase_user_b",
    email="user_b@thothcvs.ai",
    full_name="Bob Hacker",
)


@pytest.fixture
async def setup_users(async_client: AsyncClient) -> dict[str, str]:
    """Cria os usuários A e B isolados no banco de dados para os testes."""
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        res_a = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": "Bearer token_a"},
        )
        assert res_a.status_code == 200

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_B_AUTH):
        res_b = await async_client.post(
            "/api/v1/auth/sync",
            headers={"Authorization": "Bearer token_b"},
        )
        assert res_b.status_code == 200

    return {"token_a": "Bearer token_a", "token_b": "Bearer token_b"}


@pytest.mark.asyncio
async def test_experiences_crud_and_soft_delete(
    async_client: AsyncClient,
    setup_users: dict[str, str],
) -> None:
    """Testa criação, listagem ordenada, atualização e soft-delete de experiências."""
    headers_a = {"Authorization": setup_users["token_a"]}

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        # 1. Create Experience
        payload = {
            "company_name": "Acme Inc",
            "position_title": "Lead Software Engineer",
            "location": "São Paulo, SP",
            "work_model": "remote",
            "start_date": "2021-03-01",
            "end_date": None,
            "is_current": True,
            "description": "Liderança técnica e arquitetura de microsserviços escaláveis.",
            "bullet_points": ["Reduziu latência em 45%", "Liderou time de 8 engenheiros"],
            "tech_stack": ["FastAPI", "Python", "Docker", "PostgreSQL"],
            "quantifiable_results": ["Economia de $12k/mês em infraestrutura"],
            "sort_order": 0,
        }
        create_res = await async_client.post(
            "/api/v1/profile/experiences",
            headers=headers_a,
            json=payload,
        )
        assert create_res.status_code == 201
        exp_data = create_res.json()
        exp_id = exp_data["id"]
        assert exp_data["company_name"] == "Acme Inc"
        assert exp_data["tech_stack"] == ["FastAPI", "Python", "Docker", "PostgreSQL"]

        # 2. List Experiences
        list_res = await async_client.get(
            "/api/v1/profile/experiences",
            headers=headers_a,
        )
        assert list_res.status_code == 200
        items = list_res.json()
        assert len(items) == 1
        assert items[0]["id"] == exp_id

        # 3. Update Experience
        update_res = await async_client.put(
            f"/api/v1/profile/experiences/{exp_id}",
            headers=headers_a,
            json={"position_title": "Principal Architect"},
        )
        assert update_res.status_code == 200
        assert update_res.json()["position_title"] == "Principal Architect"

        # 4. Soft Delete Experience
        delete_res = await async_client.delete(
            f"/api/v1/profile/experiences/{exp_id}",
            headers=headers_a,
        )
        assert delete_res.status_code == 204

        # 5. Verify it does not appear in active list
        list_after_delete = await async_client.get(
            "/api/v1/profile/experiences",
            headers=headers_a,
        )
        assert list_after_delete.status_code == 200
        assert len(list_after_delete.json()) == 0


@pytest.mark.asyncio
async def test_tenant_isolation_boundary(
    async_client: AsyncClient,
    setup_users: dict[str, str],
) -> None:
    """Garante que o Usuário B nunca consiga acessar ou modificar dados do Usuário A."""
    headers_a = {"Authorization": setup_users["token_a"]}
    headers_b = {"Authorization": setup_users["token_b"]}

    # Usuário A cria uma experiência
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        create_res = await async_client.post(
            "/api/v1/profile/experiences",
            headers=headers_a,
            json={
                "company_name": "Confidential Corp",
                "position_title": "Secret Agent",
                "work_model": "remote",
                "start_date": "2020-01-01",
                "description": "Top secret projects.",
            },
        )
        assert create_res.status_code == 201
        exp_id = create_res.json()["id"]

    # Usuário B tenta listar (deve ver lista vazia para seu tenant)
    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_B_AUTH):
        list_res = await async_client.get(
            "/api/v1/profile/experiences",
            headers=headers_b,
        )
        assert list_res.status_code == 200
        assert len(list_res.json()) == 0

        # Usuário B tenta atualizar a experiência do Usuário A (deve retornar 404 Not Found)
        put_res = await async_client.put(
            f"/api/v1/profile/experiences/{exp_id}",
            headers=headers_b,
            json={"position_title": "Hacked Title"},
        )
        assert put_res.status_code == 404

        # Usuário B tenta deletar a experiência do Usuário A (deve retornar 404 Not Found)
        del_res = await async_client.delete(
            f"/api/v1/profile/experiences/{exp_id}",
            headers=headers_b,
        )
        assert del_res.status_code == 404


@pytest.mark.asyncio
async def test_full_dossier_aggregation(
    async_client: AsyncClient,
    setup_users: dict[str, str],
) -> None:
    """Testa cadastro de educação, certificação, projeto, skill e idioma e consulta do dossiê."""
    headers_a = {"Authorization": setup_users["token_a"]}

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        # 1. Add Education
        res_edu = await async_client.post(
            "/api/v1/profile/educations",
            headers=headers_a,
            json={
                "institution_name": "USP",
                "degree": "Bacharelado",
                "field_of_study": "Engenharia de Software",
                "start_date": "2015-02-01",
                "end_date": "2019-12-01",
            },
        )
        assert res_edu.status_code == 201

        # 2. Add Certification
        res_cert = await async_client.post(
            "/api/v1/profile/certifications",
            headers=headers_a,
            json={
                "name": "CKA Kubernetes",
                "issuing_organization": "CNCF",
                "issue_date": "2023-01-15",
            },
        )
        assert res_cert.status_code == 201

        # 3. Add Project
        res_proj = await async_client.post(
            "/api/v1/profile/projects",
            headers=headers_a,
            json={
                "title": "FastAPI Boilerplate",
                "description": "Template de microsserviço assíncrono.",
                "technologies": ["Python", "FastAPI"],
            },
        )
        assert res_proj.status_code == 201

        # 4. Add Skill
        res_skill = await async_client.post(
            "/api/v1/profile/skills",
            headers=headers_a,
            json={
                "name": "SQLAlchemy",
                "category": "backend",
                "proficiency_level": "expert",
                "years_of_experience": 4,
                "is_featured": True,
            },
        )
        assert res_skill.status_code == 201

        # 5. Add Language
        res_lang = await async_client.post(
            "/api/v1/profile/languages",
            headers=headers_a,
            json={
                "language_name": "Inglês",
                "proficiency_level": "fluent",
            },
        )
        assert res_lang.status_code == 201

        # 6. Query Full Dossier
        full_res = await async_client.get(
            "/api/v1/profile/full",
            headers=headers_a,
        )
        assert full_res.status_code == 200
        dossier = full_res.json()
        assert len(dossier["educations"]) == 1
        assert len(dossier["certifications"]) == 1
        assert len(dossier["projects"]) == 1
        assert len(dossier["skills"]) == 1
        assert len(dossier["languages"]) == 1
        assert dossier["skills"][0]["name"] == "SQLAlchemy"


@pytest.mark.asyncio
async def test_education_crud_and_not_found(
    async_client: AsyncClient,
    setup_users: dict[str, str],
) -> None:
    """Testa o ciclo de vida completo de formação acadêmica e tratamento de 404."""
    headers = {"Authorization": setup_users["token_a"]}

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        res = await async_client.post(
            "/api/v1/profile/educations",
            headers=headers,
            json={
                "institution_name": "MIT",
                "degree": "Mestrado",
                "field_of_study": "Inteligência Artificial",
                "start_date": "2021-09-01",
                "is_current": True,
            },
        )
        assert res.status_code == 201
        edu_id = res.json()["id"]

        # Atualiza
        up_res = await async_client.put(
            f"/api/v1/profile/educations/{edu_id}",
            headers=headers,
            json={"degree": "Mestrado em Ciências"},
        )
        assert up_res.status_code == 200
        assert up_res.json()["degree"] == "Mestrado em Ciências"

        # Exclui
        del_res = await async_client.delete(
            f"/api/v1/profile/educations/{edu_id}",
            headers=headers,
        )
        assert del_res.status_code == 204

        # 404 em exclusão repetida
        del_again = await async_client.delete(
            f"/api/v1/profile/educations/{edu_id}",
            headers=headers,
        )
        assert del_again.status_code == 404


@pytest.mark.asyncio
async def test_skills_and_languages_crud(
    async_client: AsyncClient,
    setup_users: dict[str, str],
) -> None:
    """Testa operações de competências com filtro por categoria e idiomas."""
    headers = {"Authorization": setup_users["token_a"]}

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        # Cria skill backend
        res_back = await async_client.post(
            "/api/v1/profile/skills",
            headers=headers,
            json={"name": "FastAPI", "category": "backend", "proficiency_level": "expert"},
        )
        assert res_back.status_code == 201
        skill_id = res_back.json()["id"]

        # Cria skill frontend
        res_front = await async_client.post(
            "/api/v1/profile/skills",
            headers=headers,
            json={"name": "Next.js", "category": "frontend", "proficiency_level": "advanced"},
        )
        assert res_front.status_code == 201

        # Filtra por categoria
        list_back = await async_client.get(
            "/api/v1/profile/skills?category=backend",
            headers=headers,
        )
        assert list_back.status_code == 200
        assert len(list_back.json()) == 1
        assert list_back.json()[0]["name"] == "FastAPI"

        # Atualiza skill
        up_skill = await async_client.put(
            f"/api/v1/profile/skills/{skill_id}",
            headers=headers,
            json={"proficiency_level": "master"},
        )
        assert up_skill.status_code == 200
        assert up_skill.json()["proficiency_level"] == "master"

        # Deleta skill
        del_skill = await async_client.delete(
            f"/api/v1/profile/skills/{skill_id}",
            headers=headers,
        )
        assert del_skill.status_code == 204

        # Cria, atualiza e deleta idioma
        res_lang = await async_client.post(
            "/api/v1/profile/languages",
            headers=headers,
            json={"language_name": "Espanhol", "proficiency_level": "intermediate"},
        )
        assert res_lang.status_code == 201
        lang_id = res_lang.json()["id"]

        up_lang = await async_client.put(
            f"/api/v1/profile/languages/{lang_id}",
            headers=headers,
            json={"proficiency_level": "advanced"},
        )
        assert up_lang.status_code == 200
        assert up_lang.json()["proficiency_level"] == "advanced"

        del_lang = await async_client.delete(
            f"/api/v1/profile/languages/{lang_id}",
            headers=headers,
        )
        assert del_lang.status_code == 204


@pytest.mark.asyncio
async def test_certifications_and_projects_lifecycle(
    async_client: AsyncClient,
    setup_users: dict[str, str],
) -> None:
    """Testa ciclo de vida de certificações e projetos pessoais."""
    headers = {"Authorization": setup_users["token_a"]}

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        # Certificação
        c_res = await async_client.post(
            "/api/v1/profile/certifications",
            headers=headers,
            json={
                "name": "Google Cloud Professional Architect",
                "issuing_organization": "Google Cloud",
                "issue_date": "2024-06-01",
            },
        )
        assert c_res.status_code == 201
        c_id = c_res.json()["id"]

        up_c = await async_client.put(
            f"/api/v1/profile/certifications/{c_id}",
            headers=headers,
            json={"credential_id": "GCP-12345"},
        )
        assert up_c.status_code == 200
        assert up_c.json()["credential_id"] == "GCP-12345"

        del_c = await async_client.delete(
            f"/api/v1/profile/certifications/{c_id}",
            headers=headers,
        )
        assert del_c.status_code == 204

        # Projeto
        p_res = await async_client.post(
            "/api/v1/profile/projects",
            headers=headers,
            json={
                "title": "Autonomous Agent",
                "description": "Multi-agent coding system",
                "technologies": ["Python", "FastAPI"],
            },
        )
        assert p_res.status_code == 201
        p_id = p_res.json()["id"]

        up_p = await async_client.put(
            f"/api/v1/profile/projects/{p_id}",
            headers=headers,
            json={"role": "Lead Architect"},
        )
        assert up_p.status_code == 200
        assert up_p.json()["role"] == "Lead Architect"

        del_p = await async_client.delete(
            f"/api/v1/profile/projects/{p_id}",
            headers=headers,
        )
        assert del_p.status_code == 204


@pytest.mark.asyncio
async def test_profile_entities_not_found_return_404(
    async_client: AsyncClient,
    setup_users: dict[str, str],
) -> None:
    """Garante resposta 404 consistente em todas as entidades filhas do perfil
    para IDs inexistentes.
    """
    import uuid

    headers = {"Authorization": setup_users["token_a"]}
    fake_id = uuid.uuid4()

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        # GET 404 na experiência (única entidade com rota GET /{id} individual)
        res_get_exp = await async_client.get(
            f"/api/v1/profile/experiences/{fake_id}", headers=headers
        )
        assert res_get_exp.status_code == 404

        entities = [
            "experiences",
            "educations",
            "certifications",
            "projects",
            "skills",
            "languages",
        ]
        for ent in entities:
            # PUT 404
            res_put = await async_client.put(
                f"/api/v1/profile/{ent}/{fake_id}", headers=headers, json={}
            )
            assert res_put.status_code == 404, f"PUT /profile/{ent}/{fake_id} deveria retornar 404"

            # DELETE 404
            res_del = await async_client.delete(f"/api/v1/profile/{ent}/{fake_id}", headers=headers)
            assert res_del.status_code == 404, (
                f"DELETE /profile/{ent}/{fake_id} deveria retornar 404"
            )


@pytest.mark.asyncio
async def test_get_full_dossier_endpoint(
    async_client: AsyncClient,
    setup_users: dict[str, str],
) -> None:
    """Valida os endpoints agregados GET /profile/full e GET /profile/dossier
    retornando todas as coleções do usuário.
    """
    headers = {"Authorization": setup_users["token_a"]}

    with patch("app.api.v1.deps.auth_adapter.verify_token", return_value=USER_A_AUTH):
        for endpoint in ["/api/v1/profile/full", "/api/v1/profile/dossier"]:
            res = await async_client.get(endpoint, headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert "experiences" in data
            assert "educations" in data
            assert "certifications" in data
            assert "projects" in data
            assert "skills" in data
            assert "languages" in data
