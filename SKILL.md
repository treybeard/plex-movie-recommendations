---
name: plex-recommendations
description: >
  Multi-genre movie recommendation system that analyzes your Plex library
  and personal ratings to suggest movies you'll actually enjoy. Supports
  both general recommendations (across all genres) and genre-specific 
  recommendations (within a single genre and its subgenres).
version: 2.1.0
author: Hermes
tags: [media, plex, recommendations, multi-genre, film-taxonomy, dvds-releases]
---

# Plex Recommendations v2.1

## Connection Details

Plex server: `http://10.0.0.130:32400`
API token: `~/.hermes/profiles/aether/api_keys/plex.txt`
Library sections: Movies (section 9), TV Shows (section 2)
- **DO NOT scan Vuze (section 5)** — it is a temporary staging area where movies sit until the user decides whether to promote them to the main libraries.

## Genre System (v2)

All recommendations use Wikipedia's film genre taxonomy (from List_of_genres wiki) as the canonical reference. Every Plex genre tag is mapped to a Wikipedia super-genre.

Full mapping is stored in `plex_to_wikipedia_genres.json`. Compound genres (e.g. "Action Horror") are mapped to the first major genre's Wikipedia super-genre.

### Library Preference Weights (from library + ratings)

Run `python3 generate_profile.py` to compute fresh preference weights. Current known weights:

| Genre | Weight | % of Library |
|---|---|---|
| Action | 0.3868 | 39% |
| Drama | 0.2345 | 23% |
| Adventure | 0.1914 | 19% |
| Comedy | 0.1779 | 18% |
| Thriller | 0.1321 | 13% |
| Science Fiction | 0.1294 | 13% |
| Crime | 0.1078 | 11% |
| Horror | 0.0970 | 10% |
| Fantasy | 0.0431 | 4% |
| Biography | 0.0404 | 4% |

See `profiles.json` for the full profile with all genres, rating adjustments, and Plex-to-Wikipedia genre mappings.

## Two Recommendation Modes

There are **two modes** for generating recommendations. The mode is determined by the user's request.

### v2.1 New Release Integration (dvdsreleasedates.com)

The recommendation engine now integrates with dvdsreleasedates.com to include newly released movies in recommendations:

- `scrape_dvds_releases.py` — Scrapes digital and DVD releases from dvdsreleasedates.com
  - Fetches current month's digital releases (`/digital-releases/YYYY/M`)
  - Fetches yearly DVD releases (`/new-movies-YYYY/`)
  - Scrapes genre pages for all major genres (Horror, Sci-Fi, Thriller, Action, Drama, Comedy, Crime, Mystery, Adventure, Fantasy)
  - Merges digital + DVD releases with actual genre data from scraped pages
  - Saves to `cache/dvds_releases.json` with title, IMDb rating, MPAA rating, and genres
  - Cache is refreshed automatically if older than 7 days

- Genre-aware filtering: When a user requests recommendations for a specific genre (e.g., "recommend horror"), the engine filters dvds releases by actual scraped genre data instead of keyword matching. This works reliably across ALL supported genres.

- New releases are scored alongside web search results and included in final recommendations when they match the user's preferences and aren't already in their library.

### Mode 1: Cross-Genre (General / Broad)

**Use when:** User makes a general request for recommendations without specifying a genre.

**User prompts that trigger this mode:**
- "Recommend movies"
- "Give me some movie recommendations"
- "Recommend me something to watch"
- "What should I watch?"
- Any general request without a genre keyword

**Behavior:**
1. Loads the top 6 genres from `profiles.json` by preference weight
2. For each genre, searches the web for highly-rated movies
3. Scores candidates by normalized genre weight + recency bonus
4. Filters out everything in the user's Plex library, Vuze, and watched list
5. Returns ranked recommendations across all genres

This is the **default** behavior — broad recommendations from your favorite genres.

### Mode 2: Genre-Specific (Narrow / Targeted)

