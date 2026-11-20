
def enrich_with_context(parsed, state):
    """
    Fill missing entities using information
    remembered from earlier messages.
    """
    entities = parsed["entities"]

    for key in ("month", "relationship"):
        if key not in entities and state.get(key) is not None:
            entities[key] = state[key]

    return parsed


def update_state(parsed, state, last_result_ids=None):
    """
    Remember useful information from the
    current conversation.
    """
    entities = parsed["entities"]

    for key in (
        "month",
        "relationship",
        "person_id",
        "person_name"
    ):
        if key in entities:
            state[key] = entities[key]

    if last_result_ids is not None:
        state["last_result_ids"] = last_result_ids

    return state


def reset_state(state):
    """Clear all remembered conversation information."""
    state.clear()
    return state
