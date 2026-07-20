#!/usr/bin/env python3
"""
v2.1 Digital Releases Scraper
Scrapes dvdsreleasedates.com for digital release titles, IMDb ratings, and genres.

Usage:
  python3 scrape_digital_releases.py [--month 7] [--year 2026] [--output digital_releases.json]

Outputs a JSON file with movie data that can be fed into the recommendation engine.

Portable: all paths resolve relative to this script's location via os.path.dirname.
"""
import json
import sys
import os
from html import unescape
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

# Resolve paths relative to this script — portable across machines
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))

# User-configurable: which genres to prioritize for recommendations
RECOMMENDATION_GENRES = {
    "Horror", "Thriller", "Science Fiction", "Action", "Drama",
    "Comedy", "Crime", "Mystery", "Adventure", "Fantasy",
}

def fetch_url(url):
    """Fetch a URL and return decoded HTML content."""
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; PlexRecScraper/1.0)"})
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except (HTTPError, URLError) as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}", file=sys.stderr)
        return None

def parse_digital_releases(html, year=2026, month=None):
    """
    Parse HTML from dvdsreleasedates.com/digital-releases/[year]/[m]/
    Returns list of movie dicts.
    """
    movies = []
    from html.parser import HTMLParser
    
    class DigitalReleaseParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.movies = []
            self.current_movie = None
            self.current_week = None
            self.in_week_header = False
            self.in_movie_card = False
            self.in_table_cell = False
            self.in_imdb_cell = False
            self.in_rating_cell = False
            self.in_title_link = False
            self.in_genres = False
            self.in_genre_links = False
            
            # State tracking for text accumulation
            self.in_table = False
            self.in_tr = False
            self.in_td = False
            self.accent_grave = False  # Track <a> tags for link extraction
            self.current_text = ""
            self.in_heading = False
            self.in_subgenres = False
            
            # Multi-genre tracking
            self.current_genre_links = []
            self.in_div_genres = False
            self.in_div_subgenres = False
            
        def handle_starttag(self, tag, attrs):
            attr_dict = dict(attrs)
            
            # Track table structure
            if tag == "table" and not self.in_table:
                self.in_table = True
            elif tag == "tr" and self.in_table:
                self.in_tr = True
            elif tag == "td" and self.in_tr:
                self.in_td = True
                
                # Check if this is an IMDb cell (has both rating number and rating badge)
                classes = attr_dict.get("class", "")
                if "imdb" in classes.lower():
                    self.in_imdb_cell = True
                elif "rating" in classes.lower() and self.in_imdb_cell:
                    self.in_rating_cell = True
                    self.in_imdb_cell = False
                else:
                    self.in_imdb_cell = False
                    self.in_rating_cell = False
                    
                # Check if this is a movie card cell (contains <a> link to release date)
                if "movie-card" in classes.lower() or "moviecard" in classes.lower():
                    self.in_movie_card = True
                    self.current_movie = {"title": "", "imdb": "", "mpaa": ""}
                
                # Detect week headers (h3 with class "week" or "month-header")
                if any("week" in c.lower() or "month" in c.lower() 
                       for c in classes.split() if c):
                    self.in_week_header = True
                    self.week_starttag = ("h3", attr_dict)
            
            # Detect week headers in different location (e.g., <a> -> <h3>)
            if tag == "a" and self.in_tr and self.in_table:
                classes = attr_dict.get("class", "")
                # Top-level nav that might lead to weeks
                if "breadcrumb" in classes:
                    self.in_breadcrumb = True
                    
            # Track <a> tags for link extraction
            if tag == "a":
                self.accent_grave = True
                href = attr_dict.get("href", "")
                rel = attr_dict.get("rel", "")
                
                # Check if this is a week header link
                if "weekly-releases" in href and self.in_tr:
                    # This <a> is likely inside a <h3> (week header)
                    self.in_week_header = True
                    self.week_starttag = ("h3", attr_dict)
                elif rel == "nofollow" and "weekly-releases" in href:
                    # Found a week header link in a <td>
                    self.in_week_header = True
                    self.week_starttag = ("h3", attr_dict)
                    self.current_week = href.split("/")[-2] if href else None
                    
                # Check if this is a movie card link
                elif "movie-card" in href or (href and "weekly-releases" not in href):
                    self.in_movie_card = True
                    self.current_movie = {"title": "", "imdb": "", "mpaa": ""}
                    # Extract month info from href if available
                    parts = href.split("/")
                    if "weekly-releases" in href:
                        idx = parts.index("weekly-releases") + 1
                        if idx < len(parts) and self.current_week != parts[idx]:
                            self.current_week = parts[idx]
                    elif parts[0] == "weekly-releases":
                        if parts[1] and self.current_week != parts[1]:
                            self.current_week = parts[1]
                    
                # Track genre links
                elif href and "genre" in href.lower() and href.count("/") >= 3:
                    # URL like /genres/horror or /genres/slasher
                    parts = href.split("/")
                    if len(parts) >= 3:
                        genre = parts[-1].replace("-", " ").title()
                        if genre:
                            self.current_genre_links.append(genre)
                            
            if tag == "h3" and self.in_tr:
                self.in_heading = True
                
            # Track div.genres for genre detection
            if tag == "div" and self.in_movie_card:
                classes = attr_dict.get("class", "")
                if "genres" in classes.lower():
                    self.in_div_genres = True
                    self.current_genre_links = []
                elif "subgenres" in classes.lower():
                    self.in_div_subgenres = True
                    self.current_genre_links = []
                    
            if tag == "a" and (self.in_div_genres or self.in_div_subgenres):
                href = attr_dict.get("href", "")
                rel = attr_dict.get("rel", "")
                if href and rel == "nofollow" and "genre" in href.lower():
                    parts = href.split("/")
                    if len(parts) >= 3:
                        genre = parts[-1].replace("-", " ").title()
                        if genre:
                            self.current_genre_links.append(genre)
                            
            if tag == "a" and href and "weekly-releases" in href and self.in_tr:
                # Weekly release link (could be week header or movie card)
                pass

        def handle_endtag(self, tag):
            # End table/row/cell tracking
            if tag == "table" and self.in_table:
                self.in_table = False
                self.in_tr = False
                self.in_td = False
                self.in_movie_card = False
                self.in_week_header = False
                self.current_movie = None
                self.in_imdb_cell = False
                self.in_rating_cell = False
                self.accent_grave = False
                self.in_div_genres = False
                self.in_div_subgenres = False
                self.in_heading = False
            elif tag == "tr" and self.in_tr:
                self.in_tr = False
                # Finish processing current movie if we have one
                if self.current_movie and self.current_movie.get("title"):
                    self.movies.append({
                        "title": self.current_movie["title"],
                        "imdb": self.current_movie.get("imdb", ""),
                        "mpaa": self.current_movie.get("mpaa", ""),
                        "genre_links": self.current_genre_links,
                    })
                    self.current_movie = None
                    self.in_movie_card = False
                    self.in_week_header = False
            elif tag == "td" and self.in_td:
                self.in_td = False
                # Check if this was an IMDb cell
                if self.in_imdb_cell:
                    self.in_imdb_cell = False
                if self.in_rating_cell:
                    self.in_rating_cell = False
            elif tag == "a":
                self.accent_grave = False
            elif tag == "div":
                self.in_div_genres = False
                self.in_div_subgenres = False

        def handle_data(self, data):
            self.current_text += data
            
            # Extract IMDb rating
            if self.in_imdb_cell:
                text = data.strip()
                if text and text.replace(".", "").isdigit() and len(text) <= 4:
                    self.current_movie["imdb"] = text
                    self.in_imdb_cell = False  # Only read once
            elif self.in_rating_cell:
                text = data.strip()
                if text and text in ("G", "PG", "PG-13", "R", "NC-17", "NR", "TV-MA"):
                    self.current_movie["mpaa"] = text
                    self.in_rating_cell = False
            
            # Week header detection
            if self.in_week_header and (tag in ("h3", "a") or self.current_text.strip()):
                pass  # Will capture week name in next section
            
            # Movie card detection: if we find "imdb:" text, we're likely in a card
            if "imdb:" in self.current_text:
                # Reset text and start tracking
                self.current_text = ""
                if not self.current_movie:
                    self.current_movie = {"title": "", "imdb": "", "mpaa": ""}
                    self.in_movie_card = True

    parser = DigitalReleaseParser()
    parser.feed(html)
    
    # Additional pass: extract week headers by looking for <h3> with "weekly-releases" links
    weeks = set()
    for movie in parser.movies:
        # Try to extract week from any genre_links or infer from title context
        pass
    
    return parser.movies

