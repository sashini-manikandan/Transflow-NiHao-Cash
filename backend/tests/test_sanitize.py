"""PII scrubbing before LLM context."""

from app.services.sanitize import mask_pii_text, sanitize_for_llm


def test_long_digit_runs_are_masked():
    assert "[account]" in mask_pii_text("NETFLIX.COM*4471890123 AMSTERDAM")
    assert "4471890123" not in mask_pii_text("NETFLIX.COM*4471890123 AMSTERDAM")


def test_emails_are_masked():
    assert mask_pii_text("contact amina@demo.billwise.ai please") == (
        "contact [email] please"
    )


def test_nested_payloads_are_scrubbed():
    payload = {
        "data": {
            "series": [{"merchant": "WISE TO ACCRA 991122334455", "note": "ok"}],
            "count": 1,
        }
    }
    cleaned = sanitize_for_llm(payload)
    assert "[account]" in cleaned["data"]["series"][0]["merchant"]
    assert cleaned["data"]["count"] == 1


def test_short_amounts_are_not_treated_as_accounts():
    """Ordinary money figures must survive; only long digit runs are dangerous."""
    assert mask_pii_text("AED 3480.50 due") == "AED 3480.50 due"
