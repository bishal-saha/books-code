"""A toy sampler: how temperature reshapes next-token probabilities. No model is called."""

import math
import random
from collections import Counter

# Made-up scores for the word after "Consumers may return unused items"; not from any model.
SCORES = {"within": 3.0, "up": 2.0, "for": 1.0, "before": 0.5}


def probabilities(scores: dict[str, float], temperature: float) -> dict[str, float]:
    """Divide each score by the temperature, then turn the scores into probabilities."""
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    scaled = {token: score / temperature for token, score in scores.items()}
    top = max(scaled.values())
    weights = {token: math.exp(value - top) for token, value in scaled.items()}
    total = sum(weights.values())
    return {token: weight / total for token, weight in weights.items()}


def sample(scores: dict[str, float], temperature: float, picks: int, seed: int = 0) -> Counter:
    """Pick the next token `picks` times; a fixed seed makes the toy repeatable."""
    probs = probabilities(scores, temperature)
    rng = random.Random(seed)
    return Counter(rng.choices(list(probs), weights=list(probs.values()), k=picks))


def main() -> None:
    for temperature in (0.2, 1.0, 2.0):
        probs = probabilities(SCORES, temperature)
        picks = sample(SCORES, temperature, picks=100)
        cells = "  ".join(f"{t} {probs[t]:.2f} ({picks[t]})" for t in SCORES)
        print(f"temperature {temperature}:  {cells}")


if __name__ == "__main__":
    main()
