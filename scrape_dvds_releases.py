#!/usr/bin/env python3
"""
v2.1 Digital & DVD Releases Scraper
Scrapes dvdsreleasedates.com for digital and DVD release titles, IMDb ratings, and MPAA ratings.

Usage:
  python3 scrape_dvds_releases.py --digital --month 7 --year 2026
  python3 scrape_dvds_releases.py --dvd --year 2026
  python3 scrape_dvds_releases.py --digital --dvd --month 7 --year 2026

Portable: all paths resolve relative to this script's location via os.path.dirname.
"""
import json
import sys
import os
import re
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))

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
    """
    Extract title, IMDb rating, and MPAA rating from a movie card chunk.
    
    Each chunk is the HTML between two movie title links.
    We find the title, then look for the celldiscs table to get IMDb/MPAA.
    """
    # Title: look for <a style='color:#000;' href='/movies/...'>TITLE</a>
    title_match = re.search(
        r"<a\s+style=['\"]?color:#000;['\"]?\s+href=['\"]?/movies/[0-9]+/[a-z0-9-]+['\"]?\s*>([^<]+)</a>",
        chunk, re.IGNORECASE
    )
    
    if not title_match:
        return None
    
    title = title_match.group(1).strip()
    if not title:
        return None
    
    # Find the celldiscs table in this chunk
    celldiscs_match = re.search(
        r"<table[^>]*class=['\"]?celldiscs['\"]?[^>]*>.*?</table>",
        chunk, re.IGNORECASE | re.DOTALL
    )
    
    if not celldiscs_match:
        return {"title": title, "imdb": "", "mpaa": ""}
    
    celldiscs = celldiscs_match.group(0)
    
    # Extract IMDb: class='imdblink left' > imdb: <a ...>NUMBER</a>
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
    
    # Extract MPAA: class='imdblink right' > RATING
    # IMPORTANT: PG-13 must come before PG, and NC-17 before NR to avoid partial matches
    mpaa_match = re.search(
        r"class=['\"]?imdblink\s+right['\"]?>(PG-13|NC-17|G|PG|R|NR|TV-MA)",
        celldiscs, re.IGNORECASE
    )
    
    mpaa = ""
    if mpaa_match:
        mpaa = mpaa_match.group(1).strip()
    
    return {"title": title, "imdb": imdb, "mpaa": mpaa}


def parse_movie_table(html):
    """
    Parse movie table from dvdsreleasedates.com pages.
    
    Strategy: find all movie title links, then extract IMDb/MPAA from the celldiscs table
    that appears in the same dvdcell block.
    
    HTML structure:
    <td class='dvdcell'>
      <a href='/movies/XXXX/xxx'><img .../></a><br/>
      <a style='color:#000;' href='/movies/XXXX/xxx'>Movie Title</a><br/>
      <table class='celldiscs'><tr>
        <td class='imdblink left'>imdb: <a ...>6.9</a></td>
        <td class='imdblink right'>R&nbsp;&nbsp;</td>
      </tr></table>
    </td>
    """
    movies = []
    
    # Strategy: split HTML on dvdcell boundaries.
    # Each <td class='dvdcell'>...</td> contains exactly one movie.
    # The tricky part: the content has nested <td> from the celldiscs table.
    # So we use a different approach: find all movie title links, then look
    # at the HTML between each title and the next one to find the IMDb/MPAA.
    
    # Find all title links with their positions
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
        
        # Extract context: from this title link to the next title link (or end of html)
        start = match.start()
        end = title_links[i + 1].start() if i + 1 < len(title_links) else len(html)
        
        # Look forward for the celldiscs table (within a reasonable distance)
        chunk = html[start:end]
        celldiscs_match = re.search(
            r"<table[^>]*class=['\"]?celldiscs['\"]?[^>]*>.*?</table>",
            chunk, re.IGNORECASE | re.DOTALL
        )
        
        if not celldiscs_match:
            movies.append({"title": title, "imdb": "", "mpaa": ""})
            continue
        
        celldiscs = celldiscs_match.group(0)
        
        # Extract IMDb
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
        
        # Extract MPAA (PG-13 before PG, NC-17 before NR to avoid partial matches)
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
        year = 2026
    if month is None:
        month = 7
    
    url = f"https://www.dvdsreleasedates.com/digital-releases/{year}/{month}/"
    print(f"Scraping: {url}", file=sys.stderr)
    
    html = fetch_url(url)
    if not html:
        return []
    
    movies = parse_movie_table(html)
    print(f"  Found {len(movies)} digital releases", file=sys.stderr)
    return movies


