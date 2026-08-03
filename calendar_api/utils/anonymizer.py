import re
from typing import Dict, Tuple


def mask_sensitive_data(user_query: str) -> Tuple[str, Dict[str, str]]:
    """
    Replaces IPv4 addresses in the query with generic tokens (e.g. 'TARGET_NODE_1').
    Returns the masked query and a token->ip map scoped to this call, so concurrent
    requests never share or overwrite each other's mappings.
    """
    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    found_ips = re.findall(ip_pattern, user_query)

    mask_map: Dict[str, str] = {}
    unmask_map: Dict[str, str] = {}
    masked_query = user_query
    for ip in set(found_ips):
        token_string = f"TARGET_NODE_{len(mask_map) + 1}"
        mask_map[ip] = token_string
        unmask_map[token_string] = ip
        masked_query = masked_query.replace(ip, token_string)

    return masked_query, unmask_map


def resolve_tokens_to_db_filters(cube_query: dict, unmask_map: Dict[str, str]) -> dict:
    """Replaces TARGET_NODE_* tokens in the LLM's Cube.js filter payload with real IPs."""
    if "filters" not in cube_query:
        return cube_query

    for filter_block in cube_query["filters"]:
        if filter_block.get("member") == "Targets.ip":
            filter_block["values"] = [
                unmask_map.get(val, val) for val in filter_block.get("values", [])
            ]

    return cube_query
