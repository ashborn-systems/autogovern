"""Count word frequencies in text."""


def count_words(text: str) -> dict[str, int]:
    """Return a mapping of lowercase word to occurrence count."""
    counts: dict[str, int] = {}
    for word in text.split():
        key = word.lower().strip(".,!?;:\"'")
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts
