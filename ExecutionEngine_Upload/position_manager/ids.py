"""Deterministic id generation for the Position Manager. Never random --
derived purely from (pm_id, sequence number), so replaying the same event
history always regenerates the same sequence position."""


def make_id(pm_id: str, seq: int, suffix: str) -> str:
    return f"pm:{pm_id}:{seq}:{suffix}"
