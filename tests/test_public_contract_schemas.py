import json
from pathlib import Path

SCHEMA_ROOT = Path(__file__).parents[1] / "schemas" / "public"


def test_public_contract_schemas_are_valid_json_documents() -> None:
    for path in sorted(SCHEMA_ROOT.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["$schema"].startswith("https://json-schema.org/")
        assert payload["type"] == "object"
        assert payload["additionalProperties"] is False
        assert payload["required"]