**Use when:** User explicitly names a genre.

**User prompts that trigger this mode:**
- "Recommend horror movies"
- "I'm in the mood for action"
- "What good comedies are out?"
- "Recommend me some thrillers"
- Any request that includes a genre keyword

**Behavior:**
1. Parses the requested genre from the user's prompt
2. Loads Wikipedia's film genre taxonomy (`plex_to_wikipedia_genres.json`)
3. Finds all Wikipedia subgenres for that genre
4. Searches only those genres (the main genre + its subgenres)
5. Filters out library, Vuze, and watched titles
6. Returns ranked recommendations focused on that genre

**Examples of genre-specific searches:**

| User says | Genres searched |
|---|---|
| "recommend horror" | Horror + Slasher, Found Footage, Monster, Zombie, etc. |
| "recommend action" | Action + Superhero, Spy, Martial Arts, Disaster, etc. |
| "recommend comedy" | Comedy + Romantic Comedy, Action Comedy, Black Comedy, etc. |
| "recommend sci-fi" | Science Fiction + Cyberpunk, Dystopian, Space Opera, etc. |

## How It Works

### Step 1: Library Scan & Cache

```bash
curl -s "http://10.0.0.130:32400/library/sections/9/all?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)" -o cache/movies.xml
curl -s "http://10.0.0.130:32400/library/sections/2/all?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)" -o cache/tv.xml
echo "Library scanned and cached."
```

**Important:** Only scan **Movies** (section 9) and **TV Shows** (section 2). Do NOT scan Vuze (section 5).

### Step 2: Map Genres

After scanning, run the genre mapper:
```bash
python3 map_genres.py
```
This maps all Plex genres to Wikipedia film genres and saves the mapping to `plex_to_wikipedia_genres.json`.

### Step 3: Generate Preference Profile

