"""Host fixture with one scoped tool contribution."""

from shiori_sdk.tools import Tool


class WeatherTool(Tool):
    """Returns a deterministic weather result."""

    name = "get_weather"
    description = "Get current weather for a city"
    parameters = {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    }

    async def execute(self, **kwargs):
        return f"{kwargs['city']}: 晴, 22°C (由 weather 插件提供)"


async def setup(ctx):
    """Owns the tool registration until unload."""
    ctx.tools.register(
        WeatherTool(), risk="read-only", search_hint="get current weather for a city"
    )