def scrape_genre_page(slug, human_name):
    """
    Scrape a genre-specific page to get movies with known genres.
    
    Args:
        slug: URL slug (e.g. "science-fiction")
        human_name: Display name (e.g. "Science Fiction")
    
    Returns dict of {title: {"imdb": "", "mpaa": "", "genres": [human_name, ...]}}
    """
    url = f"https://www.dvdsreleasedates.com/genre/{slug}-movies"
    print(f"  Scraping genre: {url}", file=sys.stderr)
    
    html = fetch_url(url)
    if not html:
        return {}
    
    movies = {}
    
    # Find all movie cards on the genre page
    # Each card has: <td class='dvdcell'>...<a style='color:#000;'...>TITLE</a>...
    title_links = list(re.finditer(
        r"<a\s+style=['\"]?color:#000;['\"]?\s+href=['\"]?/movies/[0-9]+/[a-z0-9-]+['\"]?\s*>([^<]+)</a>",
        html, re.IGNORECASE
    ))
    
    for i, match in enumerate(title_links):
        title = match.group(1).strip()
        if not title:
            continue
        
        # Get context to next movie (or end of HTML)
        start = match.start()
        end = title_links[i + 1].start() if i + 1 < len(title_links) else len(html)
        chunk = html[start:end]
        
        # Extract IMDb
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
        
        # Extract MPAA
        mpaa_match = re.search(
            r"class=['\"]?imdblink\s+right['\"]?>(PG-13|NC-17|G|PG|R|NR|TV-MA)",
            chunk, re.IGNORECASE
        )
        
        mpaa = ""
        if mpaa_match:
            mpaa = mpaa_match.group(1).strip()
        
        movies[title] = {
            "imdb": imdb,
            "mpaa": mpaa,
            "genres": [human_name],
        }
    
    print(f"    Found {len(movies)} {human_name} movies", file=sys.stderr)
    return movies


def scrape_dvd_releases(year=None):
    """Scrape DVD releases from dvdsreleasedates.com/new-movies-YYYY/."""
    if year is None:
        year = 2026
    
    url = f"https://www.dvdsreleasedates.com/new-movies-{year}/"
    print(f"Scraping DVD releases: {url}", file=sys.stderr)
    
    html = fetch_url(url)
    if not html:
        return []
    
    movies = parse_movie_table(html)
    print(f"  Found {len(movies)} DVD releases", file=sys.stderr)
    return movies


def add_genre_data(movies_with_data):
    """
    Add genre data to movies by scraping genre pages.
    
    Takes list of movie dicts and adds genre info.
    Returns updated list.
    """
    # Map of genre URL slugs to human-readable names
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
    
    # Build a set of known titles
    known_titles = {m["title"].lower() for m in movies_with_data}
    
    # Scrape each genre page and add genre data
    all_genre_movies = {}
    for slug, name in genre_urls.items():
        try:
            genre_movies = scrape_genre_page(slug, name)
            all_genre_movies.update(genre_movies)
        except Exception as e:
            print(f"    [WARN] Failed to scrape {name}: {e}", file=sys.stderr)
            continue
    
    # Match genre data to our movie list
    for movie in movies_with_data:
        title_lower = movie["title"].lower()
        if title_lower in {m.lower() for m in all_genre_movies}:
            # Find matching genre movie
            for gm_title, gm_data in all_genre_movies.items():
                if gm_title.lower() == title_lower:
                    movie["genres"] = gm_data.get("genres", [])
                    # Update IMDb/MPAA if we have better data
                    if gm_data.get("imdb") and not movie.get("imdb"):
                        movie["imdb"] = gm_data["imdb"]
                    if gm_data.get("mpaa") and not movie.get("mpaa"):
                        movie["mpaa"] = gm_data["mpaa"]
                    break
    
    return movies_with_data


