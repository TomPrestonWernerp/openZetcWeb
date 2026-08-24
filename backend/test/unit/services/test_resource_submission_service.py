from __future__ import annotations

import io
import zipfile

import pytest

from openzetc.services.resource_submission_service import sanitize_manifest, validate_skill_package


def _skill_zip(*, entry_name: str = "weekly-report/SKILL.md") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(entry_name, "---\nname: weekly-report\n---\n")
    return buffer.getvalue()


def test_mcp_submission_removes_credentials_and_sensitive_url_parameters() -> None:
    cleaned = sanitize_manifest(
        "mcp",
        {
            "slug": "Local MCP",
            "name": "Local MCP",
            "description": "Local integration",
            "transport": "streamable_http",
            "url": "https://user:password@example.com/mcp?token=secret&region=cn",
            "env": {"API_KEY": "secret"},
            "headers": {"Authorization": "Bearer secret"},
            "args": ["--region", "cn", "--api-key", "secret", "--token=also-secret", "--verbose"],
            "env_keys": ["API_KEY", "REGION", "API_KEY"],
            "header_keys": ["Authorization"],
        },
    )

    assert cleaned["slug"] == "local-mcp"
    assert cleaned["url"] == "https://example.com/mcp?region=cn"
    assert cleaned["env_keys"] == ["API_KEY", "REGION"]
    assert cleaned["header_keys"] == ["Authorization"]
    assert cleaned["args"] == ["--region", "cn", "--verbose"]
    assert "env" not in cleaned
    assert "headers" not in cleaned


def test_skill_submission_accepts_one_safe_skill_manifest() -> None:
    validate_skill_package("weekly-report.zip", _skill_zip())


@pytest.mark.parametrize("entry_name", ["../SKILL.md", "/SKILL.md"])
def test_skill_submission_rejects_unsafe_archive_paths(entry_name: str) -> None:
    with pytest.raises(ValueError, match="ZIP"):
        validate_skill_package("weekly-report.zip", _skill_zip(entry_name=entry_name))
