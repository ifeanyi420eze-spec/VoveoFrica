import re
import unicodedata


_PROFANITY = (
    "arse",
    "ass",
    "asshole",
    "bastard",
    "bitch",
    "bullshit",
    "crap",
    "cunt",
    "damn",
    "dick",
    "douche",
    "fuck",
    "motherfucker",
    "piss",
    "prick",
    "shit",
    "slut",
    "twat",
    "whore",
)
_CHAR_VARIANTS = {
    "a": "a4@",
    "b": "b8",
    "c": "c(",
    "e": "e3",
    "g": "g9",
    "i": "i1!|",
    "l": "l1!|",
    "o": "o0",
    "s": "s5$",
    "t": "t7+",
    "z": "z2",
}


def _compile_profanity_pattern(word):
    letters = []
    for character in word:
        variants = _CHAR_VARIANTS.get(character, character)
        letters.append(f"[{re.escape(variants)}]")
    return re.compile(
        r"(?<![a-z0-9])[\W_]*"
        + r"[\W_]*".join(letters)
        + r"[\W_]*(?![a-z0-9])",
        re.IGNORECASE,
    )


_PROFANITY_PATTERNS = tuple(_compile_profanity_pattern(word) for word in _PROFANITY)


def contains_profanity(text):
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(
        character for character in normalized
        if not unicodedata.combining(character)
    ).casefold()
    return any(pattern.search(normalized) for pattern in _PROFANITY_PATTERNS)
