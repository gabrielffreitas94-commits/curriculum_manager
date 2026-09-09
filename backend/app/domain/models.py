"""Modelos de dados relacionais do ThothCVs AI construídos sobre SQLAlchemy 2.0.

Implementa a totalidade das 16 entidades de domínio especificadas no PRD v2.0:
- Usuários e Configurações (users, user_settings)
- Repositório de Experiências e Portfólio (experiences, educations,
  certifications, projects, skills, languages)
- Motor de Prompts de IA (prompt_skills)
- ATS Pessoal e Gestão de Candidaturas (applications, application_stages,
  application_contacts, application_notes)
- Documentos Gerados (generated_resumes, cover_letters)
- Notificações do Sistema (notifications)
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.base import (
    JSON_COMPAT,
    Base,
    PrimaryKeyUUIDMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class User(Base, PrimaryKeyUUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Entidade principal representando um usuário autenticado no ThothCVs AI.

    Attributes:
        id: Identificador único universal (UUID v4).
        firebase_uid: Identificador único fornecido pelo Firebase Auth.
        email: E-mail primário verificado do usuário.
        full_name: Nome completo do usuário utilizado nos currículos gerados.
        phone: Telefone de contato com código de país e área.
        location: Localidade de residência (ex: 'São Paulo, SP - Brasil').
        linkedin_url: Link público do perfil profissional no LinkedIn.
        github_url: Link público do perfil ou repositórios no GitHub.
        portfolio_url: Link para website ou portfólio pessoal online.
        professional_summary: Resumo narrativo mestre das qualificações profissionais.
        target_title: Cargo ou área profissional primariamente almejada.
        is_active: Flag que indica se o usuário possui acesso ativo à plataforma.
        created_at: Data e hora do cadastro inicial (UTC).
        updated_at: Data e hora da última modificação dos dados cadastrais (UTC).
        deleted_at: Data e hora do soft delete da conta (UTC) ou None se ativa.
        settings: Relação 1:1 com as configurações de conta do usuário.
        experiences: Lista 1:N de experiências profissionais registradas.
        educations: Lista 1:N de formações acadêmicas do usuário.
        certifications: Lista 1:N de certificações e credenciais técnicas.
        projects: Lista 1:N de projetos pessoais e contribuições open-source.
        skills: Lista 1:N de competências técnicas e comportamentais.
        languages: Lista 1:N de idiomas dominados pelo usuário.
        applications: Lista 1:N de candidaturas gerenciadas no ATS pessoal.
        notifications: Lista 1:N de alertas e lembretes direcionados ao usuário.
        prompt_skills: Lista 1:N de personas/templates de prompt customizados criados pelo usuário.
    """

    __tablename__ = "users"

    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    portfolio_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    professional_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relacionamentos
    settings: Mapped["UserSettings"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    experiences: Mapped[list["Experience"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Experience.sort_order",
    )
    educations: Mapped[list["Education"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Education.sort_order",
    )
    certifications: Mapped[list["Certification"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Certification.sort_order",
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Project.sort_order",
    )
    skills: Mapped[list["Skill"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    languages: Mapped[list["Language"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    applications: Mapped[list["Application"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    prompt_skills: Mapped[list["PromptSkill"]] = relationship(
        back_populates="created_by_user",
        lazy="selectin",
    )


class UserSettings(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Configurações de preferências e chaves de criptografia do usuário.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira referenciando o usuário dono das preferências.
        encrypted_gemini_api_key: Chave de API do Google Gemini cifrada via AES-GCM-256.
        preferred_language: Código de idioma predileto da interface ('pt-BR', 'en-US', etc.).
        default_prompt_skill_id: UUID do template de prompt favorito do usuário.
        email_notifications_enabled: Flag para habilitar ou silenciar e-mails do sistema.
        in_app_notifications_enabled: Flag para habilitar alertas no dashboard web.
        created_at: Data de criação das preferências.
        updated_at: Data da última modificação das preferências.
        user: Relação com a entidade de usuário proprietária.
        default_prompt_skill: Template de prompt apontado como padrão.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    encrypted_gemini_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(10), default="pt-BR", nullable=False)
    default_prompt_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_skills.id", ondelete="SET NULL"),
        nullable=True,
    )
    email_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    in_app_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relacionamentos
    user: Mapped["User"] = relationship(back_populates="settings")
    default_prompt_skill: Mapped["PromptSkill | None"] = relationship(
        foreign_keys=[default_prompt_skill_id]
    )


class Experience(Base, PrimaryKeyUUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Experiência profissional histórica pertencente ao repositório mestre do usuário.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira referenciando o usuário titular da experiência.
        company_name: Nome oficial da empresa ou organização contratante.
        position_title: Cargo ou função exercida.
        location: Localidade da empresa (ex: 'Belo Horizonte, MG' ou 'Remoto').
        work_model: Modalidade de trabalho ('remote', 'hybrid' ou 'on-site').
        start_date: Data de início das atividades na empresa.
        end_date: Data de encerramento das atividades (None se cargo atual).
        is_current: Flag indicando se é o trabalho vigente do candidato.
        description: Narrativa descritiva abrangente das responsabilidades.
        bullet_points: Lista estruturada em JSON com realizações de destaque.
        tech_stack: Lista de tecnologias, frameworks e linguagens aplicadas.
        quantifiable_results: Métricas quantificáveis de impacto e eficiência gerada.
        sort_order: Índice sequencial para controle manual de ordenação na UI.
        created_at: Momento do registro no banco de dados (UTC).
        updated_at: Momento da última atualização cadastral (UTC).
        deleted_at: Data do soft delete ou None se o registro estiver ativo.
        user: Relação com a entidade de usuário dona deste histórico.
    """

    __tablename__ = "experiences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    position_title: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    work_model: Mapped[str] = mapped_column(String(20), default="remote", nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    bullet_points: Mapped[list[str]] = mapped_column(JSON_COMPAT, default=list, nullable=False)
    tech_stack: Mapped[list[str]] = mapped_column(JSON_COMPAT, default=list, nullable=False)
    quantifiable_results: Mapped[list[str]] = mapped_column(
        JSON_COMPAT, default=list, nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="experiences")


class Education(Base, PrimaryKeyUUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Formação acadêmica, cursos de graduação e pós-graduação do usuário.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira do usuário detentor do título acadêmico.
        institution_name: Nome da universidade ou faculdade formadora.
        degree: Nível acadêmico ('Bacharelado', 'Mestrado', 'Doutorado', etc.).
        field_of_study: Área de conhecimento ou curso (ex: 'Ciência da Computação').
        start_date: Data de ingresso no curso.
        end_date: Data de formatura ou conclusão prevista (None se cursando).
        is_current: Flag indicando se a formação ainda está em andamento.
        description: Informações adicionais como tema de TCC ou honras de mérito.
        sort_order: Posição de ordenação preferencial na listagem.
        created_at: Timestamp UTC de inserção.
        updated_at: Timestamp UTC da última edição.
        deleted_at: Data de soft delete ou None se ativo.
        user: Relação com o usuário proprietário da formação.
    """

    __tablename__ = "educations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    institution_name: Mapped[str] = mapped_column(String(150), nullable=False)
    degree: Mapped[str] = mapped_column(String(100), nullable=False)
    field_of_study: Mapped[str] = mapped_column(String(150), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="educations")


class Certification(Base, PrimaryKeyUUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Certificações técnicas profissionais e licenças regulatórias.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira referenciando o titular da certificação.
        name: Título oficial da certificação (ex: 'AWS Solutions Architect Associate').
        issuing_organization: Entidade emissora da credencial (ex: 'Amazon Web Services').
        issue_date: Data de expedição do certificado.
        expiration_date: Data de expiração da credencial (None se for vitalícia).
        credential_id: Código alfanumérico validador fornecido pela entidade emissora.
        credential_url: URL pública para verificação de autenticidade online.
        sort_order: Ordem preferencial de listagem do certificado.
        created_at: Data e hora do cadastro (UTC).
        updated_at: Data e hora da última modificação (UTC).
        deleted_at: Data de soft delete ou None se ativo.
        user: Relação com o usuário detentor do certificado.
    """

    __tablename__ = "certifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    issuing_organization: Mapped[str] = mapped_column(String(150), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    credential_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    credential_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="certifications")


class Project(Base, PrimaryKeyUUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Projetos práticos, iniciativas open source e itens de portfólio.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira do usuário autor do projeto.
        title: Nome ou título oficial do projeto.
        description: Detalhamento dos objetivos, desafios e resultados obtidos.
        role: Papel exercido no projeto (ex: 'Tech Lead', 'Creator').
        technologies: Lista de tecnologias aplicadas codificada em JSON.
        repository_url: Link público do código-fonte no GitHub ou GitLab.
        live_url: Link de demonstração ou aplicação em ambiente de produção.
        start_date: Data de início do desenvolvimento.
        end_date: Data de conclusão ou encerramento (None se contínuo).
        sort_order: Sequência de prioridade de exibição.
        created_at: Data de inserção do registro (UTC).
        updated_at: Data da última edição do registro (UTC).
        deleted_at: Data de soft delete ou None se ativo.
        user: Relação com o usuário desenvolvedor do projeto.
    """

    __tablename__ = "projects"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    technologies: Mapped[list[str]] = mapped_column(JSON_COMPAT, default=list, nullable=False)
    repository_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    live_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="projects")


class Skill(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Competência técnica ou comportamental cadastrada no inventário do usuário.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira do usuário detentor da competência.
        name: Nome da habilidade (ex: 'FastAPI', 'Docker', 'System Architecture').
        category: Categoria de domínio ('backend', 'frontend', 'cloud', 'leadership', etc.).
        proficiency_level: Nível autodeclarado ('beginner', 'intermediate', 'advanced', 'expert').
        years_of_experience: Quantidade estimada de anos de prática com a tecnologia.
        is_featured: Flag destacando a competência no cabeçalho ou resumo do perfil.
        created_at: Momento do cadastro (UTC).
        updated_at: Momento da última modificação (UTC).
        user: Relação com o usuário dono da competência.
    """

    __tablename__ = "skills"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="backend", nullable=False)
    proficiency_level: Mapped[str] = mapped_column(
        String(30), default="intermediate", nullable=False
    )
    years_of_experience: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship(back_populates="skills")


class Language(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Idioma e grau de fluência comunicativa dominado pelo candidato.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira do usuário falante do idioma.
        language_name: Nome do idioma (ex: 'Inglês', 'Espanhol', 'Alemão').
        proficiency_level: Grau de fluência ('basic', 'intermediate', 'advanced',
            'fluent', 'native').
        created_at: Data de inclusão no banco (UTC).
        updated_at: Data da última modificação (UTC).
        user: Relação com o usuário cadastrado.
    """

    __tablename__ = "languages"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    language_name: Mapped[str] = mapped_column(String(50), nullable=False)
    proficiency_level: Mapped[str] = mapped_column(String(30), nullable=False)

    user: Mapped["User"] = relationship(back_populates="languages")


class PromptSkill(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Template de persona, tom de voz e diretrizes para o motor de IA Google Gemini.

    Attributes:
        id: Identificador único universal (UUID v4).
        slug: Identificador único amigável para URL e seleção de template
            (ex: 'tech-startup', 'corporate').
        name: Nome de exibição legível na interface de usuário.
        description: Explicação clara orientando quando escolher esta skill de tom.
        category: Classificação geral da persona ('tech', 'corporate', 'academic', 'executive').
        system_prompt: Diretrizes detalhadas injetadas como system instructions no Gemini.
        default_language: Idioma primário sugerido para geração de documentos com esta skill.
        is_system_default: Flag indicando se é uma skill nativa imutável do sistema.
        created_by_user_id: UUID do usuário que criou a skill customizada (None se for de sistema).
        is_active: Flag que controla a visibilidade e disponibilidade da skill.
        created_at: Momento da criação (UTC).
        updated_at: Momento da última alteração das instruções (UTC).
        created_by_user: Relação com o usuário criador, caso seja skill personalizada.
        generated_resumes: Currículos que utilizaram esta skill durante a geração.
    """

    __tablename__ = "prompt_skills"

    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    default_language: Mapped[str] = mapped_column(String(10), default="pt-BR", nullable=False)
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by_user: Mapped["User | None"] = relationship(back_populates="prompt_skills")
    generated_resumes: Mapped[list["GeneratedResume"]] = relationship(
        back_populates="prompt_skill",
    )


class Application(Base, PrimaryKeyUUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Entidade central do ATS Pessoal gerenciando o ciclo de vida de uma candidatura.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira do usuário candidato.
        company_name: Nome da empresa que anunciou a oportunidade.
        job_title: Título da vaga pretendida.
        job_url: Link do anúncio original da vaga em job boards ou site de carreiras.
        job_description: Texto completo da descrição da vaga para análise do Gemini.
        salary_range: Faixa salarial informada ou pretensão cadastrada.
        location: Localização da vaga de emprego (Cidade/País).
        work_model: Modelo de atuação ('remote', 'hybrid', 'on-site').
        status: Status atual no funil ATS ('applied', 'interview_scheduled', etc.).
        applied_at: Data da realização do envio da candidatura.
        last_activity_at: Momento da última interação registrada para cálculo
            do follow-up proativo de 7 dias.
        next_follow_up_date: Data estipulada para próxima ação manual do usuário.
        reminder_active: Ativação dos lembretes automatizados de estagnação.
        created_at: Data e hora do cadastro da candidatura (UTC).
        updated_at: Data e hora da última modificação dos dados (UTC).
        deleted_at: Data de soft delete ou None se ativa.
        user: Relação com o usuário candidato.
        stages: Etapas dinâmicas do processo seletivo da vaga.
        contacts: Contatos de recrutadores e entrevistadores envolvidos.
        notes: Bloco de notas livres associadas ao processo seletivo.
        generated_resumes: Versões de currículos geradas especificamente para esta vaga.
        cover_letters: Cartas de apresentação customizadas vinculadas à vaga.
        notifications: Alertas e lembretes gerados a partir desta candidatura.
    """

    __tablename__ = "applications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(150), nullable=False)
    job_title: Mapped[str] = mapped_column(String(120), nullable=False)
    job_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    job_description: Mapped[str] = mapped_column(Text, nullable=False)
    salary_range: Mapped[str | None] = mapped_column(String(80), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    work_model: Mapped[str] = mapped_column(String(20), default="remote", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="applied", nullable=False)
    applied_at: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    next_follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reminder_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relacionamentos
    user: Mapped["User"] = relationship(back_populates="applications")
    stages: Mapped[list["ApplicationStage"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ApplicationStage.order_index",
    )
    contacts: Mapped[list["ApplicationContact"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    notes: Mapped[list["ApplicationNote"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ApplicationNote.created_at.desc()",
    )
    generated_resumes: Mapped[list["GeneratedResume"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="GeneratedResume.version_number.desc()",
    )
    cover_letters: Mapped[list["CoverLetter"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="application",
    )


class ApplicationStage(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Etapa sequencial de avaliação no funil da candidatura (ex: Triagem, Live Coding).

    Attributes:
        id: Identificador único universal (UUID v4).
        application_id: Chave estrangeira da candidatura correspondente.
        stage_name: Título descritivo da etapa seletiva.
        status: Situação da etapa ('pending', 'scheduled', 'completed', 'skipped').
        scheduled_at: Data e hora marcada para a entrevista ou entrega de teste (UTC).
        completed_at: Data e hora em que a etapa foi finalizada (UTC).
        feedback_notes: Impressões pessoais ou retorno fornecido pelos recrutadores.
        order_index: Posição numérica sequencial no funil de seleção.
        created_at: Momento do agendamento (UTC).
        updated_at: Momento da alteração de status (UTC).
        application: Relação com a candidatura correspondente.
    """

    __tablename__ = "application_stages"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feedback_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="stages")


class ApplicationContact(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Profissional de contato associado ao processo seletivo da oportunidade.

    Attributes:
        id: Identificador único universal (UUID v4).
        application_id: Chave estrangeira da candidatura pai.
        full_name: Nome completo do contato.
        role_type: Função no processo ('recruiter', 'hiring_manager', 'tech_interviewer', etc.).
        email: Endereço de e-mail corporativo ou pessoal.
        linkedin_url: Perfil público do contato na rede LinkedIn.
        phone: Telefone direto ou canal de mensagens do contato.
        context_notes: Anotações sobre postura, estilo ou detalhes abordados com a pessoa.
        created_at: Momento do registro no sistema (UTC).
        updated_at: Momento da última edição (UTC).
        application: Relação com a candidatura pai.
    """

    __tablename__ = "application_contacts"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role_type: Mapped[str] = mapped_column(String(30), default="recruiter", nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    context_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["Application"] = relationship(back_populates="contacts")


class ApplicationNote(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Anotação livre ou registro cronológico vinculado à vaga de emprego.

    Attributes:
        id: Identificador único universal (UUID v4).
        application_id: Chave estrangeira da candidatura pai.
        content: Texto formatado da anotação.
        note_type: Classificação ('general', 'interview_prep', 'salary_negotiation', etc.).
        created_at: Momento da criação da nota (UTC).
        updated_at: Momento da última edição (UTC).
        application: Relação com a candidatura pai.
    """

    __tablename__ = "application_notes"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(30), default="general", nullable=False)

    application: Mapped["Application"] = relationship(back_populates="notes")


class GeneratedResume(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Snapshot imutável e versionado do currículo gerado para uma candidatura específica.

    Attributes:
        id: Identificador único universal (UUID v4).
        application_id: Chave estrangeira da candidatura correspondente.
        user_id: Chave estrangeira do usuário dono do currículo.
        prompt_skill_id: Chave estrangeira da skill de prompt aplicada na geração.
        language: Código de idioma em que o currículo foi sintetizado ('pt-BR', 'en-US', etc.).
        version_number: Número da versão sequencial incrementada para a mesma candidatura.
        structured_content: Dicionário JSONB contendo o conteúdo estruturado completo do currículo.
        match_analysis: Dicionário JSONB com a avaliação de requisitos atendidos e parciais.
        match_percentage: Pontuação global de aderência quantificada (0.0 a 100.0).
        pdf_storage_path: URI ou caminho relativo do arquivo PDF no Supabase Storage/GCS.
        docx_storage_path: URI ou caminho relativo do arquivo DOCX no Storage.
        created_at: Momento exato da conclusão da geração (UTC).
        updated_at: Momento da última alteração de metadados (UTC).
        application: Relação com a candidatura correspondente.
        user: Relação com o usuário proprietário do currículo.
        prompt_skill: Template de prompt utilizado na geração.
    """

    __tablename__ = "generated_resumes"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_skills.id", ondelete="SET NULL"),
        nullable=True,
    )
    language: Mapped[str] = mapped_column(String(10), default="pt-BR", nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    structured_content: Mapped[dict[str, Any]] = mapped_column(JSON_COMPAT, nullable=False)
    match_analysis: Mapped[dict[str, Any]] = mapped_column(
        JSON_COMPAT, default=dict, nullable=False
    )
    match_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pdf_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    docx_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    application: Mapped["Application"] = relationship(back_populates="generated_resumes")
    user: Mapped["User"] = relationship()
    prompt_skill: Mapped["PromptSkill | None"] = relationship(back_populates="generated_resumes")


class CoverLetter(Base, PrimaryKeyUUIDMixin, TimestampMixin):
    """Carta de apresentação personalizada redigida para acompanhar a candidatura.

    Attributes:
        id: Identificador único universal (UUID v4).
        application_id: Chave estrangeira da candidatura correspondente.
        user_id: Chave estrangeira do usuário emitente da carta.
        content: Texto integral formatado da carta de apresentação.
        language: Idioma do texto redigido ('pt-BR', 'en-US', etc.).
        storage_path: Caminho do arquivo exportado em PDF no Storage de arquivos.
        created_at: Momento da geração da carta (UTC).
        updated_at: Momento da última edição do texto (UTC).
        application: Relação com a candidatura correspondente.
        user: Relação com o usuário proprietário da carta.
    """

    __tablename__ = "cover_letters"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="pt-BR", nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    application: Mapped["Application"] = relationship(back_populates="cover_letters")
    user: Mapped["User"] = relationship()


class Notification(Base, PrimaryKeyUUIDMixin):
    """Notificação in-app ou alerta transacional disparado pelo sistema.

    Attributes:
        id: Identificador único universal (UUID v4).
        user_id: Chave estrangeira do usuário destinatário da notificação.
        application_id: Chave opcional referenciando a vaga envolvida no alerta.
        notification_type: Tipo ('follow_up_reminder', 'interview_alert', 'system').
        title: Título sucinto exibido na central de notificações.
        message: Texto completo com as orientações do alerta.
        is_read: Flag indicando se a notificação já foi visualizada na interface.
        scheduled_for: Momento previsto para disparo do alerta (UTC).
        sent_at: Momento em que a notificação foi efetivamente enviada (UTC).
        created_at: Momento de inserção na fila (UTC).
        user: Relação com o usuário destinatário.
        application: Relação com a candidatura pai, se houver.
    """

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    notification_type: Mapped[str] = mapped_column(
        String(40), default="follow_up_reminder", nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="notifications")
    application: Mapped["Application | None"] = relationship(back_populates="notifications")
