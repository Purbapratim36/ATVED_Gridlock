def apply_positional_correction(text):
    """
    Applies deterministic positional corrections for Indian license plates.
    Format: State(2 chars) District(2 chars) Series(1-3 chars) Number(4 chars)
    """
    if not text:
        return text

    # Strip whitespace/specials
    import re
    cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())

    if len(cleaned) < 6:
        return cleaned

    corrected = list(cleaned)

    # Dictionary mappings for common OCR confusions
    letter_map = {'0': 'O', '1': 'I', '5': 'S', '8': 'B', '2': 'Z', '6': 'G', '7': 'T', '3': 'J'}
    digit_map = {'O': '0', 'I': '1', 'S': '5', 'B': '8', 'Z': '2', 'G': '6', 'T': '7', 'L': '1', 'Q': '0', 'J': '3', 'D': '0', 'A': '4'}

    # 1. State Code (Positions 0-1) MUST be letters
    for i in range(min(2, len(corrected))):
        if corrected[i] in letter_map:
            corrected[i] = letter_map[corrected[i]]

    # 2. District Code (Positions 2-3) MUST be digits
    for i in range(2, min(4, len(corrected))):
        if corrected[i] in digit_map:
            corrected[i] = digit_map[corrected[i]]

    # 3. Final 4 characters (Number) MUST be digits
    # Only apply if string is long enough
    if len(corrected) >= 8:
        for i in range(len(corrected)-4, len(corrected)):
            if corrected[i] in digit_map:
                corrected[i] = digit_map[corrected[i]]

    return "".join(corrected)
