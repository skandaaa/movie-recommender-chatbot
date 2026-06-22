"""
tmdb_client.py
Handles all communication with The Movie Database (TMDB) API.
Docs: https://developer.themoviedb.org/reference/intro/getting-started
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()  # reads variables from .env into the environment

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"


def search_movie(title: str) -> dict | None:
    """
    Search TMDB for a movie by title and return the best-matching result.
    Returns None if nothing is found.
    """
    url = f"{BASE_URL}/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()  # raises an error if the request failed
    results = response.json().get("results", [])

    if not results:
        return None

    return results[0]  # TMDB sorts by relevance, so first result is usually right


def get_recommendations(movie_id: int) -> list[dict]:
    """
    Given a TMDB movie ID, return a list of recommended movies.
    """
    url = f"{BASE_URL}/movie/{movie_id}/recommendations"
    params = {"api_key": TMDB_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get("results", [])


def get_movie_details(movie_id: int) -> dict:
    """
    Given a TMDB movie ID, return full details (runtime, genres, etc.)
    The basic search/recommendations endpoints don't include runtime,
    so we need this extra call when filtering by length.
    """
    url = f"{BASE_URL}/movie/{movie_id}"
    params = {"api_key": TMDB_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_movie_credits(movie_id: int) -> dict:
    """
    Given a TMDB movie ID, return cast and crew.
    Used for the "click for details" feature to show top actors and director.
    """
    url = f"{BASE_URL}/movie/{movie_id}/credits"
    params = {"api_key": TMDB_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def get_movie_videos(movie_id: int) -> list[dict]:
    """
    Given a TMDB movie ID, return trailers/teasers/clips (sourced from YouTube).
    Each item includes a "key" usable as a YouTube video ID.
    """
    url = f"{BASE_URL}/movie/{movie_id}/videos"
    params = {"api_key": TMDB_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get("results", [])


def get_watch_providers(movie_id: int, region: str = "IN") -> dict:
    """
    Given a TMDB movie ID, return streaming/rental/purchase availability
    for the given region (ISO 3166-1 code, defaults to India).
    Data is sourced from JustWatch via TMDB.
    """
    url = f"{BASE_URL}/movie/{movie_id}/watch/providers"
    params = {"api_key": TMDB_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    all_results = response.json().get("results", {})
    return all_results.get(region, {})


def discover_movies(original_language: str | None = None, genre_id: int | None = None,
                     min_rating: float | None = None, sort_by: str = "popularity.desc",
                     page: int = 1) -> list[dict]:
    """
    Use TMDB's discover endpoint to browse movies by language/industry,
    genre, and rating -- used when the user asks for something like
    "recommend Bollywood movies" rather than "movies similar to X".

    original_language uses ISO 639-1 codes, e.g. "hi" for Hindi,
    "ta" for Tamil, "te" for Telugu, "kn" for Kannada, "ml" for Malayalam.
    """
    url = f"{BASE_URL}/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "sort_by": sort_by,
        "page": page,
        "vote_count.gte": 20,  # avoid obscure/low-data results
    }
    if original_language:
        params["with_original_language"] = original_language
    if genre_id:
        params["with_genres"] = genre_id
    if min_rating:
        params["vote_average.gte"] = min_rating

    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get("results", [])


if __name__ == "__main__":
    # Quick manual test: run "python tmdb_client.py" to sanity-check the API key works
    movie = search_movie("Interstellar")
    print("Search result:", movie["title"] if movie else "NOT FOUND")

    if movie:
        recs = get_recommendations(movie["id"])
        print(f"\nFound {len(recs)} recommendations:")
        for r in recs[:5]:
            print(" -", r["title"])

    print("\n--- Testing discover_movies (Hindi) ---")
    hindi_movies = discover_movies(original_language="hi")
    for m in hindi_movies[:5]:
        print(" -", m["title"])
