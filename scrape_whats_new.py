#!/usr/bin/env python3
"""
v2.2 What's New — Digital Releases Scraper

Scrapes this month's digital releases from dvdsreleasedates.com and compares
against the existing cache to find titles that are NEW (not already in cache).

Usage:
  python3 scrape_whats_new.py                    # This month's new releases
  python3 scrape_whats_new.py --month 6 --year 2026  # Specific month
  python3 scrape_whats_new.py --all               # Show all current releases (no comparison)

Portable: all paths resolve relative to this script's location via os.path.dirname.
"""
import json
import sys
import os
import re
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(SKILL_DIR, "cache")
DVDS_CACHE_PATH = os.path.join(CACHE_DIR, "dvds_releases.json")


def fetch_url(url):
    """Fetch a URL and return decoded HTML content."""
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except (HTTPError, URLError, OSError) as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}", file=sys.stderr)
        return None


def extract_movie_info(chunk):
    """Extract title, IMDb rating, and MPAA rating from a movie card chunk."""
    title_match = re.search(
        r"<a\s+style=['\"]?color:#000;['\"]?\s+href=['\"]?/movies/[0-9]+/[a-z0-9-]+['\"]?\s*>([^<]+)</a>",
        chunk, re.IGNORECASE
    )

    if not title_match:
        return None

    title = title_match.group(1).strip()
    if not title:
        return None

    celldiscs_match = re.search(
        r"<table[^>]*class=['\"]?celldiscs['\"]?[^>]*>.*?</table>",
        chunk, re.IGNORECASE | re.DOTALL
    )

    if not celldiscs_match:
        return {"title": title, "imdb": "", "mpaa": ""}

    celldiscs = celldiscs_match.group(0)

    imdb_match = re.search(
        r"class=['\"]?imdblink\s+left['\"]?\s*>imdb:\s*<a[^>]*href=['\"]?http://www\.imdb\.com[^>]*>([^<]+)</a>",
        celldiscs, re.IGNORECASE
    )

    imdb = ""
    if imdb_match:
        imdb = imdb_match.group(1).strip()
        try:
            float(imdb)
        except ValueError:
            imdb = ""

    mpaa_match = re.search(
        r"class=['\"]?imdblink\s+right['\"]?>(PG-13|NC-17|G|PG|R|NR|TV-MA)",
        celldiscs, re.IGNORECASE
    )

    mpaa = ""
    if mpaa_match:
        mpaa = mpaa_match.group(1).strip()

    return {"title": title, "imdb": imdb, "mpaa": mpaa}


def parse_movie_table(html):
    """Parse movie table from dvdsreleasedates.com pages."""
    movies = []

    title_links = list(re.finditer(
        r"<a\s+style=['\"]?color:#000;['\"]?\s+href=['\"]?/movies/[0-9]+/[a-z0-9-]+['\"]?\s*>([^<]+)</a>",
        html, re.IGNORECASE
    ))

    if not title_links:
        return movies

    for i, match in enumerate(title_links):
        title = match.group(1).strip()
        if not title:
            continue

        start = match.start()
        end = title_links[i + 1].start() if i + 1 < len(title_links) else len(html)
        chunk = html[start:end]

        celldiscs_match = re.search(
            r"<table[^>]*class=['\"]?celldiscs['\"]?[^>]*>.*?</table>",
            chunk, re.IGNORECASE | re.DOTALL
        )

        if not celldiscs_match:
            movies.append({"title": title, "imdb": "", "mpaa": ""})
            continue

        celldiscs = celldiscs_match.group(0)

        imdb_match = re.search(
            r"class=['\"]?imdblink\s+left['\"]?\s*>imdb:\s*<a[^>]*href=['\"]?http://www\.imdb\.com[^>]*>([^<]+)</a>",
            celldiscs, re.IGNORECASE
        )

        imdb = ""
        if imdb_match:
            imdb = imdb_match.group(1).strip()
            try:
                float(imdb)
            except ValueError:
                imdb = ""

        mpaa_match = re.search(
            r"class=['\"]?imdblink\s+right['\"]?>(PG-13|NC-17|G|PG|R|NR|TV-MA)",
            celldiscs, re.IGNORECASE
        )

        mpaa = ""
        if mpaa_match:
            mpaa = mpaa_match.group(1).strip()

        movies.append({
            "title": title,
            "imdb": imdb,
            "mpaa": mpaa,
        })

    return movies


