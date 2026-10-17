from app.services.merchants import normalize_merchant, service_family


def test_strips_processor_noise_and_reference_numbers():
    assert normalize_merchant("NETFLIX.COM*4471 AMSTERDAM NL").key == "Netflix"
    assert normalize_merchant("SQ *SPOTIFY AB STOCKHOLM").key == "Spotify"
    assert normalize_merchant("PAYPAL *NOTION LABS INC").key == "Notion"


def test_same_service_different_descriptors_collapse_to_one_key():
    variants = [
        "NETFLIX.COM*4471 AMSTERDAM NL",
        "NETFLIX INTL BV SUBSCRIPTION",
        "netflix.com 25/03",
    ]
    assert len({normalize_merchant(v).key for v in variants}) == 1


def test_dates_and_trailing_country_codes_removed():
    assert normalize_merchant("DU TELECOM POSTPAID BILL 12/04 AE").key == "du Telecom"


def test_unknown_merchant_is_title_cased_not_dropped():
    result = normalize_merchant("ZAYED CAMPUS LAUNDRY 8812")
    assert result.key == "Zayed Campus Laundry"
    assert result.family is None


def test_service_family_groups_competing_services():
    assert service_family("Netflix") == service_family("Disney+") == "video_streaming"
    assert service_family("Spotify") == "music_streaming"


def test_empty_description_does_not_crash():
    assert normalize_merchant("").key
    assert normalize_merchant("   ").key
