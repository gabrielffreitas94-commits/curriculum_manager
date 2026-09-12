"""Testes unitários rigorosos para a porta e o adaptador FirebaseAuthAdapter.

Cobre 100% da lógica interna de parsing de JWT, verificação criptográfica RS256,
defesa contra falsificação de assinatura, validação de audiência/emissor,
tratamento de expiração, prefixos de mock e validações de claims do usuário.
"""

import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.adapters.firebase_auth_adapter import FirebaseAuthAdapter
from app.core.config import settings
from app.ports.auth_port import AuthError, AuthUser, InvalidTokenError


@pytest.fixture(scope="session")
def rsa_keys() -> tuple[bytes, bytes]:
    """Gera par de chaves RSA legítimo para testes de assinatura e verificação."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem_private, pem_public


@pytest.fixture(scope="session")
def attacker_rsa_private_key() -> bytes:
    """Gera chave privada de um invasor para testar rejeição de assinatura forjada."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_auth_user_dataclass() -> None:
    """Valida a estrutura imutável de usuário autenticado do domínio."""
    user = AuthUser(
        uid="firebase_uid_abc",
        email="dev@thothcvs.ai",
        full_name="Thoth Dev",
        picture_url="https://avatar.url/img.png",
    )
    assert user.uid == "firebase_uid_abc"
    assert user.email == "dev@thothcvs.ai"
    assert user.full_name == "Thoth Dev"
    assert user.picture_url == "https://avatar.url/img.png"


@pytest.mark.asyncio
async def test_verify_token_empty_or_whitespace_raises_invalid_token() -> None:
    """Garante que tokens vazios ou com espaços levantem InvalidTokenError imediatamente."""
    adapter = FirebaseAuthAdapter()
    with pytest.raises(InvalidTokenError, match="Token de autorização vazio"):
        await adapter.verify_token("")

    with pytest.raises(InvalidTokenError, match="Token de autorização vazio"):
        await adapter.verify_token("    ")


@pytest.mark.asyncio
async def test_verify_token_mock_prefix_in_dev_test_env() -> None:
    """Valida o atalho de ambiente de teste para tokens iniciados com 'mock_'."""
    adapter = FirebaseAuthAdapter()
    auth_user = await adapter.verify_token("mock_developer_user")

    assert auth_user.uid == "mock_uid_mock_developer_user"
    assert auth_user.email == "mock_developer_user@example.com"
    assert auth_user.full_name == "Mock Developer"
    assert auth_user.picture_url is None


@pytest.mark.asyncio
async def test_verify_token_mock_prefix_in_production_rejected(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que tokens mock sejam rejeitados e passem por verificação rigorosa em produção.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Broken Authentication) & OWASP A05:2021 (Security Misconfiguration).
    - Impacto: Uso de atalhos de depuração ('mock_') como backdoor em produção.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - Em ambiente 'production', NENHUM token mock deve ser aceito. O fluxo DEVE exigir JWT RS256.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Omitir a checagem de settings.ENVIRONMENT ou permitir 'mock_' incondicionalmente
      criaria uma brecha crítica de bypass total de autenticação.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Força settings.ENVIRONMENT='production' e prova que token mock levanta InvalidTokenError.
    """
    _, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(public_key=pem_public)
    with (
        patch.object(settings, "ENVIRONMENT", "production"),
        pytest.raises(InvalidTokenError, match="Token Firebase inválido"),
    ):
        await adapter.verify_token("mock_attacker_token")


@pytest.mark.asyncio
async def test_verify_token_real_jwt_valid(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante a validação criptográfica RS256 de um JWT legítimo pelo FirebaseAuthAdapter.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Identification and Authentication Failures / CWE-347).
    - Impacto: Falha na identificação correta de usuários legítimos autenticados pelo Google.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - JWTs íntegros assinados com chave privada RSA legítima DEVEM ser decodificados com sucesso.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Alterações no parser de claims ou remoção de campos esperados podem quebrar o login.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Valida decodificação completa conferindo sub, email, name e picture com os claims originais.
    """
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "firebase_user_999",
        "email": "sarah.connor@sky.net",
        "name": "Sarah Connor",
        "picture": "https://avatar.url/sarah.jpg",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, pem_private, algorithm="RS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "firebase_user_999"
    assert auth_user.email == "sarah.connor@sky.net"
    assert auth_user.full_name == "Sarah Connor"
    assert auth_user.picture_url == "https://avatar.url/sarah.jpg"


