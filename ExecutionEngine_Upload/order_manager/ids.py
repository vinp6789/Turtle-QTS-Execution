"""Deterministic id generation for the Order Manager.

Ids are derived purely from (om_id, sequence number) -- never random --
so that replaying the same event history always regenerates the exact
same sequence position, which is what makes a retried action after a
crash safe rather than accidentally minting a fresh, unrelated id.
"""


def make_id(om_id: str, seq: int, suffix: str) -> str:
    return f"om:{om_id}:{seq}:{suffix}"
