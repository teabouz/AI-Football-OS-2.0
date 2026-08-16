"""
Minimal duck-typed stand-ins for python-telegram-bot's Update/Context, just
enough surface area for the handlers under test. Real handler functions
are called directly (not through the Application/dispatcher), which is
the fastest way to exercise real authorization logic without a live bot
connection.
"""


class FakeMessage:
    def __init__(self):
        self.sent = []  # list of (text, kwargs) actually "sent" back to the user

    async def reply_text(self, text, **kwargs):
        self.sent.append((text, kwargs))
        return self


class FakeUser:
    def __init__(self, telegram_id, username=None, first_name="Test"):
        self.id = telegram_id
        self.username = username
        self.first_name = first_name
        self.last_name = None
        self.language_code = "en"


class FakeUpdate:
    def __init__(self, telegram_id, username=None):
        self.effective_user = FakeUser(telegram_id, username=username)
        self.message = FakeMessage()
        self.callback_query = None


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []
        self.user_data = {}