def parse_digital_releases_v2(html, year=2026):
    """
    Improved parser for dvdsreleasedates.com digital releases page.
    Extracts movies with their week, title, IMDb rating, and MPAA rating.
    """
    from html.parser import HTMLParser
    
    class ReleaseParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.movies = []
            self.current_movie = None
            self.current_week = None
            self.in_table = False
            self.in_row = False
            self.in_cell = False
            self.in_movie_cell = False
            self.in_movie_links = False  # div containing movie links
            self.in_imdb_info = False
            self.in_rating_info = False
            self.in_genres = False
            self.in_genre_list = False
            self.in_subgenres = False
            self.in_subgenre_list = False
            self.current_text = ""
            self.in_heading = False
            self.in_link = False
            self.current_link_text = ""
            self.current_link_href = ""
            self.movies_in_week = []
            self.in_div = False
            self.current_div_class = ""
            self.in_genre_section = False
            
        def handle_starttag(self, tag, attrs):
            attr_dict = dict(attrs)
            
            # Track table structure for movie cards
            if tag == "table":
                classes = attr_dict.get("class", "")
                if "weekly" in classes.lower() or "movies" in classes.lower():
                    self.in_table = True
                    
            if tag == "tr" and self.in_table:
                self.in_row = True
                
            if tag == "td" and self.in_row:
                self.in_cell = True
                classes = attr_dict.get("class", "")
                
                # Check for movie card cell
                if "movie" in classes.lower() or "card" in classes.lower():
                    self.in_movie_cell = True
                    self.current_movie = {
                        "title": "",
                        "imdb": "",
                        "mpaa": "",
                        "poster": "",
                        "genres": [],
                        "subgenres": [],
                        "genre_links": [],
                    }
                    self.in_movie_links = True
                    
                # Check for IMDb cell
                elif "imdb" in classes.lower():
                    self.in_imdb_info = True
                    
                # Check for MPAA rating cell
                elif "rating" in classes.lower() or "mpaa" in classes.lower():
                    self.in_rating_info = True
                    
                # Check for week header (any heading in a row with a release date link)
                if "week" in classes.lower() or "month" in classes.lower():
                    self.in_heading = True
                    
            if tag == "a" and self.in_row:
                self.in_link = True
                self.current_link_href = attr_dict.get("href", "")
                self.current_link_text = ""
                
                # Check if this is a movie link (not a release date link)
                if "weekly-releases" in self.current_link_href:
                    # This is a release date link — extract week info
                    parts = self.current_link_href.split("/")
                    for i, part in enumerate(parts):
                        if part == "weekly-releases" and i + 1 < len(parts):
                            week_info = parts[i + 1]
                            if week_info and week_info not in ("index.html",):
                                self.current_week = week_info
                            break
                elif self.in_movie_links:
                    # This is a movie title link
                    self.current_movie["title"] = ""  # Reset, will be set in handle_data
                elif self.in_imdb_info:
                    # IMDb rating link
                    pass
                elif self.in_rating_info:
                    # MPAA rating link
                    pass
                    
                # Check for genre links
                if "genres/" in self.current_link_href or self.current_link_href.startswith("/genres/"):
                    genre = self.current_link_href.split("/")[-1]
                    if genre and genre not in ("index.html",):
                        self.current_movie["genre_links"].append(genre.replace("-", " ").title())
                    
            if tag == "h3":
                self.in_heading = True
                
            # Track genre/subgenre sections
            if tag == "div":
                classes = attr_dict.get("class", "")
                if "genres" in classes.lower():
                    self.in_genres = True
                    self.current_movie["genres"] = self.current_movie.get("genres", [])
                elif "subgenres" in classes.lower():
                    self.in_subgenres = True
                    self.current_movie["subgenres"] = self.current_movie.get("subgenres", [])

        def handle_endtag(self, tag):
            # End table/row/cell tracking
            if tag == "table":
                self.in_table = False
                self.in_row = False
                self.in_cell = False
                self.in_movie_cell = False
                self.in_movie_links = False
                self.in_imdb_info = False
                self.in_rating_info = False
                self.in_heading = False
            elif tag == "tr":
                self.in_row = False
            elif tag == "td":
                self.in_cell = False
            elif tag == "a":
                self.in_link = False
                self.current_link_text = ""
                self.current_link_href = ""
            elif tag == "h3":
                self.in_heading = False
            elif tag == "div":
                self.in_genres = False
                self.in_subgenres = False

        def handle_data(self, data):
            if self.in_heading:
                text = data.strip()
                if "weekly" in text.lower() or "month" in text.lower():
                    # This might contain week info
                    pass
                    
            if self.in_link and self.current_link_text is not None:
                if "weekly-releases" in self.current_link_href:
                    # Release date link — extract the actual date text
                    pass
                elif self.in_movie_links:
                    # Movie title link
                    if self.current_movie:
                        self.current_movie["title"] += data.strip()
                elif self.in_imdb_info:
                    # IMDb rating
                    text = data.strip()
                    if text.replace(".", "").isdigit() and len(text) <= 4:
                        if self.current_movie:
                            self.current_movie["imdb"] = text
                elif self.in_rating_info:
                    # MPAA rating
                    text = data.strip()
                    if text in ("G", "PG", "PG-13", "R", "NC-17", "NR", "TV-MA"):
                        if self.current_movie:
                            self.current_movie["mpaa"] = text
                            
            # Genre/subgenre links text
            if self.in_link:
                href = self.current_link_href
                if href and ("genres/" in href.lower() or href.startswith("/genres/")):
                    genre = href.split("/")[-1]
                    if genre and genre not in ("index.html",):
                        genre_title = genre.replace("-", " ").title()
                        if self.current_movie:
                            if self.in_genres:
                                self.current_movie["genres"].append(genre_title)
                            elif self.in_subgenres:
                                self.current_movie["subgenres"].append(genre_title)

    parser = ReleaseParser()
    parser.feed(html)
    
    return parser.movies

