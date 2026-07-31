from types import SimpleNamespace

import pytest

from yuxi.services.knowledge_permission_service import (
    DEFAULT_ROLE_PERMISSIONS,
    allowed_share_levels,
    can_manage_database,
    normalize_department_role_permissions,
    normalize_share_config_for_user,
)


def make_user(**overrides):
    values = {
        "uid": "user-1",
        "role": "user",
        "department_id": 7,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_default_user_can_create_and_manage_only_own_database():
    policy = DEFAULT_ROLE_PERMISSIONS["user"]
    own_database = {"created_by": "user-1", "share_config": {"access_level": "user"}}
    shared_database = {
        "created_by": "other-user",
        "share_config": {"access_level": "department", "department_ids": [7]},
    }

    assert policy["create"] is True
    assert can_manage_database(make_user(), own_database, policy) is True
    assert can_manage_database(make_user(), shared_database, policy) is False


def test_department_manager_policy_can_manage_department_shared_database():
    policy = DEFAULT_ROLE_PERMISSIONS["admin"]
    database = {
        "created_by": "other-user",
        "department_id": 7,
        "share_config": {"access_level": "department", "department_ids": [7]},
    }

    assert can_manage_database(make_user(role="admin"), database, policy) is True
    assert can_manage_database(make_user(role="admin", department_id=8), database, policy) is False


def test_personal_share_is_forced_to_current_user_without_share_users_permission():
    policy = DEFAULT_ROLE_PERMISSIONS["user"]
    result = normalize_share_config_for_user(
        {"access_level": "user", "user_uids": ["other-user"]},
        user=make_user(),
        permissions=policy,
    )

    assert result == {"access_level": "user", "department_ids": [], "user_uids": ["user-1"]}


def test_disallowed_global_share_is_rejected():
    with pytest.raises(PermissionError):
        normalize_share_config_for_user(
            {"access_level": "global"},
            user=make_user(),
            permissions=DEFAULT_ROLE_PERMISSIONS["user"],
        )


def test_stored_policy_is_merged_with_safe_defaults():
    policies = normalize_department_role_permissions({"user": {"create": False, "share_global": True}})

    assert policies["user"]["create"] is False
    assert policies["user"]["manage_own"] is True
    assert policies["user"]["share_global"] is True
    assert allowed_share_levels(policies["user"]) == ["global", "user"]


def test_manage_all_policy_can_manage_any_accessible_database():
    database = {
        "created_by": "other-user",
        "share_config": {"access_level": "global"},
    }
    policy = {**DEFAULT_ROLE_PERMISSIONS["user"], "manage_all": True}

    assert can_manage_database(make_user(), database, policy) is True


def test_department_manager_cannot_manage_global_database_without_manage_all():
    database = {
        "created_by": "other-user",
        "share_config": {"access_level": "global"},
    }

    assert can_manage_database(make_user(role="admin"), database, DEFAULT_ROLE_PERMISSIONS["admin"]) is False
