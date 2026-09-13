# Crawler

Asynchronous flight-price collection with a Persian Control panel, reusable HTML learning, and provider-by-provider results. Given a route and departure date, the application captures configured travel websites, learns valid ticket layouts with a local Ollama model, and extracts flight offers into PostgreSQL.

The results page displays the **lowest price for each airline on each website**: airlines are rows and websites are columns. Each provider's update time appears below the table. Results become available progressively; a slow provider does not block prices already collected from others.

## Contents

- [Architecture](#architecture)
- [Requirements and server sizing](#requirements-and-server-sizing)
- [Development deployment](#development-deployment)
- [Production deployment](#production-deployment)
- [Control panel and API](#control-panel-and-api)
- [Configuration](#configuration)
- [Storage and learning](#storage-and-learning)
- [Operations and troubleshooting](#operations-and-troubleshooting)
- [Tests](#tests)

See [why.md](why.md) for design decisions and tradeoffs.

## Architecture

The project is a **containerized modular monolith with central orchestration and asynchronous workers**: one Python codebase, shared domain models, and separate processes/images for each runtime role. PostgreSQL stores domain data and the job queue; no Redis or RabbitMQ is required.

| Role | Python entry point | Responsibility |
| --- | --- | --- |
| Control | `python -m app.control` | FastAPI API, request validation, Persian HTML pages, Auth upload, monitoring |
| Orchestrator | `python -m app.orchestration` | Schedule requests, advance the pipeline, recover expired jobs, clean obsolete artifacts |
| Scraper | `python -m app.scraper` | Playwright browser automation; capture HTML and diagnostic artifacts |
| Learn | `python -m app.learn` | Candidate discovery, Ollama validation, publication of reusable ticket templates; uses Node/jsdom |
| Extractor | `python -m app.extractor` | Match learned HTML structures, extract offers, persist provider results; no Ollama or Node dependency |
| PostgreSQL | Compose service `postgres` | Configuration, search requests, jobs, results, and workflow state |
| Ollama | Compose service `ollama` | Local inference for Learn |

Compose also includes `migrate` (database migrations), `model-pull` (automatic model preparation), and `seed` (optional initial data).

```text
Control -> PostgreSQL search requests
                    |
              Orchestrator -> PostgreSQL job queue
                                  |
                               Scraper -> raw snapshot
                                             |
                                    Learn -> learned templates
                                             |
                      raw snapshot + usable templates -> Extractor
                                                            |
                                                   PostgreSQL results
                                                            |
                                                      Control / API
```

### Workflow and reliability

1. A search records route type, origin, destination, and a Jalali departure date; the database stores the corresponding Gregorian date.
2. Every five minutes, the orchestrator considers requests whose departure date is today or later in Tehran time. It schedules a scrape for each fully configured website, unless a scrape for that request/website is already active.
3. Scraper stores a uniquely named snapshot. Workers consume only their own job type; only the orchestrator schedules downstream jobs.
4. Learning is shared by `(website_id, route_type)`, with separate domestic and international templates. Only one pending/running Learn job is scheduled per key. Once it finishes, the latest newer successful snapshot can become the next learning input; intermediate snapshots need not each be learned.
5. Validated templates are published during Learn. At a subsequent orchestration poll, extraction can start as soon as usable templates exist, even while Learn is still running. Existing templates remain usable during refresh. If no usable template exists, extraction waits.
6. Extraction processes each eligible successful snapshot once, with bounded retries in the same job. It atomically replaces that provider's stored results. A late older snapshot cannot overwrite a newer provider result. Failed providers retain their last successful data, marked stale when applicable.

The queue claims jobs with PostgreSQL `FOR UPDATE SKIP LOCKED`, uses renewable locks and bounded exponential retry backoff, and defaults to three attempts. Each worker executes a job in a child process with its own temporary directory. Attempt ownership checks prevent an old worker from completing a newer attempt.

**Current database status convention:** active jobs use `pending` and `running`. Both successful and unsuccessful terminal jobs currently use `status=failed`; inspect `outcome=success` or `outcome=error` to distinguish them. Legacy `done` records are also recognized. The Control monitor interprets these fields; a raw `status=failed` query alone is misleading.

The supplied deployment runs one instance of each role. Queue locking alone does not make every shared-file operation safe for arbitrary scaling; do not increase replicas without reviewing template writes, scheduling, and the Ollama resource budget.

## Requirements and server sizing

Docker is the supported deployment path for both development and production. Run the commands below from the repository root, using Bash on Linux. Install Docker Engine and a Compose plugin that supports `develop.watch` with `action: restart` (Compose 2.32 or later). GPU deployment additionally requires support for the `gpus` Compose attribute.

Python, Node, PostgreSQL, Ollama, and Playwright browsers are supplied by the images; they do not need separate host installations for Docker deployment. Builds need access to image registries and Python/npm/OS package repositories. Initial startup needs access to the Ollama model registry. Runtime scraping needs outbound access to the configured providers.

| Setting | Development | Production |
| --- | --- | --- |
| Environment file | `.env.docker` | `.env.production` |
| Compose files | `compose.yaml` + `compose.local.yaml` | `compose.yaml` + `compose.production.yaml` |
| Default `OLLAMA_MODEL` | `qwen2.5-coder:7b` | `qwen2.5-coder:14b` |
| Ollama CPU limit | 4 CPUs | 8 CPUs |
| Ollama RAM limit | 10 GiB | 20 GiB |
| Application source | Read-only bind mount, optional Watch restarts | Baked into images |
| Runtime files | Project `storage/` | Project `storage/` |
| GPU | Optional | Optional; CPU-only is supported |

Production doubles Ollama's local CPU and memory limits. Changing `OLLAMA_MODEL` selects the model for the application and downloader; it does **not** automatically change resources. Resource limits come from the selected Compose override.

Production memory limits for the long-running services total approximately 30 GiB: Ollama 20 GiB, PostgreSQL 2 GiB, Scraper 3 GiB, Learn 3 GiB, Extractor 1 GiB, Control 512 MiB, and Orchestrator 384 MiB. Migration, model preparation, Docker, the OS, and filesystem caches need additional headroom.

For initial production testing, plan for **at least 8 CPU cores and 32 GiB RAM**, with more RAM/CPU when providers or concurrent activity demand it. An 8-core host cannot give every container its configured CPU ceiling simultaneously. For development, the service memory ceilings total about 16.1 GiB before host overhead; allow headroom beyond that if the machine is also running an IDE and browsers. These are capacity-planning figures from the configuration, not measured minimums or performance guarantees.

Use SSD-backed storage and start with roughly **100 GiB free** for images, build cache, model files, PostgreSQL, and snapshots; size further from actual retention and crawl volume. This is a planning allowance, not a fixed application requirement. Both local and production models may occupy disk if they have both been downloaded.

CPU inference can take many hours. Learn defaults to a six-hour no-progress timeout and a thirty-hour hard limit per attempt. RAM limits do not guarantee an inference fits: model/context size and workload matter. Measure a representative search on the target server.

## Development deployment

### 1. Prepare the environment and writable storage

On first setup only, copy the example; do not overwrite an existing environment file:

```bash
cp .env.docker.example .env.docker
id -u
id -g
mkdir -p storage/auth storage/raw storage/learned storage/extracted storage/temp
chmod 700 storage/auth
chmod 600 .env.docker
```

Edit `.env.docker`:

- Keep `OLLAMA_MODEL=qwen2.5-coder:7b` and `STORAGE_HOST_PATH=./storage`.
- Set `APP_UID` and `APP_GID` to the host account that owns the writable storage directories. The example uses `1000:1000`.
- Set matching PostgreSQL database, username, and password values in `POSTGRES_*` and `DATABASE_URL`. Inside Docker the database host is `postgres`, not `localhost`.
- Use a strong URL-safe password, or percent-encode reserved characters in the password portion of `DATABASE_URL`.

Create the application directories as that host account. For restored data, ensure `auth`, `raw`, `learned`, `extracted`, and `temp` are readable/writable by the configured UID/GID. Do not apply a recursive ownership change to the whole repository or Ollama's model directory.

### 2. Validate, build, and start

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml config --quiet
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml build
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml up -d
```

Startup brings up PostgreSQL and Ollama, runs migrations, and automatically runs `model-pull` for `OLLAMA_MODEL`. Learn starts only after migrations and model preparation succeed. Other application services require successful migrations. The first `up` can remain busy while a large model downloads; inspect progress in a second terminal:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml logs -f --tail 100 model-pull ollama migrate
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml ps -a
```

A successful `model-pull` or `migrate` container exiting with code 0 is expected. A failed model download retries according to its restart policy. No manual `ollama pull` or model profile is needed. Building images alone does not download model weights.

To import initial airlines, websites, airports, and provider airport codes:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml run --rm seed
```

Although `seed` is marked with the optional `setup` profile, explicitly targeting the service activates it; no `--profile` argument is necessary. Seeders run in dependency order and preserve existing records rather than overwrite manual edits. They are initial configuration, not a database backup or a guarantee that provider URLs remain valid.

Open [Control](http://127.0.0.1:8000/control/dashboard), upload Auth if needed, verify provider configuration, and submit a future-dated search.

### 3. Enable live code updates

Run Watch in a separate terminal after startup:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml watch --no-up
```

The local override mounts `./app` into every application container. Watch observes that directory and restarts **all five application services** when it changes. Bytecode/cache changes are ignored. A bind mount alone does not reload already-imported Python modules.

**Stop Watch before editing during a long Learn run you need to preserve.** A Watch restart can interrupt active attempts and consume retries. Without Watch, apply a change in a planned window; for a Control-only change, for example:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.local.yaml restart control
```

Dependency, Dockerfile, and migration changes require the appropriate rebuild/migration steps; Watch only covers `app/`. Environment changes need container recreation with `up -d`; `restart` alone does not load new environment values.

## Production deployment

### 1. Prepare the server

Install Docker/Compose, place the repository on the server, and run commands from its root. On first setup:

```bash
cp .env.production.example .env.production
id -u
id -g
mkdir -p storage/auth storage/raw storage/learned storage/extracted storage/temp
chmod 700 storage/auth
chmod 600 .env.production
```

Edit `.env.production` with production credentials and storage ownership, following the same UID/GID and database URL rules as development. Keep `OLLAMA_MODEL=qwen2.5-coder:14b` and `STORAGE_HOST_PATH=./storage`. The example uses `IMAGE_TAG=production`; use release-specific tags when retaining images for rollback.

Local and production files describe alternative deployments. Compose fixes the project name as `crawler`; the two env files do not by themselves create isolated stacks on one Docker host. Do not start both against the same project/storage expecting separate databases.

### 2. Build and start on CPU

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml config --quiet
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml build
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml up -d
```

The 14B model is downloaded automatically into `storage/ollama`. Learn waits for model preparation; no extra profile or manual pull is required. Production does not mount source code or run Watch. A code release takes effect through rebuilt images and recreated containers.

For a new database, import starter configuration once:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml run --rm seed
```

### 3. Optional NVIDIA GPU deployment

Install a compatible NVIDIA driver and NVIDIA Container Toolkit on the host. Add the GPU override consistently to the production command set:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml -f compose.gpu.yaml config --quiet
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml -f compose.gpu.yaml build
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml -f compose.gpu.yaml up -d
```

The override exposes GPUs only to Ollama; model selection still uses `OLLAMA_MODEL`. Host RAM limits are not VRAM budgets. Verify available VRAM and actual model placement for the intended context size. CPU deployment remains available without this override.

### 4. Access and acceptance checks

Control binds to `127.0.0.1:8000` by default. PostgreSQL is not published to the host, and Ollama is only published on loopback in development. For private server testing, use an SSH tunnel from your workstation:

```bash
ssh -N -L 8000:127.0.0.1:8000 deploy@your-server
```

Then visit the local Control URL. For shared access, put Control behind a reverse proxy with TLS and authentication or a private network. The application currently provides no built-in administrator login/access-control layer; the Auth page manages provider sessions, not panel users. Protect the API and Auth upload along with the UI.

Check readiness:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml ps -a
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml logs --tail 100 migrate model-pull learn
curl -fsS http://127.0.0.1:8000/control/status
curl -fsS 'http://127.0.0.1:8000/control/monitor/status?row_limit=50&history_hours=72'
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml exec ollama ollama list
```

Confirm migrations and model preparation exited successfully, application containers are running, and the expected model is installed. Upload a current Auth file, verify website URLs/date formats/airport codes, and submit a representative search. In Monitor, follow scrape, partial template publication, extraction, and per-provider prices. The API status endpoint alone does not prove the entire pipeline works.

### 5. Deploy a later release

Use a maintenance window for active jobs, especially Learn. Stop any development Watch process before updating source. Back up PostgreSQL and the application files before migrations. With the desired source revision already present and jobs at a suitable stopping point:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml build
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml stop control orchestrator scraper learn extractor
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml run --rm migrate
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml up -d
```

If migration fails, investigate before restarting application services. A stopped running job may be retried after lock recovery; stopping is not a resumable pause of inference. Retain the previous images/source and a matching database backup for rollback; rolling back code does not undo a migration.

## Control panel and API

| Feature | Route |
| --- | --- |
| Dashboard | `/control/dashboard` |
| Airlines and aliases | `/control/airlines/page` |
| Websites and URL/date configuration | `/control/websites/page` |
| Domestic airport/provider code matrix | `/control/flight-paths/page/domestic` |
| International airport/provider code matrix | `/control/flight-paths/page/foreign` |
| Search form and requests | `/control/search-box/page` |
| Provider-by-provider results | `/control/search-box/page/{id}/results` |
| Provider Auth upload | `/control/auth/page` |
| Monitor | `/control/monitor/page` |
| Interactive API documentation | `/docs` |
| OpenAPI schema | `/openapi.json` |

The search form uses separate Jalali year/month/day selectors. Search and result sections refresh automatically. Monitor supports a row limit of 5–200, a history window of 1–168 hours, refresh intervals or manual refresh, and expanded details. Display preferences persist in the browser.

Airline, website, and airport-code APIs are under `/control/airlines`, `/control/websites`, and `/control/flight-paths`. Search requests use `GET/POST /control/search-box`. Consult OpenAPI for exact schemas, supported operations, and validation errors.

**API compatibility detail:** `GET /control/search-box/{id}/results` currently returns the cross-provider minimum per airline in `offers`, together with provider status metadata. The HTML results matrix separately reads provider-specific airline prices. Do not treat that JSON `offers` list as the full provider-by-provider matrix.

### Domain configuration

- `Airline` stores the official Persian name and aliases used for matching.
- `Airport` stores the canonical airport and its domestic/international category.
- `Website` stores its base URL, domestic/international URL templates, and date calendar/format. URL templates require `{origin_path}`, `{destination_path}`, and `{date}`; date formats use `YYYY`, `MM`, and `DD`.
- `FlightPath` maps one airport to one provider's code. It is not an origin/destination pair. Provider-specific case and punctuation are preserved, such as `THR_city` or `thr,1`.
- `SearchRequest`, `Job`, and result tables store user requests, processing state, and extracted prices.

Incomplete provider configuration is skipped by the scheduler. Seed data lives in [app/infra/seeders](app/infra/seeders); review it when providers change.

### Provider authentication

Generate a Playwright storage-state file with Crawler Auth Setup and upload it through Auth. The server validates JSON and requires a top-level object with `cookies` and `origins` arrays, then atomically replaces `settings.auth_state_file`. The page shows existence and modification time, never the file contents.

In Docker, this file is `storage/auth/auth.json` on the host and `/data/auth/auth.json` in containers. Scraper loads it when creating a new browser context and does not write refreshed sessions back. Uploading a replacement affects subsequent contexts; it does not change a context already running. A structurally valid file can still contain an expired login. Refresh it according to provider session lifetimes; daily uploads can be part of your operating routine.

The legacy desktop helper `python -m app.auth.save_auth` requires a graphical host and Playwright, and starts at Alibaba. It is not a production Compose service. Keep actual auth files and environment secrets out of source control and distributed archives.

## Configuration

[app/infra/config.py](app/infra/config.py) defines application settings. Direct Python execution reads `.env`; Compose uses the explicitly selected env file for interpolation and supplies variables through each service's `environment` section.

**An arbitrary line added to a Compose env file is not automatically passed into a container.** The shared Compose environment currently forwards `OLLAMA_MODEL`, `OLLAMA_TIMEOUT`, `LEARN_JOB_TIMEOUT`, `LEARN_HARD_TIMEOUT`, `LOG_LEVEL`, and `DATABASE_URL`, and sets container storage/auth paths. To override other application settings below in Docker, explicitly forward them through a service `environment` override for all affected roles. Without that override, Docker uses the code defaults.

| Application setting | Code default | Purpose |
| --- | --- | --- |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Model name; production example selects 14B |
| `OLLAMA_TIMEOUT` | 360 seconds | Independent Ollama request timeout |
| `LEARN_JOB_TIMEOUT` | 21,600 seconds | Maximum interval without real Learn progress |
| `LEARN_HARD_TIMEOUT` | 108,000 seconds | Absolute maximum duration per Learn attempt |
| `LEARN_MAX_NEW_TEMPLATES` | 20 | New-template quota per Learn merge/run |
| `LEARN_MAX_TEMPLATES` | 250 | Retained template cap per website/route type |
| `SCRAPE_JOB_TIMEOUT` | 900 seconds | Scrape attempt deadline |
| `EXTRACTOR_JOB_TIMEOUT` | 300 seconds | Extraction attempt deadline |
| `PENDING_JOB_TIMEOUT` | 86,400 seconds | Maximum overdue wait for an unclaimed pending job |
| `CLEANUP_INTERVAL_SECONDS` | 3,600 seconds | Periodic cleanup interval |
| `ARTIFACT_RETENTION_SECONDS` | 604,800 seconds | Retention of unused raw/extracted artifacts |
| `JOB_RETENTION_SECONDS` | 604,800 seconds | Retention of eligible terminal job history |
| `TEMPORARY_RETENTION_SECONDS` | 86,400 seconds | Retention of abandoned temporary files |
| `FINAL_VALIDATION_MAX_HTML_CHARS` | 100,000 | Final-validation HTML size setting |

The non-Docker `.env.example` sets artifact/job retention to one day, overriding the seven-day code defaults. The Docker examples leave those settings at code defaults.

Ollama server settings in both Docker env examples limit parallel inference and loaded models to one, enable flash attention, and keep a loaded model for 30 minutes. `CONTROL_PUBLISHED_PORT` controls the host Control port; `OLLAMA_PUBLISHED_PORT` applies only to the local override. `IMAGE_TAG` labels application images. Keep the same Compose files and env file for all commands against a deployment.

## Storage and learning

Large files remain under project-local `storage/`; metadata, configuration, jobs, and prices remain in PostgreSQL. Shared file-path and atomic-write helpers live in [app/infra/storage.py](app/infra/storage.py).

```text
storage/
  auth/auth.json
  raw/website_<id>/<domestic|international>/request_<id>/<snapshot_id>/page.html
  learned/website_<id>/<domestic|international>/tickets.json
  extracted/website_<id>/<domestic|international>/scrape_<job_id>.json
  temp/
  ollama/                 # Ollama state and downloaded model files
```

Application containers mount the storage root at `/data`. Control mounts that root read-only with a writable nested Auth directory. Ollama mounts only `storage/ollama` at `/root/.ollama`. Docker creates the Ollama bind directory if missing; preserve its container-managed permissions. Runtime contents are ignored by Git and excluded from builds.

PostgreSQL is the exception: it uses the named Docker volume `crawler_postgres_data`, not a directory in project storage. Copying the repository or `storage/` alone does not migrate the database. Existing installations using an older external Ollama volume must copy/preserve that model cache separately during a planned migration or allow automatic downloading into the new directory; changing the mount does not migrate old files.

### Template publication and extraction

A learned template contains `html`, `learned_at`, and `source_snapshot_id`. Legacy lists of HTML strings remain readable; on merge their prior file modification time supplies missing timestamps. Matching consumes the HTML content.

At storage time, valid candidates are grouped by tag hierarchy and sorted class sets. Text and attributes such as IDs and `data-*` do not create separate fingerprints; class changes do. Selection proceeds round-robin through design groups, taking one from each while capacity permits, then additional samples. Exact HTML duplicates, including existing templates, do not consume the new-template quota. The total cap evicts the oldest templates. Incremental publication uses candidates accumulated so far; final publication repeats selection across the completed valid set.

Empty learning output does not erase existing data. Atomic replacement keeps readers from seeing a partially written JSON file. An invalid existing template file is not silently replaced. Validated partial publications can survive a later failure in that Learn attempt.

Extractor performs structural matching with the current 0.95 threshold and produces `time`, `price`, `airline`, and `text`. It loads airline names/aliases from PostgreSQL. Prices retain the source's numeric unit: there is currently no general rial/toman normalization, so cross-provider numeric comparisons require consistent source units.

### Timeouts and cleanup

Learn progress is emitted by completed candidate-extraction or validation work, not merely elapsed time or worker heartbeat. Progress renews the no-progress timer, while the hard maximum remains in force. The independent Ollama request timeout and existing retry logic still apply; progress elsewhere does not make an individual request unlimited.

The orchestrator recovers expired locks/deadlines and performs scheduled cleanup. Active-job inputs and retry inputs are protected. Obsolete snapshots, extracted files, eligible job history, and abandoned temporary files expire according to retention. A snapshot that cannot be extracted because no templates become available can eventually expire. Learned templates have a count limit instead of time-based expiration; configuration, search requests, Auth, and Ollama model files are outside artifact cleanup.

## Operations and troubleshooting

The commands here target production; for development substitute `.env.docker` and `compose.local.yaml`. Include `compose.gpu.yaml` consistently if using GPU deployment.

### Status and logs

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml ps -a
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml logs -f --tail 200
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml logs --since 1h scraper learn extractor orchestrator
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml exec ollama ollama list
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml exec ollama ollama ps
docker stats --no-stream
```

Python application logging uses the shared JSON formatter. Docker's local log driver rotates logs at five 10 MB files per container. Common sensitive patterns are redacted, but retained diagnostics and runtime artifacts still require restricted access. Healthchecks differ by role; a database connectivity check is not proof that a worker is making progress. Use Monitor, active-job timing, and logs together.

| Symptom | Check |
| --- | --- |
| Learn has not started on first boot | `model-pull` and `migrate` completion; model download/network errors |
| Learn queue waits while a job is running | One Learn process handles one job at a time; inspect progress before interrupting it |
| Queue waits with no active worker | Worker/container state, expired locks, startup errors, and Monitor history |
| Jobs end after edits in development | Whether Compose Watch restarted workers |
| Login/register page instead of tickets | Auth file freshness, provider session validity, stored scrape HTML/screenshots |
| Provider never gets a scrape | URL placeholders, date configuration, airport mappings, departure date |
| Empty or stale prices | Scrape output, template availability, extractor logs, and provider update time |
| Permission denied under storage | Configured UID/GID, restored directory ownership, Auth directory permissions |
| Suspected memory exhaustion | Host memory, `docker stats`, container exit/OOM state; timeouts alone do not prove OOM |

### Stop and restart

Stop containers while retaining them and their data:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml stop
```

Start/reconcile the deployment again:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml up -d
```

Remove containers and the project network while retaining persistent data:

```bash
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml down
```

Do not use `down -v` for routine operations: it removes the named PostgreSQL volume. Bind-mounted `storage/` files are not removed by that option, but that does not protect the database. Container removal also removes container-local logs; export any required logs first.

### Backups

Back up both PostgreSQL and project storage. For a consistent cross-file/database backup, arrange a maintenance window and stop application writers first as in the release procedure. A database-only logical backup can be made with:

```bash
mkdir -p storage/backups
chmod 700 storage/backups
umask 077
docker compose --env-file .env.production -f compose.yaml -f compose.production.yaml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "storage/backups/postgres-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

Check the command exit status and the resulting archive. Store backups outside Git and copy them off-server with restricted access. Preserve `storage/auth`, `storage/learned`, and any required raw/extracted data alongside the database. Model files can be backed up to avoid downloading them again; stop Ollama before copying its directory for a consistent backup. Temporary files normally do not need backup. Protect env files separately.

Test restoration into an isolated deployment before relying on a backup. A restore must use the intended database credentials and matching file snapshot, and restore application directory permissions before workers start. Do not overwrite a live database to test a backup.

### Build cache

Dependency files are copied before application source, and BuildKit caches pip/npm/apt downloads. Normal code changes reuse dependency layers. Avoid `--no-cache` and build-cache pruning during routine releases. The scraper image includes its Playwright browser; no separate browser installation is required in the Docker workflow.

## Tests

For a host-side test environment, use Python 3.12 and create a virtual environment in the repository. No project-wide host venv path is assumed:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements/base.txt -r requirements/control.txt -r requirements/learn.txt -r requirements/extractor.txt -r requirements/scraper.txt
python -m pip install httpx PyYAML
python -m unittest discover -s tests -v
```

Tests use isolated files and test databases where configured. PostgreSQL lifecycle tests require `CRAWLER_TEST_DATABASE_URL` pointing to a dedicated test database; they create and remove test schemas. Without it, those PostgreSQL tests are skipped. Do not point it at production.

The live scraper diagnostic is opt-in via `CRAWLER_LIVE_SCRAPE_URL`, requires a valid Auth file and an installed Playwright Chromium browser, and accesses a real provider. Its artifacts go to `CRAWLER_LIVE_OUTPUT_DIR` (default `/tmp/crawler-live-scrape`). Install the browser on a test host with `python -m playwright install chromium` and the required system browser libraries before using that diagnostic. The standard suite does not enable it automatically.

For documentation/deployment configuration changes, validate Compose without starting services:

```bash
docker compose --env-file .env.docker.example -f compose.yaml -f compose.local.yaml config --quiet
docker compose --env-file .env.production.example -f compose.yaml -f compose.production.yaml config --quiet
python -m unittest tests.test_deployment -v
```

Passing configuration/unit checks does not replace a production acceptance search with the actual model, provider sessions, and target server resources.
