from uuid import uuid4

from app.models.campaigns import Campaign, CampaignType
from app.models.leads.lead import Lead
from app.services.campaigns.service import CampaignService
from app.services.communications.email_connections import decrypt_secret, encrypt_secret


class _LeadRepository:
    def __init__(self, leads):
        self.leads = leads

    def get_by_tenant(self, tenant_id):
        return [lead for lead in self.leads if lead.tenant_id == tenant_id]


def _lead(tenant_id, email, *, source=None, consent=None, suppressed=False):
    profile = {}
    if source:
        profile["source"] = source
    if consent is not None:
        profile["marketing_consent"] = consent
    if suppressed:
        profile["email_suppressed"] = True
    return Lead(
        id=uuid4(),
        tenant_id=tenant_id,
        first_name="Aria",
        last_name="Chen",
        email=email,
        status="new",
        profile_data=profile,
    )


def _service(leads):
    service = CampaignService.__new__(CampaignService)
    service.lead_repo = _LeadRepository(leads)
    return service


def test_tenant_email_secret_round_trip_is_not_plaintext():
    encrypted = encrypt_secret("test-app-password")
    assert encrypted
    assert encrypted != "test-app-password"
    assert decrypt_secret(encrypted) == "test-app-password"


def test_campaign_selects_eligible_audience_and_honours_suppression():
    tenant_id = uuid4()
    normal = _lead(tenant_id, "normal@example.com")
    suppressed = _lead(tenant_id, "stop@example.com", suppressed=True)
    inbound_without_consent = _lead(
        tenant_id,
        "inbound@example.com",
        source="inbound_email",
        consent=False,
    )
    campaign = Campaign(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Follow up",
        type=CampaignType.EMAIL,
        subject="Hello {{name}}",
        body="Hi {{name}}",
        target_audience={},
    )

    selected = _service([normal, suppressed, inbound_without_consent])._select_leads(campaign)

    assert selected == [normal]
    assert CampaignService._personalize(campaign.body, normal) == "Hi Aria Chen"


def test_explicitly_added_inbound_lead_can_receive_campaign_but_suppression_wins():
    tenant_id = uuid4()
    inbound = _lead(
        tenant_id,
        "inbound@example.com",
        source="inbound_email",
        consent=False,
    )
    suppressed = _lead(tenant_id, "stop@example.com", suppressed=True)
    campaign = Campaign(
        id=uuid4(),
        tenant_id=tenant_id,
        name="Requested follow up",
        type=CampaignType.EMAIL,
        body="Hi {{name}}",
        target_audience={
            "manual_lead_ids": [str(inbound.id), str(suppressed.id)],
        },
    )

    selected = _service([inbound, suppressed])._select_leads(campaign)

    assert selected == [inbound]
