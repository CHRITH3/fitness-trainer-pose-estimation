"""Tests for trampoline overlay trust-state styling."""

from trampoline.overlay import bed_quad_style


def test_bed_quad_style_uses_non_green_for_unreliable_states():
    trusted_color, trusted_label = bed_quad_style(0.95, "trusted")
    frozen_color, frozen_label = bed_quad_style(0.2, "frozen")
    lost_color, lost_label = bed_quad_style(0.0, "tracking_lost")
    low_color, low_label = bed_quad_style(0.4, "low_confidence")

    assert trusted_color == (0, 230, 118)
    assert trusted_label == "Bed"
    assert frozen_color != trusted_color
    assert lost_color != trusted_color
    assert low_color != trusted_color
    assert frozen_label == "Bed frozen"
    assert lost_label == "Bed lost"
    assert low_label == "Bed low"
