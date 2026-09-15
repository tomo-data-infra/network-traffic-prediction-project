# Semantic catalog: business-term -> technical-metric mapping, retrieved via RAG
# (calendar_api/utils/rag.py) and injected into the LLM system prompt per-question.
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

JST = timezone(timedelta(hours=9))

SEMANTIC_CATALOG = {
    "peak_network_latency": {
        "display_name": "Peak Network Latency",
        "description": "The highest latency observed in the selected period.",
        "aliases": ["high latency", "slow internet", "traffic delay", "worst latency", "peak latency"],
        "technical_field": "highest_rtt",
        "source_view": "minute_rollups",
        "cube_measure": "PingLogs.highestRtt",
        "unit": "ms",
    },
    "average_latency": {
        "display_name": "Average Latency",
        "description": "The average latency observed in the selected period.",
        "aliases": ["average latency", "typical latency", "normal latency"],
        "technical_field": "mean_rtt",
        "source_view": "minute_rollups",
        "cube_measure": "PingLogs.meanRtt",
        "unit": "ms",
    },
    "packet_loss_rate": {
        "display_name": "Packet Loss Rate",
        "description": "The percentage of packets dropped in the selected period.",
        "aliases": ["packet loss", "drop rate", "loss rate"],
        "technical_field": "packet_loss_rate",
        "source_view": "minute_rollups",
        "cube_measure": "PingLogs.packetLossRate",
        "unit": "%",
    },
}

def build_catalog_context(catalog: Dict[str, Dict[str, Any]] = None) -> str:
    """Renders catalog entries as prompt text. Pass a subset (e.g. from rag.py's
    similarity search) to inject only the relevant entries; omit to render everything."""
    active_catalog = SEMANTIC_CATALOG if catalog is None else catalog
    lines = []
    for key, spec in active_catalog.items():
        aliases = ", ".join(spec["aliases"])
        lines.append(
            f"- {spec['display_name']} ({key}): {spec['description']} "
            f"| technical_field={spec['technical_field']} | source_view={spec['source_view']} "
            f"| aliases={aliases}"
        )
    return "\n".join(lines)

def normalize_user_query(question: str) -> str:
    q = question.lower()
    for spec in SEMANTIC_CATALOG.values():
        for alias in spec["aliases"]:
            alias_l = alias.lower()
            if alias_l in q:
                q = q.replace(alias_l, spec["display_name"].lower())
    return q

def infer_granularity(question: str) -> str:
    q = question.lower()
    if "daily" in q or "day" in q:
        return "day"
    if "hourly" in q or "hour" in q:
        return "hour"
    return "minute"

def describe_metrics(measure_names: List[str]) -> List[Dict[str, Any]]:
    out = []
    for measure_name in measure_names:
        for spec in SEMANTIC_CATALOG.values():
            if spec["cube_measure"] == measure_name:
                out.append({
                    "display_name": spec["display_name"],
                    "description": spec["description"],
                    "technical_field": spec["technical_field"],
                    "source_view": spec["source_view"],
                    "unit": spec["unit"],
                })
    return out

def relabel_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rewrite Cube.js measure keys (e.g. 'PingLogs.meanRtt') into '<display_name> (<unit>)'
    using SEMANTIC_CATALOG metadata, so the synthesis LLM sees friendly labels instead of raw
    Cube member names. Unknown/dimension keys (e.g. 'PingLogs.ts') are left untouched."""
    lookup = {spec["cube_measure"]: spec for spec in SEMANTIC_CATALOG.values()}
    out = []
    for row in rows:
        new_row = {}
        for key, value in row.items():
            spec = lookup.get(key)
            new_key = f"{spec['display_name']} ({spec['unit']})" if spec else key
            new_row[new_key] = value
        out.append(new_row)
    return out

def format_timestamps(rows: List[Dict[str, Any]], ts_keys=("PingLogs.ts",)) -> List[Dict[str, Any]]:
    """Reformats timestamp fields (default: 'PingLogs.ts') into 'YYYY-MM-DD HH:MM (JST)' for
    display in the synthesis prompt, so the small local Ollama model relays a pre-formatted
    string instead of doing timezone arithmetic itself.

    Handles both an explicit-offset/UTC-'Z' timestamp (converted to JST) and a naive timestamp
    (assumed already JST-local -- the case once the Cube.js query itself requests
    timezone="Asia/Tokyo", see views.py) so this is safe either way.
    """
    out = []
    for row in rows:
        new_row = dict(row)
        for key in ts_keys:
            raw = new_row.get(key)
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(JST)
                new_row[key] = dt.strftime("%Y-%m-%d %H:%M") + " (JST)"
            except (ValueError, TypeError):
                pass  # leave malformed/unexpected values untouched
        out.append(new_row)
    return out