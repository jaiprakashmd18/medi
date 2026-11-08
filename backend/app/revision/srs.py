"""SM-2 style spaced repetition scheduling.

Ratings: 0 = Again, 1 = Hard, 2 = Good, 3 = Easy.
"""
from __future__ import annotations

from datetime import timedelta

from app.models import Flashcard, utcnow


def schedule(card: Flashcard, rating: int) -> Flashcard:
    if rating not in (0, 1, 2, 3):
        raise ValueError("rating must be 0-3")
    q = {0: 1, 1: 3, 2: 4, 3: 5}[rating]  # map to SM-2 quality
    if rating == 0:
        card.repetitions = 0
        card.lapses += 1
        card.interval_days = 10 / (24 * 60)  # 10 minutes
    else:
        if card.repetitions == 0:
            card.interval_days = 1 if rating < 3 else 3
        elif card.repetitions == 1:
            card.interval_days = 3 if rating == 1 else 6
        else:
            mult = card.ease * (0.8 if rating == 1 else 1.0) * (1.3 if rating == 3 else 1.0)
            card.interval_days = max(1.0, round(card.interval_days * mult, 2))
        card.repetitions += 1
    card.ease = max(1.3, card.ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)))
    now = utcnow()
    card.last_reviewed_at = now
    card.due_at = now + timedelta(days=card.interval_days)
    return card
