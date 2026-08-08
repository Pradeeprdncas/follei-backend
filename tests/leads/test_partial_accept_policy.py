from app.domains.lead_import.validators import evaluate_lead_batch, lead_import_policy


def _valid_row(index: int) -> dict:
    return {"email": f"lead{index}@example.com", "phone": f"+1555000{index:04d}"}


def test_row_missing_one_of_two_contact_methods_is_rejected_individually():
    batch = evaluate_lead_batch([
        *[_valid_row(index) for index in range(50)],
        {"email": "email-only@example.com", "phone": ""},
    ])

    assert batch["accepted_rows"] == 50
    assert batch["rejected_rows"] == 1
    assert batch["can_proceed"] is True
    assert batch["rejected"][0]["row_index"] == 50
    assert batch["rejected"][0]["reasons"] == [
        "At least 2 contact methods are required; provide both email and phone"
    ]


def test_batch_does_not_proceed_when_fewer_than_fifty_rows_remain_after_rejection():
    batch = evaluate_lead_batch([
        *[_valid_row(index) for index in range(49)],
        {"email": "email-only@example.com", "phone": ""},
    ])

    assert batch["accepted_rows"] == 49
    assert batch["rejected_rows"] == 1
    assert batch["can_proceed"] is False
    assert batch["policy"] == lead_import_policy()
    assert batch["policy"]["batch_policy"] == "partial_accept"
    assert batch["policy"]["row_rejection_mode"] == "individual"
