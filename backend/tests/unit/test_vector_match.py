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


def test_match_mandatory_only_and_desirable_only() -> None:
    """Testa o cálculo do score quando a vaga possui apenas mandatórios ou apenas desejáveis."""
    engine = VectorMatchEngine()
    dossier = {
        "skills": ["Python", "FastAPI"],
        "experiences": [],
        "certifications": [],
    }

    # 1. Apenas requisitos mandatórios (num_des == 0)
    job_mand_only = JobAnalysisResult(
        job_title="Python Dev",
        seniority_level="Senior",
        mandatory_requirements=["Python"],
        desirable_requirements=[],
        keywords=["Python"],
    )
    res_mand = engine.evaluate_match(dossier=dossier, job_analysis=job_mand_only)
    assert res_mand.match_percentage == 100.0

    # 2. Apenas requisitos desejáveis (num_mand == 0)
    job_des_only = JobAnalysisResult(
        job_title="Junior Dev",
        seniority_level="Junior",
        mandatory_requirements=[],
        desirable_requirements=["FastAPI"],
        keywords=["FastAPI"],
    )
    res_des = engine.evaluate_match(dossier=dossier, job_analysis=job_des_only)
    assert res_des.match_percentage == 100.0

    # 3. Sem nenhum requisito cadastrado na vaga
    job_empty = JobAnalysisResult(
        job_title="General Role",
        seniority_level="Pleno",
        mandatory_requirements=[],
        desirable_requirements=[],
        keywords=[],
    )
    res_empty = engine.evaluate_match(dossier=dossier, job_analysis=job_empty)
    assert res_empty.match_percentage == 100.0


def test_match_in_experiences_regex_and_certifications() -> None:
    """Garante correspondência encontrada no histórico de experiência e nas certificações."""
    engine = VectorMatchEngine()
    dossier = {
        "skills": ["Python"],
        "experiences": [
            {
                "company_name": "DataCorp",
                "position_title": "Data Engineer",
                "tech_stack": [],
                "bullet_points": ["Construiu pipelines de dados em larga escala com Apache Spark."],
            }
        ],
        "certifications": ["CKA: Certified Kubernetes Administrator"],
    }

    job = JobAnalysisResult(
        job_title="Big Data & Cloud Specialist",
        seniority_level="Specialist",
        mandatory_requirements=["Apache Spark"],
        desirable_requirements=["Kubernetes"],
        keywords=["Spark", "Kubernetes"],
    )

    result = engine.evaluate_match(dossier=dossier, job_analysis=job)
    assert result.match_percentage >= 90.0
    assert any(
        m.requirement == "Apache Spark" and m.status == "matched" for m in result.mandatory_matches
    )
    assert any(
        m.requirement == "Kubernetes" and m.status == "matched" for m in result.desirable_matches
    )


def test_match_with_completely_empty_dossier() -> None:
    """Garante avaliação limpa (0% de match) para um candidato com perfil totalmente em branco."""
    engine = VectorMatchEngine()
    empty_dossier = {
        "skills": [],
        "experiences": [],
        "certifications": [],
    }
    job = JobAnalysisResult(
        job_title="DevOps Engineer",
        seniority_level="Senior",
        mandatory_requirements=["Terraform", "Ansible"],
        desirable_requirements=["AWS"],
        keywords=["Terraform", "Ansible", "AWS"],
    )

    result = engine.evaluate_match(dossier=empty_dossier, job_analysis=job)
    assert result.match_percentage == 0.0
    assert len(result.missing_mandatory) == 2
    assert len(result.missing_desirable) == 1
    assert len(result.suggested_keywords) == 3
