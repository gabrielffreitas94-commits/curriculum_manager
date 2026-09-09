"""Testes unitários do motor de internacionalização e formatação de datas.

Valida conformidade com a skill i18n-locale-engine e requisitos de negócio
do ThothCVs AI (datas estritamente em Mês/Ano e suporte dinâmico a novos idiomas).
"""

from app.core.i18n import LocaleConfig, LocaleRegistry


def test_native_locales_registered() -> None:
    """Verifica se os 5 idiomas nativos obrigatórios estão devidamente registrados."""
    expected_locales = ["pt-BR", "pt-PT", "en-US", "en-GB", "es-ES"]
    registered = LocaleRegistry.get_supported_locales()

    for locale in expected_locales:
        assert locale in registered, f"Locale '{locale}' não encontrado no registro nativo."


def test_date_formatting_all_locales() -> None:
    """Garante a formatação estrita Mês/Ano em todos os 5 idiomas nativos."""
    date_input = "2023-05-15"

    # pt-BR: mai/2023
    assert LocaleRegistry.format_date(date_input, "pt-BR") == "mai/2023"
    # pt-PT: mai/2023
    assert LocaleRegistry.format_date(date_input, "pt-PT") == "mai/2023"
    # en-US: May 2023
    assert LocaleRegistry.format_date(date_input, "en-US") == "May 2023"
    # en-GB: May 2023
    assert LocaleRegistry.format_date(date_input, "en-GB") == "May 2023"
    # es-ES: may/2023
    assert LocaleRegistry.format_date(date_input, "es-ES") == "may/2023"


def test_date_formatting_present_and_none() -> None:
    """Valida o rótulo de cargo atual e tratamento de valor nulo."""
    assert LocaleRegistry.format_date(None, "pt-BR", is_current=True) == "Atual"
    assert LocaleRegistry.format_date(None, "pt-PT", is_current=True) == "Presente"
    assert LocaleRegistry.format_date(None, "en-US", is_current=True) == "Present"
    assert LocaleRegistry.format_date(None, "en-GB", is_current=True) == "Present"
    assert LocaleRegistry.format_date(None, "es-ES", is_current=True) == "Actual"
    assert LocaleRegistry.format_date(None, "pt-BR", is_current=False) == ""


def test_extensibility_add_custom_locale() -> None:
    """Comprova a facilidade de estender o sistema com um novo idioma (ex: fr-FR)."""
    french_config = LocaleConfig(
        code="fr-FR",
        name="Français (France)",
        month_abbreviations=[
            "janv.", "févr.", "mars", "avr.", "mai", "juin",
            "juil.", "août", "sept.", "oct.", "nov.", "déc."
        ],
        date_format_pattern="{month_abbr} {year}",
        present_label="Présent",
        translations={
            "summary": "Résumé Professionnel",
            "experience": "Expérience Professionnelle",
            "education": "Formation",
            "skills": "Compétences",
            "certifications": "Certifications",
            "languages": "Langues",
        },
    )

    LocaleRegistry.register(french_config)

    assert "fr-FR" in LocaleRegistry.get_supported_locales()
    assert LocaleRegistry.format_date("2024-11-01", "fr-FR") == "nov. 2024"
    assert LocaleRegistry.format_date(None, "fr-FR", is_current=True) == "Présent"
    assert LocaleRegistry.get_translation("fr-FR", "summary") == "Résumé Professionnel"
