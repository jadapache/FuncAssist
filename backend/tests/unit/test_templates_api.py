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


def test_list_and_get_prompts():
    prompts = list_prompts()
    assert len(prompts) >= 10
    features = [p["feature"] for p in prompts]
    assert "mejoras_doc" in features
    assert "standup" in features

    p = get_prompt("mejoras_doc")
    assert p["feature"] == "mejoras_doc"
    assert "system" in p
    assert "user_template" in p


def test_list_and_get_rubrics():
    rubrics = list_rubrics()
    assert len(rubrics) >= 10
    features = [r["feature"] for r in rubrics]
    assert "mejoras_doc" in features
    assert "standup" in features

    r = get_rubric("mejoras_doc")
    assert r["feature"] == "mejoras_doc"
    assert isinstance(r["criteria"], list)


@pytest.mark.asyncio
async def test_update_and_reset_prompt_endpoint():
    original = get_prompt("standup")
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
    assert get_prompt("standup")["system"] == "Custom standup system test prompt"

    # Reset prompt to defaults
    reset_data = await reset_prompt_endpoint("standup")
    assert reset_data["system"] == DEFAULT_PROMPTS["standup"]["system"]
    assert get_prompt("standup")["system"] == DEFAULT_PROMPTS["standup"]["system"]


@pytest.mark.asyncio
async def test_update_and_reset_rubric_endpoint():
    original = get_rubric("standup")

    # Update via endpoint
    new_criteria = ["Test criterion 1", "Test criterion 2"]
    body = RubricUpdate(criteria=new_criteria)
    saved = await update_rubric("standup", body)
    assert saved["criteria"] == new_criteria

    # Verify get returns new data
    assert get_rubric("standup")["criteria"] == new_criteria

    # Reset rubric to defaults
    reset_data = await reset_rubric_endpoint("standup")
    assert reset_data["criteria"] == DEFAULT_RUBRICS["standup"]["criteria"]
    assert get_rubric("standup")["criteria"] == DEFAULT_RUBRICS["standup"]["criteria"]
