
from flask import Flask, render_template, request, jsonify
import pandas as pd
from datetime import date, datetime, timedelta
from pathlib import Path
import calendar
import re

app = Flask(__name__)

# ---------------------------------
# 1. LOAD THE EXCEL DATASET
# ---------------------------------

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "data" / "people.xlsx"

df = pd.read_excel(EXCEL_PATH)

# Convert DOB column into date values
df["DOB"] = pd.to_datetime(df["DOB"], errors="coerce")

# Remove rows with invalid dates
df = df.dropna(subset=["DOB"]).copy()

# ---------------------------------
# 2. HELPER FUNCTIONS
# ---------------------------------

def get_name(row):
    return str(row["Name"])


def get_birthday_date(row, year):
    """Create this person's birthday date for a given year."""
    month = int(row["DOB"].month)
    day = int(row["DOB"].day)

    try:
        return date(year, month, day)
    except ValueError:
        # Handle February 29 in a non-leap year
        return None


def get_next_birthday(row):
    """Find the next occurrence of a person's birthday."""
    today = date.today()

    birthday = get_birthday_date(row, today.year)

    if birthday is not None and birthday >= today:
        return birthday

    return get_birthday_date(row, today.year + 1)


def format_birthday(row):
    birthday = row["DOB"].strftime("%d %B")
    return f"{get_name(row)} – {birthday}"


# ---------------------------------
# 3. RULE-BASED QUESTION PROCESSOR
# ---------------------------------

def process_question(message):

    question = message.lower().strip()
    today = date.today()

    if not question:
        return "Please enter a birthday-related question."

    # ---------------------------------
    # RULE 1: GREETINGS
    # ---------------------------------

    if question in ["hi", "hello", "hey", "good morning", "good evening"]:
        return (
            "Hello! I'm Birthday Buddy. "
            "Ask me about upcoming birthdays, family birthdays, or a person's birthday."
        )

    # ---------------------------------
    # RULE 2: BIRTHDAYS TOMORROW
    # ---------------------------------

    if "tomorrow" in question:

        tomorrow = today + timedelta(days=1)

        matches = df[
            (df["DOB"].dt.month == tomorrow.month) &
            (df["DOB"].dt.day == tomorrow.day)
        ]

        if matches.empty:
            return "There are no birthdays tomorrow."

        names = [format_birthday(row) for _, row in matches.iterrows()]

        return "Birthdays tomorrow:\n" + "\n".join(names)

    # ---------------------------------
    # RULE 3: BIRTHDAYS NEXT MONTH
    # ---------------------------------

    if "next month" in question:

        next_month = today.month + 1
        year = today.year

        if next_month > 12:
            next_month = 1
            year += 1

        matches = df[df["DOB"].dt.month == next_month]

        if matches.empty:
            return "There are no birthdays next month."

        names = [format_birthday(row) for _, row in matches.iterrows()]

        return (
            f"There are {len(matches)} birthdays next month:\n" +
            "\n".join(names)
        )

    # ---------------------------------
    # RULE 4: BIRTHDAYS IN A MONTH
    # ---------------------------------

    month_names = {
        month.lower(): number
        for number, month in enumerate(calendar.month_name)
        if month
    }

    month_names.update({
        month.lower(): number
        for number, month in enumerate(calendar.month_abbr)
        if month
    })

    for month_name, month_number in month_names.items():

        if re.search(rf"\b{re.escape(month_name)}\b", question):

            matches = df[df["DOB"].dt.month == month_number]

            # Check whether a relationship was mentioned
            relationship_keywords = {
                "nephew": "Nephew",
                "niece": "Niece",
                "wife": "Wife",
                "husband": "Husband",
                "father": "Father",
                "mother": "Mother",
                "brother": "Brother",
                "sister": "Sister"
            }

            for keyword, relationship in relationship_keywords.items():
                if re.search(rf"\b{keyword}\b", question):
                    matches = matches[
                        matches["Relationship"].str.lower() == relationship.lower()
                    ]

            if matches.empty:
                return f"There are no matching birthdays in {calendar.month_name[month_number]}."

            names = [format_birthday(row) for _, row in matches.iterrows()]

            return (
                f"Birthdays in {calendar.month_name[month_number]}:\n" +
                "\n".join(names)
            )

    # ---------------------------------
    # RULE 5: UPCOMING BIRTHDAYS
    # ---------------------------------

    if "upcoming" in question:

        end_date = today + timedelta(days=30)
        upcoming = []

        for _, row in df.iterrows():
            next_birthday = get_next_birthday(row)

            if next_birthday is not None and today <= next_birthday <= end_date:
                upcoming.append((next_birthday, get_name(row)))

        upcoming.sort(key=lambda item: item[0])

        if not upcoming:
            return "There are no upcoming birthdays in the next 30 days."

        names = [
            f"{name} – {birthday.strftime('%d %B')}"
            for birthday, name in upcoming
        ]

        return (
            f"Here are the upcoming birthdays in the next 30 days:\n" +
            "\n".join(names)
        )

    # ---------------------------------
    # RULE 6: FIND A PERSON'S BIRTHDAY
    # ---------------------------------

    for _, row in df.iterrows():

        name = str(row["Name"]).lower()
        nickname = str(row["Nickname"]).lower()

        if name in question or (
            nickname and nickname != "nan" and
            re.search(rf"\b{re.escape(nickname)}\b", question)
        ):

            return (
                f"{get_name(row)}'s birthday is "
                f"{row['DOB'].strftime('%d %B')}."
            )

    # ---------------------------------
    # RULE 7: RELATIONSHIP QUESTIONS
    # ---------------------------------

    relationship_keywords = {
        "wife": "Wife",
        "husband": "Husband",
        "father": "Father",
        "mother": "Mother",
        "nephew": "Nephew",
        "niece": "Niece",
        "brother": "Brother",
        "sister": "Sister"
    }

    for keyword, relationship in relationship_keywords.items():

        if re.search(rf"\b{keyword}\b", question):

            matches = df[
                df["Relationship"].str.lower() == relationship.lower()
            ]

            if matches.empty:
                return f"I couldn't find anyone listed as your {keyword}."

            names = [format_birthday(row) for _, row in matches.iterrows()]

            return (
                f"Your {keyword}'s birthday:\n" +
                "\n".join(names)
            )

    # ---------------------------------
    # RULE 8: UNKNOWN QUESTIONS
    # ---------------------------------

    return (
        "I'm not sure how to answer that yet. "
        "Try asking about a person's birthday, a month, "
        "tomorrow, next month, or upcoming birthdays."
    )


# ---------------------------------
# 4. FLASK ROUTES
# ---------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    if not isinstance(message, str):
        return jsonify({"answer": "Please enter a valid text question."}), 400

    answer = process_question(message)

    return jsonify({"answer": answer})


# ---------------------------------
# 5. RUN THE APPLICATION
# ---------------------------------

if __name__ == "__main__":
    app.run(debug=True)
