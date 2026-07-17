from app.services.knowledge import memory_store


class _Collection:
    def __init__(self): self.rows = {}
    def find_one(self, key, projection=None): return self.rows.get((key['tenant_id'], key['subject_type'], key['subject_id']))
    def replace_one(self, key, value, upsert=False): self.rows[(key['tenant_id'], key['subject_type'], key['subject_id'])] = value


def test_summary_memory_upsert_is_tenant_scoped_idempotent_and_keeps_history(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(memory_store, 'get_context_database', lambda: {'tenant_context': collection})
    first = memory_store.upsert_summary_memory(tenant_id='tenant-a', subject_type='lead', subject_id='lead-1', summary_id='summary-1', conversation_id='conversation-1', structured={'budget_signals': ['$30k'], 'competitors': ['Salesforce']}, summary_text='')
    repeat = memory_store.upsert_summary_memory(tenant_id='tenant-a', subject_type='lead', subject_id='lead-1', summary_id='summary-1', conversation_id='conversation-1', structured={'budget_signals': ['$30k'], 'competitors': ['Salesforce']}, summary_text='')
    other = memory_store.upsert_summary_memory(tenant_id='tenant-b', subject_type='lead', subject_id='lead-1', summary_id='summary-1', conversation_id='conversation-2', structured={'competitors': ['HubSpot']}, summary_text='')
    assert first['budget_signals'][0]['value'] == '$30k'
    assert first['competitors'][0]['value'] == 'Salesforce'
    assert repeat['version'] == 1
    assert other['competitors'][0]['value'] == 'HubSpot'
    assert len(collection.rows) == 2
