from app.domains.lead_import.validators import evaluate_lead_batch, lead_import_policy


def _valid_row(index: int) -> dict:
    return {"email": f"lead{index}@example.com", "phone": f"+1555000{index:04d}"}


def test_any_two_valid_contact_channels_are_accepted_and_bad_row_is_rejected_individually():
    batch = evaluate_lead_batch([
        *[_valid_row(index) for index in range(48)],
        {"email": "email-whatsapp@example.com", "whatsapp": "+15550000001"},
        {"phone": "+15550000002", "whatsapp": "+15550000003"},
        {"email": "only-one@example.com"},
    ])

    assert batch["accepted_rows"] == 50
    assert batch["rejected_rows"] == 1
    assert batch["can_proceed"] is True
    assert batch["rejected"][0]["row_index"] == 50
    assert batch["rejected"][0]["reasons"] == [
        "At least two valid contactable channels are required; provide any two of email, phone, or WhatsApp"
    ]


def test_batch_does_not_proceed_when_fewer_than_fifty_rows_remain_after_rejection():
    batch = evaluate_lead_batch([
        *[_valid_row(index) for index in range(49)],
        {"first_name": "No contact channel"},
    ])

    assert batch["accepted_rows"] == 49
    assert batch["rejected_rows"] == 1
    assert batch["can_proceed"] is False
    assert batch["policy"] == lead_import_policy()
    assert batch["policy"]["batch_policy"] == "partial_accept"
    assert batch["policy"]["row_rejection_mode"] == "individual"
    assert batch["policy"]["contactability_rule"] == "at_least_two_valid_channels"
    assert batch["policy"]["minimum_contact_methods"] == 2
    assert batch["policy"]["accepted_contact_methods"] == ["email", "phone", "whatsapp"]
    assert batch["policy"]["required_contact_methods"] == []


def test_malformed_contact_value_does_not_count_as_a_valid_channel():
    batch = evaluate_lead_batch([{"email": "not-an-email"}])

    assert batch["accepted_rows"] == 0
    assert batch["rejected_rows"] == 1
    assert batch["rejected"][0]["reasons"] == [
        "At least two valid contactable channels are required; provide any two of email, phone, or WhatsApp",
        "Invalid email: not-an-email",
    ]


def test_each_pair_of_accepted_contact_methods_passes_but_single_methods_fail():
    passing = [
        {"email": "email-phone@example.com", "phone": "+15550000001"},
        {"email": "email-whatsapp@example.com", "whatsapp": "+15550000002"},
        {"phone": "+15550000003", "whatsapp": "+15550000004"},
    ]
    failing = [
        {"email": "email-only@example.com"},
        {"phone": "+15550000005"},
        {"whatsapp": "+15550000006"},
    ]

    batch = evaluate_lead_batch([*passing, *failing])

    assert batch["accepted_rows"] == 3
    assert batch["rejected_rows"] == 3
    assert [item["row_index"] for item in batch["rejected"]] == [3, 4, 5]
