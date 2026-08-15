from app.infra.db import run_migrations


def start_app():
    run_migrations()
    print("Starting application services...")


if __name__ == "__main__":
    start_app()
