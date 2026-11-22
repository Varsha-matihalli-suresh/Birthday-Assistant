
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq


# Load API key from the project's .env file
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("GROQ_API_KEY")

client = (
    Groq(api_key=API_KEY, timeout=90.0, max_retries=2)
    if API_KEY else None
)

MODEL = "openai/gpt-oss-20b"


# Only these intents are allowed
ALLOWED_INTENTS = [
    "greeting",
    "birthday_search",
    "count_birthdays",
    "upcoming_birthdays",
    "person_birthday",
    "person_place",
    "unknown"
]



SYSTEM_PROMPT = """
You are an NLU parser for a Birthday Assistant.

Your job is ONLY to understand the user's question and extract
intent and entities. Never answer factual questions.
Never invent birthdays, names, or places.
The Excel dataset is the source of factual information.

Return JSON only.

INTENT RULES:

1. greeting:
   Use for greetings such as hi, hello, hey.

2. person_birthday:
   Use ONLY when the user asks for the actual birthday date
   of a person.
   Examples:
   - When is Rahul's birthday?
   - Tell me Rahul's date of birth.
   - What is Rahul's birthday?

3. upcoming_birthdays:
   Use when the user asks whether a person's birthday is
   coming soon, approaching, or within the next 30 days.
   This rule has priority over person_birthday.
   Examples:
   - Does Rahul have a birthday coming soon?
   - Is Rahul's birthday approaching?
   - Whose birthday is coming up?
   - Are there any birthdays soon?

4. birthday_search:
   Use for birthday searches by month, relationship,
   relationship group, or other filters.
   Examples:
   - Nephew birthdays in September.
   - Sibling family birthdays next month.

5. count_birthdays:
   Use when the user asks how many birthdays match.

6. person_place:
   Use when the user asks where a person is from.

7. unknown:
   Use when the question does not match these intents.

IMPORTANT:
- If the question contains "coming soon", "coming up",
  "approaching", or asks whether a birthday is near,
  use upcoming_birthdays, even if a person's name is provided.
- Extract the person's name when mentioned.
- Do not confuse asking for a birthday date with asking
  whether a birthday is coming soon.
- "Next month" is birthday_search, not upcoming_birthdays.
- Only extract relationship_group when the user explicitly
  mentions a broad group such as "sibling family".
- Never use "sibling" as an individual relationship.
- If a relationship group is identified, leave relationship
  empty unless an individual relationship is also mentioned.
"""



# JSON schema for structured output
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ALLOWED_INTENTS
        },
        "entities": {
            "type": "object",
            "properties": {
                "person_name": {"type": "string"},
                "relationship": {"type": "string"},
                "relationship_group": {
    "type": "string",
    "enum": [
        "",
        "academic",
        "community",
        "extended family",
        "friend circle",
        "immediate family",
        "sibling family",
        "spouse/sibling family",
        "work"
    ]
},
                "month": {
                    "anyOf": [
                        {"type": "integer", "minimum": 1, "maximum": 12},
                        {"type": "null"}
                    ]
                },
                "relative_date": {
                    "type": "string",
                    "enum": ["tomorrow", ""]
                },
                "relative_month": {
                    "type": "string",
                    "enum": ["next_month", ""]
                },
                "place": {"type": "string"}
            },
            "required": [
                "person_name",
                "relationship",
                "relationship_group",
                "month",
                "relative_date",
                "relative_month",
                "place"
            ],
            "additionalProperties": False
        }
    },
    "required": ["intent", "entities"],
    "additionalProperties": False
}


def parse_with_llm(message):

    if client is None:
        raise RuntimeError("Groq API key is not configured.")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": message
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "birthday_nlu",
                "strict": True,
                "schema": RESPONSE_SCHEMA
            }
        },
        temperature=0
    )

    result = response.choices[0].message.content

    if not result:
        raise ValueError("Groq returned an empty response.")

    parsed = json.loads(result)

    return parsed


def normalize_llm(parsed, df):
    entities = parsed["entities"]
    intent = parsed["intent"]

    # Validate individual relationship
    relationship = entities.get("relationship", "").strip().lower()

    valid_relationships = set(
        df["Relationship"].dropna().astype(str).str.strip().str.lower()
    )

    if relationship and relationship not in valid_relationships:
        entities["relationship"] = ""

    # Validate relationship group
    group = entities.get("relationship_group", "").strip().lower()

    valid_groups = set(
        df["Relationship_Group"].dropna().astype(str).str.strip().str.lower()
    )

    if group and group not in valid_groups:
        entities["relationship_group"] = ""

    # Validate person name against Excel
    name = entities.get("person_name", "").strip().lower()

    if name:
        matches = df[
            (df["Name"].str.lower() == name) |
            (df["Nickname"].str.lower() == name)
        ]

        if len(matches) == 1:
            person = matches.iloc[0]
            entities["person_id"] = str(person["Person_ID"])
            entities["person_name"] = person["Name"]

        elif len(matches) > 1:
            entities["person_name"] = ""
            intent = "unknown"

        else:
            entities["person_name"] = ""
            intent = "unknown"

    # Validate month
    month = entities.get("month")

    if month is not None and (
        not isinstance(month, int) or isinstance(month, bool)
        or not 1 <= month <= 12
    ):
        entities["month"] = None

    # Remove empty entities
    entities = {
        key: value for key, value in entities.items()
        if value not in ("", None)
    }

    return {
        "intent": intent,
        "entities": entities,
        "original": ""
    }

