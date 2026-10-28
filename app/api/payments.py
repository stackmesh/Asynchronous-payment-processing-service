from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_api_key
from app.db import get_session
from app.exceptions import IdempotencyConflict
from app.schemas import PaymentAccepted, PaymentCreate, PaymentDetail
from app.services import payments as payment_service

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PaymentAccepted,
    summary="Создать платёж",
)
async def create_payment(
    body: PaymentCreate,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=255),
    ],
    session: AsyncSession = Depends(get_session),
) -> PaymentAccepted:
    """Принимает платёж и ставит его в обработку.

    Повтор с тем же Idempotency-Key и тем же телом возвращает исходный платёж.
    Повтор с другим телом — 409.
    """
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must not be blank",
        )
    try:
        payment = await payment_service.create_payment(session, body, key)
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Idempotency-Key already used with a different request body",
                "payment_id": str(exc.payment_id),
            },
        ) from exc
    return payment_service.to_accepted(payment)


@router.get(
    "/{payment_id}",
    response_model=PaymentDetail,
    summary="Получить платёж",
)
async def get_payment(
    payment_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PaymentDetail:
    payment = await payment_service.get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment_service.to_detail(payment)
