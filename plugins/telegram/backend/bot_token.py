"""Bot identity carried in a Telegram Bot Token."""


def bot_account_id(token: str) -> str:
    """The Bot's numeric platform ID, which a Bot Token starts with."""
    return token.split(":", 1)[0]
