"""导出 OpenAPI 契约：python scripts/export_openapi.py > ../../contracts/openapi.json"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aichat.app import create_app  # noqa: E402

app = create_app()
json.dump(app.openapi(), sys.stdout, ensure_ascii=False, indent=2)
sys.stdout.write("\n")
