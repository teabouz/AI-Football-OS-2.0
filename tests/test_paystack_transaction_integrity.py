"""
Paystack transaction integrity and idempotency tests.

These tests ensure that a successful Paystack transaction:
1. matches the local payment reference,
2. matches the expected amount,
3. matches the expected currency,
4. cannot grant Premium through a mismatched transaction,
5. cannot grant Premium twice through duplicate processing.
"""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker


TEST_SECRET = "sk_test_fixed_secret_for_tests"


@pytest.fixture(autouse=True)
def _paystack_secret(monkeypatch):
    monkeypatch.setattr("config.PAYSTACK_SECRET_KEY", TEST_SECRET)
    yield


def _sign(body: bytes) -> str:
    return hmac.new(
        TEST_SECRET.encode(),
        body,
        hashlib.sha512,
    ).hexdigest()


def _webhook_body(reference: str) -> bytes:
    return (
        b'{"event":"charge.success",'
        b'"data":{"reference":"' + reference.encode() + b'"}}'
    )


def _patch_test_session(payment_server, db_session, monkeypatch):
    monkeypatch.setattr(
        payment_server,
        "SessionLocal",
        sessionmaker(bind=db_session.get_bind()),
    )


def _post_success_webhook(
    payment_server,
    reference: str,
):
    body = _webhook_body(reference)
    client = payment_server.app.test_client()

    return client.post(
        "/paystack/webhook",
        data=body,
        headers={"X-Paystack-Signature": _sign(body)},
    )


def test_webhook_rejects_amount_mismatch(
    db_session,
    make_user,
    monkeypatch,
):
    """A successful Paystack transaction for the wrong amount must not
    activate Premium.
    """
    import payment_server
    from models import Payment, PaymentStatus, SubscriptionTier

    user = make_user(telegram_id=8201)

    reference = "tg8201_amount_mismatch"

    payment = Payment(
        user_id=user.id,
        reference=reference,
        amount_kobo=500000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )

    db_session.add(payment)
    db_session.commit()

    _patch_test_session(payment_server, db_session, monkeypatch)

    monkeypatch.setattr(
        payment_server.paystack,
        "verify_transaction_sync",
        lambda ref: {
            "status": True,
            "data": {
                "status": "success",
                "reference": ref,
                "amount": 100000,
                "currency": "NGN",
            },
        },
    )

    response = _post_success_webhook(payment_server, reference)

    assert response.status_code == 200
    assert response.get_json()["status"] != "ok"

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.PENDING
    assert user.subscription_tier == SubscriptionTier.FREE
    assert user.subscription_expires_at is None


def test_webhook_rejects_currency_mismatch(
    db_session,
    make_user,
    monkeypatch,
):
    """A successful transaction in the wrong currency must not activate
    Premium.
    """
    import payment_server
    from models import Payment, PaymentStatus, SubscriptionTier

    user = make_user(telegram_id=8202)

    reference = "tg8202_currency_mismatch"

    payment = Payment(
        user_id=user.id,
        reference=reference,
        amount_kobo=500000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )

    db_session.add(payment)
    db_session.commit()

    _patch_test_session(payment_server, db_session, monkeypatch)

    monkeypatch.setattr(
        payment_server.paystack,
        "verify_transaction_sync",
        lambda ref: {
            "status": True,
            "data": {
                "status": "success",
                "reference": ref,
                "amount": 500000,
                "currency": "USD",
            },
        },
    )

    response = _post_success_webhook(payment_server, reference)

    assert response.status_code == 200
    assert response.get_json()["status"] != "ok"

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.PENDING
    assert user.subscription_tier == SubscriptionTier.FREE
    assert user.subscription_expires_at is None


def test_webhook_rejects_reference_mismatch(
    db_session,
    make_user,
    monkeypatch,
):
    """The authoritative Paystack transaction must have the same reference
    as the local Payment record.
    """
    import payment_server
    from models import Payment, PaymentStatus, SubscriptionTier

    user = make_user(telegram_id=8203)

    reference = "tg8203_reference_mismatch"

    payment = Payment(
        user_id=user.id,
        reference=reference,
        amount_kobo=500000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )

    db_session.add(payment)
    db_session.commit()

    _patch_test_session(payment_server, db_session, monkeypatch)

    monkeypatch.setattr(
        payment_server.paystack,
        "verify_transaction_sync",
        lambda ref: {
            "status": True,
            "data": {
                "status": "success",
                "reference": "tg9999_other_transaction",
                "amount": 500000,
                "currency": "NGN",
            },
        },
    )

    response = _post_success_webhook(payment_server, reference)

    assert response.status_code == 200
    assert response.get_json()["status"] != "ok"

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.PENDING
    assert user.subscription_tier == SubscriptionTier.FREE
    assert user.subscription_expires_at is None


def test_webhook_duplicate_delivery_does_not_extend_premium_twice(
    db_session,
    make_user,
    monkeypatch,
):
    """Processing the same successful webhook twice must not grant two
    subscription periods.
    """
    import payment_server
    from models import Payment, PaymentStatus, SubscriptionTier

    user = make_user(telegram_id=8204)

    reference = "tg8204_duplicate_webhook"

    payment = Payment(
        user_id=user.id,
        reference=reference,
        amount_kobo=500000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )

    db_session.add(payment)
    db_session.commit()

    _patch_test_session(payment_server, db_session, monkeypatch)

    monkeypatch.setattr(
        payment_server.paystack,
        "verify_transaction_sync",
        lambda ref: {
            "status": True,
            "data": {
                "status": "success",
                "reference": ref,
                "amount": 500000,
                "currency": "NGN",
            },
        },
    )

    first = _post_success_webhook(payment_server, reference)

    assert first.status_code == 200

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.SUCCESS
    assert user.subscription_tier == SubscriptionTier.PREMIUM

    first_expiry = user.subscription_expires_at

    second = _post_success_webhook(payment_server, reference)

    assert second.status_code == 200

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.SUCCESS
    assert user.subscription_tier == SubscriptionTier.PREMIUM

    assert user.subscription_expires_at == first_expiry


def test_webhook_success_requires_exact_local_amount(
    db_session,
    make_user,
    monkeypatch,
):
    """The amount must be compared against the Payment row rather than only
    against the global Premium price.
    """
    import payment_server
    from models import Payment, PaymentStatus, SubscriptionTier

    user = make_user(telegram_id=8205)

    reference = "tg8205_local_amount"

    payment = Payment(
        user_id=user.id,
        reference=reference,
        amount_kobo=750000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )

    db_session.add(payment)
    db_session.commit()

    _patch_test_session(payment_server, db_session, monkeypatch)

    monkeypatch.setattr(
        payment_server.paystack,
        "verify_transaction_sync",
        lambda ref: {
            "status": True,
            "data": {
                "status": "success",
                "reference": ref,
                "amount": 500000,
                "currency": "NGN",
            },
        },
    )

    response = _post_success_webhook(payment_server, reference)

    assert response.status_code == 200
    assert response.get_json()["status"] != "ok"

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.PENDING
    assert user.subscription_tier == SubscriptionTier.FREE
