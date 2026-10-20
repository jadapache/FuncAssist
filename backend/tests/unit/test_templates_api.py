import pytest

from app.ai.templates import (

    DEFAULT_PROMPTS,

    DEFAULT_RUBRICS,

    get_prompt,
    get_rubric,
    list_prompts,
    list_rubrics,
    reset_prompt,
    reset_rubric,
    save_prompt,
    save_rubric,
)

from app.api.routers.ai_templates import (

    TemplateUpdate,

    RubricUpdate,

    update_prompt,

    reset_prompt_endpoint,

    update_rubric,

    reset_rubric_endpoint,
)

from app.db.database import set_session_override, set_sync_session_override

from tests.fake_session import GLOBAL_FAKE_STORAGE, fake_async_db, fake_sync_db



@pytest.fixture(autouse=True)

def setup_fake_db():

    import app.ai.templates as t_module

    t_module._DB_SEEDED = False

    GLOBAL_FAKE_STORAGE.clear()

    set_session_override(fake_async_db)

    set_sync_session_override(fake_sync_db)

    t_module.ensure_ai_templates_seeded()
    yield

    GLOBAL_FAKE_STORAGE.clear()

    set_session_override(None)

    set_sync_session_override(None)

    t_module._DB_SEEDED = False



@pytest.mark.asyncio
async def test_list_and_get_prompts():
    prompts = await list_prompts()

    assert len(prompts) >= 10

    features = [p["feature"] for p in prompts]

    assert "mejoras_doc" in features

    assert "standup" in features


    p = await get_prompt("mejoras_doc")

    assert p["feature"] == "mejoras_doc"
    assert "system" in p
    assert "user_template" in p



@pytest.mark.asyncio

async def test_list_and_get_rubrics():

    rubrics = await list_rubrics()

    assert len(rubrics) >= 10

    features = [r["feature"] for r in rubrics]

    assert "mejoras_doc" in features

    assert "standup" in features


    r = await get_rubric("mejoras_doc")

    assert r["feature"] == "mejoras_doc"

    assert isinstance(r["criteria"], list)



@pytest.mark.asyncio

async def test_update_and_reset_prompt_endpoint():

    original = await get_prompt("standup")

    original_version = original.get("version", 1)


    # Update via endpoint

    body = TemplateUpdate(

        system="Custom standup system test prompt",

        user_template="Custom user template {query} {context} {rubric}",

        allowed_sources=["jira", "github", "knowledge"],
    )

    saved = await update_prompt("standup", body)

    assert saved["system"] == "Custom standup system test prompt"

    assert saved["version"] == original_version + 1


    # Verify get returns new data

    assert (await get_prompt("standup"))["system"] == "Custom standup system test prompt"


    # Reset prompt to defaults

    reset_data = await reset_prompt_endpoint("standup")

    assert reset_data["system"] == DEFAULT_PROMPTS["standup"]["system"]

    assert (await get_prompt("standup"))["system"] == DEFAULT_PROMPTS["standup"]["system"]



@pytest.mark.asyncio

async def test_update_and_reset_rubric_endpoint():

    original = await get_rubric("standup")


    # Update via endpoint

    new_criteria = ["Test criterion 1", "Test criterion 2"]

    body = RubricUpdate(criteria=new_criteria)

    saved = await update_rubric("standup", body)

    assert saved["criteria"] == new_criteria


    # Verify get returns new data

    assert (await get_rubric("standup"))["criteria"] == new_criteria


    # Reset rubric to defaults

    reset_data = await reset_rubric_endpoint("standup")

    assert reset_data["criteria"] == DEFAULT_RUBRICS["standup"]["criteria"]

    assert (await get_rubric("standup"))["criteria"] == DEFAULT_RUBRICS["standup"]["criteria"]



@pytest.mark.asyncio

async def test_prompt_and_rubric_history():

    from app.api.routers.ai_templates import prompt_history, rubric_history
    

    # 1. Check prompt history

    p_hist = await prompt_history("standup", limit=10)

    assert "history" in p_hist

    assert len(p_hist["history"]) >= 1


    # 2. Check rubric history

    r_hist = await rubric_history("standup", limit=10)

    assert "history" in r_hist

    assert len(r_hist["history"]) >= 1

