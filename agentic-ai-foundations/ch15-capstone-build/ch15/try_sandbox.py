"""Send read_file calls a model might make through the registry, and print what it gets back.

uv run python -m ch15.try_sandbox      (needs .kestrel/exports: uv run kestrel up --no-serve)
"""

from ch15.citations import citable_locations
from ch15.model_client import ToolCall
from ch15.settings import Settings
from ch15.tools import UnconfiguredSearch, build_registry

CALLS = [
    {"path": "../kestrel.sqlite"},  # climbs out of the sandboxed folder
    {"path": "/etc/passwd"},  # absolute
    {"path": "shipmnts.csv"},  # a misspelt export
    {"path": "shipments.csv", "max_chars": 50},  # below the 200-character minimum
    {"path": "shipments.csv", "max_chars": 200},  # fine
]


def main() -> None:
    settings = Settings.from_env()
    registry = build_registry(
        settings.exports_dir, UnconfiguredSearch(), lambda: 1.0, 16_000, citable_locations
    )
    for i, args in enumerate(CALLS, 1):
        result = registry.dispatch(ToolCall(id=f"c{i}", name="read_file", arguments=args))
        first_line = result.content.splitlines()[0]
        print(f"{args} -> {'ERROR' if result.is_error else 'ok'}: {first_line}")
    print(f"citable: {sorted(registry.citable)}")


if __name__ == "__main__":
    main()