```bash
python3 generate_profile.py
```
This combines:
- **Library composition** (every movie counts as an 8/10)
- **Watched ratings** (liked +2, meh +0.5, disliked -1, couldn't finish -2)

Result: `profiles.json` with per-genre preference weights.

### Step 4: Generate Recommendations

**Cross-Genre (default):**
```bash
python3 generate_recommendations.py --count 10
```

**Genre-Specific:**
```bash
python3 generate_recommendations.py --count 10 --genre Horror
```

Both modes follow this flow:
1. Load `profiles.json` for genre weights
2. Load `plex_to_wikipedia_genres.json` for genre taxonomy
3. Load library titles from `cache/movies.xml` and `cache/tv.xml` to filter
4. Load `watched_movies.txt` to filter watched titles
5. Search web for highly-rated movies in target genre(s)
6. Return ranked recommendations with matched genre and reasoning

### Step 5: Refresh Library

When the user says "refresh my Plex library" or "update my library":
1. Re-run Step 1 (scan commands)
2. Re-run Step 2 (map_genres.py)
3. Re-run Step 3 (generate_profile.py)
4. Report what was added: "Found X new movies, Y new shows in your library."

## User Profile / Viewing Preferences

### Library as Preference Baseline
All movies/shows in the user's **Movies** (section 9) and **TV Shows** (section 2) libraries count toward preferences.
- Every entry in these libraries is treated as an 8/10 or equivalent
- The user sometimes watches content elsewhere first then downloads it to their library, so it may show as unwatched
- Unwatched library entries still count toward recommendations — the library itself IS the preference
- If a movie is in the library, it should be EXCLUDED from future recommendations (whether watched or not)

### Recommendation Filtering
When generating recommendations, EXCLUDE:
- Any movie/TV show currently in the user's Plex library (Movies section 9 + TV Shows section 2), whether watched or unwatched
- Any movie/TV show the user has explicitly marked as watched in watched_movies.txt
- Any movie/TV show currently in Vuze section (section 5) — temporary staging, also exclude
- Only recommend movies NOT in any of the user's libraries

### User's Watched Movies (from watched_movies.txt)
| Movie | Rating |
|---|---|
| Companion (2024) | liked |
| Prey (2022) | liked |
| Annihilation (2018) | meh |
| The Creator (2023) | meh |
| Her (2013) | disliked |
| Ghost in the Shell (1995) | meh |
| The Man from Earth (2007) | couldn't finish |
| Rebel Moon: Part 2 — The Scargiver (2024) | couldn't finish |

### Rating Format
- `liked` — user enjoyed it and would watch similar (boosts that genre +2)
- `disliked` — user didn't enjoy it and should avoid similar (demotes genre -1)
- `meh` — user had no strong opinion (slight boost +0.5)
- `couldn't_finish` — user couldn't finish it (strongly demotes genre -2)

## Marking a Movie as Watched

When the user says "I've seen [movie name]" or "I've already watched [movie name]", add the movie to the watched list:

```bash
echo "[Movie Name] (year) - user has seen | liked" >> watched_movies.txt
```

Rating variants: `liked`, `disliked`, `meh`, `couldn't_finish`

Then regenerate the profile:
```bash
python3 generate_profile.py
```

### Watch List Management
When the user says "add [movie] to the watch list", add it to `watch_list.txt` in the skill directory.
When the user rates a movie in `watched_movies.txt`, automatically remove it from `watch_list.txt` if it exists there.
To manually remove a movie from the watch list, the user can say "remove [movie] from the watch list" and the assistant removes the entry from `watch_list.txt`.
To see the watch list, the user can say "what's on the watch list?" and the assistant reads `watch_list.txt`.

## Library Management

### View Library Stats
```bash
curl -s "http://10.0.0.130:32400/library/sections?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)"
```

### View a Specific Library Section
```bash
curl -s "http://10.0.0.130:32400/library/sections/[section_id]/all?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)"
```

### View Currently Playing
```bash
curl -s "http://10.0.0.130:32400/status/sessions?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)"
```

## Notes

- The Plex API returns XML, not JSON. Use Python's xml.etree.ElementTree to parse.
- User ratings are stored in Plex's SQLite database, not exposed via API.
- Use viewCount, viewOffset, and lastViewedAt as proxies for "watched" status.
- Always cross-reference recommendations against the user's library to avoid duplicates.
- Genre mapping uses Wikipedia's taxonomy as the canonical reference — see `plex_to_wikipedia_genres.json`.
- After any rating change or library refresh, regenerate the profile with `generate_profile.py`.

## Script Reference

| Script | Purpose |
|---|---|
| `map_genres.py` | Maps Plex genres to Wikipedia film genre taxonomy |
| `generate_profile.py` | Creates preference profile from library + ratings |
| `generate_recommendations.py` | Generates cross-genre or genre-specific recommendations (`--genre` flag for specific) |
| `parse_library.py` | Parses XML cache into structured JSON |
| `scrape_dvds_releases.py` | Scrapes digital/DVD releases from dvdsreleasedates.com with genre data (v2.1) |

## File Structure

```
plex-recommendations/
├── SKILL.md                    # This file
├── cache/
│   ├── movies.xml              # Cached Plex movie library
│   ├── tv.xml                  # Cached Plex TV show library
│   ├── dvds_releases.json      # Merged digital/DVD releases with genre data (v2.1)
│   └── digital_releases.json   # Raw digital releases cache
├── profiles.json               # Generated preference profile (v2)
├── plex_to_wikipedia_genres.json  # Genre mapping (v2)
├── watched_movies.txt          # Movies watched + ratings
├── watch_list.txt              # Movies user wants to watch
├── map_genres.py               # Plex→Wikipedia genre mapper
├── generate_profile.py         # Preference profile generator
├── generate_recommendations.py # Recommendation engine (v2.1: includes dvds releases)
├── parse_library.py            # XML cache parser
└── scrape_dvds_releases.py     # dvdsreleasedates.com scraper (v2.1)
```
