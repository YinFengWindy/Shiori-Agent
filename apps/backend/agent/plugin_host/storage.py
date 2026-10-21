"""Plugin data operations exposed through the SDK storage protocol."""

from agent.plugin_host.data_migration import migrate_private_data


class PluginStorage:
    """Resolve plugin data targets without exposing host implementation modules."""

    migrate_data = staticmethod(migrate_private_data)
