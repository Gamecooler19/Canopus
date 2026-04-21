"""Canopus legacy plugin: text_tools

Provides deterministic, local text transformation capabilities.
Safe, no side effects, no network access, no filesystem access.

Drop this file into ``~/.canopus/plugins/`` and run:

    canopus plugin list
    canopus capability invoke text_tools.upper --input-json '{"text": "hello world"}'
    canopus capability invoke text_tools.word_count --input-json '{"text": "one two three"}'
"""

PLUGIN_META = {
    "name": "text_tools",
    "description": "Local text transformation utilities: case conversion, word count, and more.",
    "version": "1.0.0",
    "author": "Canopus Examples",
    "tags": ["text", "transform", "example"],
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def upper(inputs: dict, ctx) -> dict:  # type: ignore[no-untyped-def]
    """Convert text to upper case.

    Inputs:
        text (str): Input text.

    Returns:
        result (str): Upper-cased text.
        original_length (int): Length of the input text.
    """
    text = str(inputs.get("text", ""))
    return {
        "result": text.upper(),
        "original_length": len(text),
    }


def lower(inputs: dict, ctx) -> dict:  # type: ignore[no-untyped-def]
    """Convert text to lower case.

    Inputs:
        text (str): Input text.

    Returns:
        result (str): Lower-cased text.
        original_length (int): Length of the input text.
    """
    text = str(inputs.get("text", ""))
    return {
        "result": text.lower(),
        "original_length": len(text),
    }


def word_count(inputs: dict, ctx) -> dict:  # type: ignore[no-untyped-def]
    """Count the words, characters, and lines in a text string.

    Inputs:
        text (str): Input text.

    Returns:
        words (int): Number of whitespace-separated words.
        characters (int): Total character count including spaces.
        lines (int): Number of newline-separated lines.
        non_empty_lines (int): Lines with at least one non-whitespace character.
    """
    text = str(inputs.get("text", ""))
    lines = text.splitlines()
    return {
        "words": len(text.split()),
        "characters": len(text),
        "lines": len(lines),
        "non_empty_lines": sum(1 for ln in lines if ln.strip()),
    }


def reverse(inputs: dict, ctx) -> dict:  # type: ignore[no-untyped-def]
    """Reverse a text string.

    Inputs:
        text (str): Input text.

    Returns:
        result (str): Reversed text.
    """
    text = str(inputs.get("text", ""))
    return {"result": text[::-1]}


def title_case(inputs: dict, ctx) -> dict:  # type: ignore[no-untyped-def]
    """Convert text to title case.

    Inputs:
        text (str): Input text.

    Returns:
        result (str): Title-cased text.
    """
    text = str(inputs.get("text", ""))
    return {"result": text.title()}


# ---------------------------------------------------------------------------
# Plugin contract
# ---------------------------------------------------------------------------


def capabilities() -> list:  # type: ignore[type-arg]
    """Declare the capabilities provided by this plugin."""
    return [
        {
            "name": "text_tools.upper",
            "description": "Convert text to upper case.",
            "handler": upper,
            "tags": ["text", "transform", "case"],
            "examples": ["convert to upper case", "make text uppercase"],
        },
        {
            "name": "text_tools.lower",
            "description": "Convert text to lower case.",
            "handler": lower,
            "tags": ["text", "transform", "case"],
            "examples": ["convert to lower case", "make text lowercase"],
        },
        {
            "name": "text_tools.word_count",
            "description": "Count words, characters, and lines in text.",
            "handler": word_count,
            "tags": ["text", "analysis", "count"],
            "examples": ["count the words in this text", "how many words"],
        },
        {
            "name": "text_tools.reverse",
            "description": "Reverse a text string.",
            "handler": reverse,
            "tags": ["text", "transform"],
            "examples": ["reverse this string", "flip the text"],
        },
        {
            "name": "text_tools.title_case",
            "description": "Convert text to title case (capitalize each word).",
            "handler": title_case,
            "tags": ["text", "transform", "case"],
            "examples": ["title case this text", "capitalize each word"],
        },
    ]
