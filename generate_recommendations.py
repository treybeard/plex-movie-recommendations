#!/usr/bin/env python3
"""
v2 Recommendation Engine — generates cross-genre movie recommendations
based on the user's Plex library profile.

Usage: python3 generate_recommendations.py [--count 10] [--output results.json]
"""
import json
import sys
import os
import xml.etree.ElementTree as ET

# Add skill dir to path so we can import our helpers
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

def web_search(query, limit=5):
    """Search the web for movie recommendations."""
    from hermes_tools import web_search as _ws
    return _ws(query, limit=limit)

def load_profile():
    """Load the preference profile."""
    profile_path = os.path.join(SKILL_DIR, "profiles.json")
    with open(profile_path, "r") as f:
        return json.load(f)

def get_library_titles():
    """Get all titles currently in the Plex library."""
    titles = set()
    movies_file = os.path.join(SKILL_DIR, "cache", "movies.xml")
    try:
        tree = ET.parse(movies_file)
        root = tree.getroot()
        for video in root.findall(".//Video"):
            title = video.get("title", "")
            titles.add(title.lower())
    except FileNotFoundError:
        pass
    tv_file = os.path.join(SKILL_DIR, "cache", "tv.xml")
    try:
        tree = ET.parse(tv_file)
        root = tree.getroot()
        for video in root.findall(".//Video"):
            title = video.get("title", "")
            titles.add(title.lower())
    except FileNotFoundError:
        pass
    return titles