@pytest.mark.asyncio
async def test_verify_token_valid_via_jwks_client(rsa_keys: tuple[bytes, bytes]) -> None:
    """Valida a resolução da chave pública através de PyJWKClient quando
    public_key não é injetada.
    """
    pem_private, pem_public = rsa_keys
    mock_jwks = MagicMock()
    mock_signing_key = MagicMock()
    mock_signing_key.key = pem_public
    mock_jwks.get_signing_key_from_jwt.return_value = mock_signing_key

    adapter = FirebaseAuthAdapter(
        firebase_project_id="thothcvs-ai",
        jwks_client=mock_jwks,
    )

    payload = {
        "sub": "jwks_verified_user",
        "email": "jwks@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, pem_private, algorithm="RS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "jwks_verified_user"
    assert auth_user.email == "jwks@thothcvs.ai"
    assert auth_user.full_name == "Jwks"
    mock_jwks.get_signing_key_from_jwt.assert_called_once_with(encoded_token)


@pytest.mark.asyncio
async def test_verify_token_forged_signature_rejected(
    rsa_keys: tuple[bytes, bytes],
    attacker_rsa_private_key: bytes,
) -> None:
    """Garante que um token assinado por chave privada não autorizada seja rejeitado.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Broken Authentication) / CWE-347 (Improper Signature Verification).
    - Impacto: Falsificação de assinatura JWT permitindo login como qualquer usuário ou admin.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O adaptador DEVE rejeitar tokens cuja assinatura não coincida com a chave pública Google.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Se alguém desativar 'verify_signature' no jwt.decode ou usar métodos inseguros como
      jwt.decode(..., options={"verify_signature": False}), assinaturas forjadas seriam aceitas.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Assina o payload com chave privada desconhecida e valida rejeição estrita contra pem_public.
    """
    _, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "victim_user_123",
        "email": "victim@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    forged_token = jwt.encode(payload, attacker_rsa_private_key, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(forged_token)


@pytest.mark.asyncio
async def test_verify_token_algorithm_confusion_rejected(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante rejeição imediata contra confusão de algoritmo (HMAC HS256 em vez de RS256).

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Broken Authentication) / CWE-327 (Risky Cryptographic Algorithm).
    - Impacto: O atacante assina o token com a chave pública RSA como segredo HMAC (Key Confusion).

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O adaptador DEVE aceitar estritamente 'RS256', rejeitando tokens com qualquer outro algoritmo.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Omitir o parâmetro algorithms=['RS256'] no jwt.decode faria o PyJWT inferir o algoritmo,
      tornando a aplicação vulnerável ao ataque clássico de confusão de chave pública.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Envia um token forjado assinado via HS256 e valida que é categoricamente recusado.
    """
    _, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "victim_user_123",
        "email": "victim@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    # Tenta enviar token HS256 quando o sistema só aceita RS256
    confused_token = jwt.encode(
        payload,
        "symmetric_secret_key_at_least_32_bytes_long_123",
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(confused_token)


@pytest.mark.asyncio
async def test_verify_token_algorithm_none_rejected() -> None:
    """Garante que tokens com alg='none' (não assinados) sejam categoricamente rejeitados.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Broken Authentication) / CWE-347 / CVE-2015-9235 (Algorithm None).
    - Impacto: Bypass total de autenticação através do envio de tokens sem assinatura criptográfica.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O adaptador DEVE rejeitar tokens que declarem alg='none' no cabeçalho.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Caso a lista de algoritmos seja afrouxada ou o cabeçalho seja confiado sem restrição,
      o motor JWT poderia aceitar tokens não assinados.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Monta token manual com header {"alg": "none"} e sem assinatura, validando rejeição estrita.
    """
    import base64
    import json

    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai")

    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = {
        "sub": "attacker_superadmin",
        "email": "attacker@evil.com",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    none_token = f"{header}.{payload_b64}."

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(none_token)


@pytest.mark.asyncio
async def test_verify_token_wrong_audience_rejected(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante que tokens emitidos para outros projetos Firebase sejam rejeitados.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Cross-Service Token Relaying) / CWE-287 (Improper Authentication).
    - Impacto: Uso de um token gerado para outra aplicação para acessar este sistema.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O token DEVE conter 'aud' correspondente ao projeto Firebase configurado.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Desativar a validação de audiência (verify_aud=False) permitiria confusão de serviço.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Envia token assinado com aud='malicious-foreign-project' e valida erro imediato.
    """
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "user_other_project",
        "email": "user@other.com",
        "aud": "malicious-foreign-project",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    wrong_aud_token = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(wrong_aud_token)


