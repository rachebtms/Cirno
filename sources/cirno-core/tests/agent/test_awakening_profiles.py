"""One-time profile guidance and role isolation in actual prompt construction."""
import pytest
from cirno_core.config.home import get_home_path, set_instance_path
from cirno_core.profiles.awakening import awakening_prompt, initialize_awakening
from cirno_core.agent.context import ContextBuilder
from cirno_core.session.keys import ROUTER_SESSION_KEY


@pytest.fixture(autouse=True)
def instance(tmp_path):
    set_instance_path(tmp_path)
    get_home_path().mkdir(parents=True, exist_ok=True)
    yield
    set_instance_path(None)


def test_awakening_is_router_only_and_completion_survives_initialization(tmp_path):
    initialize_awakening()
    builder = ContextBuilder(tmp_path / "workspace")
    router = builder.build_system_prompt(session_key=ROUTER_SESSION_KEY)
    worker = builder.build_system_prompt(session_key="websocket:worker")
    assert "# First awakening" in router and "# First awakening" not in worker
    assert "Only Dream memory-consolidation tasks may edit" not in router
    assert "preferred form of address" in router and "USER.md" in router
    assert "SOUL.md" in router and "WORKER.md" in worker
    soul = get_home_path() / "SOUL.md"
    user = get_home_path() / "USER.md"
    soul.write_text("# Identity\nCirno, an ice fairy.\n")
    user.write_text("# User\nPreferred address: 主人.\n")
    (get_home_path() / "BOOTSTRAP.md").write_text("")
    initialize_awakening()
    assert awakening_prompt() == ""
    prompt = builder.build_system_prompt(session_key=ROUTER_SESSION_KEY)
    assert "ice fairy" in prompt and "主人" in prompt
    assert "# First awakening" not in prompt


def test_existing_profiles_are_not_replaced_by_registration():
    soul = get_home_path() / "SOUL.md"
    soul.write_text("Existing personality")
    initialize_awakening()
    assert soul.read_text() == "Existing personality"
