"""
Tests for Vision-Assisted Self-Healing Form Automation.
"""

from __future__ import annotations

from agent import vision_applier


def test_vision_coordinate_parsing():
    json_resp = '{"x": 450, "y": 620, "confidence": 0.95}'
    coords = vision_applier.parse_vision_coordinates(json_resp)
    assert coords == (450, 620)

    tuple_resp = "The button is located at (320, 510)"
    coords_tuple = vision_applier.parse_vision_coordinates(tuple_resp)
    assert coords_tuple == (320, 510)

    empty = vision_applier.parse_vision_coordinates("")
    assert empty is None


def test_vision_prompt_synthesis():
    prompt = vision_applier.synthesize_vision_prompt("Years of Experience Slider", page_title="Stripe Careers")
    assert "Years of Experience Slider" in prompt
    assert "Stripe Careers" in prompt
    assert "selector_hint" in prompt


def test_selector_cache_persistence(tmp_path, monkeypatch):
    test_cache = tmp_path / "test_selector_cache.json"
    monkeypatch.setattr(vision_applier, "CACHE_FILE", test_cache)

    assert vision_applier.get_cached_selector("boards.greenhouse.io", "gender") is None

    vision_applier.save_cached_selector("https://boards.greenhouse.io/stripe/jobs/123", "gender", "#custom_gender_select")
    cached = vision_applier.get_cached_selector("boards.greenhouse.io", "gender")
    assert cached == "#custom_gender_select"

