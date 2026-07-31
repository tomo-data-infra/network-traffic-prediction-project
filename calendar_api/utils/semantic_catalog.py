# Intended semantic catalog module for mapping user queries to technical metrics.
# Integration with the LLM routing layer is planned.
from typing import Any, Dict, List

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

def build_catalog_context() -> str:
    lines = []
    for key, spec in SEMANTIC_CATALOG.items():
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