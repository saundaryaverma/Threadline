import os
from unittest.mock import MagicMock

import pytest

# Point the app at a separate test database before it's imported.
os.environ.setdefault("DATABASE_URL", "postgresql://chat:chat@localhost:5432/threadline_test")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import app as threadline  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    threadline.init_db()


@pytest.fixture(autouse=True)
def clean_db():
    """Every test starts with empty tables."""
    with threadline.db() as conn:
        conn.execute("TRUNCATE messages, conversations RESTART IDENTITY CASCADE")
    yield


@pytest.fixture
def client():
    threadline.app.config["TESTING"] = True
    return threadline.app.test_client()


def chunk(text):
    """One piece of a streamed OpenAI response."""
    c = MagicMock()
    c.choices = [MagicMock()]
    c.choices[0].delta.content = text
    return c


@pytest.fixture
def fake_model(monkeypatch):
    """Replace the OpenAI call. Set .reply to the chunks the model should stream,
    or .error to an exception it should raise. .calls records what was sent."""

    class FakeModel:
        reply = ["Hello", " there!"]
        error = None
        error_after = None  # raise after streaming this many chunks
        calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if self.error and self.error_after is None:
                raise self.error

            def stream():
                for i, text in enumerate(self.reply):
                    if self.error and i == self.error_after:
                        raise self.error
                    yield chunk(text)

            return stream()

    fake = FakeModel()
    fake.calls = []
    monkeypatch.setattr(threadline.client.chat.completions, "create", fake.create)
    return fake
