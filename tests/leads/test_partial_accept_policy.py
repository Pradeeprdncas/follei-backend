from app.domains.lead_import.validators import evaluate_lead_batch, lead_import_policy


def _valid_row(index: int) -> dict:
    return {"email": f"lead{index}@example.com", "phone": f"+1555000{index:04d}"}


def test_any_one_valid_contact_channel_is_accepted_and_bad_row_is_rejected_individually():
    batch = evaluate_lead_batch([
        *[{"email": f"lead{index}@example.com"} for index in range(48)],
        {"phone": "+15550000001"},
        {"whatsapp": "+15550000002"},
        {"first_name": "No contact channel"},
    ])

    assert batch["accepted_rows"] == 50
    assert batch["rejected_rows"] == 1
    assert batch["can_proceed"] is True
    assert batch["rejected"][0]["row_index"] == 50
    assert batch["rejected"][0]["reasons"] == [
        "At least one valid contactable channel is required; provide email, phone, or WhatsApp"
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
    assert batch["policy"]["contactability_rule"] == "at_least_one_valid_channel"
    assert batch["policy"]["minimum_contact_methods"] == 1
    assert batch["policy"]["accepted_contact_methods"] == ["email", "phone", "whatsapp"]
    assert batch["policy"]["required_contact_methods"] == []


def test_malformed_contact_value_does_not_count_as_a_valid_channel():
    batch = evaluate_lead_batch([{"email": "not-an-email"}])

    assert batch["accepted_rows"] == 0
    assert batch["rejected_rows"] == 1
    assert batch["rejected"][0]["reasons"] == [
        "At least one valid contactable channel is required; provide email, phone, or WhatsApp",
        "Invalid email: not-an-email",
    ]
