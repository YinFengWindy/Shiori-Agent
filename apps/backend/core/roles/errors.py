"""Role-domain failures whose identity is stable across callers."""


class RoleNotFoundError(KeyError):
    """The requested role is absent, regardless of the operation that needs it."""

    def __init__(self, role_id: str) -> None:
        self.role_id = role_id
        super().__init__(f"角色不存在: {role_id}")
