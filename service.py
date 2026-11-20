
from datetime import date, timedelta
import calendar


def format_birthday(person):
    dob = person["DOB"]
    return dob.strftime("%d %B %Y")



def next_birthday(dob):
    today = date.today()

    # Convert Pandas Timestamp into Python date
    if hasattr(dob, "date"):
        dob = dob.date()

    try:
        upcoming = dob.replace(year=today.year)
    except ValueError:
        upcoming = date(today.year, 2, 28)

    if upcoming < today:
        try:
            upcoming = dob.replace(year=today.year + 1)
        except ValueError:
            upcoming = date(today.year + 1, 2, 28)

    return upcoming



def execute(parsed, df):
    intent = parsed["intent"]
    entities = parsed["entities"]

    if intent == "greeting":
        return "Hello! I am your Birthday Assistant. Ask me about upcoming birthdays."

    if intent == "unknown":
        return "Sorry, I couldn't understand that. Try asking about a person's birthday, a month, or upcoming birthdays."

    # Individual person's birthday
    if intent == "person_birthday":
        person = df[df["Person_ID"] == entities["person_id"]]

        if person.empty:
            return "I couldn't find that person."

        person = person.iloc[0]
        return (
            f"{person['Name']}'s birthday is "
            f"{format_birthday(person)}."
        )

    # Start with the complete dataset
    results = df.copy()

    # Filter by month
    if "month" in entities:
        results = results[results["DOB"].dt.month == entities["month"]]

    # Filter by relationship
    if "relationship" in entities:
        results = results[
            results["Relationship"].str.lower()
            == entities["relationship"]
        ]

    # Tomorrow's birthdays
    if entities.get("relative_date") == "tomorrow":
        tomorrow = date.today() + timedelta(days=1)
        results = results[
            (results["DOB"].dt.month == tomorrow.month)
            & (results["DOB"].dt.day == tomorrow.day)
        ]

    # Next month's birthdays
    if entities.get("relative_month") == "next_month":
        next_month = date.today().month % 12 + 1
        results = results[results["DOB"].dt.month == next_month]

    if intent == "upcoming_birthdays":
        today = date.today()
        end_date = today + timedelta(days=30)

        upcoming = []

        for _, person in results.iterrows():
            next_date = next_birthday(person["DOB"])

            if today <= next_date <= end_date:
                upcoming.append((next_date, person))

        upcoming.sort(key=lambda item: item[0])

        if not upcoming:
            return "There are no birthdays in the next 30 days."

        lines = [
            f"{person['Name']} - {birthday.strftime('%d %B')}"
            for birthday, person in upcoming
        ]

        return "Upcoming birthdays:\n" + "\n".join(lines)

    if results.empty:
        return "No matching birthdays found."

    if intent == "count_birthdays":
        return f"There are {len(results)} matching birthdays."

    lines = [
        f"{row['Name']} - {format_birthday(row)}"
        for _, row in results.iterrows()
    ]

    return "Here are the matching birthdays:\n" + "\n".join(lines)
