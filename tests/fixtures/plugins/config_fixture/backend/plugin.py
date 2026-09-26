from pydantic import BaseModel, Field


class ConfigFixtureModel(BaseModel):
    """Fields used to verify the host's generic plugin config transaction."""

    app_id: str = Field(default="", title="App ID")
    client_secret: str = Field(default="", title="App Secret")
    groups: list[str] = Field(default_factory=list, title="Groups")


async def setup(ctx):
    """Validate the values the host applies to this fixture."""
    ConfigFixtureModel.model_validate(ctx.config.as_dict())