def scrape_digital_releases(month=None, year=None):
    """Scrape digital releases from dvdsreleasedates.com."""
    if year is None:
        year = datetime.now().year
    if month is None:
        month = datetime.now().month

    url = f"https://www.dvdsreleasedates.com/digital-releases/{year}/{month}/"
    print(f"Scraping: {url}", file=sys.stderr)

    html = fetch_url(url)
    if not html:
        return []

    movies = parse_movie_table(html)
    print(f"  Found {len(movies)} digital releases", file=sys.stderr)
    return movies


def add_genre_data(movies_with_data):
    """Add genre data to movies by scraping genre pages."""
    genre_urls = {
        "horror": "Horror",
        "science-fiction": "Science Fiction",
        "thriller": "Thriller",
        "action": "Action",
        "drama": "Drama",
        "comedy": "Comedy",
        "crime": "Crime",
        "mystery": "Mystery",
        "adventure": "Adventure",
        "fantasy": "Fantasy",
    }

    known_titles = {m["title"].lower() for m in movies_with_data}
    all_genre_movies = {}

    for slug, name in genre_urls.items():
        try:
            url = f"https://www.dvdsreleasedates.com/genre/{slug}-movies"
            html = fetch_url(url)
            if not html:
                continue

            title_links = list(re.finditer(
                r"<a\s+style=['\"]?color:#000;['\"]?\s+href=['\"]?/movies/[0-9]+/[a-z0-9-]+['\"]?\s*>([^<]+)</a>",
                html, re.IGNORECASE
            ))

            for i, match in enumerate(title_links):
                title = match.group(1).strip()
                if not title:
                    continue

                start = match.start()
                end = title_links[i + 1].start() if i + 1 < len(title_links) else len(html)
                chunk = html[start:end]

                imdb_match = re.search(
                    r"class=['\"]?imdblink\s+left['\"]?\s*>imdb:\s*<a[^>]*href=['\"]?http://www\.imdb\.com[^>]*>([^<]+)</a>",
                    chunk, re.IGNORECASE
                )

                imdb = ""
                if imdb_match:
                    imdb = imdb_match.group(1).strip()
                    try:
                        float(imdb)
                    except ValueError:
                        imdb = ""

                mpaa_match = re.search(
                    r"class=['\"]?imdblink\s+right['\"]?>(PG-13|NC-17|G|PG|R|NR|TV-MA)",
                    chunk, re.IGNORECASE
                )

                mpaa = ""
                if mpaa_match:
                    mpaa = mpaa_match.group(1).strip()

                all_genre_movies[title] = {
                    "imdb": imdb,
                    "mpaa": mpaa,
                    "genres": [name],
                }

        except Exception as e:
            print(f"    [WARN] Failed to scrape {name}: {e}", file=sys.stderr)
            continue

    for movie in movies_with_data:
        title_lower = movie["title"].lower()
        for gm_title, gm_data in all_genre_movies.items():
            if gm_title.lower() == title_lower:
                movie["genres"] = gm_data.get("genres", [])
                if gm_data.get("imdb") and not movie.get("imdb"):
                    movie["imdb"] = gm_data["imdb"]
                if gm_data.get("mpaa") and not movie.get("mpaa"):
                    movie["mpaa"] = gm_data["mpaa"]
                break

    return movies_with_data


def load_existing_cache():
    """Load the existing dvds_releases.json cache."""
    if not os.path.exists(DVDS_CACHE_PATH):
        return []

    try:
        with open(DVDS_CACHE_PATH, "r") as f:
            data = json.load(f)
        return data.get("merged_releases", [])
    except (json.JSONDecodeError, IOError):
        return []


