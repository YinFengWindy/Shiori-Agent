"""Plugin data operations delegated to the existing migration owner."""

from agent.plugin_host.data_migration import migrate_private_data


class PluginStorage:
    """Provide receipt-aware migration without exposing host implementation modules."""

    migrate_data = staticmethod(migrate_private_data)
