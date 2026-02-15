import os

import pytest

_TEST_ENV_VARS = {
    "AZURE_CLIENT_ID": "00000000-0000-0000-0000-000000000001",
    "AZURE_TENANT_ID": "00000000-0000-0000-0000-000000000002",
    "AZURE_AGENT_CALLER_GROUP_ID": "00000000-0000-0000-0000-000000000003",
    "AZURE_CLIENT_SECRET": "test-secret",
    "AZURE_REDIRECT_URI": "http://localhost:8501",
    "OPENROUTER_API_KEY": "test-key",
}


@pytest.fixture(autouse=True, scope="session")
def _set_test_env_vars():
    """Set test environment variables before any modules are imported."""
    original = {}
    for key, value in _TEST_ENV_VARS.items():
        original[key] = os.environ.get(key)
        os.environ.setdefault(key, value)
    yield
    for key, orig_value in original.items():
        if orig_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_value