def parse_digital_releases_v3(html, year=2026):
    """
    Final version: simple but effective parser using regex + HTML structure.
    """
    import re
    
    movies = []
    
    # Extract week headers
    week_pattern = re.compile(
        r'<a[^>]*href="/weekly-releases/(\d{4})/(\d+)/(\d+)"[^>]*>(.*?)</a>',
        re.IGNORECASE
    )
    
    # Extract movie cards
    movie_pattern = re.compile(
        r'<a[^>]*href="([^"]*weekly-releases/[^"]+)"[^>]*>[^<]*</a>\s*'
        r'<a[^>]*href="[^"]*"[^>]*>\s*([^<]+)\s*</a>\s*'
        r'<div[^>]*class="imdb"[^>]*>imdb:\s*<a[^>]*href="[^"]*"[^>]*>([^<]+)</a>',
        re.IGNORECASE | re.DOTALL
    )
    
    # Simpler approach: use regex to find movie entries
    movie_entry_pattern = re.compile(
        r'<td[^>]*class="[^"]*movie[^"]*"[^>]*>\s*'
        r'<div[^>]*class="movie-card"[^>]*>\s*'
        r'<a[^>]*href="([^"]+)"[^>]*>[^<]*</a>\s*'
        r'<a[^>]*href="[^"]+genre/[a-z-]+/[a-z0-9]+[^"]*"[^>]*>.*?</a>\s*'
        r'<div[^>]*class="imdb"[^>]*>.*?imdb:\s*<a[^>]*href="[^"]*"[^>]*>([^<]+)</a>',
        re.IGNORECASE | re.DOTALL
    )
    
    # Even simpler: just extract all movie links with their IMDB ratings
    title_pattern = re.compile(
        r'<a[^>]*href="[^"]*(?:weekly-releases/[0-9]+/[0-9]+/[0-9]+/[^"]+)"[^>]*>[^<]*</a>\s*'
        r'<a[^>]*href="[^"]+genre/[a-z-]+/[a-z0-9]+[^"]*"[^>]*>(.*?)</a>\s*'
        r'<div[^>]*class="imdb"[^>]*>.*?imdb:\s*<a[^>]*href="[^"]*"[^>]*>([^<]+)</a>',
        re.IGNORECASE | re.DOTALL
    )
    
    # Simplest approach: extract title + IMDB from each movie card
    cards = re.findall(
        r'<div[^>]*class="movie-card"[^>]*>.*?</div>\s*</td>',
        html, re.IGNORECASE | re.DOTALL
    )
    
    for card in cards:
        title_match = re.search(
            r'<a[^>]*href="[^"]+genre/[a-z-]+/[a-z0-9]+[^"]*"[^>]*>(.*?)</a>',
            card, re.IGNORECASE | re.DOTALL
        )
        imdb_match = re.search(
            r'imdb:\s*<a[^>]*href="[^"]*"[^>]*>([^<]+)</a>',
            card, re.IGNORECASE
        )
        rating_match = re.search(
            r'<td[^>]*class="[^"]*rating[^"]*"[^>]*>([^<]+)</td>',
            card, re.IGNORECASE
        )
        
        if title_match and imdb_match:
            title = title_match.group(1).strip()
            imdb = imdb_match.group(1).strip()
            mpaa = ""
            if rating_match:
                mpaa = rating_match.group(1).strip()
            
            movies.append({
                "title": title,
                "imdb": imdb,
                "mpaa": mpaa,
            })
    
    return movies

