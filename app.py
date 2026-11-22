
from flask import Flask, render_template, request, jsonify, session
import pandas as pd
from pathlib import Path
import re
from datetime import date, timedelta

from nlu import parse
from service import execute
from dialogue import enrich_with_context, update_state, reset_state
from llm_nlu import parse_with_llm, normalize_llm


app = Flask(__name__)

# ----------------------------------
# 1. SESSION CONFIGURATION
# ----------------------------------

app.secret_key = "birthday-assistant-development-key"


# ----------------------------------
# 2. LOAD EXCEL DATASET ONCE
# ----------------------------------

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "data" / "people.xlsx"

df = pd.read_excel(EXCEL_PATH)

df["DOB"] = pd.to_datetime(df["DOB"], errors="coerce")
df["Relationship"] = (
    df["Relationship"].fillna("").astype(str).str.strip().str.lower()
)
df["Name"] = df["Name"].fillna("").astype(str).str.strip()
df["Nickname"] = df["Nickname"].fillna("").astype(str).str.strip()
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
# 3. HOME PAGE
# ----------------------------------

@app.route("/")
def home():
    return render_template("index.html")


# ----------------------------------
# 4. CHAT ROUTE
# ----------------------------------

@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"answer": "Please enter a question."})

    q = message.lower()

    # ----------------------------------
    # 4.1 RESET CONVERSATION
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
            "answer": "Conversation reset! What birthday would you like to know about?"
        })

    state = session.get("dialogue_state", {})

    # ----------------------------------
    # 4.2 HANDLE PENDING CLARIFICATION
    # ----------------------------------

    pending = session.get("pending_clarification")

    if pending:

        candidate_ids = pending["candidate_ids"]

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
            # Search name fragments
            name_matches = candidates[
                candidates["Name"].str.lower().str.contains(
                    re.escape(q), na=False
                )
            ]

            # Search nicknames
            nickname_matches = candidates[
                candidates["Nickname"].str.lower() == q
            ]

            matches = pd.concat(
                [name_matches, nickname_matches]
            ).drop_duplicates(subset=["Person_ID"])

        if len(matches) == 0:
            return jsonify({
                "answer": (
                    "I couldn't identify that person. "
                    "Please choose: " + ", ".join(pending["names"])
                )
            })

        if len(matches) > 1:
            return jsonify({
                "answer": (
                    "I found more than one matching person. "
                    "Please provide the full name: "
                    + ", ".join(matches["Name"].tolist())
                ),
                "clarification_required": True
            })

        selected_person = matches.iloc[0]

        session.pop("pending_clarification", None)

        parsed = {
            "intent": "person_birthday",
            "entities": {
                "person_id": selected_person["Person_ID"],
                "person_name": selected_person["Name"]
            },
            "original": message,
            "source": "clarification"
        }

        answer = execute(parsed, df)

        update_state(parsed, state)
        session["dialogue_state"] = state

        return jsonify({
            "answer": answer,
            "parsed": parsed
        })

    # ----------------------------------
    # 4.3 V4 GROQ NLU WITH V3 FALLBACK
    # ----------------------------------

    try:
        parsed = parse_with_llm(message)
        parsed = normalize_llm(parsed, df)

        parsed["original"] = message
        parsed["source"] = "groq"

    except Exception as e:

        print("Groq NLU failed. Using rule-based NLU:", e)

        parsed = parse(message, df)
        parsed["source"] = "rule-based"

    # ----------------------------------
    # 4.4 APPLY REMEMBERED CONTEXT
    # ----------------------------------

    parsed = enrich_with_context(parsed, state)

    # ----------------------------------
    # 4.5 DETECT AMBIGUOUS RELATIONSHIPS
    # ----------------------------------

    relationship = parsed["entities"].get("relationship")

    is_singular_question = (
        re.search(r"\bwhen\s+is\s+(?:my|the)\b", q)
        and "birthdays" not in q
    )

    if relationship and is_singular_question:

        matches = df[
            df["Relationship"] == relationship
        ]

        if len(matches) > 1:

            names = matches["Name"].tolist()
            candidate_ids = matches["Person_ID"].tolist()

            session["pending_clarification"] = {
                "candidate_ids": candidate_ids,
                "names": names
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

    # ----------------------------------
    # 4.6 EXECUTE QUERY
    # ----------------------------------

    answer = execute(parsed, df)

    # ----------------------------------
    # 4.7 CALCULATE RESULT IDS
    # ----------------------------------

    result_ids = None

    if parsed["intent"] in [
        "birthday_search",
        "count_birthdays",
        "upcoming_birthdays"
    ]:

        results = df.copy()
        entities = parsed["entities"]

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
                results["Relationship_Group"]
                == relationship_group.lower()
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

        result_ids = results["Person_ID"].tolist()

    # ----------------------------------
    # 4.8 UPDATE CONVERSATION MEMORY
    # ----------------------------------

    update_state(parsed, state, result_ids)

    session["dialogue_state"] = state

    # ----------------------------------
    # 4.9 RETURN RESPONSE
    # ----------------------------------

    return jsonify({
        "answer": answer,
        "parsed": parsed
    })


# ----------------------------------
# 5. RESET ROUTE
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
# 6. RUN FLASK APPLICATION
# ----------------------------------

if __name__ == "__main__":
    app.run(debug=True)
