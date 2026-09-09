---
name: supabase-postgres-alembic
description: Padrões de persistência relacional com SQLAlchemy 2.0 assíncrono, migrations no Alembic e isolamento de tenants.
---

# Skill: Supabase PostgreSQL & Alembic

Esta skill orienta a modelagem relacional, execução de migrações e garantia de integridade com SQLAlchemy 2.0 e PostgreSQL 16+ no Supabase.

## Diretrizes de Modelagem

1. **Herança Declarativa Base:** Todos os modelos herdam de `Base` (SQLAlchemy 2.0 `DeclarativeBase`).
2. **Tipagem Mapped:** Use anotações de tipo `Mapped[type]` e `mapped_column(...)`.
3. **Auditoria Padrão:** Toda entidade de negócio deve possuir:
   - `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())`
   - `updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())`
   - `deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)` (Soft Delete)
4. **Isolamento de Dados (Tenant Isolation):**
   - Toda consulta filtrada por usuário deve ter `WHERE user_id = :current_user_id AND deleted_at IS NULL`.
