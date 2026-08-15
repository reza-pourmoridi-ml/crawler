# Why worker-based architecture?

1. **Keep HTTP fast** — heavy, long-running jobs (ML inference) must never block request handling.
2. **Resource isolation** — each module (extraction, learning) runs as its own container/process with explicit CPU/RAM limits; heavy jobs can't degrade the API tier. Scaling is done by running multiple replicas of the same worker process, coordinated safely via `SKIP LOCKED`.
3. **Queue-based backpressure** — a Postgres-backed job queue (`FOR UPDATE SKIP LOCKED`) absorbs spikes; throughput is controlled by how many workers we run, not by request concurrency. No separate broker (Redis/RabbitMQ) is needed at current volume (<100 jobs/hour).
4. **Reliability & retries** — failed jobs can be retried without losing work; the web app doesn't crash or timeout on them.
5. **Independent scaling** — we scale compute-heavy workers up/down without touching the (light) web service.

**In short:** the job types in this project are CPU-heavy and long-running, so we offload them to dedicated workers instead of running them inside the request path.