def merge_digital_and_dvd(digital_movies, dvd_movies):
    """
    Merge digital and DVD releases, adding genre data.
    """
    # Create a dict for quick lookup by title
    merged = {}
    
    for movie in digital_movies:
        key = movie["title"].lower()
        merged[key] = {
            "title": movie["title"],
            "imdb": movie.get("imdb", ""),
            "mpaa": movie.get("mpaa", ""),
            "genres": [],
            "release_type": "Digital",
        }
    
    for movie in dvd_movies:
        key = movie["title"].lower()
        if key in merged:
            # Update existing entry
            merged[key].update({
                "imdb": movie.get("imdb") or merged[key]["imdb"],
                "mpaa": movie.get("mpaa") or merged[key]["mpaa"],
                "release_type": "DVD/Digital",
            })
        else:
            merged[key] = {
                "title": movie["title"],
                "imdb": movie.get("imdb", ""),
                "mpaa": movie.get("mpaa", ""),
                "genres": [],
                "release_type": "DVD",
            }
    
    result = list(merged.values())
    
    # Add genre data
    result = add_genre_data(result)
    
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Scrape digital/DVD releases from dvdsreleasedates.com"
    )
    parser.add_argument(
        "--digital", action="store_true", help="Scrape digital release dates"
    )
    parser.add_argument(
        "--dvd", action="store_true", help="Scrape DVD release dates"
    )
    parser.add_argument(
        "--month", type=int, default=None, help="Month to scrape (1-12)"
    )
    parser.add_argument(
        "--year", type=int, default=None, help="Year to scrape"
    )
    parser.add_argument(
        "--output", default=None, help="Output file path"
    )
    args = parser.parse_args()
    
    if not args.digital and not args.dvd:
        print("  [ERROR] Must specify --digital and/or --dvd", file=sys.stderr)
        sys.exit(1)
    
    output_path = args.output or os.path.join(SKILL_DIR, "cache", "dvds_releases.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Scrape both sources
    digital_movies = []
    dvd_movies = []
    
    if args.digital:
        digital_movies = scrape_digital_releases(args.month, args.year)
    if args.dvd:
        dvd_movies = scrape_dvd_releases(args.year)
    
    # Merge with genre data
    if digital_movies or dvd_movies:
        merged = merge_digital_and_dvd(digital_movies, dvd_movies)
    else:
        merged = []
    
    result = {
        "source": "dvdsreleasedates.com",
        "merged_releases": merged,
        "digital_count": len(digital_movies),
        "dvd_count": len(dvd_movies),
        "merged_count": len(merged),
    }
    
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    
    total = result["merged_count"]
    print(f"\nResults saved to: {output_path}", file=sys.stderr)
    print(f"Total unique merged releases: {total}", file=sys.stderr)
    print(f"  Digital: {len(digital_movies)}, DVD: {len(dvd_movies)}", file=sys.stderr)
    
    # Print summary by genre
    genre_counts = {}
    for m in merged:
        for g in m.get("genres", []):
            genre_counts[g] = genre_counts.get(g, 0) + 1
    
    if genre_counts:
        print(f"\nBy genre:", file=sys.stderr)
        for genre, count in sorted(genre_counts.items(), key=lambda x: -x[1]):
            print(f"  {genre}: {count} movies", file=sys.stderr)
    
    # Print top movies
    sorted_movies = sorted(merged, key=lambda x: (float(x.get("imdb") or "0"), x["title"]), reverse=True)
    print(f"\nTop {min(10, len(sorted_movies))} by IMDb:", file=sys.stderr)
    for i, m in enumerate(sorted_movies[:10]):
        imdb_str = f" IMDb: {m['imdb']}" if m["imdb"] else ""
        mpaa_str = f" | {m['mpaa']}" if m.get("mpaa") else ""
        genres_str = f" | {', '.join(m.get('genres', []))}" if m.get("genres") else ""
        print(f"  {i+1}. {m['title']}{imdb_str}{mpaa_str}{genres_str}", file=sys.stderr)


if __name__ == "__main__":
    main()
