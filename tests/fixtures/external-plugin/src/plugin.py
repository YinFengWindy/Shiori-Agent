"""Minimal backend using only the host-injected runtime context."""


async def setup(ctx):
    """Publish a small API without depending on host source/import layout."""
    ctx.expose({"message": "External package ready"})
