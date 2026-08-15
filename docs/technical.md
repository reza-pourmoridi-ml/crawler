main goal:
    form this websites (alibaba safar360 booking flytody), for all airlines
    find lowest price fly for specific pathes and return data like a provider.
    best case scenario: is that all process can be done only using a basic linux server nor Ai graphical server.


attributes:


architect:
    name: Containerized Modular Monolith with Central Orchestration and Asynchronous Workers

    overview:
        - One repository and shared Python codebase
        - Separate Docker containers for API, orchestration, learning, and extraction workers
        - Central orchestration manages workflows, job state, retries, and result aggregation
        - Long-running crawling and AI tasks run asynchronously in workers
        - Must run on a basic CPU-only Linux server

    modules:
        control:
            - External API, request validation, job status, and responses

        orchestration:
            - Create jobs, dispatch tasks, track workflow state, and aggregate results

        extraction:
            - Provider-specific crawling, browser automation, parsing, and flight-offer normalization

        learning:
            - Manage learned selectors, extraction mappings, evaluations, and optional local AI inference

        infra:
            - PostgreSQL, queue/broker, storage, configuration, logging, and common utilities

    data:
        postgresql:
            - Search requests, jobs, workflow state, providers, normalized flight offers, errors

        shared_storage:
            mount: /app/storage
            directories:
                - raw: original responses and downloaded artifacts
                - learned: selectors, schemas, and learning artifacts
                - extracted: parsed extraction outputs
                - temp: temporary processing files

        rules:
            - Large or temporary files go to storage
            - Metadata and state go to PostgreSQL
            - File access must use app.infra.storage

    execution:
        - python -m app.control
        - python -m app.orchestration
        - python -m app.learning
        - python -m app.extraction

    workflow:
        - Receive flight search request
        - Create and persist a job
        - Dispatch provider extraction tasks asynchronously
        - Normalize and aggregate offers
        - Store results and return job status or final offers

    reliability:
        - Job states: pending, running, succeeded, partially_succeeded, failed, cancelled
        - Timeouts, bounded retries, and exponential backoff
        - Provider failure must not discard successful results from other providers

    deployment:
        - Docker Compose on a Linux server
        - PostgreSQL and a shared Docker volume
        - Optional queue/broker and Ollama container
        - Extraction and learning workers can scale independently


e2e tests:


deployment:

backlog:
    sprint:


