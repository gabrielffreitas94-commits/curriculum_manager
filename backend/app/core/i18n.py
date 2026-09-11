"""Motor de internacionalização (i18n) e convenções regionais do ThothCVs AI.

Centraliza a formatação de datas estritamente em Mês e Ano, dicionários de tradução
e o manifesto dinâmico LocaleRegistry para facilitar a inclusão de novos idiomas.
Em estrita conformidade com a skill i18n-locale-engine.
"""

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class LocaleConfig:
    """Configurações dialetais e regras de apresentação regional para um locale.

    Attributes:
        code: Código ISO do idioma e região (ex: 'pt-BR', 'en-US').
        name: Nome amigável e descritivo do locale.
        month_abbreviations: Lista com 12 abreviações de meses (1-indexados logicamente).
        date_format_pattern: Padrão textual para formatação de data (ex: '{month_abbr}/{year}').
        present_label: Rótulo representativo para vínculo ou cargo em andamento (ex: 'Atual').
        translations: Mapeamento de termos-chave da interface e seções de currículo.
    """

    code: str
    name: str
    month_abbreviations: list[str]
    date_format_pattern: str = "{month_abbr}/{year}"
    present_label: str = "Atual"
    translations: dict[str, str] = field(default_factory=dict)


class LocaleRegistry:
    """Registro mestre e despachante de formatação regional do sistema.

    Permite a consulta e injeção dinâmica de novos idiomas sem alterar a lógica de negócio.
    """

    _registry: dict[str, LocaleConfig] = {}
    _default_locale: str = "pt-BR"

    @classmethod
    def register(cls, config: LocaleConfig) -> None:
        """Registra ou sobrescreve uma configuração de locale no sistema.

        Args:
            config: Instância contendo regras de apresentação e formatação.
        """
        cls._registry[config.code] = config

    @classmethod
    def get(cls, code: str) -> LocaleConfig:
        """Recupera a configuração de um locale, com fallback seguro para o padrão.

        Args:
            code: Código do locale desejado (ex: 'pt-BR').

        Returns:
            LocaleConfig correspondente ou o padrão (pt-BR).
        """
        return cls._registry.get(code, cls._registry[cls._default_locale])

    @classmethod
    def get_supported_locales(cls) -> list[str]:
        """Retorna todos os códigos de idioma registrados e disponíveis.

        Returns:
            Lista de códigos de locale suportados.
        """
        return list(cls._registry.keys())

    @classmethod
    def get_translation(cls, locale_code: str, key: str, default: str = "") -> str:
        """Obtém a tradução de uma chave terminológica para o locale especificado.

        Args:
            locale_code: Código do idioma de destino.
            key: Chave semântica do termo (ex: 'experience').
            default: Valor retornado se a chave não for encontrada.

        Returns:
            Termo traduzido ou default.
        """
        config = cls.get(locale_code)
        return config.translations.get(key, default)

    @classmethod
    def format_date(
        cls,
        value: str | date | datetime | None,
        locale_code: str = "pt-BR",
        is_current: bool = False,
    ) -> str:
        """Formata uma data exclusivamente no padrão Mês/Ano conforme a região.

        Trata strings ISO (YYYY-MM-DD, YYYY-MM), instâncias date/datetime ou
        retorna o rótulo de cargo atual caso is_current seja True.

        Args:
            value: Data a ser formatada ou None.
            locale_code: Código do idioma regional.
            is_current: Se True e data nula, indica atividade profissional presente.

        Returns:
            String formatada (ex: 'mai/2023', 'May 2023', 'Atual') ou string vazia.
        """
        config = cls.get(locale_code)

        if is_current or value is None:
            return config.present_label if is_current else ""

        parsed_date: date | None = None

        if isinstance(value, datetime):
            parsed_date = value.date()
        elif isinstance(value, date):
            parsed_date = value
        elif isinstance(value, str):
            clean_str = value.strip()
            if not clean_str:
                return config.present_label if is_current else ""
            try:
                # Tenta formato YYYY-MM-DD
                parsed_date = datetime.strptime(clean_str[:10], "%Y-%m-%d").date()
            except ValueError:
                try:
                    # Tenta formato YYYY-MM
                    parsed_date = datetime.strptime(clean_str[:7], "%Y-%m").date()
                except ValueError:
                    return clean_str

        if not parsed_date:
            return ""

        month_idx = parsed_date.month - 1
        month_abbr = (
            config.month_abbreviations[month_idx]
            if 0 <= month_idx < len(config.month_abbreviations)
            else f"{parsed_date.month:02d}"
        )

        return config.date_format_pattern.format(
            month_abbr=month_abbr,
            month_num=f"{parsed_date.month:02d}",
            year=parsed_date.year,
        )


# Inicialização dos 5 idiomas nativos obrigatórios
_NATIVE_TRANSLATIONS_PT_BR = {
    "summary": "Resumo Profissional",
    "experience": "Experiência Profissional",
    "education": "Formação Acadêmica",
    "skills": "Habilidades e Tecnologias",
    "certifications": "Certificações",
    "languages": "Idiomas",
    "projects": "Projetos em Destaque",
    "contact": "Contato",
}

_NATIVE_TRANSLATIONS_PT_PT = {
    "summary": "Resumo Profissional",
    "experience": "Experiência Profissional",
    "education": "Formação Académica",
    "skills": "Competências e Tecnologias",
    "certifications": "Certificações",
    "languages": "Línguas",
    "projects": "Projetos em Destaque",
    "contact": "Contacto",
}

_NATIVE_TRANSLATIONS_EN = {
    "summary": "Professional Summary",
    "experience": "Professional Experience",
    "education": "Education",
    "skills": "Skills & Technologies",
    "certifications": "Certifications",
    "languages": "Languages",
    "projects": "Featured Projects",
    "contact": "Contact",
}

_NATIVE_TRANSLATIONS_ES = {
    "summary": "Perfil Profesional",
    "experience": "Experiencia Laboral",
    "education": "Formación Académica",
    "skills": "Habilidades y Tecnologías",
    "certifications": "Certificaciones",
    "languages": "Idiomas",
    "projects": "Proyectos Destacados",
    "contact": "Contacto",
}

# Registro padrão pt-BR
LocaleRegistry.register(
    LocaleConfig(
        code="pt-BR",
        name="Português (Brasil)",
        month_abbreviations=[
            "jan",
            "fev",
            "mar",
            "abr",
            "mai",
            "jun",
            "jul",
            "ago",
            "set",
            "out",
            "nov",
            "dez",
        ],
        date_format_pattern="{month_abbr}/{year}",
        present_label="Atual",
        translations=_NATIVE_TRANSLATIONS_PT_BR,
    )
)

# Registro pt-PT
LocaleRegistry.register(
    LocaleConfig(
        code="pt-PT",
        name="Português (Portugal)",
        month_abbreviations=[
            "jan",
            "fev",
            "mar",
            "abr",
            "mai",
            "jun",
            "jul",
            "ago",
            "set",
            "out",
            "nov",
            "dez",
        ],
        date_format_pattern="{month_abbr}/{year}",
        present_label="Presente",
        translations=_NATIVE_TRANSLATIONS_PT_PT,
    )
)

# Registro en-US
LocaleRegistry.register(
    LocaleConfig(
        code="en-US",
        name="English (United States)",
        month_abbreviations=[
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ],
        date_format_pattern="{month_abbr} {year}",
        present_label="Present",
        translations=_NATIVE_TRANSLATIONS_EN,
    )
)

# Registro en-GB
LocaleRegistry.register(
    LocaleConfig(
        code="en-GB",
        name="English (United Kingdom)",
        month_abbreviations=[
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ],
        date_format_pattern="{month_abbr} {year}",
        present_label="Present",
        translations=_NATIVE_TRANSLATIONS_EN,
    )
)

# Registro es-ES
LocaleRegistry.register(
    LocaleConfig(
        code="es-ES",
        name="Español (España)",
        month_abbreviations=[
            "ene",
            "feb",
            "mar",
            "abr",
            "may",
            "jun",
            "jul",
            "ago",
            "sep",
            "oct",
            "nov",
            "dic",
        ],
        date_format_pattern="{month_abbr}/{year}",
        present_label="Actual",
        translations=_NATIVE_TRANSLATIONS_ES,
    )
)
