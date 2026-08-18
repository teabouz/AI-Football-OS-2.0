"""
Regression tests for the Premium subscription/upgrade flow.

These tests protect against:
1. Premium users seeing an Upgrade button on the Subscription screen.
2. Premium users being able to start another Paystack transaction.
3. Free users retaining the normal upgrade flow.
"""

import pytest

from models import SubscriptionTier


@pytest.mark.asyncio
async def test_premium_user_subscription_screen_has_no_upgrade_button(
    db_session, make_user, monkeypatch
):
    from handlers import subscription

    user = make_user(
        telegram_id=11001,
        subscription_tier=SubscriptionTier.PREMIUM,
    )

    # Give the Premium subscription a valid expiry.
    from datetime import datetime, timedelta, timezone

    user.subscription_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
    db_session.commit()

    class FakeCallbackQuery:
        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, text, **kwargs):
            self.text = text
            self.kwargs = kwargs

    class FakeTelegramUser:
        id = 11001

    class FakeUpdate:
        callback_query = FakeCallbackQuery()
        effective_user = FakeTelegramUser()

    HandlerSession = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(
        bind=db_session.get_bind()
    )
    monkeypatch.setattr(subscription, "SessionLocal", HandlerSession)

    await subscription.show_subscription(FakeUpdate(), None)

    markup = FakeUpdate.callback_query.kwargs["reply_markup"]

    buttons = [
        button
        for row in markup.inline_keyboard
        for button in row
    ]

    callback_data = [button.callback_data for button in buttons if button.callback_data]

    assert "sub:upgrade_start" not in callback_data


@pytest.mark.asyncio
async def test_premium_user_cannot_start_second_upgrade(
    db_session, make_user, monkeypatch
):
    from handlers import payments

    from datetime import datetime, timedelta, timezone

    user = make_user(
        telegram_id=11002,
        subscription_tier=SubscriptionTier.PREMIUM,
    )
    user.subscription_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
    db_session.commit()

    class FakeCallbackQuery:
        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, text, **kwargs):
            self.text = text
            self.kwargs = kwargs

    class FakeTelegramUser:
        id = 11002

    class FakeUpdate:
        callback_query = FakeCallbackQuery()
        effective_user = FakeTelegramUser()

    HandlerSession = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(
        bind=db_session.get_bind()
    )
    monkeypatch.setattr(payments, "SessionLocal", HandlerSession)

    # If the guard is broken, this function could reach Paystack.
    async def fail_if_called(*args, **kwargs):
        raise AssertionError(
            "Premium user must not reach Paystack payment initialization"
        )

    monkeypatch.setattr(
        payments.paystack,
        "initialize_transaction",
        fail_if_called,
    )

    monkeypatch.setattr(
        payments.config,
        "PAYSTACK_SECRET_KEY",
        "sk_test_regression_secret",
    )

    result = await payments.upgrade_start(FakeUpdate(), None)

    assert result == payments.ConversationHandler.END

    assert "already Premium" in FakeUpdate.callback_query.text


@pytest.mark.asyncio
async def test_free_user_can_enter_upgrade_flow(
    db_session, make_user, monkeypatch
):
    from handlers import payments

    user = make_user(
        telegram_id=11003,
    )

    class FakeCallbackQuery:
        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, text, **kwargs):
            self.text = text
            self.kwargs = kwargs

    class FakeTelegramUser:
        id = 11003

    class FakeUpdate:
        callback_query = FakeCallbackQuery()
        effective_user = FakeTelegramUser()

    HandlerSession = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(
        bind=db_session.get_bind()
    )
    monkeypatch.setattr(payments, "SessionLocal", HandlerSession)

    monkeypatch.setattr(
        payments.config,
        "PAYSTACK_SECRET_KEY",
        "sk_test_regression_secret",
    )

    result = await payments.upgrade_start(FakeUpdate(), None)

    assert result == payments.ASK_EMAIL
    assert "email" in FakeUpdate.callback_query.text.lower()
