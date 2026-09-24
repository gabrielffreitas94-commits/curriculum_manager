# ADR 0001: Gestão Segura de Chaves de IA Multi-Dispositivo com Divisão de Segredo (Split-Secret Vault)

* **Status:** Aceito (Accepted)
* **Data:** 2026-09-17
* **Decisores:** Gabriel Freitas, Engenharia de Software & AppSec
* **Contexto Técnico:** Backend FastAPI (Hexagonal), PostgreSQL/Alembic, Google Gemini API, Frontend Next.js 15

---

## 1. Contexto e Problema

O **ThothCVs AI** opera no modelo **BYOK (*Bring Your Own Key*)**, permitindo que os usuários configurem sua própria chave de API do **Google Gemini** para otimizações e geração de currículos.

O gerenciamento de credenciais de terceiros traz dilemas críticos de segurança e usabilidade:
1. **Armazenamento Centralizado no Banco de Dados (Risco Alto):** Salvar chaves em texto plano ou com criptografia reversível unicamente pelo servidor expõe todas as credenciais em caso de vazamento de dump do banco, SQL Injection ou comprometimento de backups.
2. **Entrada Manual a Cada Requisição (UX Inviável):** Forçar o usuário a digitar a chave a cada operação elimina riscos no servidor, mas torna a experiência frustrante e incentiva o usuário a guardar a chave em locais inseguros locais (ex: bloco de notas).
3. **Armazenamento no Navegador via `localStorage` (Risco Crítico de XSS):** Qualquer script malicioso injetado por dependências comprometidas no frontend pode extrair a chave diretamente.
4. **Múltiplos Dispositivos:** Usuários operam simultaneamente em notebooks, desktops e smartphones, exigindo que a arquitetura suporte múltiplos aparelhos sem comprometer a segurança caso um deles seja extraviado ou roubado.

---

## 2. Decisão Arquitetural

Decidimos adotar o padrão **Divisão de Segredo em Dupla Custódia (*Split-Secret / Dual-Party Custody*)** com **Criptografia Autenticada (AEAD)** e **Identidade Criptográfica por Dispositivo**:

### 2.1. Dupla Custódia (Nenhum lado possui o segredo sozinho)
Para que a chave de API da IA seja materializada em memória RAM para uma chamada ao Google Gemini, duas partes independentes são estritamente necessárias:
* **Parte A (Cliente / Dispositivo):** Um cookie seguro (`ai_vault`), com as flags `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/`, contendo o *Ciphertext* + *Nonce* + *Auth Tag* criptografados com a chave específica daquele dispositivo.
* **Parte B (Servidor / Banco de Dados):** Uma chave de criptografia exclusiva do dispositivo (**DEK - Data Encryption Key**, 256 bits), salva na tabela `user_device_vaults` e envolvida (*wrapped*) pela chave mestra do servidor (**KEK - Key Encryption Key**).

### 2.2. Criptografia Autenticada Obrigatória (AEAD)
* Fica **terminantemente proibido** o uso de AES em modo ECB ou CBC sem autenticação, devido à vulnerabilidade a ataques de inversão de bits (*bit-flipping*) e oráculo de preenchimento (*padding oracle*).
* O sistema deve utilizar exclusivamente **AES-256-GCM** (ou ChaCha20-Poly1305), que gera uma *Authentication Tag* de 128 bits para validação de integridade. Qualquer adulteração no cookie resulta no descarte imediato da requisição (*fail-closed* com `HTTP 400 Bad Request` ou `412 Precondition Failed`).

### 2.3. Gestão de Múltiplos Dispositivos e Revogação Granular
* Cada aparelho conectado recebe um `device_id` único e sua própria DEK no banco.
* O usuário pode visualizar todos os seus dispositivos ativos em uma tela de configurações.
* A revogação de um aparelho específico é realizada com um clique: o backend remove ou invalida a DEK correspondente no banco, tornando o cookie daquele aparelho inutilizável instantaneamente, sem afetar os outros dispositivos do usuário.

---

## 3. Arquitetura de Dados e Hexagonal

### 3.1. Modelo Relacional (`user_device_vaults`)
```sql
CREATE TABLE user_device_vaults (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id UUID NOT NULL UNIQUE,
    device_name VARCHAR(120) NOT NULL,
    encrypted_dek BYTEA NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE NULL
);

CREATE INDEX idx_user_device_active ON user_device_vaults (user_id, device_id) WHERE revoked_at IS NULL;
```

### 3.2. Estrutura Hexagonal no Backend
* **Domínio:** `app/domain/device_vault.py` (Entidade `DeviceVault` pura, imutável).
* **Portas:**
  * `app/ports/vault_crypto_port.py` (Contratos para `generate_dek`, `encrypt_with_dek`, `decrypt_with_dek`, `wrap_dek`, `unwrap_dek`).
  * `app/ports/device_vault_port.py` (Contrato de repositório para persistência das sessões).
* **Adaptadores:**
  * `app/adapters/crypto/aes_gcm_vault_adapter.py` (Implementação com biblioteca `cryptography`).
  * `app/adapters/repositories/sql_device_vault_repo.py` (Implementação SQLAlchemy).
* **Serviço de Aplicação:** `app/services/device_vault_service.py` (Orquestração dos fluxos de registro, validação e revogação).
* **Camada de Entrada (FastAPI):**
  * `app/api/v1/deps.py` com dependência `get_active_ai_key() -> SecretStr`.
  * `app/api/v1/device_vault.py` com endpoints de gestão `/api/v1/vault/*`.

---

## 4. Consequências

### Positivas
* **Blindagem Total contra Vazamento do Banco:** Se o banco de dados for exfiltrado em um ataque de SQL Injection ou vazamento de backup, **zero chaves de API são comprometidas**, pois o texto cifrado existe apenas nos navegadores dos usuários.
* **Imunidade a XSS:** O cookie `HttpOnly` não pode ser acessado por scripts JavaScript invasores.
* **Segurança Operacional:** Chaves trafegam descriptografadas exclusivamente em memória RAM volátil durante os milissegundos da requisição de IA e são tratadas como `pydantic.SecretStr` para prevenir vazamentos em logs do OpenTelemetry e GCP Cloud Logging.
* **Governança do Usuário:** O usuário tem controle total sobre quais aparelhos têm acesso à sua cota.

### Negativas / Trade-offs
* **Configuração Inicial por Aparelho:** O usuário precisa cadastrar sua chave uma vez em cada novo dispositivo que for utilizar (mitigado pelo fato de ser uma ação única por navegador).
* **Overhead Mínimo de Rede:** O cookie de ~120 bytes trafega nas requisições direcionadas às rotas de IA sob o prefixo `/api/v1/`.

---

## 5. Roadmap de Implementação

1. **Fase 1: Domínio, Portas e Adaptador Criptográfico** (AES-256-GCM e testes unitários de encriptação/tampering).
2. **Fase 2: Banco de Dados & Migração Alembic** (Criação da tabela `user_device_vaults` e repositório SQLAlchemy).
3. **Fase 3: Serviço de Aplicação (Core)** (`DeviceVaultService` com registro, resolução e revogação).
4. **Fase 4: Endpoints FastAPI e Injeção de Dependências** (Roteador `/vault`, dependência `get_active_ai_key`, proteção contra logs).
5. **Fase 5: Frontend Next.js** (Modal de onboarding de chave com interceptor de status 412 e tela de gestão de dispositivos).
6. **Fase 6: Testes Automatizados & Quality Gate** (100% de cobertura, testes de fail-closed e auditoria de segurança).
