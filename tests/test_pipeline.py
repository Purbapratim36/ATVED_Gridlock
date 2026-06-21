"""Unit tests for the end-to-end pipeline components."""

import pytest
from unittest.mock import Mock

from atved.plate.pipeline import PlateRecognitionPipeline
from atved.plate.post_correct import PostCorrector, CorrectedPlate
from atved.config import PlatePostCorrectionConfig

def test_plate_post_correction_india_format():
    """Test OCR error correction against Indian license plate regex."""
    config = PlatePostCorrectionConfig(jurisdiction="IN")
    corrector = PostCorrector(config)
    
    # Common OCR error: 'O' instead of '0', 'I' instead of '1'
    raw_ocr = "MH12AB1O3I"
    
    result = corrector.correct(raw_ocr, jurisdiction="IN")
    
    assert result.format_matched is True
    assert result.corrected_text == "MH12AB1031"
    assert result.correction_confidence > 0.5

def test_unified_classifier_calibration():
    """Test that temperature scaling properly reduces overconfidence."""
    from atved.violations.classifier import UnifiedClassifier
    
    classifier = UnifiedClassifier(temperature=2.0)
    
    # Raw confidence of 0.999 (logit = 6.9)
    # Scaled logit = 3.45 -> sigmoid(3.45) = 0.969
    calibrated = classifier._calibrate_score(0.999)
    
    assert calibrated < 0.999
    assert calibrated > 0.95
