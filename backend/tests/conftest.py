import os

# Before the app is imported: a separate database, and a fake key so a real model call
# could never succeed. load_dotenv() doesn't override variables that are already set.
os.environ["DATABASE_URL"] = "postgresql://localhost/clearpath_test"
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.llm import checker, store  # noqa: E402
from app.review import store as review_store  # noqa: E402

store.metadata.create_all(engine)
review_store.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE llm_results, llm_calls, events, flags, asset_versions, assets RESTART IDENTITY"))

    def no_real_calls(prompt):
        raise AssertionError("tests must not call the real model; use the fake_model fixture")

    monkeypatch.setattr(checker, "call_model", no_real_calls)


@pytest.fixture
def fake_model(monkeypatch):
    """Replace the model with a stub. Set `.output` to what it should return."""

    class Fake:
        output = checker.ModelOutput(findings=[])
        prompts: list[str] = []

        def __call__(self, prompt):
            self.prompts.append(prompt)
            if isinstance(self.output, Exception):
                raise self.output
            return self.output

    fake = Fake()
    fake.prompts = []
    monkeypatch.setattr(checker, "call_model", fake)
    return fake
