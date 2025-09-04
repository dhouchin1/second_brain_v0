# schemas/discord.py
from pydantic import BaseModel

class DiscordWebhook(BaseModel):
    note: str
    tags: str | None = ""
    type: str = "discord"