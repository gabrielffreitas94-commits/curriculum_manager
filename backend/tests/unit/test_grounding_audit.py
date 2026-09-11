"""Testes unitários para o validador algorítmico anti-alucinação (GroundingAuditEngine)."""

import pytest

from app.core.grounding_audit import (
    AuditResult,
    GroundingAuditEngine,
    HallucinationSeverity,
    ValidationTier,
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


def test_cascade_tier2_provenance_validation(sample_user_dossier: dict) -> None:
    """Testa aprovação pela Camada 2 (Proveniência) onde a IA cita o termo original do dossiê."""
    engine = GroundingAuditEngine()

    # Adiciona "Amazon Web Services" ao dossiê
    sample_user_dossier["skills"].append("Amazon Web Services")

    # A IA gerou a sigla "AWS", mas informou a proveniência original no provenance_map
    generated_content = {
        "selected_experiences": [
            {
                "company_name": "Acme Tech",
                "position_title": "Senior Software Engineer",
                "tech_stack": ["Python", "AWS"],
                "bullet_points": ["Infraestrutura cloud"],
            }
        ],
        "skills_highlighted": ["AWS"],
        "provenance_map": {
            "AWS": "Amazon Web Services",
        },
    }

    result = engine.audit(generated_content=generated_content, user_dossier=sample_user_dossier)
    assert result.is_valid is True
    assert result.trust_score == 100.0
    assert result.verified_counts_by_tier.get("provenance", 0) >= 2


def test_cascade_tier3_fuzzy_matching(sample_user_dossier: dict) -> None:
    """Testa aprovação pela Camada 3 (Fuzzy Matching ~85%) para variações de grafia."""
    engine = GroundingAuditEngine()

    # No dossiê temos "PostgreSQL", a IA gerou "Postgres" sem provenance_map
    # SequenceMatcher("postgres", "postgresql").ratio() == 0.888 (88.9% >= 85%)
    generated_content = {
        "selected_experiences": [
            {
                "company_name": "Acme Tech",
                "position_title": "Senior Software Engineer",
                "tech_stack": ["Python", "Postgres"],
                "bullet_points": ["Banco relacional"],
            }
        ],
        "skills_highlighted": ["Python", "Postgres"],
    }

    result = engine.audit(generated_content=generated_content, user_dossier=sample_user_dossier)
    assert result.is_valid is True
    # Média ponderada dos 5 fatos: 3 sintáticos (1.0) e 2 fuzzy (0.90) -> 4.80 / 5 = 96.0%
    assert result.trust_score == 96.0
    assert result.verified_counts_by_tier.get("fuzzy", 0) >= 2


def test_cascade_tier4_vector_validation_with_embeddings(sample_user_dossier: dict) -> None:
    """Testa aprovação pela Camada 4 (Vetorial) usando embeddings para termos correlacionados."""
    engine = GroundingAuditEngine()

    # Dossiê possui "Go" cadastrado
    sample_user_dossier["skills"].append("Go")

    # A IA gerou "Golang" (distância sintática ratio ~0.50, reprovada em fuzzy)
    generated_content = {
        "selected_experiences": [
            {
                "company_name": "Acme Tech",
                "position_title": "Senior Software Engineer",
                "tech_stack": ["Python", "Golang"],
                "bullet_points": ["Desenvolveu em Go"],
            }
        ],
        "skills_highlighted": ["Golang"],
    }

    # Fornece vetores de embeddings semânticos densos para Go e Golang
    mock_embeddings = {
        "Golang": [0.95, 0.05, 0.0],
        "Go": [0.93, 0.07, 0.0],
        "Python": [0.1, 0.9, 0.0],
    }

    result = engine.audit(
        generated_content=generated_content,
        user_dossier=sample_user_dossier,
        vector_embeddings=mock_embeddings,
    )

    assert result.is_valid is True
    # Média ponderada dos 4 fatos: 2 sintáticos (1.0) e 2 vetoriais (0.85) -> 3.70 / 4 = 92.5%
    assert result.trust_score == 92.5
    assert result.verified_counts_by_tier.get("vector", 0) >= 2


def test_cascade_all_tiers_fail_for_true_hallucination(sample_user_dossier: dict) -> None:
    """Garante rejeição quando uma tecnologia inventada falha em todas as 4 camadas do pipeline."""
    engine = GroundingAuditEngine()

    # IA inventou "QuantumBlockchainAI"
    generated_content = {
        "selected_experiences": [
            {
                "company_name": "Acme Tech",
                "position_title": "Senior Software Engineer",
                "tech_stack": ["Python", "QuantumBlockchainAI"],
                "bullet_points": ["Alucinação"],
            }
        ],
        "skills_highlighted": ["QuantumBlockchainAI"],
        "provenance_map": {
            "QuantumBlockchainAI": "NonExistentSource",
        },
    }

    result = engine.audit(generated_content=generated_content, user_dossier=sample_user_dossier)
    assert result.is_valid is False
    assert any("QuantumBlockchainAI" in h.hallucinated_value for h in result.hallucinations)
    assert any("reprovada em todas as camadas" in h.description for h in result.hallucinations)

    # Verifica se a poda remove a habilidade
    sanitized = engine.sanitize(generated_content, result)
    assert "QuantumBlockchainAI" not in sanitized["skills_highlighted"]
    assert "QuantumBlockchainAI" not in sanitized["selected_experiences"][0]["tech_stack"]


def test_audit_vector_evaluator_callable_and_zero_norms(sample_user_dossier: dict) -> None:
    """Testa o suporte a vector_evaluator customizado e tratamento de vetores nulos."""
    engine = GroundingAuditEngine()

    # 1. Cosseno com norma zero deve retornar 0.0 seguramente
    assert engine._cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
    assert engine._cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0

    # 2. String menor que n (ex: 2 caracteres como "Go") no extrator de n-gram
    v_short = engine._char_ngram_vector("Go", n=3)
    assert v_short == {"Go": 1}

    # 3. Similaridade subpalavra com string vazia vs string com conteúdo retorna 0.0
    assert engine._subword_vector_similarity("", "python") == 0.0

    # 4. Avaliador vetorial dinâmico (vector_evaluator callable)
    def custom_evaluator(t1: str, t2: str) -> float:
        if (t1.lower() == "golang" and t2.lower() == "go") or (
            t1.lower() == "go" and t2.lower() == "golang"
        ):
            return 0.95
        return 0.1

    sample_user_dossier["skills"].append("Go")
    content = {
        "selected_experiences": [],
        "skills_highlighted": ["Golang"],
    }

    result = engine.audit(
        generated_content=content,
        user_dossier=sample_user_dossier,
        vector_evaluator=custom_evaluator,
    )
    assert result.is_valid is True
    assert result.verified_counts_by_tier.get("vector", 0) >= 1


def test_audit_subword_vector_fallback() -> None:
    """Valida o tier vetorial por n-gramas e fallback de similaridade subpalavra."""
    engine = GroundingAuditEngine()
    # Com fuzzy_threshold=0.95 e vector_threshold=0.70, "Postgres" vs "PostgreSQL"
    # (sim ~0.72) ativa o fallback vetorial subpalavra
    tier = engine.validate_term(
        term="Postgres",
        registered_terms={"PostgreSQL"},
        fuzzy_threshold=0.95,
        vector_threshold=0.70,
    )
    assert tier == ValidationTier.VECTOR

    # Valida diretamente o cálculo de similaridade por n-gramas subpalavra
    sim = engine._subword_vector_similarity("Postgres", "PostgreSQL")
    assert sim >= 0.70

    # Valida caso de borda com vetores vazios
    assert engine._subword_vector_similarity("", "") == 0.0
