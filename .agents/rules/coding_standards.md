# 📜 Padrões de Código e Diretrizes de Engenharia — ThothCVs AI

Este documento estabelece as regras obrigatórias de desenvolvimento para o projeto **ThothCVs AI**. Todo código escrito (por desenvolvedores humanos ou agentes de IA) deve estar em total conformidade com estas diretrizes.

---

## 1. Política Rígida de TDD (Test-Driven Development)

1. **Ciclo Red-Green-Refactor Obrigatório:**
   - **RED:** Escreva o teste antes da implementação. O teste deve falhar pelas razões certas.
   - **GREEN:** Escreva a implementação mínima para fazer o teste passar.
   - **REFACTOR:** Melhore a qualidade do código, adicione docstrings completas, otimize e garanta conformidade com os linters.
2. **Isolamento de Testes:**
   - Testes unitários devem usar mocks ou stubs para serviços externos (Gemini API, Storage, Firebase).
   - Testes de integração devem rodar contra instâncias de banco isoladas ou fixtures transacionais com rollback automático.

---

## 2. Padrão Obrigatório de Docstrings (Google Python Style)

Todas as funções, métodos, classes e módulos devem conter docstrings completas seguindo o estilo Google:

```python
def example_function(param1: str, param2: int) -> bool:
    """Resumo claro em uma linha explicando o que a função faz.

    Explicação mais detalhada do contexto arquitetural, motivação
    e fluxo de execução, se aplicável.

    Args:
        param1: Descrição do primeiro parâmetro e suas restrições.
        param2: Descrição do segundo parâmetro.

    Returns:
        bool: Significado do valor retornado.

    Raises:
        DomainException: Condição sob a qual a exceção é levantada.

    Business Rules:
        - BR-01: Descrição da regra de negócio atendida.
    """
```

---

## 3. Arquitetura Hexagonal (Ports & Adapters)

1. **Isolamento do Domínio:**
   - O diretório `app/domain/` contém entidades puras e lógica de negócio. Não importa FastAPI, SQLAlchemy, Firebase ou Gemini.
2. **Ports (`app/ports/`):**
   - Interfaces abstratas puras (`abc.ABC` com `@abstractmethod`).
3. **Adapters (`app/adapters/`):**
   - Implementações concretas que conectam às bibliotecas externas (banco, nuvem, IA, geração de PDF).
4. **Injeção de Dependências:**
   - Os serviços recebem as portas via injeção (`Depends()` do FastAPI ou construtor). Nunca instancie adapters concretos diretamente dentro de serviços de domínio.

---

## 4. Diretrizes de Qualidade de Código

- **Tipagem Estrita:** Uso de `typing` (ex: `list[str]`, `dict[str, Any]`, `UUID`, `Optional[str]`) em todas as assinaturas.
- **Linter & Formatação:** `ruff check` e `ruff format` para Python; `eslint` e `prettier` para TypeScript.
- **Segurança:** Nunca comitar senhas, chaves de API ou segredos. Use `.env` e injeção de variáveis de ambiente.
