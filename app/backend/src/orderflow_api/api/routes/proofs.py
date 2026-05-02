"""Routes for the Proof-Authenticity Verifier (P0-3).

Exposes a stateless verification endpoint that the UI can call before
attempting to close an obligation, and that the obligation PATCH gate
calls internally when status transitions to `completed`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from orderflow_api.api.dependencies.auth import get_current_user
from orderflow_api.api.response import success
from orderflow_api.core.proof_verifier import ProofPayload, verify_proof
from orderflow_api.schemas.proofs import (
    ProofCheckResult,
    ProofVerifyData,
    ProofVerifyEnvelope,
    ProofVerifyRequest,
)

router = APIRouter(tags=["proofs"])


@router.post("/proofs/verify", response_model=ProofVerifyEnvelope)
async def verify_proof_route(
    request: Request,
    payload: ProofVerifyRequest,
    _user=Depends(get_current_user),
) -> dict[str, object]:
    request_id = getattr(request.state, "request_id", None)

    result = verify_proof(
        ProofPayload(
            obligation_text=payload.obligation_text,
            proof_text=payload.proof_text,
            obligation_due_date=payload.obligation_due_date,
            obligation_issued_date=payload.obligation_issued_date,
            proof_timestamp=payload.proof_timestamp,
            proof_bytes_sha256=payload.proof_bytes_sha256,
            expected_sha256=payload.expected_sha256,
            proof_pdf_metadata=payload.proof_pdf_metadata,
            original_pdf_metadata=payload.original_pdf_metadata,
        )
    )

    data = ProofVerifyData(
        passed=result.passed,
        summary=result.summary,
        checks=[ProofCheckResult(**c) for c in result.to_dict()["checks"]],
    )

    return success(data=data, request_id=request_id, message="proof_verified")
