from app.infra.seeders.airlines import seed_airlines
from app.infra.seeders.websites import seed_websites
from app.infra.seeders.airports import seed_airports
from app.infra.seeders.flight_paths import seed_flight_paths


def seed_database() -> None:
    print("Starting database seeding...")

    seed_airlines()
    seed_websites()
    seed_airports()
    seed_flight_paths()

    print("Database seeding completed.")


if __name__ == "__main__":
    seed_database()