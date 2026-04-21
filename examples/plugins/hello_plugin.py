"""Canopus legacy plugin: hello

A minimal example plugin demonstrating the Canopus plugin contract.
Drop this file into ``~/.canopus/plugins/`` and run:

    canopus plugin list
    canopus capability invoke hello.greet --input-json '{"name": "Alice"}'
"""

PLUGIN_META = {
    "name": "hello",
    "description": "A greeting example plugin — useful for testing plugin loading.",
    "version": "1.0.0",
    "author": "Canopus Examples",
    "tags": ["example", "greeting"],
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def greet(inputs: dict, ctx) -> dict:  # type: ignore[no-untyped-def]
    """Return a personalised greeting.

    Inputs:
        name (str): Name to greet. Defaults to "World".

    Returns:
        message (str): The greeting string.
    """
    name = str(inputs.get("name", "World"))
    return {"message": f"Hello, {name}! Greetings from the hello plugin."}


def farewell(inputs: dict, ctx) -> dict:  # type: ignore[no-untyped-def]
    """Return a farewell message.

    Inputs:
        name (str): Name to bid farewell to. Defaults to "World".

    Returns:
        message (str): The farewell string.
    """
    name = str(inputs.get("name", "World"))
    return {"message": f"Goodbye, {name}! Until next time."}


# ---------------------------------------------------------------------------
# Plugin contract
# ---------------------------------------------------------------------------


def capabilities() -> list:  # type: ignore[type-arg]
    """Declare the capabilities provided by this plugin."""
    return [
        {
            "name": "hello.greet",
            "description": "Return a personalised greeting message.",
            "handler": greet,
            "tags": ["greeting", "example"],
            "examples": [
                "say hello to Alice",
                "greet Bob",
            ],
        },
        {
            "name": "hello.farewell",
            "description": "Return a personalised farewell message.",
            "handler": farewell,
            "tags": ["greeting", "example"],
            "examples": [
                "say goodbye to Alice",
                "farewell Bob",
            ],
        },
    ]
