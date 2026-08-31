from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection


DERIVED_TABLES = (
    "chat_sync_ai_knowledge_chunk",
    "chat_sync_ai_knowledge_index_state",
    "chat_sync_ai_knowledge_index_version",
    "chat_sync_ai_knowledge_retrieval_audit",
)
MAIN_TABLES = (
    "chat_sync_ai_knowledge_base",
    "chat_sync_ai_knowledge_document",
)


class Command(BaseCommand):
    help = "Backup derived knowledge-index tables and list documents whose imported file body is empty."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="",
            help="Directory for JSON backups. Defaults to SparkService/tmp/knowledge-audit-<timestamp>.",
        )

    def handle(self, *args, **options):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = Path(options["output_dir"] or Path.cwd() / "tmp" / f"knowledge-audit-{stamp}")
        output_dir.mkdir(parents=True, exist_ok=True)

        existing = set(connection.introspection.table_names())
        report: dict[str, object] = {"tables": {}, "empty_imported_documents": []}

        for table in MAIN_TABLES + DERIVED_TABLES:
            if table not in existing:
                report["tables"][table] = {"exists": False, "count": 0}
                continue
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                count = int(cursor.fetchone()[0])
            report["tables"][table] = {"exists": True, "count": count}
            if table in DERIVED_TABLES and count:
                rows = _dump_table(table)
                path = output_dir / f"{table}.json"
                path.write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")
                report["tables"][table]["backup"] = str(path)

        empty_docs = []
        if "chat_sync_ai_knowledge_document" in existing:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, user_id, knowledge_base_id, title, source_file_uuid
                    FROM chat_sync_ai_knowledge_document
                    WHERE source_file_uuid IS NOT NULL
                      AND (content IS NULL OR TRIM(content) = '')
                    """
                )
                columns = [col[0] for col in cursor.description]
                empty_docs = [dict(zip(columns, row)) for row in cursor.fetchall()]
        report["empty_imported_documents"] = empty_docs
        empty_path = output_dir / "empty_imported_documents.json"
        empty_path.write_text(json.dumps(empty_docs, ensure_ascii=False, default=str), encoding="utf-8")

        summary_path = output_dir / "summary.json"
        summary_path.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote knowledge audit to {summary_path}"))
        self.stdout.write(json.dumps(report["tables"], ensure_ascii=False, indent=2, default=str))
        self.stdout.write(f"empty imported documents: {len(empty_docs)}")


def _dump_table(table: str) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM `{table}`")
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
