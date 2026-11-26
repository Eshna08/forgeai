import os
import sys
import tempfile
from pathlib import Path

# Force offline, deterministic settings BEFORE forgeai is imported (env beats .env: load_dotenv(override=False)).
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_BACKEND"] = "hash"
os.environ["RUNS_DIR"] = tempfile.mkdtemp(prefix="forgeai_test_runs_")
os.environ["TARGET_SCORE"] = "100"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def demos() -> Path:
    d = ROOT / "demos"
    if not (d / "hr" / "docs_v2" / "leave_policy.pdf").exists():
        import demos.synth_docs as s

        sys.argv = ["synth_docs"]
        s.main()
    return d


@pytest.fixture()
def llm():
    from forgeai.llm import LLM

    return LLM()


@pytest.fixture(scope="session")
def hr_docs(demos):
    from forgeai.ingest import load_folder

    docs, _ = load_folder(demos / "hr" / "docs")
    return docs


@pytest.fixture(scope="session")
def spares_docs(demos):
    from forgeai.ingest import load_folder

    docs, _ = load_folder(demos / "spares" / "docs")
    return docs
