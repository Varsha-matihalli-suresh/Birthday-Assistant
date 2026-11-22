
from datetime import date, timedelta
import calendar


def format_birthday(person):
    dob = person["DOB"]
    return dob.strftime("%d %B %Y")


def next_birthday(dob):
    today = date.today()

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

    # ----------------------------------
    # 1. GREETING
    # ----------------------------------

    if intent == "greeting":
        return (
            "Hey there! 🌸 Welcome to Birthday Buddy!\n\n"
            "I'm here to help you remember all the special birthdays. "
            "Who are we wishing today? 🎂"
        )

    # ----------------------------------
    # 2. UNKNOWN QUESTION
    # ----------------------------------

    if intent == "unknown":
        return (
            "Oops! I'm not quite sure what you mean. 🌸\n\n"
            "You can ask me about someone's birthday, "
            "birthdays in a particular month, or upcoming celebrations."
        )

    # ----------------------------------
    # 3. SPECIFIC PERSON'S BIRTHDAY
    # ----------------------------------

    if intent == "person_birthday":

        person_id = entities.get("person_id")

        if not person_id:
            return (
                "I couldn't identify that person. "
                "Could you check the name and try again? 🌸"
            )

        person = df[
            df["Person_ID"].astype(str) == str(person_id)
        ]

        if person.empty:
            return "I couldn't find that person in my birthday list. 🌸"

        person = person.iloc[0]

        dob = person["DOB"]

        return (
            f"Of course! 🎂 {person['Name']}'s birthday is "
            f"{format_birthday(person)}.\n\n"
            "Make sure to save the date! 💗"
        )

    # ----------------------------------
    # 4. SPECIFIC PERSON'S PLACE
    # ----------------------------------

    if intent == "person_place":

        person_id = entities.get("person_id")

        if not person_id:
            return "I couldn't identify that person. Could you check the name? 🌸"

        person = df[
            df["Person_ID"].astype(str) == str(person_id)
        ]

        if person.empty:
            return "I couldn't find that person in my records. 🌸"

        person = person.iloc[0]

        place_column = next(
            (
                column for column in ["Place", "Location", "City"]
                if column in df.columns
            ),
            None
        )

        if not place_column or not str(person[place_column]).strip():
            return f"I couldn't find a place for {person['Name']} in my records."

        return (
            f"Here's what I found! 🌸\n\n"
            f"{person['Name']} is from {person[place_column]}."
        )

    # ----------------------------------
    # 5. FILTER THE DATASET
    # ----------------------------------

    results = df.copy()

    # Person filter
    person_id = entities.get("person_id")

    if person_id:
        results = results[
            results["Person_ID"].astype(str) == str(person_id)
        ]

    # Month filter
    month = entities.get("month")

    if month:
        results = results[
            results["DOB"].dt.month == int(month)
        ]

    # Individual relationship filter
    relationship = entities.get("relationship")

    if relationship:
        results = results[
            results["Relationship"].str.lower()
            == relationship.lower()
        ]

    # Relationship group filter
    relationship_group = entities.get("relationship_group")

    if relationship_group and "Relationship_Group" in results.columns:
        results = results[
            results["Relationship_Group"].str.lower()
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

    # Upcoming birthdays: next 30 days
    if intent == "upcoming_birthdays":

        today = date.today()
        end_date = today + timedelta(days=30)

        results = results[
            results["DOB"].apply(
                lambda dob: (
                    today <= next_birthday(dob) <= end_date
                )
            )
        ]

    # ----------------------------------
    # 6. HANDLE NO RESULTS
    # ----------------------------------

    if results.empty:

        if intent == "upcoming_birthdays":
            person_name = entities.get("person_name")

            if person_name:
                return (
                    f"No birthday for {person_name} falls within "
                    "the next 30 days. 🌸"
                )

            return (
                "Looks like there are no birthdays coming up "
                "in the next 30 days. Enjoy the little break! 🌸"
            )

        return (
            "I couldn't find any birthdays matching those details. 🌸\n\n"
            "Would you like to try another month or relationship?"
        )

    # ----------------------------------
    # 7. COUNT BIRTHDAYS
    # ----------------------------------

    if intent == "count_birthdays":

        count = len(results)

        if count == 1:
            return "You have one birthday to remember! 🎂"

        return (
            f"You have {count} birthdays to remember! 🎉\n\n"
            "Better keep those wishes ready! 🌸"
        )

    # ----------------------------------
    # 8. DISPLAY BIRTHDAYS
    # ----------------------------------

    if intent in ["birthday_search", "upcoming_birthdays"]:

        results = results.copy()

        results["Next_Birthday"] = results["DOB"].apply(next_birthday)

        results = results.sort_values("Next_Birthday")

        count = len(results)

        lines = [
            f"🎂 {row['Name']} — {row['DOB'].strftime('%d %B')}"
            for _, row in results.iterrows()
        ]

        birthday_list = "\n".join(lines)

        if intent == "upcoming_birthdays":

            heading = (
                "Good news! Here are the birthdays coming up soon! 🎉"
                if count > 1
                else "Good news! There's a birthday coming up soon! 🎉"
            )

        elif relationship_group:

            heading = (
                f"Absolutely! Here are the birthdays from your "
                f"{relationship_group} next month! 🌸"
            )

        elif relationship:

            heading = (
                f"Of course! Here are the {relationship} birthdays I found! 💗"
            )

        elif month:

            month_name = calendar.month_name[int(month)]

            heading = (
                f"Here are the birthdays in {month_name}! 🎂"
            )

        else:

            heading = "Of course! Here are the birthdays I found! 🌸"

        if count == 1:
            closing = "Don't forget to send your wishes! 💗"
        else:
            closing = "Plenty of special days to remember! 🌸"

        return (
            f"{heading}\n\n"
            f"{birthday_list}\n\n"
            f"{closing}"
        )

    # ----------------------------------
    # 9. FALLBACK
    # ----------------------------------

    return (
        "I understood part of your question, "
        "but I'm not sure how to answer it yet. 🌸"
    )
