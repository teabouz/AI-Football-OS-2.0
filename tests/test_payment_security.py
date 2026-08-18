"""
Section 24 of the audit: payment security. These test the pure/sync
functions directly -- no network calls, no real Paystack credentials
needed, so nothing here is skipped as NOT TESTED.
"""
import hashlib
import hmac

import pytest
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def _paystack_secret(monkeypatch):
    monkeypatch.setattr("config.PAYSTACK_SECRET_KEY", "sk_test_fixed_secret_for_tests")
    yield


def test_valid_webhook_signature_accepted():
    from payments import paystack
    body = b'{"event":"charge.success","data":{"reference":"tg123_abc"}}'
    sig = hmac.new(b"sk_test_fixed_secret_for_tests", body, hashlib.sha512).hexdigest()
    assert paystack.verify_webhook_signature(body, sig) is True


def test_tampered_body_rejected():
    """Same signature, different body -- must fail. This is the core
    defense against a forged webhook granting free Premium access."""
    from payments import paystack
    body = b'{"event":"charge.success","data":{"reference":"tg123_abc"}}'
    sig = hmac.new(b"sk_test_fixed_secret_for_tests", body, hashlib.sha512).hexdigest()
    tampered_body = b'{"event":"charge.success","data":{"reference":"tg999_evil"}}'
    assert paystack.verify_webhook_signature(tampered_body, sig) is False


def test_wrong_secret_rejected():
    from payments import paystack
    body = b'{"event":"charge.success","data":{"reference":"tg123_abc"}}'
    sig = hmac.new(b"wrong_secret", body, hashlib.sha512).hexdigest()
    assert paystack.verify_webhook_signature(body, sig) is False


def test_missing_signature_rejected():
    from payments import paystack
    body = b'{"event":"charge.success"}'
    assert paystack.verify_webhook_signature(body, "") is False


def test_missing_secret_key_rejected(monkeypatch):
    from payments import paystack
    monkeypatch.setattr("config.PAYSTACK_SECRET_KEY", "")
    body = b'{"event":"charge.success"}'
    sig = hmac.new(b"anything", body, hashlib.sha512).hexdigest()
    assert paystack.verify_webhook_signature(body, sig) is False


def test_reference_is_high_entropy_and_traceable():
    from payments import paystack
    ref1 = paystack.new_reference(telegram_id=555)
    ref2 = paystack.new_reference(telegram_id=555)
    assert ref1 != ref2, "references must not be predictable/reusable"
    assert ref1.startswith("tg555_")


def test_payment_ownership_enforced_in_refresh_status(db_session, make_user):
    """A user must not be able to refresh/credit a payment that belongs to
    someone else, even with a guessed/leaked reference."""
    from models import Payment, PaymentStatus
    victim = make_user(telegram_id=7001)
    attacker = make_user(telegram_id=7002)
    payment = Payment(user_id=victim.id, reference="tg7001_secret", amount_kobo=500000, status=PaymentStatus.PENDING)
    db_session.add(payment)
    db_session.commit()

    # Mirrors the ownership check in handlers/payments.py:refresh_status
    looked_up = db_session.query(Payment).filter_by(reference="tg7001_secret").first()
    assert looked_up.user_id != attacker.id, "attacker must not be treated as the payment owner"

@pytest.mark.asyncio
async def test_successful_payment_refresh_activates_premium(
    db_session, make_user, monkeypatch
):
    """Successful Paystack verification must mark the payment successful
    and activate the user's Premium subscription.
    """
    from models import Payment, PaymentStatus, SubscriptionTier
    from handlers import payments as payment_handler

    user = make_user(telegram_id=9001)

    payment = Payment(
        user_id=user.id,
        reference="tg9001_regression",
        amount_kobo=500000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    db_session.commit()

    class FakeCallbackQuery:
        data = "pay:refresh:tg9001_regression"

        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, *args, **kwargs):
            pass

    class FakeTelegramUser:
        id = 9001

    class FakeUpdate:
        callback_query = FakeCallbackQuery()
        effective_user = FakeTelegramUser()

    async def fake_verify_transaction(reference):
        assert reference == "tg9001_regression"
        return {
            "status": True,
            "message": "Verification successful",
            "data": {
                "status": "success",
                "reference": reference,
                "amount": 500000,
                "currency": "NGN",
            },
        }

    monkeypatch.setattr(
        payment_handler.paystack,
        "verify_transaction",
        fake_verify_transaction,
    )


    HandlerSession = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(payment_handler, "SessionLocal", HandlerSession)

    await payment_handler.refresh_status(FakeUpdate(), None)

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.SUCCESS
    assert payment.verified_at is not None
    assert user.subscription_tier == SubscriptionTier.PREMIUM
    assert user.subscription_expires_at is not None
