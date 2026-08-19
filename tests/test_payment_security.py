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


@pytest.mark.asyncio
async def test_payment_ownership_enforced_in_refresh_status(
    db_session, make_user, monkeypatch
):
    """An attacker must not be able to use another user's payment reference
    to trigger Paystack verification or receive Premium access.
    """
    from models import Payment, PaymentStatus, SubscriptionTier
    from handlers import payments as payment_handler

    victim = make_user(telegram_id=7001)
    attacker = make_user(telegram_id=7002)

    payment = Payment(
        user_id=victim.id,
        reference="tg7001_secret",
        amount_kobo=500000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    db_session.commit()

    class FakeCallbackQuery:
        data = "pay:refresh:tg7001_secret"

        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, *args, **kwargs):
            self.text = args[0] if args else ""

    class FakeTelegramUser:
        id = 7002

    class FakeUpdate:
        callback_query = FakeCallbackQuery()
        effective_user = FakeTelegramUser()

    async def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "Attacker must not reach Paystack verification"
        )

    monkeypatch.setattr(
        payment_handler.paystack,
        "verify_transaction",
        fail_if_called,
    )

    HandlerSession = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(payment_handler, "SessionLocal", HandlerSession)

    await payment_handler.refresh_status(FakeUpdate(), None)

    db_session.refresh(victim)
    db_session.refresh(payment)

    assert victim.subscription_tier == SubscriptionTier.FREE
    assert victim.subscription_expires_at is None
    assert payment.status == PaymentStatus.PENDING
    assert "Couldn't find that payment" in FakeUpdate.callback_query.text


def test_webhook_rejects_invalid_signature(db_session, monkeypatch):
    """The real Flask webhook route must reject forged requests before
    attempting Paystack verification or touching payment records.
    """
    import payment_server

    monkeypatch.setattr(
        payment_server,
        "SessionLocal",
        sessionmaker(bind=db_session.get_bind()),
    )

    async_or_sync_called = False

    def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "Paystack verification must not run for an invalid webhook signature"
        )

    monkeypatch.setattr(
        payment_server.paystack,
        "verify_transaction_sync",
        fail_if_called,
    )

    client = payment_server.app.test_client()

    response = client.post(
        "/paystack/webhook",
        data=b'{"event":"charge.success","data":{"reference":"tg999_forged"}}',
        headers={"X-Paystack-Signature": "invalid-signature"},
    )

    assert response.status_code == 401
    assert response.get_json()["status"] == "invalid signature"


def test_webhook_success_activates_premium(
    db_session, make_user, monkeypatch
):
    """A correctly signed charge.success webhook must re-verify the
    transaction and then activate Premium for the payment owner.
    """
    import payment_server
    from models import Payment, PaymentStatus, SubscriptionTier

    user = make_user(telegram_id=8101)

    reference = "tg8101_webhook_success"

    payment = Payment(
        user_id=user.id,
        reference=reference,
        amount_kobo=500000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    db_session.commit()

    monkeypatch.setattr(
        payment_server,
        "SessionLocal",
        sessionmaker(bind=db_session.get_bind()),
    )

    def fake_verify_transaction_sync(ref):
        assert ref == reference
        return {
            "status": True,
            "data": {
                "status": "success",
                "reference": reference,
                "amount": 500000,
                "currency": "NGN",
            },
        }

    monkeypatch.setattr(
        payment_server.paystack,
        "verify_transaction_sync",
        fake_verify_transaction_sync,
    )

    body = (
        b'{"event":"charge.success",'
        b'"data":{"reference":"tg8101_webhook_success"}}'
    )

    signature = hmac.new(
        b"sk_test_fixed_secret_for_tests",
        body,
        hashlib.sha512,
    ).hexdigest()

    client = payment_server.app.test_client()

    response = client.post(
        "/paystack/webhook",
        data=body,
        headers={"X-Paystack-Signature": signature},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.SUCCESS
    assert payment.verified_at is not None
    assert user.subscription_tier == SubscriptionTier.PREMIUM
    assert user.subscription_expires_at is not None


def test_webhook_failed_paystack_verification_does_not_upgrade(
    db_session, make_user, monkeypatch
):
    """A validly signed webhook must not grant Premium when Paystack's
    authoritative transaction verification says the payment failed.
    """
    import payment_server
    from models import Payment, PaymentStatus, SubscriptionTier

    user = make_user(telegram_id=8102)

    reference = "tg8102_webhook_failed"

    payment = Payment(
        user_id=user.id,
        reference=reference,
        amount_kobo=500000,
        currency="NGN",
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    db_session.commit()

    monkeypatch.setattr(
        payment_server,
        "SessionLocal",
        sessionmaker(bind=db_session.get_bind()),
    )

    monkeypatch.setattr(
        payment_server.paystack,
        "verify_transaction_sync",
        lambda ref: {
            "status": True,
            "data": {
                "status": "failed",
                "reference": ref,
                "amount": 500000,
                "currency": "NGN",
            },
        },
    )

    body = (
        b'{"event":"charge.success",'
        b'"data":{"reference":"tg8102_webhook_failed"}}'
    )

    signature = hmac.new(
        b"sk_test_fixed_secret_for_tests",
        body,
        hashlib.sha512,
    ).hexdigest()

    client = payment_server.app.test_client()

    response = client.post(
        "/paystack/webhook",
        data=body,
        headers={"X-Paystack-Signature": signature},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "not successful"

    db_session.refresh(user)
    db_session.refresh(payment)

    assert payment.status == PaymentStatus.PENDING
    assert user.subscription_tier == SubscriptionTier.FREE
    assert user.subscription_expires_at is None


def test_webhook_unknown_reference_does_not_upgrade(
    db_session, monkeypatch
):
    """A validly signed webhook for a reference that does not exist in our
    database must never create or credit an account.
    """
    import payment_server

    monkeypatch.setattr(
        payment_server,
        "SessionLocal",
        sessionmaker(bind=db_session.get_bind()),
    )

    reference = "tg9999_unknown"

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

    body = (
        b'{"event":"charge.success",'
        b'"data":{"reference":"tg9999_unknown"}}'
    )

    signature = hmac.new(
        b"sk_test_fixed_secret_for_tests",
        body,
        hashlib.sha512,
    ).hexdigest()

    client = payment_server.app.test_client()

    response = client.post(
        "/paystack/webhook",
        data=body,
        headers={"X-Paystack-Signature": signature},
    )

    assert response.status_code == 404
    assert response.get_json()["status"] == "unknown reference"
