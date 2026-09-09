"""Testes unitários para o validador algorítmico anti-alucinação (GroundingAuditEngine)."""

import pytest

from app.core.grounding_audit import (
    AuditResult,
    GroundingAuditEngine,
    HallucinationSeverity,
)


@pytest.fixture
def sample_user_dossier() -> dict:
    """Retorna um dossiê factual representativo do candidato."""
    return {
        "companies": ["Acme Tech", "Beta Solutions"],
        "positions": ["Senior Software Engineer", "Backend Developer"],
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "Git"],
        "degrees": ["Bacharelado em Ciência da Computação"],
        "certifications": ["AWS Certified Developer"],
    }


def test_audit_perfect_grounding(sample_user_dossier: dict) -> None:
    """Garante que currículo com fatos cadastrados alcance 100% de confiança."""
    engine = GroundingAuditEngine()

    generated_content = {
        "selected_experiences": [
            {
                "company_name": "Acme Tech",
                "position_title": "Senior Software Engineer",
                "tech_stack": ["Python", "FastAPI", "PostgreSQL"],
                "bullet_points": ["Desenvolveu microsserviços em Python"],
            }
        ],
        "skills_highlighted": ["Python", "FastAPI", "Docker"],
        "education": [{"degree": "Bacharelado em Ciência da Computação"}],
        "certifications": [{"name": "AWS Certified Developer"}],
    }

    result: AuditResult = engine.audit(
        generated_content=generated_content,
        user_dossier=sample_user_dossier,
    )

    assert result.is_valid is True
    assert result.trust_score == 100.0
    assert len(result.hallucinations) == 0


def test_audit_detects_hallucinated_company(sample_user_dossier: dict) -> None:
    """Garante rejeição imediata caso a IA invente uma empresa onde o usuário nunca trabalhou."""
    engine = GroundingAuditEngine()

    generated_content = {
        "selected_experiences": [
            {
                "company_name": "Invented Fake Enterprise",  # Empresa alucinada
                "position_title": "Senior Software Engineer",
                "tech_stack": ["Python"],
                "bullet_points": ["Trabalho fictício"],
            }
        ],
        "skills_highlighted": ["Python"],
        "education": [],
        "certifications": [],
    }

    result: AuditResult = engine.audit(
        generated_content=generated_content,
        user_dossier=sample_user_dossier,
    )

    assert result.is_valid is False
    assert result.severity == HallucinationSeverity.CRITICAL
    assert any("Empresa não cadastrada" in h.description for h in result.hallucinations)


def test_audit_prunes_hallucinated_skills(sample_user_dossier: dict) -> None:
    """Testa a detecção e poda de skills inventadas pela IA que não constam no banco."""
    engine = GroundingAuditEngine()

    generated_content = {
        "selected_experiences": [
            {
                "company_name": "Acme Tech",
                "position_title": "Senior Software Engineer",
                "tech_stack": ["Python", "Rust", "Solidity"],  # Rust e Solidity fora do dossiê
                "bullet_points": ["Trabalhou com APIs"],
            }
        ],
        "skills_highlighted": ["Python", "Kubernetes", "Rust"],  # Não cadastrados
        "education": [],
        "certifications": [],
    }

    result: AuditResult = engine.audit(
        generated_content=generated_content,
        user_dossier=sample_user_dossier,
    )

    # Skills inventadas devem ser identificadas
    assert len(result.hallucinations) > 0
    assert result.trust_score < 100.0

    # Aplica sanitização automática (poda silenciosa de skills espúrias)
    sanitized = engine.sanitize(generated_content, result)
    assert "Rust" not in sanitized["skills_highlighted"]
    assert "Kubernetes" not in sanitized["skills_highlighted"]
    assert "Python" in sanitized["skills_highlighted"]
