"""
llm_client.py
Uses Google Gemini (google-genai package) to turn natural-language chat
messages into structured data: movie titles mentioned + filter preferences.
"""

import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

TMDB_GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Science Fiction",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
}

# ISO 639-1 language codes for common film industries/languages, used when
# someone asks for "Bollywood", "Tamil movies", etc. instead of a genre.
LANGUAGE_CODES = {
    "Hindi": "hi", "Bollywood": "hi",
    "Tamil": "ta", "Kollywood": "ta",
    "Telugu": "te", "Tollywood": "te",
    "Kannada": "kn", "Sandalwood": "kn",
    "Malayalam": "ml", "Mollywood": "ml",
    "Punjabi": "pa", "Bengali": "bn", "Marathi": "mr",
    "English": "en", "Korean": "ko", "Japanese": "ja",
    "French": "fr", "Spanish": "es",
}

FILTER_PROMPT = f"""You convert a user's movie filter request into structured JSON.

Available genres: {list(TMDB_GENRES.values())}
Available languages/industries: {list(LANGUAGE_CODES.keys())}

Return ONLY valid JSON (no markdown, no explanation, no backticks) with this exact shape:
{{
  "genre": <one of the available genres exactly as listed, or null if none mentioned>,
  "max_runtime_minutes": <integer, or null if no upper time limit mentioned>,
  "min_runtime_minutes": <integer, or null if no lower time limit mentioned>,
  "min_rating": <float 0-10, or null if no rating preference mentioned>,
  "language": <one of the available languages/industries exactly as listed, or null if none mentioned>
}}

Examples:
"comedy under 2 hours" -> {{"genre": "Comedy", "max_runtime_minutes": 120, "min_runtime_minutes": null, "min_rating": null, "language": null}}
"something scary" -> {{"genre": "Horror", "max_runtime_minutes": null, "min_runtime_minutes": null, "min_rating": null, "language": null}}
"highly rated action movie" -> {{"genre": "Action", "max_runtime_minutes": null, "min_runtime_minutes": null, "min_rating": 7.0, "language": null}}
"short thriller" -> {{"genre": "Thriller", "max_runtime_minutes": 100, "min_runtime_minutes": null, "min_rating": null, "language": null}}
"recommend Bollywood movies" -> {{"genre": null, "max_runtime_minutes": null, "min_runtime_minutes": null, "min_rating": null, "language": "Bollywood"}}
"highly rated Tamil films" -> {{"genre": null, "max_runtime_minutes": null, "min_runtime_minutes": null, "min_rating": 7.0, "language": "Tamil"}}
"Hindi comedy" -> {{"genre": "Comedy", "max_runtime_minutes": null, "min_runtime_minutes": null, "min_rating": null, "language": "Hindi"}}
"""

MESSAGE_PARSE_PROMPT = """You read a single chat message from a user talking to a movie
recommendation chatbot. Extract two things:

1. "new_titles": any movie titles the user is mentioning as something they liked/watched/enjoyed
   in THIS message. Do NOT invent titles. If the message has no movie titles, return an empty list.
2. "filter_text": any filtering preference mentioned (genre, runtime, rating), as a short phrase.
   If no filter is mentioned, return an empty string.

Return ONLY valid JSON, no markdown, no backticks, in this exact shape:
{"new_titles": ["Title One", "Title Two"], "filter_text": "comedy under 2 hours"}

Examples:
"I liked Interstellar and Inception" -> {"new_titles": ["Interstellar", "Inception"], "filter_text": ""}
"now show me a comedy" -> {"new_titles": [], "filter_text": "comedy"}
"I also liked The Hangover" -> {"new_titles": ["The Hangover"], "filter_text": ""}
"under 90 minutes please" -> {"new_titles": [], "filter_text": "under 90 minutes"}
"I loved The Matrix, show me something scary and short" -> {"new_titles": ["The Matrix"], "filter_text": "something scary and short"}
"""

INTENT_PROMPT = """You are the intent router for a movie recommendation chatbot.
Read the user's message and classify it into exactly ONE of these categories:

- "recommend": user is stating movies they liked/watched, or asking for a recommendation,
  or giving a filter for recommendations (genre/runtime/rating/language), or continuing a
  recommendation conversation (e.g. "show me more", "something else", "under 2 hours").
  Look for framing like "I liked", "I watched", "suggest", "recommend".
- "movie_lookup": user names ONE specific movie with no "I liked/watched" framing, often
  with no other context, OR asks to see details/trailer/where to watch a specific movie.
  This is for when the user wants information ABOUT that one movie, not recommendations
  similar to it. Examples: just a bare title, "show me Inception", "where can I watch RRR",
  "trailer for Pathaan", "tell me about Dangal".
- "movie_question": user is asking a factual or opinion question about a movie, actor,
  director, or general movie trivia (e.g. "who directed Inception?", "is Interstellar good?").
- "chitchat": greetings, thanks, small talk, or meta questions about the chatbot itself.

Return ONLY valid JSON, no markdown, no backticks, in this exact shape:
{"intent": "recommend"}

Examples:
"I liked Interstellar and Inception" -> {"intent": "recommend"}
"show me a comedy" -> {"intent": "recommend"}
"Inception" -> {"intent": "movie_lookup"}
"RRR" -> {"intent": "movie_lookup"}
"where can I watch Pathaan" -> {"intent": "movie_lookup"}
"trailer for Dangal" -> {"intent": "movie_lookup"}
"tell me about 3 Idiots" -> {"intent": "movie_lookup"}
"who directed Inception?" -> {"intent": "movie_question"}
"is The Matrix worth watching?" -> {"intent": "movie_question"}
"hi there" -> {"intent": "chitchat"}
"what can you do?" -> {"intent": "chitchat"}
"thanks!" -> {"intent": "chitchat"}
"""

