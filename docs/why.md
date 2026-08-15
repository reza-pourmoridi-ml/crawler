# Why worker-based architecture?

1. **Keep HTTP fast** — heavy, long-running jobs (ML inference) must never block request handling.
2. **Resource isolation** — workers run in separate containers with explicit CPU/RAM limits, so one heavy job can't degrade the web tier.
3. **Queue-based backpressure** — a message queue absorbs spikes; throughput is controlled by how many workers we run, not by request concurrency.
4. **Reliability & retries** — failed jobs can be retried without losing work; the web app doesn't crash or timeout on them.
5. **Independent scaling** — we scale compute-heavy workers up/down without touching the (light) web service.

**In short:** the job types in this project are CPU-heavy and long-running, so we offload them to dedicated workers instead of running them inside the request path.
