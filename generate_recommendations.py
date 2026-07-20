#!/usr/bin/env python3
"""
v2 Recommendation Engine — generates cross-genre or genre-specific movie recommendations.

Usage:
  python3 generate_recommendations.py [--count 10] [--genre ACTION] [--output results.json]

Modes:
  --genre ACTION   Search only within Action and its subgenres
  --genre          (omitted)          Search across all genres weighted by profile

Portable: all paths resolve relative to this script's location via os.path.dirname.
When run inside the Hermes agent, web_search is available automatically.
When run standalone, it logs the profile/genres but cannot perform web searches.
"""
import json
import sys
import os
import xml.etree.ElementTree as ET

# Resolve paths relative to this script — portable across machines
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
DVDS_CACHE = os.path.join(SKILL_DIR, "cache", "dvds_releases.json")


def web_search(query, limit=5):
    """Search the web for movie recommendations.
    
    Uses the agent's built-in web_search tool when available.
    Falls back gracefully when run standalone (returns empty results with a warning).
    """
    try:
        from hermes_tools import web_search as _ws
        return _ws(query, limit=limit)
    except ImportError:
        # Running standalone outside the agent — log a warning and return empty
        print(f"  [INFO] hermes_tools not available (web_search unavailable); skipping search for: {query}", file=sys.stderr)
        return {"data": {"web": []}}

def load_profile():
    """Load the preference profile."""
    profile_path = os.path.join(SKILL_DIR, "profiles.json")
    with open(profile_path, "r") as f:
        return json.load(f)

def load_genre_mapping():
    """Load the Plex-to-Wikipedia genre mapping."""
    mapping_path = os.path.join(SKILL_DIR, "plex_to_wikipedia_genres.json")
    with open(mapping_path, "r") as f:
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

def get_genre_subgenres(target_genre, genre_mapping):
    """
    Get all Wikipedia subgenres for a target genre.
    Returns list of subgenre strings.
    """
    summary = genre_mapping.get("summary_by_super_genre", {})
    
    target_lower = target_genre.lower()
    subgenres = []
    for super_key, data in summary.items():
        if super_key.lower() == target_lower:
            # Get all Plex genres mapped to this super-genre
            plex_genres = data.get("plex_genres", [])
            # Also get the wikipedia_genres field
            wg = data.get("wikipedia_genres", [])
            subgenres.extend(wg)
            subgenres.extend(plex_genres)
            break
    
    # Also check the mapping directly
    for plex_genre, entry in genre_mapping.get("genre_mapping", {}).items():
        if entry.get("wikipedia_super_genre", "").lower() == target_lower:
            if entry.get("wikipedia_genre") and entry["wikipedia_genre"] not in subgenres:
                subgenres.append(entry["wikipedia_genre"])
    
    return list(set(subgenres))

def search_recommendations_for_genre(target_genre, count_needed, excluded_titles):
    """
    Search for highly-rated movies in a specific genre.
    Returns list of candidate dicts.
    """
    candidates = []
    target_lower = target_genre.lower()
    
    # Build search queries
    queries = [
        f"best {target_genre} movies 2023 2024 2025 2026 highly rated",
        f"top {target_genre} films critics choice must watch",
        f"highest rated {target_genre} movies not mainstream",
    ]
    
    # Also search subgenres
    subgenres = get_genre_subgenres(target_genre, load_genre_mapping())
    for subgenre in subgenres[:3]:
        sub_lower = subgenre.lower()
        if sub_lower != target_lower:
            queries.append(f"best {subgenre} movies 2024 2025 highly rated")
    
    seen = set()
    for query in queries:
        if len(candidates) >= count_needed:
            break
        try:
            results = web_search(query, limit=10)
            for item in results.get("data", {}).get("web", []):
                title = item.get("title", "")
                # Extract just the movie title
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
                
                # Try to extract year from title
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
                    "genre": target_genre,
                    "source": url,
                    "description": description[:300],
                    "score": 0,
                })
        except Exception as e:
            print(f"  Search error for '{query}': {e}", file=sys.stderr)
    
    return candidates

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

