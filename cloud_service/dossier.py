"""Acceptance dossier metadata never authorizes clinical decisions or execution."""
from .security import DomainError

SCHEMA = "ankang-sync-acceptance-1"
SECTION_KEYS = {"profile", "health", "medications", "assessment", "rehab_plan", "training",
                "fitness", "daily_health", "followup", "family", "assistant"}


def validate_dossier(document, actor, patient_id):
    payload = document["payload"]
    if payload.get("schema") != SCHEMA:
        return
    valid = (document["source_kind"] == "IMPORT" and payload.get("source") == "SYNC_ACCEPTANCE"
        and payload.get("synthetic") is True and payload.get("read_only") is True
        and payload.get("clinical_use") is False and payload.get("execution_enabled") is False
        and payload.get("patient_id") == patient_id and payload.get("username") == actor["username"]
        and payload.get("provenance") == {"kind": "SYNC_ACCEPTANCE", "evidence": "NONE", "created_for": "CROSS_CLIENT_SYNC_CHECK"})
    sections = payload.get("sections")
    valid &= isinstance(sections, list) and len(sections) == len(SECTION_KEYS)
    if valid:
        valid = all(isinstance(s, dict) and isinstance(s.get("key"), str) for s in sections)
    if valid:
        valid = {s["key"] for s in sections} == SECTION_KEYS
    if valid:
        for section in sections:
            rows = section.get("rows")
            valid &= (isinstance(section.get("title"), str) and len(section["title"]) <= 80
                and isinstance(section.get("summary"), str) and len(section["summary"]) <= 200
                and isinstance(rows, list) and 1 <= len(rows) <= 25)
            if not valid:
                break
            valid &= all(isinstance(r, dict) and set(r) == {"label", "value"}
                and isinstance(r["label"], str) and 1 <= len(r["label"]) <= 80
                and isinstance(r["value"], str) and len(r["value"]) <= 500 for r in rows)
    if not valid:
        raise DomainError(422, "DOSSIER_PROVENANCE_REQUIRED", "验收档案需保留来源、本人归属和不可执行标记")
