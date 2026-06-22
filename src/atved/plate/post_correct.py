"""
Jurisdiction-based plate text post-correction.

Fixes common OCR misreads (0↔O, 1↔I, 5↔S, 8↔B) and validates
the corrected text against known plate format patterns for the
configured jurisdiction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

from atved.config import PlatePostCorrectionConfig

logger = structlog.get_logger(__name__)

# Common OCR character confusions.  Keys are the misread character;
# values are the likely corrections depending on context (alpha vs digit).
_ALPHA_TO_DIGIT = {"O": "0", "I": "1", "S": "5", "B": "8", "Z": "2", "G": "6"}
_DIGIT_TO_ALPHA = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "6": "G"}


@dataclass(frozen=True, slots=True)
class CorrectedPlate:
    """Result of post-correction with format matching."""

    original_text: str
    corrected_text: str
    format_matched: bool
    format_name: str | None
    correction_confidence: float  # 1.0 if no correction needed; lower if chars were swapped


class PostCorrector:
    """
    Applies OCR error correction heuristics and validates against
    jurisdiction-specific plate format patterns.

    Strategy:
        1. Normalise the raw OCR text (strip spaces, uppercase).
        2. Try matching against all known patterns for the jurisdiction.
        3. If no match, try common character substitutions and re-match.
        4. Return the best-matching corrected text, or the normalised
           original if no pattern matches.
    """

    def __init__(self, config: PlatePostCorrectionConfig) -> None:
        self._jurisdiction = config.jurisdiction
        self._formats: dict[str, list[re.Pattern[str]]] = {}

        for country, fmt in config.plate_formats.items():
            self._formats[country] = [re.compile(p) for p in fmt.patterns]

    def correct(self, text: str, jurisdiction: str | None = None) -> CorrectedPlate:
        """
        Attempt to correct OCR output and match a plate format.

        Parameters
        ----------
        text:
            Raw OCR output string.
        jurisdiction:
            ISO 3166-1 alpha-2 country code. Falls back to configured default.
        """
        jur = jurisdiction or self._jurisdiction
        normalised = self._normalise(text)

        # 1. Direct match
        match_result = self._try_match(normalised, jur)
        if match_result:
            return CorrectedPlate(
                original_text=text,
                corrected_text=normalised,
                format_matched=True,
                format_name=match_result,
                correction_confidence=1.0,
            )

        # 2. Try substitution variants
        best_corrected = normalised
        best_confidence = 0.0
        best_format: str | None = None

        variants = self._generate_variants(normalised)
        for variant, n_changes in variants:
            match_result = self._try_match(variant, jur)
            if match_result:
                confidence = max(0.5, 1.0 - 0.1 * n_changes)
                if confidence > best_confidence:
                    best_corrected = variant
                    best_confidence = confidence
                    best_format = match_result

        if best_format:
            return CorrectedPlate(
                original_text=text,
                corrected_text=best_corrected,
                format_matched=True,
                format_name=best_format,
                correction_confidence=best_confidence,
            )

        # 3. No match — return normalised text with low confidence
        return CorrectedPlate(
            original_text=text,
            corrected_text=normalised,
            format_matched=False,
            format_name=None,
            correction_confidence=0.3,
        )

    def _normalise(self, text: str) -> str:
        """Strip whitespace, uppercase, remove non-alphanumeric."""
        return re.sub(r"[^A-Z0-9]", "", text.upper().strip())

    def _try_match(self, text: str, jurisdiction: str) -> str | None:
        """Try to match text against patterns for the given jurisdiction."""
        patterns = self._formats.get(jurisdiction, [])
        # Also try with spaces inserted at typical positions
        spaced_variants = [text, self._insert_spaces(text, jurisdiction)]

        for variant in spaced_variants:
            for i, pattern in enumerate(patterns):
                if pattern.match(variant):
                    return f"{jurisdiction}_format_{i}"
        return None

    def _insert_spaces(self, text: str, jurisdiction: str) -> str:
        """Insert spaces at jurisdiction-typical positions for matching."""
        if jurisdiction == "IN" and len(text) >= 9:
            # Indian plates: XX 00 XX 0000
            return f"{text[:2]} {text[2:4]} {text[4:6]} {text[6:]}"
        return text

    def _generate_variants(
        self, text: str
    ) -> list[tuple[str, int]]:
        """
        Generate plausible OCR correction variants.

        For each position, try swapping confusable characters.
        Returns (variant_text, number_of_changes) tuples.
        Limits to variants with at most 2 changes to avoid explosion.
        """
        variants: list[tuple[str, int]] = []
        chars = list(text)

        # Single-character swaps
        for i, ch in enumerate(chars):
            for swap in self._get_swaps(ch):
                variant = chars.copy()
                variant[i] = swap
                variants.append(("".join(variant), 1))

        # Two-character swaps (pairwise)
        if len(chars) <= 12:
            for i in range(len(chars)):
                for j in range(i + 1, len(chars)):
                    for swap_i in self._get_swaps(chars[i]):
                        for swap_j in self._get_swaps(chars[j]):
                            variant = chars.copy()
                            variant[i] = swap_i
                            variant[j] = swap_j
                            variants.append(("".join(variant), 2))

        return variants

    @staticmethod
    def _get_swaps(ch: str) -> list[str]:
        """Get possible OCR confusion swaps for a character."""
        swaps = []
        if ch in _ALPHA_TO_DIGIT:
            swaps.append(_ALPHA_TO_DIGIT[ch])
        if ch in _DIGIT_TO_ALPHA:
            swaps.append(_DIGIT_TO_ALPHA[ch])
        return swaps