def get_genres_for_movie(title, movies_with_genres):
    """Look up genres for a movie from the scanned database."""
    title_lower = title.lower().strip()
    for m in movies_with_genres:
        if m["title"].lower() == title_lower:
            genres = m.get("genre_links", []) + m.get("genres", []) + m.get("subgenres", [])
            return [g for g in genres if g in RECOMMENDATION_GENRES]
    return []

def scrape_digital_releases(month=None, year=None, output=None):
    """Main scraping function."""
    if year is None:
        year = 2026
    if month is None:
        month = 7  # July 2026
    
    url = f"https://www.dvdsreleasedates.com/digital-releases/{year}/{month}/"
    print(f"Scraping: {url}", file=sys.stderr)
    
    html = fetch_url(url)
    if not html:
        return []
    
    # Try the regex-based parser first
    movies = parse_digital_releases_v3(html, year)
    
    if not movies:
        print("  [WARN] Regex parser found nothing, trying fallback...", file=sys.stderr)
        movies = parse_digital_releases_v2(html, year)
    
    if not movies:
        print("  [WARN] Fallback parser found nothing, trying original parser...", file=sys.stderr)
        movies = parse_digital_releases(html, year)
    
    print(f"  Found {len(movies)} movies", file=sys.stderr)
    return movies