def parse_watched_movies():
    """Get watched movie titles."""
    watched = set()
    watched_file = os.path.join(SKILL_DIR, "watched_movies.txt")
    try:
        with open(watched_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    title = line.split(" (")[0].strip()
                    watched.add(title.lower())
    except FileNotFoundError:
        pass
    return watched

def search_recommendations_for_genre(top_genre, count_needed, excluded_titles):
    """
    Search for highly-rated movies in a specific genre.
    Returns list of candidate dicts.
    """
    candidates = []
    
    # Build search queries for this genre
    queries = [
        f"best {top_genre} movies 2023 2024 2025 2026 highly rated",
        f"top {top_genre} films critics choice must watch",
        f"highest rated {top_genre} movies not mainstream",
    ]
    
    seen = set()
    for query in queries:
        if len(candidates) >= count_needed:
            break
        try:
            results = web_search(query, limit=10)
            for item in results.get("data", {}).get("web", []):
                title = item.get("title", "")
                # Extract just the movie title
                # Remove extra text like " - IMDB", " - Rotten Tomatoes", etc.
                if " - " in title:
                    title = title.split(" - ")[0].strip()
                if " (" in title:
                    title = title.split(" (")[0].strip()
                
                if not title:
                    continue
                title_lower = title.lower()
                if title_lower in seen:
                    continue
                seen.add(title_lower)
                
                # Filter: skip if in library or watched
                if title_lower in excluded_titles:
                    continue
                
                description = item.get("description", "")
                url = item.get("url", "")
                
                # Try to extract year from title or description
                year = ""
                for part in title.split(" ("):
                    part = part.strip().rstrip(")")
                    if part.isdigit() and len(part) <= 4:
                        year = part
                        break
                if not year:
                    for match in [c for c in description.split() if c.isdigit() and len(c) == 4 and 1950 <= int(c) <= 2027]:
                        year = match
                        break
                
                candidates.append({
                    "title": title,
                    "year": year,
                    "genre": top_genre,
                    "source": url,
                    "description": description[:300],
                    "score": 0,  # calculated below
                })
        except Exception as e:
            print(f"  Search error for '{query}': {e}", file=sys.stderr)
    
    return candidates

def score_candidates(candidates, profile):
    """Score candidates based on how well they match the user's genre preferences."""
    # Normalize genre weights for scoring
    max_weight = max(profile["library_weights"].values()) if profile["library_weights"] else 1.0
    normalized_weights = {k: v / max_weight for k, v in profile["library_weights"].items()}
    
    genre = profile["top_genres"][0] if profile["top_genres"] else "Action"
    
    for c in candidates:
        # Base score from genre weight
        c["score"] = normalized_weights.get(c["genre"], 0.1)
        
        # Bonus for newer movies (more recent = better match for what user might have missed)
        if c["year"]:
            try:
                year_int = int(c["year"])
                recency = max(0, (2026 - year_int) / 100)
                c["score"] += recency * 0.1
            except ValueError:
                pass
    
    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

def filter_excluded(candidates, excluded_titles):
    """Remove candidates that are in the excluded set."""
    return [c for c in candidates if c["title"].lower() not in excluded_titles]

def deduplicate(candidates):
    """Remove duplicate titles."""
    seen = set()
    unique = []
    for c in candidates:
        title_key = c["title"].lower()
        if title_key not in seen:
            seen.add(title_key)
            unique.append(c)
    return unique

def generate_reason(movie, profile, library_titles):
    """Generate a personalized reason why the user might like this movie."""
    genre = movie.get("genre", "Action")
    reason_parts = []
    
    # Library composition reason
    genre_count = sum(1 for t in library_titles if t)
    if genre in profile["library_weights"]:
        pct = profile["library_weights"][genre] * 100
        reason_parts.append(f"Your library has strong {genre} content ({pct:.0f}% of your collection)")
    
    # Add subgenre reasons based on watched ratings
    watched = profile.get("watched_ratings", {})
    if watched:
        liked_genres = set()
        for title, rating in watched.items():
            if rating == "liked":
                # Find which genres this watched title belongs to
                for title_lower in library_titles:
                    if title.lower() in title_lower:
                        # We'd need per-title genre info; skip for now
                        pass
    
    if reason_parts:
        return " — " + " ".join(reason_parts[:2])
    return f" — a highly-rated {genre} film"

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate cross-genre Plex recommendations")
    parser.add_argument("--count", type=int, default=10, help="Number of recommendations")
    parser.add_argument("--profile", default=os.path.join(SKILL_DIR, "profiles.json"))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    
    print(f"Loading profile: {args.profile}")
    profile = load_profile()
    
    print("Loading library titles...")
    library_titles = get_library_titles()
    print(f"  {len(library_titles)} titles in library")
    
    print("Loading watched movies...")
    watched_titles = parse_watched_movies()
    print(f"  {len(watched_titles)} watched titles")
    
    # Combined exclusion set
    excluded = library_titles | watched_titles
    
    top_genres = profile.get("top_genres", [])[:6]  # Top 6 genres
    print(f"\nTop genres: {top_genres}")
    print(f"Generating {args.count} recommendations...")
    
    # Calculate candidates per genre
    candidates_per_genre = max(1, args.count // len(top_genres))
    all_candidates = []
    
    for genre in top_genres:
        print(f"  Searching {genre}...")
        genre_candidates = search_recommendations_for_genre(genre, candidates_per_genre + 3, excluded)
        all_candidates.extend(genre_candidates)
    
    # Score, filter, and deduplicate
    score_candidates(all_candidates, profile)
    all_candidates = filter_excluded(all_candidates, excluded)
    all_candidates = deduplicate(all_candidates)
    
    # Take top N
    top_candidates = all_candidates[:args.count]
    
    # Build final recommendations with reasons
    recommendations = []
    for i, movie in enumerate(top_candidates):
        candidate_genre = movie.get("genre", "Action")
        # Get some library titles that match this genre for personalization
        matching_library = []
        movies_file = os.path.join(SKILL_DIR, "cache", "movies.xml")
        try:
            tree = ET.parse(movies_file)
            root = tree.getroot()
            for video in root.findall(".//Video"):
                title = video.get("title", "")
                vgenres = [g.get("tag", "") for g in video.findall("Genre")]
                # Check if this movie's genres match the candidate's genre
                for g in vgenres:
                    if g.lower() == candidate_genre.lower() or candidate_genre.lower() in g.lower():
                        matching_library.append(title)
                        if len(matching_library) >= 2:
                            break
                if len(matching_library) >= 2:
                    break
        except Exception:
            pass
        
        if not matching_library:
            matching_library = ["several {} films".format(candidate_genre.lower())]
        
        description = movie.get("description", "")
        year = movie.get("year", "")
        title = movie["title"]
        
        if year:
            full_title = "{} ({})".format(title, year)
        else:
            full_title = title
        
        recommendations.append({
            "rank": i + 1,
            "title": full_title,
            "genre": candidate_genre,
            "year": year,
            "description": description[:250],
            "why_you_might_like_it": "You have strong {} content in your library. ".format(candidate_genre)
                                     + "You also enjoy {}".format(', '.join(matching_library[:2])),
        })
    
    # Output
    result = {
        "genre_weights": dict(list(profile.get("library_weights", {}).items())[:10]),
        "top_genres": profile.get("top_genres", [])[:10],
        "recommendations": recommendations,
        "total_found": len(all_candidates),
        "total_shown": len(recommendations),
    }
    
    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults written to: {args.output}")
    else:
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
