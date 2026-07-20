#!/usr/bin/env python3
"""
Generate a multi-genre preference profile for the Plex recommendations skill.

Uses the Wikipedia genre mapping to weight genres from the library + watched ratings.
This is the core of v2 — multi-genre recommendations instead of sci-fi only.

Usage: python3 generate_profile.py [--output profiles.json]
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))

def load_genre_mapping():
    """Load the Plex-to-Wikipedia genre mapping."""
    mapping_path = f"{SKILL_DIR}/plex_to_wikipedia_genres.json"
    with open(mapping_path, "r") as f:
        return json.load(f)

def parse_library():
    """Parse movies.xml and return per-movie genre data."""
    movies_file = f"{SKILL_DIR}/cache/movies.xml"
    tree = ET.parse(movies_file)
    root = tree.getroot()
    total = int(root.get("size", 0))

    movies = []
    for video in root.findall(".//Video"):
        title = video.get("title", "Unknown")
        year = video.get("year", "Unknown")
        genres = [g.get("tag", "").strip() for g in video.findall("Genre") if g.get("tag", "").strip()]
        movies.append({"title": title, "year": year, "genres": genres})

    return movies, total

def parse_watched_ratings():
    """Parse watched_movies.txt and return dict of {title: rating}."""
    watched = {}
    watched_file = f"{SKILL_DIR}/watched_movies.txt"
    try:
        with open(watched_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "|" in line:
                    parts = line.split("|")
                    movie_part = parts[0].strip()
                    rating = parts[1].strip().lower()
                    title = movie_part.split(" (")[0].strip()
                    watched[title] = rating
    except FileNotFoundError:
        pass
    return watched

def get_wikipedia_genre(plex_genre, genre_mapping):
    """Get the Wikipedia super-genre for a Plex genre."""
    mapping = genre_mapping["genre_mapping"]
    entry = mapping.get(plex_genre)
    if entry:
        return entry.get("wikipedia_super_genre")
    return None

def build_profile(movies, total, watched, genre_mapping):
    """Build multi-genre preference profile."""

    # 1. Library-based genre weights
    # Count how many movies have each Wikipedia super-genre
    wiki_genre_counts = Counter()
    plex_genre_counts = Counter()

    for movie in movies:
        seen_wiki = set()
        for plex_genre in movie["genres"]:
            plex_genre_counts[plex_genre] += 1
            wiki_genre = get_wikipedia_genre(plex_genre, genre_mapping)
            if wiki_genre and wiki_genre not in seen_wiki:
                wiki_genre_counts[wiki_genre] += 1
                seen_wiki.add(wiki_genre)

    # Base library weights (proportion of library)
    library_weights = {g: c / total for g, c in wiki_genre_counts.items()}

    # 2. Rating-based adjustments
    # Parse per-movie wiki genres to find which movies user watched
    movie_genres_by_title = {}
    for movie in movies:
        seen_wiki = set()
        for plex_genre in movie["genres"]:
            wiki_genre = get_wikipedia_genre(plex_genre, genre_mapping)
            if wiki_genre and wiki_genre not in seen_wiki:
                seen_wiki.add(wiki_genre)
        movie_genres_by_title[movie["title"]] = seen_wiki

    rating_adjustments = defaultdict(float)
    for title, rating in watched.items():
        wiki_genres = movie_genres_by_title.get(title, set())
        if rating == "liked":
            for w in wiki_genres:
                rating_adjustments[w] += 2.0  # boost liked genres
        elif rating == "meh":
            for w in wiki_genres:
                rating_adjustments[w] += 0.5  # slight preference
        elif rating == "disliked":
            for w in wiki_genres:
                rating_adjustments[w] -= 1.0  # demote disliked genres
        elif rating == "couldnt_finish":
            for w in wiki_genres:
                rating_adjustments[w] -= 2.0  # strongly demote

    # 3. Final weights: library base + rating adjustments normalized
    final_weights = {}
    for genre, base in library_weights.items():
        adjusted = base + rating_adjustments.get(genre, 0) / total
        final_weights[genre] = max(0.001, adjusted)  # floor to avoid zero

    # Sort by weight descending
    sorted_weights = dict(sorted(final_weights.items(), key=lambda x: x[1], reverse=True))

    # 4. Also track which Wikipedia genres map to which Plex genres for search queries
    wiki_to_plex = defaultdict(set)
    for plex_genre, data in genre_mapping["genre_mapping"].items():
        wiki = data.get("wikipedia_super_genre")
        if wiki:
            wiki_to_plex[wiki].add(plex_genre)

    return {
        "version": "2.0",
        "generated_from": "Plex library (cache/movies.xml) + watched_ratings",
        "total_movies_analyzed": total,
        "library_weights": {k: round(v, 4) for k, v in sorted_weights.items()},
        "top_genres": list(sorted_weights.keys())[:15],
        "rating_adjustments": {k: round(v, 4) for k, v in sorted(rating_adjustments.items(), key=lambda x: x[1], reverse=True)},
        "wiki_to_plex_genres": {k: sorted(v) for k, v in wiki_to_plex.items()},
        "watched_count": len(watched),
        "watched_ratings": watched,
        "genre_mapping_summary": genre_mapping["summary_by_super_genre"],
    }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate multi-genre Plex preference profile")
    parser.add_argument("--output", default=f"{SKILL_DIR}/profiles.json", help="Output JSON file")
    args = parser.parse_args()

    print("Loading genre mapping...")
    genre_mapping = load_genre_mapping()

    print("Parsing library...")
    movies, total = parse_library()
    print(f"  {total} movies parsed")

    print("Parsing watched ratings...")
    watched = parse_watched_ratings()
    print(f"  {len(watched)} watched entries")

    print("Building preference profile...")
    profile = build_profile(movies, total, watched, genre_mapping)

    # Write output
    with open(args.output, "w") as f:
        json.dump(profile, f, indent=2)

    print(f"\nProfile written to: {args.output}")

    # Print top genres
    print(f"\n=== Top Genres by Preference Weight ===")
    for i, (genre, weight) in enumerate(profile["library_weights"].items()):
        bar = "█" * int(weight * 200)
        print(f"  {i+1:2}. {genre:20s} {weight:.4f}  {bar}")

    # Print rating adjustments
    if profile["rating_adjustments"]:
        print(f"\n=== Rating Adjustments ===")
        for genre, adj in profile["rating_adjustments"].items():
            print(f"  {genre}: {adj:+.4f}")

    # Print watched summary
    print(f"\n=== Watched Summary ({len(watched)} entries) ===")
    ratings_summary = Counter(watched.values())
    for rating, count in ratings_summary.most_common():
        print(f"  {rating}: {count}")

if __name__ == "__main__":
    main()
