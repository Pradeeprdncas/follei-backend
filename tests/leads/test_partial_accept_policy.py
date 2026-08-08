from app.domains.lead_import.validators import evaluate_lead_batch, lead_import_policy


EMAIL_ONLY_POLICY = lead_import_policy(
    minimum_contact_methods=1,
    accepted_contact_methods=["email"],
    active_channel_types=["email"],
)
REDUNDANT_MULTI_CHANNEL_POLICY = lead_import_policy(
    minimum_contact_methods=2,
    accepted_contact_methods=["email", "phone", "whatsapp"],
    active_channel_types=["email", "voice", "whatsapp"],
)


def _valid_row(index: int) -> dict:
    return {"email": f"lead{index}@example.com"}


def test_email_only_policy_accepts_email_rows_and_rejects_unusable_phone_only_row_individually():
    batch = evaluate_lead_batch([
        *[_valid_row(index) for index in range(50)],
        {"phone": "+15550000001"},
    ], policy=EMAIL_ONLY_POLICY)

    assert batch["accepted_rows"] == 50
    assert batch["rejected_rows"] == 1
    assert batch["can_proceed"] is True
    assert batch["rejected"][0]["row_index"] == 50
    assert batch["rejected"][0]["reasons"] == [
        "Tenant requires at least 1 valid active-channel contact method(s); provide: email"
    ]


def test_batch_does_not_proceed_when_fewer_than_fifty_rows_remain_after_rejection():
    batch = evaluate_lead_batch([
        *[_valid_row(index) for index in range(49)],
        {"first_name": "No contact channel"},
    ], policy=EMAIL_ONLY_POLICY)

    assert batch["accepted_rows"] == 49
    assert batch["rejected_rows"] == 1
    assert batch["can_proceed"] is False
    assert batch["policy"] == EMAIL_ONLY_POLICY
    assert batch["policy"]["batch_policy"] == "partial_accept"
    assert batch["policy"]["row_rejection_mode"] == "individual"
    assert batch["policy"]["contactability_rule"] == "minimum_active_channel_matches"
    assert batch["policy"]["minimum_contact_methods"] == 1
    assert batch["policy"]["lead_contact_requirement"] == 1
    assert batch["policy"]["accepted_contact_methods"] == ["email"]
    assert batch["policy"]["required_contact_methods"] == []
    assert batch["policy"]["policy_scope"] == "tenant"


def test_malformed_active_contact_value_does_not_count():
    batch = evaluate_lead_batch([{"email": "not-an-email"}], policy=EMAIL_ONLY_POLICY)

    assert batch["accepted_rows"] == 0
    assert batch["rejected_rows"] == 1
    assert batch["rejected"][0]["reasons"] == [
        "Tenant requires at least 1 valid active-channel contact method(s); provide: email",
        "Invalid email: not-an-email",
    ]


def test_two_method_policy_accepts_active_channel_pairs_but_rejects_email_only():
    passing = [
        {"email": "email-phone@example.com", "phone": "+15550000001"},
        {"email": "email-whatsapp@example.com", "whatsapp": "+15550000002"},
        {"phone": "+15550000003", "whatsapp": "+15550000004"},
    ]
    failing = [{"email": "email-only@example.com"}]

    batch = evaluate_lead_batch([*passing, *failing], policy=REDUNDANT_MULTI_CHANNEL_POLICY)

    assert batch["accepted_rows"] == 3
    assert batch["rejected_rows"] == 1
    assert batch["rejected"][0]["row_index"] == 3
    assert batch["policy"]["minimum_contact_methods"] == 2
    assert batch["policy"]["accepted_contact_methods"] == ["email", "phone", "whatsapp"]
