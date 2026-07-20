---
name: plex-recommendations
description: >
  Recommend sci-fi movies from the user's Plex library while excluding
  movies they've already watched. Includes functionality to mark movies
  as watched so they are filtered from future recommendations.
version: 1.0.0
author: Hermes
tags: [media, plex, recommendations, sci-fi]
---

# Plex Recommendations

## Connection Details

Plex server: `http://10.0.0.130:32400`
API token: stored in `~/.hermes/profiles/aether/api_keys/plex.txt`
Library sections: Movies (section 9), TV Shows (section 2)
- **DO NOT scan Vuze (section 5)** — it is a temporary staging area where movies sit until the user decides whether to promote them to the main libraries.

## User Profile / Viewing Preferences

### Sci-Fi Preference Baseline
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

### User's Actual Watched Movies (from watched_movies.txt)
- Coherence (2013) — watched
- Upgrade (2018) — watched
- Stowaway (2021) — watched

### Watched Movies Tracking
Movies the user has actively marked as watched (not just in library):
- **Coherence (2013)** — user has seen this
- **Upgrade (2018)** — user has seen this
- **Stowaway (2021)** — user has seen this

These are excluded from recommendations even though they may not be in the Plex library.

## How It Works

### Library Scanning & Caching

By default, the skill keeps a local cache of the library to avoid repeated API calls. When the user updates their library, run a fresh scan.

**Scan command:**
```bash
curl -s "http://10.0.0.130:32400/library/sections/9/all?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)" -o ~/.hermes/profiles/aether/skills/media/plex-recommendations/cache/movies.xml
curl -s "http://10.0.0.130:32400/library/sections/2/all?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)" -o ~/.hermes/profiles/aether/skills/media/plex-recommendations/cache/tv.xml
echo "Library scanned and cached."
```

**Important:** Only scan **Movies** (section 9) and **TV Shows** (section 2). Do NOT scan Vuze (section 5) — it is a temporary staging area where movies sit until the user decides whether to promote them to the main libraries.

### Step 2: Parse Cached Library
Parse the XML files to find all titles, genres, and metadata.

### Step 3: Identify New Content
Compare the new scan against the existing cache. Any titles that appear in the new scan but not in the old cache are "new." Treat all new titles as having a rating of **7/10** for recommendation purposes.

### Step 4: Filter Out Watched
Exclude movies/TV shows from recommendations that:
- Are in the watched_movies.txt file (user has already seen them)
- The user has explicitly marked as watched

### Step 5: Generate Recommendations
Search the web for:
- Similar sci-fi movies NOT in the user's library
- Movies from the same subgenre as their favorites
- Critically acclaimed sci-fi from 2024-2026

### Step 6: Present Results
Return 10 recommendations with:
- Title, year, brief description
- Which subgenre it matches (time travel, space, AI, etc.)
- Why the user might like it based on their library

**When the user says "refresh my Plex library" or "update my library":**
1. Re-run the scan commands above
2. Compare against the old cache to find new content
3. Mark new content as 7/10
4. Recalculate recommendations with the updated library
5. Save the new cache to replace the old one
6. Report back what was added: "Found X new movies, Y new shows in your library."

## Marking a Movie as Watched

When the user says "I've seen [movie name]" or "I've already watched [movie name]", add the movie to the watched list:

```bash
# Add to watched list file with rating
echo "[Movie Name] (year) - user has seen | liked" >> ~/.hermes/profiles/aether/skills/media/plex-recommendations/watched_movies.txt
# or
echo "[Movie Name] (year) - user has seen | disliked" >> ~/.hermes/profiles/aether/skills/media/plex-recommendations/watched_movies.txt
# or
echo "[Movie Name] (year) - user has seen | meh" >> ~/.hermes/profiles/aether/skills/media/plex-recommendations/watched_movies.txt
# or
echo "[Movie Name] (year) - user has seen | couldnt_finish" >> ~/.hermes/profiles/aether/skills/media/plex-recommendations/watched_movies.txt
```

### Rating Format
- `liked` — user enjoyed it and would watch similar
- `disliked` — user didn't enjoy it and should avoid similar
- `meh` — user had no strong opinion
- `couldnt_finish` — user couldn't finish it (strongly disliked or found it too slow)

### Watching Movies
To tell the assistant they have watched a movie, just say:
- "I've seen [movie name]"
- "I already watched [movie]"

The assistant will add it to the exclusion list for future recommendations.

### Watch List Management
When the user says "add [movie] to the watch list", add it to `watch_list.txt` in the skill directory.
When the user rates a movie in `watched_movies.txt`, automatically remove it from `watch_list.txt` if it exists there.
To manually remove a movie from the watch list, the user can say "remove [movie] from the watch list" and the assistant removes the entry from `watch_list.txt`.
To see the watch list, the user can say "what's on the watch list?" and the assistant reads `watch_list.txt`.

The watched list is stored in the skill directory so it persists across sessions.

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
- The assistant should proactively exclude movies the user has marked as watched.