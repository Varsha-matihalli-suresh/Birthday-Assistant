
from flask import Flask, render_template, request, jsonify, session
import pandas as pd
from pathlib import Path
import re
from datetime import date, timedelta

from nlu import parse
from service import execute, next_birthday
from dialogue import enrich_with_context, update_state, reset_state
from llm_nlu import parse_with_llm, normalize_llm


# ----------------------------------
# 1. FLASK CONFIGURATION
# ----------------------------------

app = Flask(__name__)

app.secret_key = "birthday-assistant-development-key"


# ----------------------------------
# 2. LOAD EXCEL DATASET ONCE
# ----------------------------------

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "data" / "people.xlsx"

df = pd.read_excel(EXCEL_PATH)

df["DOB"] = pd.to_datetime(
    df["DOB"],
    errors="coerce"
)

df["Relationship"] = (
    df["Relationship"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.lower()
)

df["Name"] = (
    df["Name"]
    .fillna("")
    .astype(str)
    .str.strip()
)

df["Nickname"] = (
    df["Nickname"]
    .fillna("")
    .astype(str)
    .str.strip()
)

df["Person_ID"] = df["Person_ID"].astype(str)

if "Relationship_Group" in df.columns:

    df["Relationship_Group"] = (
        df["Relationship_Group"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )


# ----------------------------------
# 3. HELPER: CALCULATE RESULT IDS
# ----------------------------------

def get_result_ids(parsed):

    intent = parsed["intent"]
    entities = parsed["entities"]

    if intent not in [
        "birthday_search",
        "count_birthdays",
        "upcoming_birthdays"
    ]:
        return None

    results = df.copy()

    results = results[results["DOB"].notna()]

    # Person filter
    person_id = entities.get("person_id")

    if person_id:
        results = results[
            results["Person_ID"] == str(person_id)
        ]

    # Month filter
    month = entities.get("month")

    if month:
        results = results[
            results["DOB"].dt.month == int(month)
        ]

    # Relationship filter
    relationship = entities.get("relationship")

    if relationship:
        results = results[
            results["Relationship"] == relationship.lower()
        ]

    # Relationship group filter
    relationship_group = entities.get("relationship_group")

    if relationship_group and "Relationship_Group" in results.columns:
        results = results[
            results["Relationship_Group"] == relationship_group.lower()
        ]

    # Tomorrow filter
    if entities.get("relative_date") == "tomorrow":

        tomorrow = date.today() + timedelta(days=1)

        results = results[
            (results["DOB"].dt.month == tomorrow.month)
            & (results["DOB"].dt.day == tomorrow.day)
        ]

    # Next month filter
    if entities.get("relative_month") == "next_month":

        next_month = date.today().month % 12 + 1

        results = results[
            results["DOB"].dt.month == next_month
        ]

    # Upcoming birthdays: next 30 days
    if (
        intent == "upcoming_birthdays"
        and entities.get("relative_date") != "tomorrow"
    ):

        today = date.today()
        end_date = today + timedelta(days=30)

        results = results[
            results["DOB"].apply(
                lambda dob: (
                    today <= next_birthday(dob) <= end_date
                )
            )
        ]

    return results["Person_ID"].astype(str).tolist()


# ----------------------------------
# 4. HOME PAGE
# ----------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# ----------------------------------
# 5. CHAT ROUTE
# ----------------------------------

@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json(silent=True) or {}

    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({
            "answer": "Please enter a question."
        })

    q = message.lower()

    # ----------------------------------
    # 5.1 RESET CONVERSATION
    # ----------------------------------

    reset_commands = [
        "reset",
        "reset conversation",
        "reset the conversation",
        "start over",
        "clear conversation"
    ]

    if q in reset_commands:

        session.pop("dialogue_state", None)
        session.pop("pending_clarification", None)

        return jsonify({
            "answer": (
                "Conversation reset! "
                "What birthday would you like to know about?"
            )
        })

    state = session.get("dialogue_state", {})

    # ----------------------------------
    # 5.2 HANDLE PENDING CLARIFICATION
    # ----------------------------------

    pending = session.get("pending_clarification")

    if pending:

        candidate_ids = [
            str(person_id)
            for person_id in pending["candidate_ids"]
        ]

        candidates = df[
            df["Person_ID"].isin(candidate_ids)
        ]

        # Exact full-name match
        exact_matches = candidates[
            candidates["Name"].str.lower() == q
        ]

        if not exact_matches.empty:

            matches = exact_matches

        else:

            # Match full-name fragments
            name_matches = candidates[
                candidates["Name"].str.lower().str.contains(
                    re.escape(q),
                    na=False
                )
            ]

            # Match nicknames
            nickname_matches = candidates[
                candidates["Nickname"].str.lower() == q
            ]

            matches = pd.concat(
                [name_matches, nickname_matches]
            ).drop_duplicates(
                subset=["Person_ID"]
            )

        # ----------------------------------
        # NEW FIX:
        # If the message is not a candidate name,
        # treat it as a new question.
        # ----------------------------------

        if len(matches) == 0:

            print(
                "New question detected. "
                "Clearing old pending clarification."
            )

            session.pop("pending_clarification", None)

            # Continue to normal NLU processing below.

        # Still ambiguous
        elif len(matches) > 1:

            return jsonify({
                "answer": (
                    "I found more than one matching person. "
                    "Please provide the full name: "
                    + ", ".join(matches["Name"].tolist())
                ),
                "clarification_required": True
            })

        # Exactly one person selected
        elif len(matches) == 1:

            selected_person = matches.iloc[0]

            session.pop("pending_clarification", None)

            # Preserve original intent and entities
            parsed = {
                "intent": pending.get(
                    "intent",
                    "person_birthday"
                ),
                "entities": pending.get(
                    "entities",
                    {}
                ).copy(),
                "original": message,
                "source": "clarification"
            }

            parsed["entities"]["person_id"] = str(
                selected_person["Person_ID"]
            )

            parsed["entities"]["person_name"] = str(
                selected_person["Name"]
            )

            # Execute original question
            answer = execute(parsed, df)

            result_ids = get_result_ids(parsed)

            update_state(parsed, state, result_ids)

            session["dialogue_state"] = state

            return jsonify({
                "answer": answer,
                "parsed": parsed
            })

    # ----------------------------------
    # 5.3 V4 GROQ NLU WITH V3 FALLBACK
    # ----------------------------------

    try:

        parsed = parse_with_llm(message)

        parsed = normalize_llm(parsed, df)

        parsed["original"] = message
        parsed["source"] = "groq"

    except Exception as e:

        print(
            "Groq NLU failed. Using rule-based NLU:",
            e
        )

        parsed = parse(message, df)

        parsed["source"] = "rule-based"

    # ----------------------------------
    # 5.4 APPLY REMEMBERED CONTEXT
    # ----------------------------------

    parsed = enrich_with_context(parsed, state)

    # ----------------------------------
    # 5.5 HANDLE AMBIGUOUS PERSON NAMES
    # ----------------------------------

    person_name = parsed["entities"].get("person_name")

    person_id = parsed["entities"].get("person_id")

    if (
        person_name
        and not person_id
        and parsed["intent"] in [
            "person_birthday",
            "person_place",
            "upcoming_birthdays",
            "birthday_search"
        ]
    ):

        search_name = str(person_name).strip().lower()

        name_column = df["Name"].str.lower()

        nickname_column = df["Nickname"].str.lower()

        first_name_column = name_column.str.split().str[0]

        candidates = df[
            (name_column == search_name)
            | (first_name_column == search_name)
            | (nickname_column == search_name)
        ].drop_duplicates(
            subset=["Person_ID"]
        )

        if len(candidates) > 1:

            names = candidates["Name"].tolist()

            candidate_ids = candidates["Person_ID"].tolist()

            session["pending_clarification"] = {
                "candidate_ids": candidate_ids,
                "names": names,
                "intent": parsed["intent"],
                "entities": parsed["entities"]
            }

            session["dialogue_state"] = state

            return jsonify({
                "answer": (
                    f"I found multiple people named {person_name}. "
                    "Which person do you mean? "
                    + ", ".join(names)
                ),
                "clarification_required": True
            })

        elif len(candidates) == 1:

            selected_person = candidates.iloc[0]

            parsed["entities"]["person_id"] = str(
                selected_person["Person_ID"]
            )

            parsed["entities"]["person_name"] = str(
                selected_person["Name"]
            )

    # ----------------------------------
    # 5.6 RESOLVE RELATIONSHIP QUESTIONS
    # ----------------------------------

    relationship = parsed["entities"].get("relationship")

    is_singular_question = (
        re.search(
            r"\b(?:when|what)\s+is\s+(?:my|the)\b",
            q
        )
        and "birthdays" not in q
    )

    if relationship and is_singular_question:

        matches = df[
            df["Relationship"] == relationship.lower()
        ].drop_duplicates(
            subset=["Person_ID"]
        )

        # Multiple people with the same relationship
        if len(matches) > 1:

            names = matches["Name"].tolist()

            candidate_ids = matches["Person_ID"].tolist()

            session["pending_clarification"] = {
                "candidate_ids": candidate_ids,
                "names": names,
                "intent": parsed["intent"],
                "entities": parsed["entities"]
            }

            session["dialogue_state"] = state

            return jsonify({
                "answer": (
                    f"I found multiple {relationship}s. "
                    "Which person do you mean? "
                    + ", ".join(names)
                ),
                "clarification_required": True
            })

        # Exactly one person found
        elif len(matches) == 1:

            selected_person = matches.iloc[0]

            parsed["entities"]["person_id"] = str(
                selected_person["Person_ID"]
            )

            parsed["entities"]["person_name"] = str(
                selected_person["Name"]
            )

        # No matching relationship
        else:

            return jsonify({
                "answer": (
                    f"I couldn't find anyone listed as your "
                    f"{relationship} in the birthday records."
                )
            })

    # ----------------------------------
    # 5.7 EXECUTE QUERY
    # ----------------------------------

    answer = execute(parsed, df)

    # ----------------------------------
    # 5.8 CALCULATE RESULT IDS
    # ----------------------------------

    result_ids = get_result_ids(parsed)

    # ----------------------------------
    # 5.9 UPDATE CONVERSATION MEMORY
    # ----------------------------------

    update_state(parsed, state, result_ids)

    session["dialogue_state"] = state

    # ----------------------------------
    # 5.10 RETURN RESPONSE
    # ----------------------------------

    return jsonify({
        "answer": answer,
        "parsed": parsed
    })


# ----------------------------------
# 6. RESET ROUTE
# ----------------------------------

@app.route("/reset", methods=["POST"])
def reset():

    state = session.get("dialogue_state", {})

    reset_state(state)

    session.pop("dialogue_state", None)
    session.pop("pending_clarification", None)

    return jsonify({
        "answer": "Your conversation has been reset."
    })


# ----------------------------------
# 7. RUN FLASK APPLICATION
# ----------------------------------

if __name__ == "__main__":

    app.run(debug=True)
