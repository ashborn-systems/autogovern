"""Support triage agent entrypoint.

Classifies incoming support tickets by severity and category, then suggests
a routing team. Never closes a ticket automatically.
"""

from __future__ import annotations

import os

from anthropic import Anthropic

MODEL = "claude-3-5-sonnet"
TEMPERATURE = 0.0

_client = Anthropic(
    model=MODEL,
    api_key=os.environ["ANTHROPIC_API_KEY"],
)


def triage(ticket_text: str) -> str:
    """Classify a ticket and return a suggested routing team.

    Reads the ticket text, classifies by severity (P1-P4) and category
    (billing, technical, account), and returns the target team name. The
    caller is responsible for acting on the suggestion.
    """
    response = _client.messages.create(
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=256,
        system="You classify support tickets. Respond with one line.",
        messages=[{"role": "user", "content": ticket_text}],
    )
    text = response.content[0].text if response.content else ""
    return text.strip()