@pytest.mark.asyncio
async def test_verify_token_wrong_issuer_rejected(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante que tokens com emissor (iss) forjado sejam rejeitados.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Token Issuer Spoofing / CWE-287).
    - Impacto: Tokens emitidos por servidores falsos tentando se passar pelo Google.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O emissor DEVE ser exatamente 'https://securetoken.google.com/{project_id}'.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Desativar verify_iss permitiria qualquer token emitido por IdPs não autorizados.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Envia token com iss='https://fake-issuer.attacker.com' e valida rejeição categórica.
    """
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "user_fake_iss",
        "email": "user@fake.com",
        "aud": "thothcvs-ai",
        "iss": "https://fake-issuer.attacker.com",
        "exp": int(time.time()) + 3600,
    }
    wrong_iss_token = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token(wrong_iss_token)


@pytest.mark.asyncio
async def test_verify_token_fallback_name_from_email(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante que a ausência do claim 'name' gere o nome a partir do prefixo do e-mail."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "user_without_name",
        "email": "carlos.silva@empresa.com",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, pem_private, algorithm="RS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "user_without_name"
    assert auth_user.email == "carlos.silva@empresa.com"
    assert auth_user.full_name == "Carlos.silva"


@pytest.mark.asyncio
async def test_verify_token_expired_jwt_raises_invalid_token(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que um token com 'exp' expirado levante InvalidTokenError com mensagem clara.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Replay Attack / Stale Token Usage / CWE-613).
    - Impacto: Reutilização indefinida de credenciais antigas ou vazadas de sessões encerradas.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - O token DEVE ser rejeitado imediatamente se o timestamp 'exp' for anterior ao instante atual.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Desativar verify_exp ou definir leeway excessivo permitiria o reuso de tokens comprometidos.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Cria token com exp expirado (timestamp - 1000s) e valida lançamento de InvalidTokenError.
    """
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "expired_user",
        "email": "old@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) - 1000,
    }
    expired_token = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(InvalidTokenError, match="O token Firebase informado expirou"):
        await adapter.verify_token(expired_token)


