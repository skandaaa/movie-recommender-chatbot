"""
main.py
FastAPI app — combines TMDB recommendations + Gemini-powered filtering.
Run with: uvicorn main:app --reload
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

import tmdb_client
import llm_client

app = FastAPI(title="Movie Recommender API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RecommendRequest(BaseModel):
    titles: list[str]          # e.g. ["Interstellar", "Inception"]
    filter_text: Optional[str] = None  # e.g. "comedy under 2 hours"


class ChatRequest(BaseModel):
    message: str               # raw user message, e.g. "I also liked The Hangover"
    known_titles: list[str] = []  # titles already accumulated in this conversation


def apply_filters(movies: list[dict], filters: dict) -> list[dict]:
    """
    Given a list of movies and parsed filters, fetch full details for
    each and return only those that pass all active filter constraints.
    """
    genre = filters.get("genre")
    max_runtime = filters.get("max_runtime_minutes")
    min_runtime = filters.get("min_runtime_minutes")
    min_rating = filters.get("min_rating")
    language_code = filters.get("language_code")

    # If no filters are active at all, skip the extra TMDB detail calls
    if not any([genre, max_runtime, min_runtime, min_rating, language_code]):
        return movies

    filtered = []
    for movie in movies:
        try:
            details = tmdb_client.get_movie_details(movie["id"])
        except Exception:
            continue  # skip movies where the detail call fails

        # --- Rating filter ---
        if min_rating is not None:
            if details.get("vote_average", 0) < min_rating:
                continue

        # --- Runtime filters ---
        runtime = details.get("runtime")  # in minutes, can be None
        if max_runtime is not None:
            if runtime is None or runtime > max_runtime:
                continue
        if min_runtime is not None:
            if runtime is None or runtime < min_runtime:
                continue

        # --- Language / industry filter ---
        if language_code is not None:
            if details.get("original_language") != language_code:
                continue

        # --- Genre filter ---
        if genre is not None:
            movie_genres = [g["name"] for g in details.get("genres", [])]
            if genre not in movie_genres:
                continue

        filtered.append(movie)

    return filtered


@app.get("/")
def root():
    return {"status": "ok", "message": "Movie Recommender API is running"}


@app.post("/recommend")
def recommend(request: RecommendRequest):
    """
    1. Search TMDB for each liked title and fetch recommendations.
    2. Merge + deduplicate across all liked titles.
    3. If filter_text provided, parse it with Gemini and filter the list.
    4. Return final recommendations.
    """
    if not request.titles:
        raise HTTPException(status_code=400, detail="Provide at least one movie title.")

    # --- Step 1 & 2: Fetch and merge recommendations ---
    all_recommendations = {}
    not_found = []

    for title in request.titles:
        movie = tmdb_client.search_movie(title)
        if movie is None:
            not_found.append(title)
            continue

        recs = tmdb_client.get_recommendations(movie["id"])
        for rec in recs:
            all_recommendations[rec["id"]] = {
                "id": rec["id"],
                "title": rec["title"],
                "overview": rec.get("overview"),
                "release_date": rec.get("release_date"),
                "vote_average": rec.get("vote_average"),
                "poster_path": rec.get("poster_path"),
            }

    if not all_recommendations and not_found:
        raise HTTPException(
            status_code=404,
            detail=f"Could not find any of these on TMDB: {not_found}",
        )

    movies = list(all_recommendations.values())

    # --- Step 3: Parse filter text and apply filters ---
    filters = llm_client.parse_filter(request.filter_text or "")
    filtered_movies = apply_filters(movies, filters)

    return {
        "recommendations": filtered_movies,
        "total": len(filtered_movies),
        "filters_applied": filters,
        "not_found": not_found,
    }


@app.get("/movie/{movie_id}")
def movie_details(movie_id: int):
    """
    Fetch full details + top cast for a single movie, used by the
    frontend's click-for-details modal.
    """
    try:
        details = tmdb_client.get_movie_details(movie_id)
        credits = tmdb_client.get_movie_credits(movie_id)
        videos = tmdb_client.get_movie_videos(movie_id)
        providers = tmdb_client.get_watch_providers(movie_id, region="IN")
    except Exception:
        raise HTTPException(status_code=404, detail="Could not fetch movie details.")

    cast = credits.get("cast", [])[:6]  # top 6 billed actors
    director = next(
        (c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"),
        None,
    )

    # Prefer an official YouTube trailer; fall back to any YouTube video if no trailer tagged
    trailer = next(
        (v for v in videos if v.get("site") == "YouTube" and v.get("type") == "Trailer"),
        None,
    ) or next((v for v in videos if v.get("site") == "YouTube"), None)

    # Combine subscription (flatrate), rental, and purchase options into one list
    watch_options = []
    for category in ("flatrate", "rent", "buy"):
        for p in providers.get(category, []):
            watch_options.append({
                "provider_name": p.get("provider_name"),
                "logo_path": p.get("logo_path"),
                "type": {"flatrate": "Stream", "rent": "Rent", "buy": "Buy"}[category],
            })

    return {
        "id": details.get("id"),
        "title": details.get("title"),
        "overview": details.get("overview"),
        "release_date": details.get("release_date"),
        "runtime": details.get("runtime"),
        "vote_average": details.get("vote_average"),
        "poster_path": details.get("poster_path"),
        "genres": [g["name"] for g in details.get("genres", [])],
        "director": director,
        "cast": [{"name": c["name"], "character": c.get("character")} for c in cast],
        "tmdb_url": f"https://www.themoviedb.org/movie/{movie_id}",
        "trailer_key": trailer.get("key") if trailer else None,
        "watch_options": watch_options,
        "watch_link": providers.get("link"),  # TMDB's own "where to watch" page for this region
    }


def get_recommendations_for_titles(titles: list[str]):
    """Shared logic: search + merge + dedupe recommendations for a list of titles."""
    all_recommendations = {}
    not_found = []

    for title in titles:
        movie = tmdb_client.search_movie(title)
        if movie is None:
            not_found.append(title)
            continue

        recs = tmdb_client.get_recommendations(movie["id"])
        for rec in recs:
            all_recommendations[rec["id"]] = {
                "id": rec["id"],
                "title": rec["title"],
                "overview": rec.get("overview"),
                "release_date": rec.get("release_date"),
                "vote_average": rec.get("vote_average"),
                "poster_path": rec.get("poster_path"),
            }

    return list(all_recommendations.values()), not_found


@app.post("/chat")
def chat(request: ChatRequest):
    """
    Main chat endpoint, now intent-aware:
    1. Classify the message: recommend / movie_question / chitchat.
    2. "movie_question" and "chitchat" get a direct text answer from Gemini,
       no TMDB calls needed.
    3. "recommend" follows the original pipeline: extract titles + filter,
       merge with known_titles, fetch TMDB recommendations, apply filters.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    intent = llm_client.classify_intent(request.message)

    # --- Chitchat: greetings, thanks, "what can you do" ---
    if intent == "chitchat":
        reply = llm_client.answer_chitchat(request.message)
        return {
            "reply_type": "text",
            "text": reply,
            "recommendations": [],
            "total": 0,
            "filters_applied": {},
            "not_found": [],
            "known_titles": request.known_titles,
            "needs_titles": False,
        }

    # --- Movie question: trivia, opinions, factual lookups ---
    if intent == "movie_question":
        reply = llm_client.answer_general_question(request.message)
        return {
            "reply_type": "text",
            "text": reply,
            "recommendations": [],
            "total": 0,
            "filters_applied": {},
            "not_found": [],
            "known_titles": request.known_titles,
            "needs_titles": False,
        }

    # --- Movie lookup: user named one specific movie, wants its detail card ---
    if intent == "movie_lookup":
        title = llm_client.extract_movie_title(request.message)
        movie = tmdb_client.search_movie(title)

        if movie is None:
            return {
                "reply_type": "text",
                "text": f"I couldn't find a movie called \"{title}\". Could you check the spelling?",
                "recommendations": [],
                "total": 0,
                "filters_applied": {},
                "not_found": [title],
                "known_titles": request.known_titles,
                "needs_titles": False,
            }

        return {
            "reply_type": "movie_lookup",
            "text": f"Here's what I found for {movie['title']}:",
            "recommendations": [],
            "total": 0,
            "filters_applied": {},
            "not_found": [],
            "known_titles": request.known_titles,
            "needs_titles": False,
            "lookup_movie_id": movie["id"],
        }

    # --- Recommend: the original pipeline ---
    parsed = llm_client.parse_message(request.message)
    new_titles = parsed["new_titles"]
    filter_text = parsed["filter_text"]

    known_lower = {t.lower() for t in request.known_titles}
    merged_titles = list(request.known_titles) + [
        t for t in new_titles if t.lower() not in known_lower
    ]

    if not merged_titles:
        # No liked movies yet -- but if the message specifies a language/industry
        # or genre (e.g. "recommend Bollywood movies"), we can still use TMDB's
        # discover endpoint directly instead of requiring a reference movie first.
        filters = llm_client.parse_filter(filter_text)
        language_code = filters.get("language_code")
        genre_name = filters.get("genre")

        if language_code or genre_name:
            genre_id = None
            if genre_name:
                genre_id = next(
                    (gid for gid, name in llm_client.TMDB_GENRES.items() if name == genre_name),
                    None,
                )

            discovered = tmdb_client.discover_movies(
                original_language=language_code,
                genre_id=genre_id,
                min_rating=filters.get("min_rating"),
            )
            movies = [
                {
                    "id": m["id"],
                    "title": m["title"],
                    "overview": m.get("overview"),
                    "release_date": m.get("release_date"),
                    "vote_average": m.get("vote_average"),
                    "poster_path": m.get("poster_path"),
                }
                for m in discovered
            ]
            # Runtime filters still need the detail call, so route through apply_filters
            filtered_movies = apply_filters(movies, filters)

            return {
                "reply_type": "recommendations",
                "text": "",
                "recommendations": filtered_movies,
                "total": len(filtered_movies),
                "filters_applied": filters,
                "not_found": [],
                "known_titles": [],
                "needs_titles": False,
            }

        return {
            "reply_type": "text",
            "text": "I don't have any movies to base recommendations on yet. Tell me something you liked!",
            "recommendations": [],
            "total": 0,
            "filters_applied": {},
            "not_found": [],
            "known_titles": [],
            "needs_titles": True,
        }

    movies, not_found = get_recommendations_for_titles(merged_titles)

    if not movies and not_found:
        return {
            "reply_type": "recommendations",
            "text": "",
            "recommendations": [],
            "total": 0,
            "filters_applied": {},
            "not_found": not_found,
            "known_titles": merged_titles,
            "needs_titles": False,
        }

    filters = llm_client.parse_filter(filter_text)
    filtered_movies = apply_filters(movies, filters)

    return {
        "reply_type": "recommendations",
        "text": "",
        "recommendations": filtered_movies,
        "total": len(filtered_movies),
        "filters_applied": filters,
        "not_found": not_found,
        "known_titles": merged_titles,
        "needs_titles": False,
    }
