
from flask import Flask, render_template, request, jsonify
import pandas as pd
from datetime import date, timedelta
from pathlib import Path
import calendar
import re

app = Flask(__name__)

# ---------------------------------
# 1. LOAD DATASET
# ---------------------------------

BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "data" / "people.xlsx"

df = pd.read_excel(EXCEL_PATH)
df["DOB"] = pd.to_datetime(df["DOB"], errors="coerce")
df = df.dropna(subset=["DOB"]).copy()

df["Relationship"] = df["Relationship"].fillna("").astype(str)
df["Name"] = df["Name"].fillna("").astype(str)
df["Nickname"] = df["Nickname"].fillna("").astype(str)


# ---------------------------------
# 2. LANGUAGE NORMALIZATION
# ---------------------------------

def normalize_question(message):
    question = message.lower().strip()
    question = re.sub(r"[?!,]", " ", question)
    question = re.sub(r"\s+", " ", question)

    # Different expressions with the same meaning
    replacements = {
        "birth date": "birthday",
        "date of birth": "birthday",
        "dob": "birthday",
        "born on": "birthday",
        "when was": "when is",
        "coming soon": "upcoming",
        "approaching": "upcoming",
        "coming up": "upcoming",
        "soon": "upcoming",
        "show me": "show",
        "list out": "list",
        "display": "show",
        "give me": "show",
        "tell me": "show",
        "do i have": "show",
        "are there any": "any",
        "is there any": "any",
    }

    for old, new in replacements.items():
        question = re.sub(
            rf"\b{re.escape(old)}\b",
            new,
            question
        )

    return re.sub(r"\s+", " ", question).strip()


# ---------------------------------
# 3. HELPER FUNCTIONS
# ---------------------------------

def format_birthday(row):
    return (
        f"{row['Name']} – "
        f"{row['DOB'].strftime('%d %B')}"
    )


def get_next_birthday(row):
    today = date.today()
    month = int(row["DOB"].month)
    day = int(row["DOB"].day)

    for year in [today.year, today.year + 1]:
        try:
            birthday = date(year, month, day)
            if birthday >= today:
                return birthday
        except ValueError:
            continue

    return None


def format_list(matches):
    if matches.empty:
        return "I couldn't find any matching birthdays."

    return "\n".join(
        format_birthday(row)
        for _, row in matches.iterrows()
    )


def is_count_question(question):
    count_words = [
        "how many", "count", "number of",
        "total", "quantity"
    ]
    return any(word in question for word in count_words)


# ---------------------------------
# 4. INTENT AND ENTITY DETECTION
# ---------------------------------

MONTHS = {
    month.lower(): number
    for number, month in enumerate(calendar.month_name)
    if month
}

MONTHS.update({
    month.lower(): number
    for number, month in enumerate(calendar.month_abbr)
    if month
})

RELATIONSHIPS = {
    "wife": "Wife",
    "husband": "Husband",
    "father": "Father",
    "mother": "Mother",
    "nephew": "Nephew",
    "niece": "Niece",
    "brother": "Brother",
    "sister": "Sister"
}


def find_relationship(question):
    for keyword, relationship in RELATIONSHIPS.items():
        if re.search(rf"\b{keyword}s?\b", question):
            return relationship

    return None


def find_month(question):
    for month_name, month_number in MONTHS.items():
        if re.search(rf"\b{re.escape(month_name)}\b", question):
            return month_number

    return None


def find_person(question):
    for _, row in df.iterrows():
        name = row["Name"].strip().lower()
        nickname = row["Nickname"].strip().lower()

        if name and re.search(rf"\b{re.escape(name)}\b", question):
            return row

        if (
            nickname
            and nickname != "nan"
            and re.search(rf"\b{re.escape(nickname)}\b", question)
        ):
            return row

    return None


# ---------------------------------
# 5. BIRTHDAY QUERY PROCESSOR
# ---------------------------------

