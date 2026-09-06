from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from app.services.link_policy import is_link_only, suppress_link_translation


def load_records(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("translations") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("translation file must contain a translations array")
    return {str(row["external_id"]): row for row in records}


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach reviewed translations to normalized JSONL before import.")
    parser.add_argument("--jsonl", required=True, type=Path)
    parser.add_argument("--translations", required=True, type=Path)
    args = parser.parse_args()

    translations = load_records(args.translations)
    output: list[str] = []
    updated = 0
    for line in args.jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if is_link_only(item):
            suppress_link_translation(item)
            output.append(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            continue
        external_id = str((item.get("external") or {}).get("id") or "")
        record = translations.get(external_id)
        if record:
            source_language = str(record.get("source_language") or "en")
            item.setdefault("content", {})["language"] = source_language
            text = str(record.get("text") or "").strip()
            if text:
                raw_payload = item.setdefault("raw_payload", {})
                raw_payload["translation_policy"] = {
                    "required": True,
                    "target_language": "zh-CN",
                    "reviewer": "codex",
                    "preserve_original": True,
                    "status": "complete",
                }
                raw_payload["translation"] = {
                    "source_language": source_language,
                    "target_language": "zh-CN",
                    "title": str(record.get("title") or "").strip() or None,
                    "text": text,
                    "method": "llm_context_translation",
                    "reviewer": "codex",
                    "preserve_tickers": True,
                    "preserve_numbers": True,
                }
            updated += 1
        output.append(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    args.jsonl.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(json.dumps({"updated": updated, "jsonl": str(args.jsonl)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
