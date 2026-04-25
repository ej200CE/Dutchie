"""Mock bunq API endpoints — mirrors the real bunq sandbox URL shape.

Real:  GET https://public-api.sandbox.bunq.com/v1/user/{user_id}/monetary-account/{account_id}/payment
Mock:  GET /api/mock/bunq/v1/user/{user_id}/monetary-account/{account_id}/payment
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from billion_hackathon.modules.bunq_mock.fixtures import STORY1_PAYMENTS

router = APIRouter(prefix="/api/mock/bunq/v1", tags=["bunq-mock"])


@router.get("/user/{user_id}/monetary-account/{account_id}/payment")
async def list_payments(user_id: int, account_id: int) -> JSONResponse:
    return JSONResponse({"Response": STORY1_PAYMENTS})
