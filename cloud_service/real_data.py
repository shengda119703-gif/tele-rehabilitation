"""Keep explicitly synthetic acceptance fixtures outside production care views."""
from sqlalchemy import String, and_, cast, or_


def synthetic(payload):
    if not isinstance(payload, dict):
        return False
    result = payload.get("result")
    nested = isinstance(result, dict) and (result.get("synthetic") not in (None, False) or result.get("fixture") is not None
        or result.get("source_kind") == "SYNTHETIC" or result.get("usage_context") == "TEST")
    return (nested or payload.get("synthetic") not in (None, False) or payload.get("fixture") is not None
            or payload.get("schema") == "ankang-sync-acceptance-1"
            or payload.get("source") in {"SYNTHETIC", "SYNC_ACCEPTANCE"})


def real_record_condition(table):
    p = table.c.payload
    return and_(or_(p["synthetic"].as_string().is_(None), cast(p["synthetic"].as_string(), String).in_(("false", "0"))),
                or_(p["result"]["synthetic"].as_string().is_(None), cast(p["result"]["synthetic"].as_string(), String).in_(("false", "0"))),
                or_(p["result"]["source_kind"].as_string().is_(None), p["result"]["source_kind"].as_string() != "SYNTHETIC"),
                or_(p["result"]["usage_context"].as_string().is_(None), p["result"]["usage_context"].as_string() != "TEST"),
                p["fixture"].as_string().is_(None), p["result"]["fixture"].as_string().is_(None),
                or_(p["schema"].as_string().is_(None), p["schema"].as_string() != "ankang-sync-acceptance-1"),
                or_(p["source"].as_string().is_(None), p["source"].as_string().not_in(("SYNTHETIC", "SYNC_ACCEPTANCE"))))
