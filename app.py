
from flask import Flask, render_template, request, jsonify
import pandas as pd
from pathlib import Path

from nlu import parse
from service import execute

app = Flask(__name__)

# Load Excel dataset once when the application starts
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

    parsed = parse(message, df)
    answer = execute(parsed, df)

    return jsonify({
        "answer": answer,
        "parsed": parsed
    })


if __name__ == "__main__":
    app.run(debug=True)