GENERAL_QUESTION_PROMPT = """You are a knowledgeable, friendly movie expert chatbot.
Answer the user's movie-related question directly and conversationally in 2-4 sentences.
Stick to movies, actors, directors, and film trivia. If you are not confident about a fact
(release dates, box office numbers, awards), say so rather than guessing.
Do not use markdown formatting -- plain conversational text only.
"""

CHITCHAT_PROMPT = """You are the friendly front-end of a movie recommendation chatbot.
Respond briefly and warmly (1-2 sentences) to greetings, thanks, or meta questions about
what you can do. If asked what you can do, mention: recommending movies based on ones they
liked, filtering by genre/runtime/rating, and answering movie trivia questions.
Do not use markdown formatting -- plain conversational text only.
"""


def classify_intent(message: str) -> str:
    """
    Decide what the user wants: a recommendation, a specific movie lookup,
    a factual movie question, or just chitchat. Falls back to "recommend"
    if parsing fails, since that's the original core feature and the
    safest default.
    """
    if not message or not message.strip():
        return "chitchat"

    try:
        raw = _call_gemini(message, INTENT_PROMPT)
        parsed = json.loads(_strip_json_fences(raw))
        intent = parsed.get("intent", "recommend")
        if intent not in ("recommend", "movie_lookup", "movie_question", "chitchat"):
            return "recommend"
        return intent
    except json.JSONDecodeError:
        return "recommend"


LOOKUP_TITLE_PROMPT = """Extract the single movie title the user is asking about.
Return ONLY the title as plain text, no quotes, no markdown, no explanation.

Examples:
"Inception" -> Inception
"where can I watch RRR" -> RRR
"trailer for Pathaan" -> Pathaan
"tell me about 3 Idiots" -> 3 Idiots
"""


def extract_movie_title(message: str) -> str:
    """Pull out just the movie title from a movie_lookup message."""
    try:
        raw = _call_gemini(message, LOOKUP_TITLE_PROMPT)
        return raw.strip().strip('"').strip("'")
    except Exception:
        return message.strip()


def answer_general_question(message: str) -> str:
    """Answer a movie trivia / factual / opinion question directly using Gemini."""
    try:
        return _call_gemini(message, GENERAL_QUESTION_PROMPT)
    except Exception:
        return "Sorry, I couldn't look that up right now. Could you try rephrasing?"


def answer_chitchat(message: str) -> str:
    """Respond to greetings, thanks, or meta questions about the bot."""
    try:
        return _call_gemini(message, CHITCHAT_PROMPT)
    except Exception:
        return "Hi! I can recommend movies based on ones you've liked, or answer movie questions."


def _call_gemini(message: str, system_prompt: str, max_retries: int = 2) -> str:
    """
    Calls Gemini with a simple retry for rate-limit (429) errors,
    since the free tier allows only a small number of requests per minute.
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0,
                ),
            )
            return response.text.strip()
        except Exception as e:
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and attempt < max_retries:
                wait_time = 15 * (attempt + 1)
                print(f"  (rate limited, waiting {wait_time}s before retry...)")
                time.sleep(wait_time)
                continue
            raise


def _strip_json_fences(raw: str) -> str:
    """Gemini sometimes wraps JSON in markdown code fences despite instructions not to."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


def parse_filter(filter_text: str) -> dict:
    """Turn free text like 'comedy under 2 hours' or 'Bollywood movies' into structured filter fields."""
    empty = {
        "genre": None,
        "max_runtime_minutes": None,
        "min_runtime_minutes": None,
        "min_rating": None,
        "language": None,
        "language_code": None,
    }

    if not filter_text or not filter_text.strip():
        return empty

    try:
        raw = _call_gemini(filter_text, FILTER_PROMPT)
        parsed = json.loads(_strip_json_fences(raw))
        language = parsed.get("language")
        parsed["language_code"] = LANGUAGE_CODES.get(language) if language else None
        # Ensure all expected keys exist even if Gemini omits one
        for key in empty:
            parsed.setdefault(key, None)
        return parsed
    except json.JSONDecodeError:
        return empty


def parse_message(message: str) -> dict:
    """
    Given a raw chat message, extract movie titles mentioned and any
    filter preference, using Gemini for natural language understanding
    instead of brittle regex/keyword matching.
    """
    empty = {"new_titles": [], "filter_text": ""}

    if not message or not message.strip():
        return empty

    try:
        raw = _call_gemini(message, MESSAGE_PARSE_PROMPT)
        parsed = json.loads(_strip_json_fences(raw))
        return {
            "new_titles": parsed.get("new_titles", []) or [],
            "filter_text": parsed.get("filter_text", "") or "",
        }
    except json.JSONDecodeError:
        return empty


if __name__ == "__main__":
    print("--- Testing parse_filter ---")
    tests = [
        "comedy under 2 hours",
        "something scary and short",
        "highly rated sci-fi",
    ]
    for t in tests:
        print(f"'{t}'\n  ->", parse_filter(t), "\n")
        time.sleep(3)  # small gap to stay well under free-tier rate limits

    print("--- Testing parse_message ---")
    message_tests = [
        "I liked Interstellar and Inception",
        "now show me a comedy",
        "I also liked The Hangover",
    ]
    for m in message_tests:
        print(f"'{m}'\n  ->", parse_message(m), "\n")
        time.sleep(3)

    print("--- Testing classify_intent ---")
    intent_tests = [
        "I liked Interstellar and Inception",
        "who directed Inception?",
        "hi there!",
    ]
    for m in intent_tests:
        print(f"'{m}'\n  ->", classify_intent(m), "\n")
        time.sleep(3)

    print("--- Testing answer_general_question ---")
    print(answer_general_question("who directed Inception?"))
