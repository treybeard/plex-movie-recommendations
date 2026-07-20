#!/usr/bin/env python3
"""
Map Plex library genres to Wikipedia Film/TV genre taxonomy (from List_of_genres wiki).

Produces a JSON file mapping every Plex genre tag to the canonical film genre
hierarchy, so future recommendation scripts can weight genres properly.
"""
import json
import xml.etree.ElementTree as ET
from collections import defaultdict

SKILL_DIR = "/Users/trey/.hermes/profiles/aether/skills/media/plex-recommendations"
CACHE_DIR = f"{SKILL_DIR}/cache"

# Wikipedia Film/TV Genre Taxonomy (from List_of_genres)
# Structure: dict where keys are super-genres and values are lists of subgenre strings

FILM_TAXONOMY = {
    # === SCRIPTED (structured as dict: super_genre -> [subgenre1, ...]) ===
    "Scripted": {
        "Action": [
            "Superhero", "Disaster", "Spy", "Martial arts", "Wuxia",
            "Girls with guns", "Heroic bloodshed",
        ],
        "Adventure": [
            "Swashbuckler", "Pirate",
        ],
        "Comedy": [
            "Action comedy", "Bromantic comedy", "Black comedy",
            "Comedy drama", "Comedy horror", "Zombie comedy",
            "Comedy thriller", "Gross out", "Mafia comedy",
            "Mockumentary", "Parody", "Spoof", "Romantic comedy",
            "Satire", "Screwball comedy", "Silent comedy",
            "Sitcom", "Sketch comedy", "Slapstick", "Surreal humour",
            "Whimsical", "Mo lei tau", "Commedia all'italiana",
            "Commedia sexy all'italiana", "Sex comedy",
            "Comedy of remarriage",
        ],
        "Crime": [
            "Detective", "Film noir", "Neo-noir", "Gangster", "Mafia",
            "Heist", "Mystery", "Vigilante", "Poliziotteschi",
            "Hood film", "Yakuza", "Gokudō", "Mumbai underworld",
            "Heroic bloodshed", "Mafia comedy",
        ],
        "Drama": [
            "Docudrama", "Legal drama", "Medical drama",
            "Melodrama", "Military drama", "Philosophical drama",
            "Psychological drama", "Political drama", "Teen drama",
        ],
        "Fantasy": [
            "Contemporary fantasy", "Urban fantasy", "Dark fantasy",
            "High fantasy", "Epic fantasy", "Fantasy comedy",
            "Fairy tale", "Historical fantasy", "Magic realism",
            "Science fantasy", "Fantastique",
        ],
        "Horror": [
            "Found footage", "Ghost", "Monster", "Vampire",
            "Werewolf", "Kaiju", "Psychological horror", "Folk horror",
            "Satanic horror", "Slasher", "Splatter", "Zombie",
            "Art horror", "Body horror", "Cannibal", "Comedy horror",
            "Eco horror", "Fantastique", "Holiday horror",
            "Horror drama", "Lovecraftian horror", "Mumblegore",
            "Natural horror", "Psycho-biddy", "Religious horror",
            "Sci-fi horror",
        ],
        "Musical": [
            "Jukebox musical", "Sung-through musical",
        ],
        "Romance": [
            "Gothic romance", "Paranormal romance", "Period romance",
            "Romance drama", "Romantic thriller",
        ],
        "Science Fiction": [
            "Cyberpunk", "Dieselpunk", "Dystopian", "Military sci-fi",
            "Post-apocalyptic", "Space opera", "Steampunk",
            "Tech noir", "Utopian", "Sci-fi comedy", "Science fantasy",
            "Gothic sci-fi", "New Wave sci-fi", "Parallel universe",
            "Tokusatsu",
        ],
        "Thriller": [
            "Mystery thriller", "Political thriller",
            "Psychological thriller", "Techno-thriller",
        ],
        "Western": [
            "Epic Western", "Empire Western", "Marshal Western",
            "Outlaw Western", "Revenge Western", "Revisionist Western",
            "Science fiction Western", "Space Western", "Spaghetti Western",
        ],
    },
    # === FLAT LISTS (super_genre -> [genre1, genre2, ...]) ===
    "Animation": [
        "Traditional animation", "CGI", "Stop motion",
        "Claymation", "Puppetry", "Animated series",
    ],
    "Documentary": [
        "Television documentary", "Concert film", "Music television",
    ],
    "Reality": [
        "Court show", "Dramality", "Talk show", "Game show",
        "Variety show", "Stand-up comedy",
    ],
    "Biopic": [
        "Historical epic", "Historical event", "Historical fiction",
        "Period piece", "Costume drama", "Alternate history",
    ],
    "History": [
        "Historical fiction", "Period piece", "Biopic",
        "Historical epic", "Documentary",
    ],
    "War": [
        "Military drama", "Military fiction", "Military sci-fi",
    ],
    "Family": [
        "Fairy tale", "Comedy drama", "Fantasy", "Adventure",
    ],
    "Sports": [],
    "Biography": [
        "Historical epic", "Historical event", "Historical fiction",
        "Period piece", "Costume drama", "Alternate history",
    ],
    "Music": [
        "Jukebox musical", "Musical documentary", "Concert film",
    ],
    "Sport": [],  # subgenre of drama/documentary, no specific wiki entry
    "Short": [],  # not a story genre
    "Drama-Sports": [
        "Melodrama", "Psychological drama", "Teen drama",
    ],
}


