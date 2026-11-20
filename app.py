
from flask import Flask, render_template, request, jsonify, session
import pandas as pd
from pathlib import Path
import re

from nlu import parse
from service import execute
from dialogue import enrich_with_context, update_state, reset_state

app = Flask(__name__)

# Session configuration
app.secret_key = "birthday-assistant-development-key"

# Load Excel dataset once
BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "data" / "people.xlsx"

df = pd.read_excel(EXCEL_PATH)

df["DOB"] = pd.to_datetime(df["DOB"], errors="coerce")
df["Relationship"] = df["Relationship"].fillna("").str.strip().str.lower()
df["Name"] = df["Name"].fillna("").astype(str).str.strip()
df["Nickname"] = df["Nickname"].fillna("").astype(str).str.strip()
df["Person_ID"] = df["Person_ID"].astype(str)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"answer": "Please enter a question."})

    q = message.lower()

    # Handle reset requests
    if (
    q in [
        "reset",
        "reset conversation",
        "reset the conversation",
        "start over",
        "clear conversation"
    ]
):
        session.pop("dialogue_state", None)
        session.pop("pending_clarification", None)

        return jsonify({
            "answer": "Conversation reset! What birthday would you like to know about?"
        })

    state = session.get("dialogue_state", {})

    # Parse the current message
    parsed = parse(message, df)
    entities = parsed["entities"]

    
    # ----------------------------------
    # 1. Handle pending clarification
    # ----------------------------------

    pending = session.get("pending_clarification")

    if pending:
        candidate_ids = pending["candidate_ids"]
        candidates = df[
            df["Person_ID"].isin(candidate_ids)
        ]

        
        # First check for an exact full-name match
        exact_matches = candidates[
            candidates["Name"].str.lower() == q
        ]

        if not exact_matches.empty:
            matches = exact_matches
        else:
            # Match both first/full-name fragments and nicknames
            name_matches = candidates[
                candidates["Name"].str.lower().str.contains(
                    re.escape(q), na=False
                )
            ]

            nickname_matches = candidates[
                candidates["Nickname"].str.lower() == q
            ]

            # Combine matches without duplicates
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
            "original": message
        }

        answer = execute(parsed, df)

        update_state(parsed, state)
        session["dialogue_state"] = state

        return jsonify({
            "answer": answer,
            "parsed": parsed
        })

    # ----------------------------------
    # 2. Apply remembered context
    # ----------------------------------

    parsed = enrich_with_context(parsed, state)

    # ----------------------------------
    # 3. Detect ambiguous relationships
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
                    f"Which person do you mean? "
                    + ", ".join(names)
                ),
                "clarification_required": True
            })

    # ----------------------------------
    # 4. Execute the query
    # ----------------------------------

    answer = execute(parsed, df)

    # ----------------------------------
    # 5. Update conversation memory
    # ----------------------------------

    result_ids = None

    if parsed["intent"] in ["birthday_search", "count_birthdays"]:
        results = df.copy()

        if "month" in parsed["entities"]:
            results = results[
                results["DOB"].dt.month
                == parsed["entities"]["month"]
            ]

        if "relationship" in parsed["entities"]:
            results = results[
                results["Relationship"]
                == parsed["entities"]["relationship"]
            ]

        if parsed["entities"].get("relative_date") == "tomorrow":
            from datetime import date, timedelta
            tomorrow = date.today() + timedelta(days=1)

            results = results[
                (results["DOB"].dt.month == tomorrow.month)
                & (results["DOB"].dt.day == tomorrow.day)
            ]

        if parsed["entities"].get("relative_month") == "next_month":
            from datetime import date
            next_month = date.today().month % 12 + 1

            results = results[
                results["DOB"].dt.month == next_month
            ]

        result_ids = results["Person_ID"].tolist()

    update_state(parsed, state, result_ids)
    session["dialogue_state"] = state

    return jsonify({
        "answer": answer,
        "parsed": parsed
    })


@app.route("/reset", methods=["POST"])
def reset():
    state = session.get("dialogue_state", {})
    reset_state(state)

    session.pop("dialogue_state", None)
    session.pop("pending_clarification", None)

    return jsonify({
        "answer": "Your conversation has been reset."
    })


if __name__ == "__main__":
    app.run(debug=True)
