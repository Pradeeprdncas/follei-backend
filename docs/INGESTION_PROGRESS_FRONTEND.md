# Follei ingestion progress: frontend contract

Google Workspace and website ingestion are asynchronous. Never wait on the
OAuth callback or website `POST` until crawling/indexing completes. Both flows
return a `run_id` plus the same two authenticated progress URLs:

- `GET /api/v1/onboarding/runs/{run_id}` — one current JSON snapshot.
- `GET /api/v1/onboarding/runs/{run_id}/events` — SSE snapshots until terminal.

The tenant-wide readiness endpoint remains
`GET /api/v1/onboarding/state`. Refresh it after a run completes; do not use it
as the primary per-run progress feed.

## Starting a website run

```http
POST /api/v1/knowledge/websites/ingest
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "url": "https://company.example/",
  "engine": "auto",
  "crawl_consent": true
}
```

Do not send `max_pages` or `category`. The worker follows the same-host site
until exhausted, downloads supported linked documents, and automatically
classifies every page/document. Server-only safety ceilings still prevent an
infinite URL space or excessive download from exhausting a worker.

The `202` response's `data` contains `source`, `run`, `jobs`, `status_url`,
`events_url`, and `onboarding_state_url`.

## Starting/receiving a Google run

- Public Google signup/sign-in: after `POST /api/v1/auth/google/exchange`, read
  `ingestion.run_id`, `ingestion.status_endpoint`, and
  `ingestion.events_endpoint` from the session response.
- Authenticated Google Workspace popup: the success `postMessage` contains
  `run_id`, `status_url`, and `events_url`.
- Manual resync: `POST
  /api/v1/integrations/google-workspace/connections/{connection_id}/sync`
  returns those same URLs in `data`.

## Reading the authenticated SSE response

Native `EventSource` cannot attach `Authorization`; use `fetch()` streaming.

```ts
export type IngestionRun = {
  run_id: string;
  source: { id: string; name: string | null; type: string | null; status: string | null };
  status: string;
  stage: string;
  terminal: boolean;
  progress_percent: number;
  counts: {
    pages_discovered: number;
    documents_discovered: number;
    records_discovered: number;
    items_queued: number;
    documents_indexed: number;
    categories_found: number;
    items_extracted: number;
  };
  jobs: Array<{
    id: string;
    type: string;
    status: string;
    attempt: number;
    error: string | null;
    progress?: {
      resource?: "gmail" | "drive" | "calendar" | "contacts";
      stage?: string;
      selected_engine?: "aiohttp" | "crawl4ai" | "scrapy";
      record_count?: number;
      pages_discovered?: number;
      documents_discovered?: number;
      items_queued?: number;
      current_url?: string;
    };
    document_id?: string | null;
  }>;
  results: {
    documents: Array<{
      id: string;
      title: string;
      source_uri: string | null;
      status: string;
      category: string | null;
      summary: string | null;
      chunk_count: number;
    }>;
    categories: Array<{
      key: string;
      status: "found" | "partial";
      item_count: number;
      document_count: number;
      sample_items: string[];
      items_endpoint: string | null;
    }>;
  };
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string | null;
};

export async function watchIngestion(
  apiOrigin: string,
  eventsUrl: string,
  accessToken: string,
  onUpdate: (run: IngestionRun) => void,
): Promise<IngestionRun> {
  const response = await fetch(new URL(eventsUrl, apiOrigin), {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: "text/event-stream",
    },
    cache: "no-store",
  });
  if (response.status === 401) throw new Error("Session expired");
  if (response.status === 404) throw new Error("Ingestion run not found");
  if (!response.ok || !response.body) throw new Error(`Progress HTTP ${response.status}`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let latest: IngestionRun | undefined;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = block.split("\n").find(line => line.startsWith("event: "))?.slice(7);
      const data = block.split("\n").find(line => line.startsWith("data: "))?.slice(6);
      if (!data) continue; // keep-alive comment
      if (event === "timeout") throw new Error("Progress stream timed out; reconnect");
      if (event === "error") throw new Error(JSON.parse(data).message);
      latest = JSON.parse(data) as IngestionRun;
      onUpdate(latest);
      if (latest.terminal) return latest;
    }
  }
  if (!latest) throw new Error("Progress stream ended before its first snapshot");
  return latest;
}
```

Render `stage` as the primary label. For website ingestion, show live
`pages_discovered`, `documents_discovered`, and `current_url`; the final total
number of site URLs is unknowable during discovery, so the crawler portion of
the bar is intentionally coarse. For Google, render one row per job/resource
and show `record_count` independently.

On the terminal event:

1. Render `results.documents` and `results.categories` immediately.
2. For full extracted records, call a category's returned `items_endpoint` when
   it is non-null. `general`/unclassified supporting evidence may not have a
   reviewable taxonomy endpoint.
   It is already filtered to the source that produced this run.
3. Refresh `GET /api/v1/onboarding/state` once to update all 25 category cards,
   mandatory-group readiness, `can_continue`, and
   `ready_for_autonomous_actions`.
4. If `status` is `partial` or `failed`, show safe `error`/job errors and a retry
   action. Internal provider exceptions and OAuth credentials are never sent.

If the stream drops because the user changes network/tab, reconnect to the
same `events_url`; its first event is a fresh full snapshot. In environments
where streaming is blocked, poll `status_url` every 1–2 seconds and stop when
`data.terminal === true`.