def process_question(message):

    question = normalize_question(message)
    today = date.today()

    if not question:
        return "Please enter a birthday-related question."

    # Greeting
    if question in ["hi", "hello", "hey", "good morning", "good evening"]:
        return (
            "Hello! I'm Birthday Buddy. "
            "You can ask me about birthdays, family members, "
            "months, or upcoming celebrations."
        )

    # Detect entities
    relationship = find_relationship(question)
    month = find_month(question)

    # ---------------------------------
    # PERSON SEARCH
    # ---------------------------------

    person = find_person(question)

    if person is not None:
        return (
            f"{person['Name']}'s birthday is "
            f"{person['DOB'].strftime('%d %B')}."
        )

    # ---------------------------------
    # TOMORROW
    # ---------------------------------

    if "tomorrow" in question:

        tomorrow = today + timedelta(days=1)

        matches = df[
            (df["DOB"].dt.month == tomorrow.month) &
            (df["DOB"].dt.day == tomorrow.day)
        ]

        if matches.empty:
            return "There are no birthdays tomorrow."

        return "Birthdays tomorrow:\n" + format_list(matches)

    # ---------------------------------
    # NEXT MONTH
    # ---------------------------------

    if "next month" in question:

        next_month = today.month % 12 + 1

        matches = df[df["DOB"].dt.month == next_month]

        if matches.empty:
            return "There are no birthdays next month."

        if is_count_question(question):
            return (
                f"There are {len(matches)} birthdays next month."
            )

        return "Birthdays next month:\n" + format_list(matches)

    # ---------------------------------
    # MONTH SEARCH
    # ---------------------------------

    if month is not None:

        matches = df[df["DOB"].dt.month == month]

        if relationship:
            matches = matches[
                matches["Relationship"].str.lower()
                == relationship.lower()
            ]

        month_name = calendar.month_name[month]

        if matches.empty:
            return (
                f"I couldn't find any matching birthdays "
                f"in {month_name}."
            )

        if is_count_question(question):
            return (
                f"There are {len(matches)} matching birthdays "
                f"in {month_name}."
            )

        return (
            f"Birthdays in {month_name}:\n"
            + format_list(matches)
        )

    # ---------------------------------
    # UPCOMING BIRTHDAYS
    # ---------------------------------

    if "upcoming" in question:

        end_date = today + timedelta(days=30)
        upcoming = []

        for _, row in df.iterrows():
            birthday = get_next_birthday(row)

            if birthday and today <= birthday <= end_date:
                upcoming.append((birthday, row["Name"]))

        upcoming.sort(key=lambda item: item[0])

        if not upcoming:
            return "There are no upcoming birthdays in the next 30 days."

        if is_count_question(question):
            return (
                f"There are {len(upcoming)} upcoming birthdays "
                f"in the next 30 days."
            )

        result = [
            f"{name} – {birthday.strftime('%d %B')}"
            for birthday, name in upcoming
        ]

        return (
            "Here are the upcoming birthdays:\n"
            + "\n".join(result)
        )

    # ---------------------------------
    # RELATIONSHIP SEARCH
    # ---------------------------------

    if relationship:

        matches = df[
            df["Relationship"].str.lower()
            == relationship.lower()
        ]

        if matches.empty:
            return (
                f"I couldn't find anyone listed as your "
                f"{relationship.lower()}."
            )

        if is_count_question(question):
            return (
                f"You have {len(matches)} "
                f"{relationship.lower()} birthday records."
            )

        return (
            f"Birthdays of your {relationship.lower()}:\n"
            + format_list(matches)
        )

    # ---------------------------------
    # UNKNOWN QUESTION
    # ---------------------------------

    return (
        "I'm not sure I understood that question. "
        "Try asking in another way, such as "
        "'When is Rahul's birthday?' or "
        "'Show birthdays in September'."
    )


# ---------------------------------
# 6. FLASK ROUTES
# ---------------------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    if not isinstance(message, str):
        return jsonify({
            "answer": "Please enter a valid text question."
        }), 400

    answer = process_question(message)

    return jsonify({"answer": answer})


# ---------------------------------
# 7. RUN APPLICATION
# ---------------------------------

if __name__ == "__main__":
    app.run(debug=True)
