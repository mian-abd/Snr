import json
from pathlib import Path

from app.main import create_app

repository_root = Path(__file__).resolve().parents[2]
destination = repository_root / "frontend" / "openapi.json"
destination.write_text(
    json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(destination)
