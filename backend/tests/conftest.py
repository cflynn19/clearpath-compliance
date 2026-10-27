import os
import re

# Before the app is imported: a separate database, and a fake key so a real model call
# could never succeed. load_dotenv() doesn't override variables that are already set.
os.environ["DATABASE_URL"] = "postgresql://localhost/clearpath_test"
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.llm import checker, store  # noqa: E402
from app.review import store as review_store  # noqa: E402
from app.rules import registry  # noqa: E402

store.metadata.create_all(engine)
review_store.metadata.create_all(engine)
registry.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE llm_results, llm_calls, events, flags, asset_versions, assets, custom_rules, rule_settings RESTART IDENTITY"))

    def no_real_calls(prompt):
        raise AssertionError("tests must not call the real model; use the fake_model fixture")

    monkeypatch.setattr(checker, "call_model", no_real_calls)


@pytest.fixture
def fake_model(monkeypatch):
    """Replace the model with a stub. Set `.output` to the verdicts it should return.

    Like the real model is told to, it answers every rule in the prompt: rules missing
    from `.output` get a "not violated" verdict. Set `.complete = False` to make it skip
    them instead, the way a manipulated model might.
    """

    class Fake:
        output = checker.ModelOutput(verdicts=[])
        complete = True
        prompts: list[str] = []

        def __call__(self, prompt):
            self.prompts.append(prompt)
            if isinstance(self.output, Exception):
                raise self.output
            if not self.complete:
                return self.output
            given = re.findall(r"^- ([a-z0-9-]+): ", prompt, re.M)
            answered = {v.rule_id for v in self.output.verdicts}
            filler = [
                checker.Verdict(rule_id=r, violated=False, quotes=[], why="Not violated.")
                for r in given
                if r not in answered
            ]
            return checker.ModelOutput(verdicts=[*self.output.verdicts, *filler])

    fake = Fake()
    fake.prompts = []
    monkeypatch.setattr(checker, "call_model", fake)
    return fake
