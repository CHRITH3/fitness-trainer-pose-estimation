from __future__ import annotations

from app import app


def test_trampoline_page_smoke() -> None:
    client = app.test_client()
    response = client.get("/trampoline")

    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert 'id="upload-panel"' in html
    assert 'id="timeline-panel"' in html
    assert 'id="detail-panel"' in html