def build_flat_index():
    """Build a flat dict of lowercase genre -> (super_genre, matched_genre) for fast lookup."""
    flat_index = {}

    # Scripted genres: dict of super -> [subs]
    for super_genre, subgenres in FILM_TAXONOMY.get("Scripted", {}).items():
        # The super_genre itself is a valid match
        super_lower = super_genre.lower()
        if super_lower not in flat_index:
            flat_index[super_lower] = []
        flat_index[super_lower].append((super_genre, super_genre))

        for sub in subgenres:
            sub_lower = sub.lower()
            if sub_lower not in flat_index:
                flat_index[sub_lower] = []
            flat_index[sub_lower].append((super_genre, sub))

    # Flat list genres: list of [genres]
    for super_genre, genres in FILM_TAXONOMY.items():
        if super_genre == "Scripted":
            continue
        super_lower = super_genre.lower()
        if super_lower not in flat_index:
            flat_index[super_lower] = []
        flat_index[super_lower].append((super_genre, super_genre))

        for genre in genres:
            genre_lower = genre.lower()
            if genre_lower not in flat_index:
                flat_index[genre_lower] = []
            flat_index[genre_lower].append((super_genre, genre))

    return flat_index


def map_plex_genre_to_wikipedia(plex_genre, flat_index):
    """
    Map a single Plex genre tag to Wikipedia film genre hierarchy.

    Strategy:
    1. Exact match (case-insensitive)
    2. If compound Plex genre (e.g. "Action Comedy"), split and map each part,
       returning the first/best match
    3. No fuzzy/partial word matching — too noisy with overlapping words
    """
    plex_lower = plex_genre.lower()

    # Exact match
    if plex_lower in flat_index:
        matches = flat_index[plex_lower]
        return matches[0]  # (super_genre, matched_genre)

    # Compound Plex genre: take the first word and match that
    words = plex_genre.split()
    if len(words) > 1:
        # Try first word
        first_word = words[0].lower()
        if first_word in flat_index:
            return flat_index[first_word][0]
        # Try second word (sometimes genre comes second, e.g. "Comedy Fantasy")
        second_word = words[1].lower()
        if second_word in flat_index:
            return flat_index[second_word][0]

    return None, None


def main():
    # Parse movies cache
    movies_file = f"{CACHE_DIR}/movies.xml"
    tree = ET.parse(movies_file)
    root = tree.getroot()
    total = int(root.get("size", 0))

    # Collect all unique Plex genres
    all_plex_genres = set()
    genre_counts = defaultdict(int)

    for video in root.findall(".//Video"):
        for g in video.findall("Genre"):
            tag = g.get("tag", "").strip()
            if tag:
                all_plex_genres.add(tag)
                genre_counts[tag] += 1

    print(f"Parsing {total} movies...")
    print(f"Found {len(all_plex_genres)} unique Plex genres")

    # Build fast lookup index
    flat_index = build_flat_index()

    # Map each Plex genre to Wikipedia film genre
    mapping = {}
    unmapped = []

    for plex_genre in sorted(all_plex_genres):
        super_genre, film_genre = map_plex_genre_to_wikipedia(plex_genre, flat_index)

        entry = {
            "plex_genre": plex_genre,
            "count": genre_counts[plex_genre],
            "percentage": round(genre_counts[plex_genre] / total * 100, 1),
            "wikipedia_super_genre": super_genre,
            "wikipedia_genre": film_genre,
        }
        mapping[plex_genre] = entry

        if not super_genre:
            unmapped.append(plex_genre)

    # Output
    output = {
        "metadata": {
            "source": "Plex Movies library (cache/movies.xml)",
            "total_movies": total,
            "total_plex_genres": len(all_plex_genres),
            "mapped_genres": len(all_plex_genres) - len(unmapped),
            "unmapped_genres": len(unmapped),
        },
        "genre_mapping": mapping,
        "summary_by_super_genre": {},
    }

    # Aggregate counts by Wikipedia super genre
    for plex_genre, entry in mapping.items():
        sg = entry["wikipedia_super_genre"]
        if sg is None:
            sg = "Unclassified"
        if sg not in output["summary_by_super_genre"]:
            output["summary_by_super_genre"][sg] = {
                "plex_genres": [],
                "total_count": 0,
                "film_genre": None,
            }
        output["summary_by_super_genre"][sg]["plex_genres"].append(plex_genre)
        output["summary_by_super_genre"][sg]["total_count"] += genre_counts[plex_genre]
        if entry["wikipedia_genre"]:
            output["summary_by_super_genre"][sg]["film_genre"] = entry["wikipedia_genre"]

    # Sort by total_count descending
    output["summary_by_super_genre"] = dict(
        sorted(output["summary_by_super_genre"].items(),
               key=lambda x: x[1]["total_count"], reverse=True)
    )

    if unmapped:
        output["unmapped"] = unmapped
        print(f"\nUnmapped Plex genres ({len(unmapped)}):")
        for g in unmapped:
            print(f"  - {g}")
    else:
        print("\nAll Plex genres mapped to Wikipedia film genres!")

    # Print summary
    print(f"\n=== Wikipedia Super-Genre Summary ===")
    for sg, data in output["summary_by_super_genre"].items():
        n_plex = len(data["plex_genres"])
        film_genre = data["film_genre"] or "(compound/unmapped)"
        plex_list = ", ".join(sorted(data["plex_genres"]))
        print(f"\n  {sg}: {data['total_count']} films ({data['total_count']/total*100:.0f}%)")
        print(f"    Wikipedia genre: {film_genre}")
        print(f"    Plex genres: {plex_list}")

    # Write output
    out_path = f"{SKILL_DIR}/plex_to_wikipedia_genres.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nMapping written to: {out_path}")


if __name__ == "__main__":
    main()
