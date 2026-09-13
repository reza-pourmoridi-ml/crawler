# Why this architecture?

Crawler collects flight prices from multiple websites for a requested route and date. A useful result preserves the lowest fare for each airline **on each provider**, along with its freshness. The architecture is designed to keep that work manageable on a CPU-only Linux server while allowing slow browser and model tasks to finish asynchronously.

See [README.md](README.md) for the current implementation, deployment commands, configuration, and operational limits.

## One codebase, separate runtime roles

The system is a containerized modular monolith: Control, orchestration, scraping, learning, and extraction share Python models and utilities but run in separate processes and Docker containers. This keeps a small deployment understandable without requiring independent service repositories, API contracts between every module, or a separate message broker.

Separate runtime roles let us budget browser memory, model inference, and ordinary API work independently. Container limits reduce the impact of heavy work on the API, but do not eliminate host-wide CPU, memory, or disk contention. Server capacity still matters.

The tradeoff is shared schema and release coordination. Migrations and application releases must be deployed in a compatible order. These are not independently versioned microservices.

## Keep long work outside HTTP requests

Browser navigation and local inference can take minutes or hours. Keeping that work in workers lets Control accept a request, persist it, and serve status and available results without waiting for an entire learning run.

A PostgreSQL queue absorbs work when workers are busy. Increasing the number of simultaneous HTTP requests does not directly create more browser or inference processes. The current deployment deliberately uses one instance per role.

Users therefore see asynchronous progress and potentially stale provider data. Explicit status and per-provider update times are part of the product, rather than an assumption that every request immediately produces complete results.

## PostgreSQL as both state store and queue

PostgreSQL already stores provider configuration, requests, and prices. Keeping jobs there provides persistent scheduling state, row locking, attempt counts, and recovery after process restarts without operating Redis or RabbitMQ as another dependency.

Workers claim jobs with `FOR UPDATE SKIP LOCKED`. Renewable leases, deadlines, and attempt ownership protect queue transitions. Retries remain bounded and use backoff.

A queue does not create an exactly-once guarantee across database writes, external browsing, and files. Duplicate work and interrupted attempts must still be considered. Current safeguards include source-snapshot IDs, atomic file replacement, provider-result ordering, and checks against stale worker attempts.

A separate broker may become useful if workload and operational requirements justify it; the current code does not require one.

## Central orchestration

Only the orchestrator creates the scrape → learn/extract follow-up jobs. Workers execute a single stage and report their outcome. This keeps dependency decisions in one place and lets them be reconstructed from persistent jobs and published files after a restart.

The scheduler polls every five minutes. That introduces a bounded scheduling delay under normal operation, separate from queue wait and processing time. A successful partial template publication can therefore become usable before Learn finishes, without requiring workers to schedule each other directly.

Learning is keyed by website and route type, so templates can be reused across requests. While one learning job is active for a key, newer snapshots may accumulate; the next learning run uses the newest eligible source rather than replaying every intermediate snapshot.

## Separate learning from repeated extraction

Learning uses candidate discovery and a local language model to validate reusable ticket layouts. Extraction then matches stored structures and reads price, time, and airline fields without invoking Ollama.

This spends model compute on learning layouts rather than on every extraction. The extractor stays relatively lightweight and can continue using existing templates while Learn refreshes them.

Templates are a learned cache, not a guarantee that every future page is understood. Provider redesigns, login pages, unexpected markup, and mixed price units still need validation and operational checks. Current extraction preserves source numeric units; it does not provide universal currency/unit normalization.

## Publish validated templates progressively

Waiting for an entire multi-hour Learn job would delay useful extraction even after the first valid tickets were found. Learn therefore publishes accumulated validated templates during the run and performs a final merge when validation completes.

Atomic replacement ensures readers see a complete old or new file. Empty output does not erase prior templates. Previously published valid data may remain useful even when a later part of the same attempt fails.

At storage time, tag hierarchy and class sets group similar designs, and selection takes samples round-robin while quota remains. Exact duplicates do not consume the new-template quota. A total template cap limits retained data. These storage decisions provide broader design coverage without changing detection, recursion, or validation.

## Local inference and resource limits

Ollama keeps inference local to the deployment. A GPU is optional; CPU-only operation is a supported design target, with the expectation that learning can be slow.

Development selects `qwen2.5-coder:7b`; production selects `qwen2.5-coder:14b` through its own `OLLAMA_MODEL` environment value. Compose automatically prepares the selected model before starting Learn. The production override doubles Ollama's local CPU/RAM ceilings to 8 CPUs and 20 GiB, while keeping parallel inference limited.

A larger model is a deployment choice, not a promise of throughput or extraction quality. Its runtime must be measured on representative pages and the actual server. Automatic preparation still needs network access and disk space on first startup.

## Progress-aware timeouts

A healthy CPU-bound Learn attempt can run for many hours, so duration alone is not an adequate early failure signal. Real candidate/validation progress resets a no-progress timer. A separate hard maximum remains the final safety net.

The defaults are six hours without progress and thirty hours total per attempt. The independent Ollama request timeout still applies, and queue heartbeats are not counted as learning progress. Scraper and Extractor retain their own fixed attempt deadlines.

Worker subprocess isolation makes termination and temporary-file cleanup practical. Restarting a worker, including through development Watch, can still interrupt work and consume retries; it is not a resumable checkpoint of the full inference process.

## Files for artifacts, PostgreSQL for records

HTML, screenshots, learned templates, extracted JSON, and model weights are better handled as files than as large job payloads. Application file operations use shared storage helpers, and runtime files remain under the project's `storage/` directory in both deployment modes.

PostgreSQL stores metadata, configuration, workflow state, and queryable results in a named Docker volume. Backups must therefore include the database as well as required storage files. Copying source code alone does not move the running system's data.

Unique snapshots prevent a later scrape from overwriting the input of a long Learn attempt. Cleanup protects active inputs and removes eligible old artifacts/history; learned templates use a count cap instead of time-based expiration.

Shared files also constrain scaling. PostgreSQL queue locking is not a replacement for coordination between multiple template writers. The supplied single-instance topology is the supported starting point.

## Provider failures and observable freshness

A provider's failure must not discard another provider's valid prices. Results are persisted independently per website/request, and old workers cannot overwrite newer snapshots. The UI shows each provider separately with its update time and processing state.

Monitor combines queue state, active work, recent outcomes, and dependency checks. Neither an empty queue nor an old error is sufficient by itself to declare a worker unhealthy. Container health and application progress are different observations and should be interpreted together.

The current database retains a legacy terminal-state convention: `status=failed` is paired with `outcome=success` or `outcome=error`. Operational tooling must interpret the outcome rather than infer failure from the status string alone.

## Explicit session management and deployment boundaries

Provider login state is uploaded through Control as Playwright storage-state JSON and atomically replaced. The UI exposes existence and modification time, not credentials. Scraper reads the file for each new context and does not silently overwrite the operator's session file.

Structural JSON validation does not prove a session is still logged in. Operators maintain and refresh provider sessions, and protect Auth files and backups accordingly. Provider Auth is distinct from access control for the Control panel itself.

Production keeps code inside built images, while development offers bind mounts and explicit Watch restarts. Both use the same application flow and project-local artifacts. Migrations and model preparation gate startup; release deployment still requires attention to active jobs, data compatibility, and an acceptance search on the target server.
