from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ItemReport:
    raw: str
    query: str
    alt_query: str | None
    chosen_title: str | None
    chosen_url: str | None
    chosen_size_oz: float | None
    chosen_price: str | None
    undersized: bool
    status: str  # ADDED, SKIPPED_NO_MATCH, FAILED, NEEDS_REVIEW, DRY_RUN


@dataclass
class RunReport:
    timestamp: str
    total: int
    added: int
    skipped: int
    failed: int
    needs_review: int
    dry_run: bool
    items: list[ItemReport]

    def summary_text(self) -> str:
        lines = [
            f"Run: {self.timestamp}  (dry_run={self.dry_run})",
            f"Total: {self.total}  Added: {self.added}  Skipped: {self.skipped}  "
            f"Failed: {self.failed}  Review: {self.needs_review}",
            "",
        ]
        for i, it in enumerate(self.items, 1):
            tag = it.status
            if it.undersized:
                tag += " (undersized)"
            title = it.chosen_title or "—"
            lines.append(f"  {i}. [{tag}] {it.raw}")
            lines.append(f"     → {title}  {it.chosen_price or ''}")
        return "\n".join(lines)

    def write_json(self, path: str = "artifacts/run_report.json") -> str:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(asdict(self), indent=2))
        return str(out)


def build_report(items: list[ItemReport], *, dry_run: bool) -> RunReport:
    return RunReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total=len(items),
        added=sum(1 for i in items if i.status == "ADDED"),
        skipped=sum(1 for i in items if i.status == "SKIPPED_NO_MATCH"),
        failed=sum(1 for i in items if i.status == "FAILED"),
        needs_review=sum(1 for i in items if i.status == "NEEDS_REVIEW"),
        dry_run=dry_run,
        items=items,
    )
