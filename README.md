# Plex Movie Recommendations

A smart sci-fi movie recommendation system that learns from your Plex library and personal ratings to suggest movies you'll actually enjoy.

## How It Works

The skill analyzes your **Plex Movies** and **TV Shows** libraries to understand your preferences. Every movie in your library counts as an 8/10 — if it's in your collection, you chose it for a reason.

### Key Features

- **Library-based preferences** — All movies/shows in your Plex libraries (Movies & TV Shows sections) count toward recommendations
- **Personal ratings** — Track what you've watched and how you felt about it (liked, disliked, meh, couldn't finish)
- **Watch list** — Keep track of movies you want to see later
- **Smart filtering** — Automatically excludes movies from your library and watched content from recommendations
- **Manual refresh** — Scan your library whenever it updates to catch new additions

## Setup

### 1. Configure Plex Connection

Plex server details are stored in the skill:

```
Plex server: http://10.0.0.130:32400
API token: ~/.hermes/profiles/aether/api_keys/plex.txt
```

### 2. Library Sections

| Section | Purpose | Scanned? |
|---------|---------|----------|
| **Movies (section 9)** | Your main movie library | ✅ Yes |
| **TV Shows (section 2)** | Your TV show library | ✅ Yes |
| **Vuze (section 5)** | Temporary staging area | ❌ No |

> **Vuze section is skipped** — movies sit here until you decide whether to promote them to the main libraries.

### 3. Initial Scan

Run a library scan to populate the cache:

```bash
curl -s "http://10.0.0.130:32400/library/sections/9/all?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)" -o cache/movies.xml
curl -s "http://10.0.0.130:32400/library/sections/2/all?X-Plex-Token=$(cat ~/.hermes/profiles/aether/api_keys/plex.txt)" -o cache/tv.xml
```

## File Structure

```
plex-movie-recommendations/
├── SKILL.md              # Skill instructions for the assistant
├── README.md             # This file
├── cache/
│   ├── movies.xml        # Cached Plex movie library
│   └── tv.xml            # Cached Plex TV show library
├── watched_movies.txt    # Movies you've watched + your ratings
└── watch_list.txt        # Movies you want to watch
```

## Usage

### Movie Interactions

| Command | Action |
|---------|--------|
| "Recommend some sci-fi" | Generate new recommendations based on library + ratings |
| "I've seen [movie] — liked it" | Add to watched list with `liked` rating |
| "I've seen [movie] — hated it" | Add to watched list with `disliked` rating |
| "I've seen [movie] — meh" | Add to watched list with `meh` rating |
| "I've seen [movie] — couldn't finish" | Add to watched list with `couldnt_finish` rating |
| "Add [movie] to the watch list" | Add to watch list |
| "What's on the watch list?" | Show current watch list |
| "Remove [movie] from watch list" | Remove from watch list |

### Library Management

| Command | Action |
|---------|--------|
| "Refresh my Plex library" | Re-scan Movies & TV Shows, detect new content, update cache |
| "Show my watch list" | Display watched movies and ratings |
| "What's on the watch list?" | Display movies you want to watch |

### Rating System

When you rate a movie, it is **automatically removed** from the watch list if it exists there.

| Rating | Meaning | Effect on Future Recommendations |
|--------|---------|-----------------------------------|
| `liked` | You enjoyed it | Seek out similar movies |
| `disliked` | You didn't like it | Avoid similar movies |
| `meh` | No strong opinion | Use with caution |
| `couldnt_finish` | Couldn't get through it | Avoid completely |

## Recommendations

When generating recommendations, the skill:

1. **Reads your library** to understand what genres, themes, and styles you prefer
2. **Reads your ratings** to understand what you actually liked vs. what you just collected
3. **Filters out** everything in your library, your Vuze staging area, and watched movies
4. **Searches the web** for similar, critically acclaimed sci-fi that isn't in your collection
5. **Presents 10 recommendations** with genre tags and reasoning

## Tips

- Your library is the source of truth — every movie you've added counts as a preference
- Unwatched movies still count — you may have downloaded something you watched elsewhere
- Keep your library fresh by refreshing when you add new content
- Your ratings get better over time — the more you use this, the better the recommendations become
