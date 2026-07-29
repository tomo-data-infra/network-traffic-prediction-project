import re
from django.db import connection

# In-memory session dictionaries to track runtime string mappings
TEXT_MASK_MAP = {}
TEXT_UNMASK_MAP = {}

def mask_sensitive_data(user_query: str) -> str:
    """
    Detects real IP addresses in user text queries and replaces them 
    with anonymous, generic tokens (e.g., 'TARGET_NODE_1').
    """
    global TEXT_MASK_MAP, TEXT_UNMASK_MAP
    
    # Regular expression to match standard IPv4 network strings
    ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
    found_ips = re.findall(ip_pattern, user_query)
    
    masked_query = user_query
    for ip in set(found_ips):
        if ip not in TEXT_MASK_MAP:
            # Dynamically assign an anonymous string index identifier
            node_index = len(TEXT_MASK_MAP) + 1
            token_string = f"TARGET_NODE_{node_index}"
            
            TEXT_MASK_MAP[ip] = token_string
            TEXT_UNMASK_MAP[token_string] = ip
            
        # Swap out raw IPs for safe public API exposure
        masked_query = masked_query.replace(ip, TEXT_MASK_MAP[ip])
        
    return masked_query


def resolve_tokens_to_db_filters(cube_query: dict) -> dict:
    """
    Intersects the LLM's JSON payload, extracts token strings, 
    queries the local PostgreSQL targets table, and updates filters 
    to use the correct database primary key integers or original text strings.
    """
    global TEXT_UNMASK_MAP
    
    if "filters" not in cube_query:
        return cube_query

    for filter_block in cube_query["filters"]:
        # If the LLM filtered by Targets.ip, map the token back to reality
        if filter_block.get("member") == "Targets.ip":
            raw_values = filter_block.get("values", [])
            resolved_values = []
            
            for val in raw_values:
                if val in TEXT_UNMASK_MAP:
                    # Retrieve original IP address string from memory map
                    real_ip = TEXT_UNMASK_MAP[val]
                    resolved_values.append(real_ip)
                else:
                    resolved_values.append(val)
                    
            filter_block["values"] = resolved_values
            
    return cube_query
