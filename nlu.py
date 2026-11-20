
import re

MONTHS = {
    month.lower(): number
    for number, month in enumerate(
        [
            "January", "February", "March", "April",
            "May", "June", "July", "August",
            "September", "October", "November", "December"
        ],
        start=1
    )
}

RELATIONSHIPS = [
    "grandfather", "grandmother", "daughter", "brother",
    "sister", "nephew", "niece", "husband", "wife",
    "father", "mother", "son", "uncle", "aunt",
    "cousin", "friend"
]


def normalize_question(message):
    q = message.lower().strip()

    replacements = {
        "date of birth": "birthday",
        "birth date": "birthday",
        "dob": "birthday",
        "coming soon": "upcoming",
        "coming up": "upcoming",
        "approaching": "upcoming",
        "show me": "",
        "list out": "",
        "display": "",
        "give me": "",
        "are there any": "any",
        "is there any": "any"
    }

    for old, new in replacements.items():
        q = q.replace(old, new)

    return re.sub(r"\s+", " ", q).strip()


def parse(message, df):
    q = normalize_question(message)
    entities = {}

    # Greeting
    if q in ["hi", "hello", "hey", "good morning", "good evening"]:
        return {
            "intent": "greeting",
            "entities": entities,
            "original": message
        }

    # Extract month
    for month, number in MONTHS.items():
        if re.search(r"\b" + month + r"\b", q):
            entities["month"] = number
            break

    # Extract relationship
    for relationship in RELATIONSHIPS:
        if re.search(r"\b" + relationship + r"s?\b", q):
            entities["relationship"] = relationship
            break

    # Extract person name or nickname
    for _, person in df.iterrows():
        name = str(person["Name"]).lower()
        nickname = str(person["Nickname"]).lower()

        if name in q or (nickname and nickname in q):
            entities["person_id"] = str(person["Person_ID"])
            entities["person_name"] = str(person["Name"])
            break

    # Extract relative dates
    if "tomorrow" in q:
        entities["relative_date"] = "tomorrow"

    if "next month" in q:
        entities["relative_month"] = "next_month"

    # Determine intent
    if "tomorrow" in entities.values():
        intent = "birthday_search"

    elif "relative_month" in entities:
        intent = "count_birthdays" if "how many" in q else "birthday_search"

    elif "person_id" in entities:
        intent = "person_birthday"

    elif "month" in entities or "relationship" in entities:
        intent = "count_birthdays" if "how many" in q else "birthday_search"

    elif "upcoming" in q:
        intent = "upcoming_birthdays"

    else:
        intent = "unknown"

    return {
        "intent": intent,
        "entities": entities,
        "original": message
    }