def find_new_releases(current_monthly, existing_cache):
    """Find titles in current month's releases that aren't in the cache."""
    existing_titles = {m["title"].lower() for m in existing_cache}
    new_movies = []

    for movie in current_monthly:
        if movie["title"].lower() not in existing_titles:
            new_movies.append(movie)

    return new_movies


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="What's New — find new digital releases compared to cache"
    )
    parser.add_argument(
        "--month", type=int, default=None, help="Month to scrape (1-12)"
    )
    parser.add_argument(
        "--year", type=int, default=None, help="Year to scrape"
    )
    parser.add_argument(
        "--all", action="store_true", help="Show all current releases (no cache comparison)"
    )
    args = parser.parse_args()

    # Scrape this month's digital releases
    current_movies = scrape_digital_releases(args.month, args.year)

    if not current_movies:
        print("\nNo digital releases found for this month.", file=sys.stderr)
        sys.exit(0)

    # Add genre data
    current_movies = add_genre_data(current_movies)

    if args.all:
        # Show all releases without comparison
        print(f"\n{'='*60}")
        print(f"ALL Digital Releases — {datetime.now().strftime('%B %Y')}")
        print(f"{'='*60}")

        sorted_movies = sorted(current_movies, key=lambda x: (float(x.get("imdb") or "0"), x["title"]), reverse=True)

        for i, m in enumerate(sorted_movies):
            imdb_str = f" IMDb: {m['imdb']}" if m.get("imdb") else ""
            mpaa_str = f" | {m['mpaa']}" if m.get("mpaa") else ""
            genres_str = f" | {', '.join(m.get('genres', []))}" if m.get("genres") else ""
            print(f"  {i+1}. {m['title']}{imdb_str}{mpaa_str}{genres_str}")

        print(f"\nTotal: {len(sorted_movies)} releases")
    else:
        # Compare against cache to find new titles
        existing_cache = load_existing_cache()

        if not existing_cache:
            print("\nNo existing cache found. Showing all releases as 'new'.", file=sys.stderr)
            new_movies = current_movies
        else:
            print(f"\nComparing against {len(existing_cache)} cached titles...", file=sys.stderr)
            new_movies = find_new_releases(current_movies, existing_cache)

        print(f"\n{'='*60}")
        month_name = datetime(args.year or datetime.now().year, args.month or datetime.now().month, 1).strftime('%B %Y')
        print(f"WHAT'S NEW — {month_name}")
        print(f"{'='*60}")

        if not new_movies:
            print("\nNo new releases this month — all titles are already in cache.")
        else:
            # Sort by IMDb rating (highest first)
            sorted_movies = sorted(new_movies, key=lambda x: (float(x.get("imdb") or "0"), x["title"]), reverse=True)

            print(f"\nFound {len(new_movies)} new release{'s' if len(new_movies) != 1 else ''}:\n")

            for i, m in enumerate(sorted_movies):
                imdb_str = f" IMDb: {m['imdb']}" if m.get("imdb") else ""
                mpaa_str = f" | {m['mpaa']}" if m.get("mpaa") else ""
                genres_str = f" | {', '.join(m.get('genres', []))}" if m.get("genres") else ""
                print(f"  {i+1}. {m['title']}{imdb_str}{mpaa_str}{genres_str}")

            # Summary by genre
            if new_movies:
                genre_counts = {}
                for m in new_movies:
                    for g in m.get("genres", []):
                        genre_counts[g] = genre_counts.get(g, 0) + 1

                if genre_counts:
                    print(f"\nBy genre:")
                    for genre, count in sorted(genre_counts.items(), key=lambda x: -x[1]):
                        print(f"  {genre}: {count}")

        # Save updated cache (merge new releases into existing)
        if new_movies and not args.all:
            # Merge new movies into cache
            existing_cache.extend(new_movies)

            result = {
                "source": "dvdsreleasedates.com",
                "merged_releases": existing_cache,
                "digital_count": len(current_movies),
                "dvd_count": 0,
                "merged_count": len(existing_cache),
            }

            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(DVDS_CACHE_PATH, "w") as f:
                json.dump(result, f, indent=2)

            print(f"\nCache updated: {DVDS_CACHE_PATH}")
            print(f"Total cached titles: {len(existing_cache)}")


if __name__ == "__main__":
    main()
