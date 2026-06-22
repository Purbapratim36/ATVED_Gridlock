class VehicleTypeViolationMap:
    """
    Maps vehicle classes to the violations they are eligible for.
    Prevents false positives (e.g. triple-riding on an auto-rickshaw).
    """
    def __init__(self):
        # Base mapping according to Indian traffic rules
        self.eligible_violations = {
            'motorcycle': ['TRIPLE_RIDING', 'HELMET', 'SPEEDING', 'WRONG_SIDE', 'RED_LIGHT', 'STOP_LINE', 'ILLEGAL_PARKING'],
            'bicycle': ['HELMET', 'WRONG_SIDE', 'RED_LIGHT', 'STOP_LINE'],
            'car': ['SEATBELT', 'SPEEDING', 'WRONG_SIDE', 'RED_LIGHT', 'STOP_LINE', 'ILLEGAL_PARKING'],
            'truck': ['SPEEDING', 'WRONG_SIDE', 'RED_LIGHT', 'STOP_LINE', 'ILLEGAL_PARKING'], # Overloading future
            'bus': ['SPEEDING', 'WRONG_SIDE', 'RED_LIGHT', 'STOP_LINE', 'ILLEGAL_PARKING'],
            'lcv': ['SEATBELT', 'SPEEDING', 'WRONG_SIDE', 'RED_LIGHT', 'STOP_LINE', 'ILLEGAL_PARKING'],
            'three_wheeler': ['SPEEDING', 'WRONG_SIDE', 'RED_LIGHT', 'STOP_LINE', 'ILLEGAL_PARKING'], # Auto-rickshaw
            'tractor': ['SPEEDING', 'WRONG_SIDE', 'RED_LIGHT', 'STOP_LINE', 'ILLEGAL_PARKING'],
            'person': [] # Pedestrians cannot get vehicular challans
        }
        
    def is_eligible(self, vehicle_class, violation_type):
        """
        Returns True if the vehicle_class is eligible to be ticketed for violation_type.
        """
        if not vehicle_class:
            return True # Fallback: if class is unknown, allow detection
            
        vehicle_class = vehicle_class.lower()
        if vehicle_class not in self.eligible_violations:
            # If we detect a completely unknown class, allow by default or drop? 
            # Allow by default to prevent silent drops, but flag it.
            return True
            
        return violation_type in self.eligible_violations[vehicle_class]

vehicle_violation_map = VehicleTypeViolationMap()