def get_matching_library_titles(target_genre, genre_mapping):
    """Find library titles that match this genre."""
    summary = genre_mapping.get("summary_by_super_genre", {})
    
    target_lower = target_genre.lower()
    matching = []
    for super_key, data in summary.items():
        if super_key.lower() == target_lower:
            matching.extend(data.get("plex_genres", []))
            break
    
    # Search library for these genres
    movies_file = os.path.join(SKILL_DIR, "cache", "movies.xml")
    try:
        tree = ET.parse(movies_file)
        root = tree.getroot()
        for video in root.findall(".//Video"):
            title = video.get("title", "")
            vgenres = [g.get("tag", "") for g in video.findall("Genre")]
            # Check if any genre matches
            for g in vgenres:
                for mapped_genre in matching:
                    if mapped_genre.lower() == g.lower() or mapped_genre.lower() in g.lower():
                        matching.append(title)
                        break
    except Exception:
        pass
    
    # Deduplicate and limit
    matching = list(set(matching))[:3]
    return matching


def load_dvds_releases():
    """
    Load dvds_releases.json cache or scrape if missing/stale.
    Returns list of movie dicts with title, imdb, mpaa, genres.
    """
    cache_path = os.path.join(SKILL_DIR, "cache", "dvds_releases.json")
    
    # Check if cache exists and is less than 7 days old
    if os.path.exists(cache_path):
        import time
        file_age = time.time() - os.path.getmtime(cache_path)
        if file_age < 7 * 86400:  # 7 days
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                # Use merged_releases if available, otherwise fall back to old format
                if "merged_releases" in data:
                    movies = data["merged_releases"]
                    print(f"  Loaded {len(movies)} movies from dvds_releases cache", file=sys.stderr)
                    return movies
                else:
                    # Old format with separate lists
                    movies = data.get("digital_releases", []) + data.get("dvd_releases", [])
                    print(f"  Loaded {len(movies)} movies from dvds_releases cache (legacy format)", file=sys.stderr)
                    return movies
            except (json.JSONDecodeError, FileNotFoundError):
                pass
    
    # Cache missing or stale - scrape fresh data
    print("  No valid cache found, scraping dvdsreleasedates.com...", file=sys.stderr)
    
    # Import the scraper module (portable)
    scraper_path = os.path.join(SKILL_DIR, "scrape_dvds_releases.py")
    if not os.path.exists(scraper_path):
        print("  [WARN] scrape_dvds_releases.py not found, skipping dvds source", file=sys.stderr)
        return []
    
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("scraper", scraper_path)
        scraper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scraper)
        
        # Run the scraper
        digital = scraper.scrape_digital_releases()
        dvd = scraper.scrape_dvd_releases()
        merged = scraper.merge_digital_and_dvd(digital, dvd)
        
        # Save cache
        cache_data = {
            "source": "dvdsreleasedates.com",
            "merged_releases": merged,
            "digital_count": len(digital),
            "dvd_count": len(dvd),
            "merged_count": len(merged),
        }
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(cache_data, f, indent=2)
        
        print(f"  Cached {len(merged)} dvds releases with genre data", file=sys.stderr)
        return merged
    except Exception as e:
        print(f"  [WARN] Failed to scrape dvds releases: {e}", file=sys.stderr)
        return []


