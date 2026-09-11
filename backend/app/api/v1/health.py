"""Endpoints de diagnóstico e integridade operacional (Health Checks).

Fornece sondas HTTP de liveness (/healthz) e readiness (/ready)
compatíveis com o orquestrador do Google Cloud Run e Kubernetes.
"""

from typing import Any

from fastapi import APIRouter, status

router = APIRouter(tags=["Health"])


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def liveness_probe() -> dict[str, Any]:
    """Sonda de liveness confirmando que o processo Uvicorn está de pé e respondendo.

    Returns:
        Dict[str, Any]: Status operacional básico da aplicação.

    Business Rules:
        - Deve responder com baixa latência sem depender de conexões com banco.
    """
    return {
        "status": "healthy",
        "service": "thothcvs-backend",
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_probe() -> dict[str, Any]:
    """Sonda de readiness confirmando que a aplicação está pronta para receber tráfego.

    Returns:
        Dict[str, Any]: Prontidão dos subsistemas essenciais.

    Business Rules:
        - Utilizado pelo balanceador de carga antes de rotear tráfego para a instância.
    """
    return {
        "status": "ready",
        "service": "thothcvs-backend",
    }
