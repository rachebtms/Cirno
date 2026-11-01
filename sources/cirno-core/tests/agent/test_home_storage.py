"""Home owns assistant profiles and learned skills across project workspaces."""

from cirno.agent.context import ContextBuilder
from cirno.skills.loader import SkillsLoader
from cirno.config.home import get_home_path
from cirno.config.loader import save_config
from cirno.config.schema import Config
from cirno.utils.helpers import sync_workspace_templates
from cirno.webui.skills_api import delete_webui_skill


async def test_dream_skill_is_learned_in_home_and_available_from_another_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.txt").write_text("Project content")
    sync_workspace_templates(project, silent=True)
    home = get_home_path()
    context = ContextBuilder(project)
    assert context.memory.memory_file == home / "memory" / "MEMORY.md"
    assert context.memory.soul_file == home / "SOUL.md"
    context.memory.write_soul("Be precise and concise.")
    assert "Be precise and concise." in context.build_system_prompt()

    skill = "---\nname: learned-workflow\ndescription: Repeat a verified workflow.\n---\n\nCheck the inputs, execute the workflow and verify its outputs.\n"
    tools = context.memory.build_dream_tools()
    await tools.execute("write_file", {"path": "skills/learned-workflow/SKILL.md", "content": skill})
    assert (home / "skills" / "learned-workflow" / "SKILL.md").read_text() == skill
    second_project = tmp_path / "second-project"
    second_project.mkdir()
    assert SkillsLoader(second_project).load_skill("learned-workflow") == skill
    assert not (project / "SOUL.md").exists()
    assert not (project / "memory").exists()
    assert not (project / "skills").exists()
    assert (project / "notes.txt").read_text() == "Project content"


def test_skill_management_deletes_from_home_without_touching_the_project(tmp_path):
    home = get_home_path()
    path = home / "skills" / "example" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: example\ndescription: An example workflow.\n---\nInstructions.")
    project = tmp_path / "project"
    project.mkdir()
    config_path = tmp_path / "config.json"
    save_config(Config(), config_path)
    delete_webui_skill(project, "example", disabled_skills=set(), config_path=config_path)
    assert not path.parent.exists()
    assert list(project.iterdir()) == []
