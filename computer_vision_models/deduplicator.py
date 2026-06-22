import time

class ViolationDeduplicator:
    def __init__(self, cooldown_seconds=30):
        self.cooldown_seconds = cooldown_seconds
        self.history = {}  # {(track_id, violation_type, plate_text): timestamp}

    def is_duplicate(self, track_id, violation_type, plate_text=None):
        """
        Returns True if this exact violation was triggered within the cooldown period.
        Otherwise, registers it and returns False.
        """
        now = time.time()
        # Clean up old entries to prevent memory leak
        self.history = {k: v for k, v in self.history.items() if now - v < self.cooldown_seconds}

        key = (track_id, violation_type, plate_text)
        
        if key in self.history:
            return True
        
        self.history[key] = now
        return False