def get_dvds_release_candidates(genre_filter=None, count_needed=10, excluded_titles=None):
    """
    Get candidate movies from dvdsreleasedates.com cache.
    
    Uses actual genre data scraped from dvdsreleasedates.com genre pages.
    If genre_filter is provided, filters to movies that match that genre.
    
    Returns list of candidate dicts.
    """
    if excluded_titles is None:
        excluded_titles = set()
    
    movies = load_dvds_releases()
    candidates = []
    
    for movie in movies:
        title = movie.get("title", "").strip()
        if not title:
            continue
        
        # Filter out concerts, documentaries, non-movies
        title_lower = title.lower()
        exclude_terms = ["concert", "tour", "music", "video", "talk show", "news",
                        "sports", "anime", "series", "documentary", "epic", "billie",
                        "the weeknd", "beyonce", "adele", "artist", "tribute",
                        "losers", "winners"]
        if any(term in title_lower for term in exclude_terms):
            continue
        
        title_lower = title.lower()
        
        # Filter excluded
        if title_lower in excluded_titles:
            continue
        
        imdb = movie.get("imdb", "")
        mpaa = movie.get("mpaa", "")
        movie_genres = movie.get("genres", [])
        
        # Genre filtering: use actual genre data from scraper
        if genre_filter:
            genre_filter_lower = genre_filter.lower()
            # Check if movie's genres match the requested genre
            matching_genres = [g for g in movie_genres if genre_filter_lower in g.lower()]
            
            if not matching_genres:
                # No genre match, skip this movie
                continue
            
            # Use the matched genres for the candidate
            genre = matching_genres[0].title()
        else:
            # No genre filter - use first available genre or "New Release"
            genre = movie_genres[0].title() if movie_genres else "New Release"
        
        # Determine year from title or use current year
        year = ""
        for part in title.split(" "):
            part = part.strip().rstrip(")").lstrip("(")
            if part.isdigit() and 1950 <= int(part) <= 2027:
                year = part
                break
        if not year:
            year = "2026"
        
        # Score: higher IMDb = higher score
        score = 0.5  # Base score for being a recent release
        if imdb:
            try:
                imdb_float = float(imdb)
                # Scale IMDb 1-10 to 0-1 score
                score += (imdb_float / 10.0) * 0.5
            except ValueError:
                pass
        
        # Bonus for highly-rated releases
        if imdb:
            try:
                if float(imdb) >= 7.0:
                    score += 0.3
                elif float(imdb) >= 6.5:
                    score += 0.2
            except ValueError:
                pass
        
        candidates.append({
            "title": title,
            "year": year,
            "genre": genre,
            "source": "dvdsreleasedates.com",
            "description": f"New release | IMDb: {imdb} | {mpaa} | Genre: {', '.join(movie_genres)}" if movie_genres else f"New release | IMDb: {imdb} | {mpaa}",
            "score": score,
            "imdb": imdb,
            "mpaa": mpaa,
            "genres": movie_genres,
        })
    
    # Sort by score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    return candidates[:count_needed * 2]  # Return extra to allow filtering

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Plex movie recommendations")
    parser.add_argument("--count", type=int, default=10, help="Number of recommendations")
    parser.add_argument("--genre", type=str, default=None, help="Filter to specific genre (e.g. Horror, Action, Comedy)")
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
    
    # Load genre mapping
    genre_mapping = load_genre_mapping()
    
    # Initialize for output (will be set in both branches)
    recommendations = []
    final_candidates = []
    
    # Determine which genres to search
    if args.genre:
        # SPECIFIC GENRE MODE
        target_genre = args.genre.title()
        print(f"\nMode: Specific genre — {target_genre}")
        
        # Get subgenres
        subgenres = get_genre_subgenres(target_genre, genre_mapping)
        print(f"  Target genre: {target_genre}")
        if subgenres:
            print(f"  Subgenres: {', '.join(subgenres[:5])}")
        
        # Search this genre
        candidates = search_recommendations_for_genre(target_genre, args.count + 5, excluded)
        
        # Also add dvds releases as candidates
        dvds_candidates = get_dvds_release_candidates(
            genre_filter=target_genre, 
            count_needed=args.count + 5, 
            excluded_titles=excluded
        )
        # Mark dvds candidates with the target genre
        for c in dvds_candidates:
            c["genre"] = target_genre
        
        # Merge: web search candidates first, then dvds
        candidates.extend(dvds_candidates)
        candidates = filter_excluded(candidates, excluded)
        candidates = deduplicate(candidates)
        
        # Score by genre weight
        weight = profile["library_weights"].get(target_genre, 0.1)
        for c in candidates:
            c["score"] = weight
        
        # Take top N
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = candidates[:args.count]
        final_candidates = candidates
        
        # Build recommendations
        recommendations = []
        for i, movie in enumerate(top_candidates):
            matching_library = get_matching_library_titles(target_genre, genre_mapping)
            
            year = movie.get("year", "")
            title = movie["title"]
            full_title = "{} ({})".format(title, year) if year else title
            
            recommendations.append({
                "rank": i + 1,
                "title": full_title,
                "genre": target_genre,
                "year": year,
                "description": movie.get("description", "")[:250],
                "why_you_might_like_it": "Your library has {}% {} content. ".format(
                    round(weight * 100, 0), target_genre.lower()) +
                    ("Also from your collection: {}".format(", ".join(matching_library[:2])) if matching_library else ""),
            })
        
    else:
        # CROSS-GENRE MODE (default v2 behavior)
        top_genres = profile.get("top_genres", [])[:6]
        print(f"\nMode: Cross-genre — searching all top genres")
        print(f"  Top genres: {', '.join(top_genres[:6])}")
        
        candidates_per_genre = max(1, args.count // len(top_genres))
        all_candidates = []
        
        for genre in top_genres:
            print(f"  Searching {genre}...")
            genre_candidates = search_recommendations_for_genre(genre, candidates_per_genre + 3, excluded)
            all_candidates.extend(genre_candidates)
        
        # Also add dvds releases as cross-genre candidates
        print("  Checking dvds releases...")
        dvds_candidates = get_dvds_release_candidates(
            count_needed=args.count + 5, 
            excluded_titles=excluded
        )
        # Assign dvds candidates to the highest-weight genre
        if dvds_candidates and top_genres:
            best_genre = top_genres[0]  # Action typically
            for c in dvds_candidates:
                c["genre"] = best_genre
        all_candidates.extend(dvds_candidates)
        
        # Score candidates by genre weight
        max_weight = max(profile["library_weights"].values()) if profile["library_weights"] else 1.0
        normalized_weights = {k: v / max_weight for k, v in profile["library_weights"].items()}
        
        for c in all_candidates:
            c["score"] = normalized_weights.get(c["genre"], 0.1)
            # Bonus for newer movies
            if c["year"]:
                try:
                    year_int = int(c["year"])
                    recency = max(0, (2026 - year_int) / 100)
                    c["score"] += recency * 0.1
                except ValueError:
                    pass
        
        # Sort, filter, deduplicate
        all_candidates.sort(key=lambda x: x["score"], reverse=True)
        all_candidates = filter_excluded(all_candidates, excluded)
        all_candidates = deduplicate(all_candidates)
        top_candidates = all_candidates[:args.count]
        final_candidates = all_candidates
        
        # Build recommendations
        recommendations = []
        for i, movie in enumerate(top_candidates):
            candidate_genre = movie.get("genre", "Action")
            matching_library = get_matching_library_titles(candidate_genre, genre_mapping)
            
            year = movie.get("year", "")
            title = movie["title"]
            full_title = "{} ({})".format(title, year) if year else title
            
            recommendations.append({
                "rank": i + 1,
                "title": full_title,
                "genre": candidate_genre,
                "year": year,
                "description": movie.get("description", "")[:250],
                "why_you_might_like_it": "You have strong {}% {} content in your library. ".format(
                    round(normalized_weights.get(candidate_genre, 0.1) * 100, 0),
                    candidate_genre.lower()) +
                    ("Also from your collection: {}".format(", ".join(matching_library[:2])) if matching_library else ""),
            })
    
    # Output
    result = {
        "mode": "specific" if args.genre else "cross-genre",
        "genre_weights": dict(list(profile.get("library_weights", {}).items())[:10]),
        "top_genres": profile.get("top_genres", [])[:10],
        "recommendations": recommendations,
        "total_found": len(final_candidates),
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