@pytest.mark.asyncio
async def test_verify_token_strictly_enforces_rs256_parameters_in_jwt_decode(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que a chamada interna a jwt.decode utilize os parâmetros de segurança estritos.

    VETOR DE AMEAÇA:
    - OWASP A07:2021 (Broken Authentication) & OWASP A02:2021 (Cryptographic Failures).
    - Impacto: Relaxamento silencioso de verificações criptográficas no decodificador PyJWT.

    COMPORTAMENTO ESPERADO (FAIL-CLOSED):
    - A chamada DEVE impor algorithms=['RS256'] e options com todas as flags de verificação True.

    RISCO DE REGRESSÃO SILENCIOSA (ALERTA PARA REFACTOR HUMANO E IA/LLM):
    - Um desenvolvedor ou agente IA poderia tentar simplificar chamadas removendo options
      ou expandindo algorithms para aceitar múltiplos esquemas, enfraquecendo a produção.

    PREMISSA DO GUARDRAIL (ORÁCULO ABSOLUTO):
    - Espiona jwt.decode via spy e assere que os argumentos batem com o contrato de segurança.
    """
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "audited_user_1",
        "email": "audit@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, pem_private, algorithm="RS256")

    with patch("jwt.decode", wraps=jwt.decode) as spy_decode:
        await adapter.verify_token(encoded_token)

        spy_decode.assert_called_once()
        kwargs = spy_decode.call_args.kwargs

        # 1. Oráculo absoluto: algoritmo deve ser estritamente RS256
        assert kwargs["algorithms"] == ["RS256"]

        # 2. Oráculo absoluto: opções de verificação devem ser estritas e fail-closed
        assert kwargs["options"]["verify_signature"] is True
        assert kwargs["options"]["verify_exp"] is True
        assert kwargs["options"]["verify_aud"] is True
        assert kwargs["options"]["verify_iss"] is True


@pytest.mark.asyncio
async def test_verify_token_malformed_jwt_raises_invalid_token() -> None:
    """Garante que string JWT inválida ou corrompida levante InvalidTokenError."""
    adapter = FirebaseAuthAdapter()
    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token("invalid.jwt.payload.string")


@pytest.mark.asyncio
async def test_verify_token_missing_sub_raises_auth_error(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que um JWT sem claim 'sub' levante AuthError."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "email": "user.without.sub@thothcvs.ai",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    token_without_sub = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(AuthError, match="Token não contém o identificador único"):
        await adapter.verify_token(token_without_sub)


@pytest.mark.asyncio
async def test_verify_token_missing_email_raises_auth_error(
    rsa_keys: tuple[bytes, bytes],
) -> None:
    """Garante que um JWT sem claim 'email' levante AuthError."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "sub": "user_without_email_123",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    token_without_email = jwt.encode(payload, pem_private, algorithm="RS256")

    with pytest.raises(AuthError, match="Token não contém o e-mail"):
        await adapter.verify_token(token_without_email)


@pytest.mark.asyncio
async def test_verify_token_missing_alg_header() -> None:
    """Garante que um JWT com header sem 'alg' levante InvalidTokenError."""
    adapter = FirebaseAuthAdapter()
    with (
        patch("jwt.get_unverified_header", return_value={}),
        pytest.raises(InvalidTokenError, match="Token JWT com cabeçalho de algoritmo ausente"),
    ):
        await adapter.verify_token("some.valid.jwt")


def test_firebase_auth_adapter_default_attributes() -> None:
    """Valida a inicialização padrão do adaptador com o endpoint oficial JWKS do Google."""
    adapter = FirebaseAuthAdapter()
    assert adapter._firebase_project_id == "thothcvs-ai"
    assert adapter._public_key is None
    assert adapter._jwks_client is not None


@pytest.mark.asyncio
async def test_verify_token_fallback_user_id(rsa_keys: tuple[bytes, bytes]) -> None:
    """Garante fallback para claim 'user_id' quando 'sub' estiver ausente no payload."""
    pem_private, pem_public = rsa_keys
    adapter = FirebaseAuthAdapter(firebase_project_id="thothcvs-ai", public_key=pem_public)

    payload = {
        "user_id": "legacy_firebase_user_888",
        "email": "legacy@thothcvs.ai",
        "name": "Legacy User",
        "aud": "thothcvs-ai",
        "iss": "https://securetoken.google.com/thothcvs-ai",
        "exp": int(time.time()) + 3600,
    }
    encoded_token = jwt.encode(payload, pem_private, algorithm="RS256")

    auth_user = await adapter.verify_token(encoded_token)

    assert auth_user.uid == "legacy_firebase_user_888"
    assert auth_user.email == "legacy@thothcvs.ai"
    assert auth_user.full_name == "Legacy User"


@pytest.mark.asyncio
async def test_verify_token_jwks_network_failure_raises_invalid_token() -> None:
    """Garante que falhas de rede no PyJWKClient levantem InvalidTokenError com clareza."""
    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.side_effect = ConnectionError("Google JWKS unreachable")
    adapter = FirebaseAuthAdapter(jwks_client=mock_jwks)

    with pytest.raises(InvalidTokenError, match="Token Firebase inválido"):
        await adapter.verify_token("some.valid.jwt")
