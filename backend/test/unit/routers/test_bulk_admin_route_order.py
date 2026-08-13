from server.routers.auth_router import auth
from server.routers.rbac_router import rbac


def test_auth_fixed_user_routes_are_registered_before_dynamic_route():
    paths = [route.path for route in auth.routes]
    dynamic_index = paths.index("/auth/users/{user_id}")
    for path in (
        "/auth/users/batch/department",
        "/auth/users/import-template",
        "/auth/users/import/preview",
        "/auth/users/import",
    ):
        assert paths.index(path) < dynamic_index


def test_rbac_batch_route_is_registered_before_dynamic_route():
    paths = [route.path for route in rbac.routes]
    assert paths.index("/rbac/users/batch/roles") < paths.index("/rbac/users/{user_id}/roles")
