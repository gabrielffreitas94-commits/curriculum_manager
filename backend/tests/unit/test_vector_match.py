"""Testes unitários do motor de correspondência semântica e matriz de match (VectorMatchEngine).

Valida o cálculo determinístico de aderência de perfil, identificação de requisitos
atendidos, parciais e ausentes, e sugestão de palavras-chave ATS sem alucinação.
"""

import pytest

from app.core.vector_match import VectorMatchEngine
from app.ports.ai_port import JobAnalysisResult


@pytest.fixture
def sample_dossier() -> dict:
    """Fixture com perfil técnico do candidato para teste de match."""
    return {
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "GCP"],
        "experiences": [
            {
                "company_name": "CloudWorks",
                "position_title": "Backend Engineer",
                "tech_stack": ["Python", "GCP", "PostgreSQL"],
                "bullet_points": ["Construiu microsserviços em Python e Cloud Run."],
            }
        ],
        "certifications": ["Google Cloud Professional Cloud Architect"],
    }


def test_perfect_match_score(sample_dossier: dict) -> None:
    """Verifica score de 100% quando todos os requisitos da vaga estão presentes."""
    engine = VectorMatchEngine()
    job_analysis = JobAnalysisResult(
        job_title="Python Cloud Engineer",
        seniority_level="Senior",
        mandatory_requirements=["Python", "GCP"],
        desirable_requirements=["Docker"],
        keywords=["Python", "GCP", "Docker", "Microservices"],
    )

    result = engine.evaluate_match(dossier=sample_dossier, job_analysis=job_analysis)

    assert result.match_percentage == 100.0
    assert len(result.missing_mandatory) == 0
    assert len(result.missing_desirable) == 0
    assert any(
        m.requirement == "Python" and m.status == "matched" for m in result.mandatory_matches
    )


def test_partial_match_with_missing_requirements(sample_dossier: dict) -> None:
    """Verifica penalização de pontuação e identificação de gaps em requisitos ausentes."""
    engine = VectorMatchEngine()
    job_analysis = JobAnalysisResult(
        job_title="Senior Polyglot Architect",
        seniority_level="Lead",
        mandatory_requirements=["Python", "Rust", "Kubernetes"],
        desirable_requirements=["GCP", "GraphQL"],
        keywords=["Python", "Rust", "Kubernetes", "GCP", "GraphQL"],
    )

    result = engine.evaluate_match(dossier=sample_dossier, job_analysis=job_analysis)

    assert result.match_percentage < 100.0
    assert "Rust" in result.missing_mandatory
    assert "Kubernetes" in result.missing_mandatory
    assert "GraphQL" in result.missing_desirable
    # Palavras-chave faltantes para atenção do usuário
    assert "Rust" in result.suggested_keywords