def scrape_dvd_releases(year=None, output=None):
    """
    Scrape dvdsreleasedates.com/new-movies-YYYY/ for DVD releases.
    """
    if year is None:
        year = 2026
    
    url = f"https://www.dvdsreleasedates.com/new-movies-{year}/"
    print(f"Scraping DVD releases: {url}", file=sys.stderr)
    
    html = fetch_url(url)
    if not html:
        return []
    
    movies = parse_digital_releases_v3(html, year)
    
    print(f"  Found {len(movies)} DVD releases", file=sys.stderr)
    return movies

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape digital/DVD releases from dvdsreleasedates.com")
    parser.add_argument("--month", type=int, default=None, help="Month to scrape (1-12)")
    parser.add_argument("--year", type=int, default=None, help="Year to scrape")
    parser.add_argument("--dvd", action="store_true", help="Also scrape DVD releases")
    parser.add_argument("--output", default=None, help="Output file path")
    args = parser.parse_args()
    
    output_path = args.output or os.path.join(SKILL_DIR, "cache", "digital_releases.json")
    
    # Create cache directory if needed
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Scrape digital releases
    digital_movies = scrape_digital_releases(month=args.month, year=args.year)
    
    result = {
        "source": "dvdsreleasedates.com",
        "digital_releases": digital_movies,
        "total_count": len(digital_movies),
    }
    
    # Also scrape DVD releases if requested
    if args.dvd:
        dvd_movies = scrape_dvd_releases(year=args.year)
        result["dvd_releases"] = dvd_movies
        result["total_count"] += len(dvd_movies)
    
    # Write output
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    
    print(f"\nResults saved to: {output_path}", file=sys.stderr)
    print(f"Total: {result['total_count']} movies", file=sys.stderr)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Digital Releases ({args.year}/{args.month:02d}): {len(digital_movies)} movies")
    print(f"{'='*60}")
    for i, m in enumerate(digital_movies[:10]):
        imdb_str = f" IMDb: {m['imdb']}" if m['imdb'] else ""
        mpaa_str = f" | {m['mpaa']}" if m.get('mpaa') else ""
        print(f"  {i+1}. {m['title']}{imdb_str}{mpaa_str}")

if __name__ == "__main__":
    main()
