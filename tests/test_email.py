"""
Transactional email stub behaviour — without SENDGRID_API_KEY the dispatch must
degrade gracefully to a no-op that returns True (never raises, never blocks).

Runnable with pytest OR directly:  python tests/test_email.py
"""

from app.services import email


def test_send_sync_stubs_when_unconfigured(monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("SENDGRID_API_KEY", "")
    assert email.send_email_sync("user@example.com", "Hi", "<p>hi</p>") is True
    get_settings.cache_clear()


def test_welcome_template_renders():
    subject, html = email._render_welcome("Ada")
    assert "Ada" in html
    assert "Welcome" in subject


def test_rebalance_template_renders():
    subject, html = email._render_rebalance_approval("Momentum NSE", "Boost of 50,000 queued.")
    assert "Momentum NSE" in subject
    assert "Boost of 50,000 queued." in html


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            if "monkeypatch" in fn.__code__.co_varnames:
                continue
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed")
