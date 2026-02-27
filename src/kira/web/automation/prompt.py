"""Prompt template rendering for automation."""

from __future__ import annotations

DEFAULT_PROMPT_TEMPLATE = """\
You are a {agent_type} agent working on a kanban card.

## Card: {card_title}

{card_description}

## Previous Agent Output
{last_agent_output}

## Instructions
Perform your role as {agent_type}. Be thorough and specific.
If you are reviewing, clearly state APPROVED or REJECTED with reasoning."""


def render_prompt(template: str, card: dict, column: dict) -> str:
    """Render prompt template with card/column variables.

    Supported variables:
        {card_title}, {card_description}, {card_labels}, {card_priority},
        {column_name}, {agent_type}, {last_agent_output}
    """
    if not template:
        template = DEFAULT_PROMPT_TEMPLATE

    variables = {
        "card_title": card.get("title", ""),
        "card_description": card.get("description", ""),
        "card_labels": card.get("labels", "[]"),
        "card_priority": card.get("priority", "medium"),
        "column_name": column.get("name", ""),
        "agent_type": column.get("agent_type", ""),
        "last_agent_output": "",
    }

    # Safe substitution: ignore missing keys
    result = template
    for key, value in variables.items():
        result = result.replace("{" + key + "}", str(value))

    return result
