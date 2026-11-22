
def enrich_with_context(parsed, state):
    entities = parsed["entities"]

    # Do not reuse an old individual relationship
    # when a new relationship group is specified.
    if "relationship_group" in entities:
        pass
    elif "relationship" not in entities and state.get("relationship"):
        entities["relationship"] = state["relationship"]

    # Do not reuse an old group when a new individual
    # relationship is specified.
    elif "relationship" in entities and "relationship_group" not in entities:
        pass
    elif state.get("relationship_group"):
        entities["relationship_group"] = state["relationship_group"]

    # Do not reuse an old month when the user says next month.
    if "relative_month" in entities:
        pass
    elif "month" not in entities and state.get("month") is not None:
        entities["month"] = state["month"]

    return parsed


def update_state(parsed, state, last_result_ids=None):
    entities = parsed["entities"]

    # Clear conflicting old relationship context.
    if "relationship_group" in entities and "relationship" not in entities:
        state.pop("relationship", None)

    if "relationship" in entities and "relationship_group" not in entities:
        state.pop("relationship_group", None)

    # Clear conflicting old date context.
    if "relative_month" in entities and "month" not in entities:
        state.pop("month", None)

    if "month" in entities and "relative_month" not in entities:
        state.pop("relative_month", None)

    # Save the latest entities.
    for key in (
        "month",
        "relationship",
        "relationship_group",
        "person_id",
        "person_name",
        "relative_month",
        "relative_date"
    ):
        if key in entities:
            state[key] = entities[key]

    if last_result_ids is not None:
        state["last_result_ids"] = last_result_ids

    return state


def reset_state(state):
    state.clear()
    return state
