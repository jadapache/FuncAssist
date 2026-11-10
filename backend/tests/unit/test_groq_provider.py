import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.ai.providers.implementations import (
    GroqProvider,
    OpenAIProvider,
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    LiteLLMProvider,
)
from app.ai.providers.base import AIMessage


@pytest.mark.asyncio
async def test_groq_provider_with_litellm():
    provider = GroqProvider(api_key="gsk_testkey")
    messages = [AIMessage(role="user", content="Hola")]

    mock_choice = MagicMock()
    mock_choice.message.content = "OK desde Groq LiteLLM"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model_dump.return_value = {"choices": [{"message": {"content": "OK desde Groq LiteLLM"}}]}

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = mock_response
        result = await provider.complete(messages, model="llama-3.3-70b-versatile")

        assert result.text == "OK desde Groq LiteLLM"
        assert result.model == "llama-3.3-70b-versatile"
        assert mock_acompletion.call_count == 1
        kwargs = mock_acompletion.call_args[1]
        assert kwargs["model"] == "groq/llama-3.3-70b-versatile"
        assert kwargs["api_key"] == "gsk_testkey"


@pytest.mark.asyncio
async def test_all_litellm_model_formatting():
    groq_p = GroqProvider("key")
    assert groq_p._format_model_name("llama3") == "groq/llama3"
    assert groq_p._format_model_name("qwen-2.5-32b") == "groq/qwen-2.5-32b"
    assert groq_p._format_model_name("groq/qwen-2.5-32b") == "groq/qwen-2.5-32b"

    claude_p = ClaudeProvider("key")
    assert claude_p._format_model_name("claude-3-5-haiku-latest") == "anthropic/claude-3-5-haiku-latest"

    gemini_p = GeminiProvider("key")
    assert gemini_p._format_model_name("gemini-1.5-flash") == "gemini/gemini-1.5-flash"
    assert gemini_p._format_model_name("models/gemini-1.5-flash") == "gemini/gemini-1.5-flash"

    ollama_p = OllamaProvider("http://localhost:11434")
    assert ollama_p._format_model_name("llama3.2") == "ollama_chat/llama3.2"

    openai_p = OpenAIProvider("key")
    assert openai_p._format_model_name("openai/gpt-4o") == "gpt-4o"


def test_provider_registry():
    from app.ai.providers.registry import find_provider_spec, PROVIDER_REGISTRY
    assert find_provider_spec("groq") is not None
    assert find_provider_spec("groq").litellm_prefix == "groq"
    assert find_provider_spec("anthropic").id == "claude"
    assert find_provider_spec("google").id == "gemini"
    assert find_provider_spec("ollama_remote").id == "ollama_remote"
    assert find_provider_spec("ollama").id == "ollama_remote"
    assert find_provider_spec("local") is None
    assert find_provider_spec("builtin") is None
    assert find_provider_spec("unknown_xyz") is None


def test_resolve_provider_with_registry():
    from app.ai.providers.factory import resolve_provider
    p_groq = resolve_provider("groq", "llama-3.3-70b-versatile", api_key="gsk_test")
    assert p_groq.id == "groq"
    assert p_groq._format_model_name("llama-3.3-70b-versatile") == "groq/llama-3.3-70b-versatile"

    p_ollama = resolve_provider("ollama_remote", "llama3.2", base_url="https://ollama.mycorp.com")
    assert p_ollama.id == "ollama_remote"
    assert p_ollama._format_model_name("llama3.2") == "ollama_chat/llama3.2"

    with pytest.raises(ValueError, match="El endpoint remoto debe utilizar protocolo HTTPS"):
        resolve_provider("ollama", "llama3.2", base_url="http://localhost:11434")


def test_resolve_model_max_tokens():
    from app.ai.providers.registry import resolve_model_max_tokens
    # Limits are supplied by the persisted catalog after frontier synchronization.
    assert resolve_model_max_tokens("groq", "qwen/qwen3.8-27b", 4096) == 950
    # Small requested max_tokens is preserved
    assert resolve_model_max_tokens("groq", "qwen/qwen3.8-27b", 100) == 100
    # Llama 3.3 70B uses requested or default
    assert resolve_model_max_tokens("groq", "llama-3.3-70b-versatile", 4096) == 4096
    # Gemini uses requested or default
    assert resolve_model_max_tokens("gemini", "gemini-1.5-flash", 8192) == 8192


@pytest.mark.asyncio
async def test_qwen_groq_caps_max_tokens():
    provider = GroqProvider(api_key="gsk_testkey")
    messages = [AIMessage(role="user", content="Test Qwen")]

    mock_choice = MagicMock()
    mock_choice.message.content = "Respuesta de Qwen"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model_dump.return_value = {"choices": [{"message": {"content": "Respuesta de Qwen"}}]}

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = mock_response
        result = await provider.complete(messages, model="qwen/qwen3.8-27b", max_tokens=4096)

        assert result.text == "Respuesta de Qwen"
        assert mock_acompletion.call_count == 1
        kwargs = mock_acompletion.call_args[1]
        assert kwargs["max_tokens"] == 950


@pytest.mark.asyncio
async def test_ratelimit_friendly_exception():
    provider = GroqProvider(api_key="gsk_testkey")
    messages = [AIMessage(role="user", content="Test RateLimit")]

    err_msg = (
        "RateLimitError: GroqException - {\"error\":{\"message\":\"Request too large for model "
        "`qwen/qwen3.8-27b` on output tokens per minute (OTPM): Limit 1000, Requested 1313. "
        "The request's expected output tokens exceed the enforced limit; reduce max_tokens\"}}"
    )

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.side_effect = Exception(err_msg)
        with pytest.raises(RuntimeError) as exc_info:
            await provider.complete(messages, model="qwen/qwen3.8-27b", max_tokens=1500)

        err_text = str(exc_info.value)
        assert "1313 tokens supera el límite de 1000 tokens de salida" in err_text
        assert "Configuración (Settings)" in err_text
        # Verifica que NO hubo reintento automático (llamado exactamente 1 vez)
        assert mock_acompletion.call_count == 1


@pytest.mark.asyncio
async def test_itpm_ratelimit_friendly_exception():
    provider = GroqProvider(api_key="gsk_testkey")
    messages = [AIMessage(role="user", content="Test ITPM")]

    err_msg = (
        'RateLimitError: GroqException - {"error":{"message":"Request too large for model '
        '`qwen/qwen3.8-27b` in organization `org_123` service tier `on_demand` on input tokens '
        'per minute (ITPM): Limit 7000, Requested 53257, please reduce your message size and try again."}}'
    )

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.side_effect = Exception(err_msg)
        with pytest.raises(RuntimeError) as exc_info:
            await provider.complete(messages, model="qwen/qwen3.8-27b")

        err_text = str(exc_info.value)
        assert "53257" in err_text
        assert "7000" in err_text
        assert "Gemini" in err_text
        assert mock_acompletion.call_count == 1

