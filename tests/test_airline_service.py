"""Airline service regressions using an isolated, in-memory database."""

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.control import service
from app.control.airlines.models import Airline, AirlineAlias
from app.infra.db import Base


class AirlineServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(
            self.engine,
            tables=[Airline.__table__, AirlineAlias.__table__],
        )
        self.db = Session(self.engine, autoflush=False)
        self.addCleanup(self.db.close)

        airline = Airline(
            official_name_fa="ایران ایر",
            aliases=[
                AirlineAlias(alias_name="Iran Air"),
                AirlineAlias(alias_name="Homa"),
            ],
        )
        other_airline = Airline(
            official_name_fa="ماهان",
            aliases=[AirlineAlias(alias_name="Mahan")],
        )
        self.db.add_all([airline, other_airline])
        self.db.commit()
        self.airline_id = airline.id
        self.other_airline_id = other_airline.id
        self.original_alias_ids = {
            alias.alias_name: alias.id for alias in airline.aliases
        }

    def snapshot(self):
        """Read committed rows independently of the service's identity map."""
        with Session(self.engine) as db:
            airlines = list(
                db.execute(
                    select(Airline.id, Airline.official_name_fa).order_by(Airline.id)
                )
            )
            aliases = list(
                db.execute(
                    select(
                        AirlineAlias.id,
                        AirlineAlias.airline_id,
                        AirlineAlias.alias_name,
                    ).order_by(AirlineAlias.id)
                )
            )
        return airlines, aliases

    def test_unchanged_save_preserves_alias_ids(self):
        original = self.snapshot()

        for _ in range(2):
            airline = service.update_airline(
                self.db,
                self.airline_id,
                "ایران ایر",
                ["Iran Air", "Homa"],
            )
            self.assertEqual(
                {alias.alias_name: alias.id for alias in airline.aliases},
                self.original_alias_ids,
            )
            self.assertEqual(self.snapshot(), original)

    def test_mixed_alias_edit_retains_existing_ids_and_removes_orphans(self):
        airline = service.update_airline(
            self.db,
            self.airline_id,
            "ایران‌ایر",
            ["Homa", "IR"],
        )

        aliases = {alias.alias_name: alias.id for alias in airline.aliases}
        self.assertEqual(airline.official_name_fa, "ایران‌ایر")
        self.assertEqual(set(aliases), {"Homa", "IR"})
        self.assertEqual(aliases["Homa"], self.original_alias_ids["Homa"])
        with Session(self.engine) as db:
            self.assertIsNone(db.get(AirlineAlias, self.original_alias_ids["Iran Air"]))
            other = db.get(Airline, self.other_airline_id)
            self.assertEqual(other.official_name_fa, "ماهان")
            self.assertEqual([alias.alias_name for alias in other.aliases], ["Mahan"])

    def test_clearing_aliases_deletes_persisted_rows(self):
        airline = service.update_airline(
            self.db, self.airline_id, "ایران ایر", []
        )

        self.assertEqual(airline.aliases, [])
        with Session(self.engine) as db:
            self.assertEqual(
                list(
                    db.scalars(
                        select(AirlineAlias).where(
                            AirlineAlias.airline_id == self.airline_id
                        )
                    )
                ),
                [],
            )

    def test_names_are_trimmed_and_blank_duplicate_aliases_removed(self):
        airline = service.update_airline(
            self.db,
            self.airline_id,
            "  ایران ایر\t",
            [" Iran Air ", "", "  ", "Iran Air", " IR\n", "IR", "\t"],
        )

        self.assertEqual(airline.official_name_fa, "ایران ایر")
        aliases = {alias.alias_name: alias.id for alias in airline.aliases}
        self.assertEqual(set(aliases), {"Iran Air", "IR"})
        self.assertEqual(aliases["Iran Air"], self.original_alias_ids["Iran Air"])

    def test_empty_or_whitespace_name_is_rejected_without_changes(self):
        original = self.snapshot()
        for name in ("", " ", "\t\n"):
            with self.subTest(name=repr(name)):
                with self.assertRaises(ValueError):
                    service.update_airline(self.db, self.airline_id, name, ["New alias"])
                self.db.commit()
                self.assertEqual(self.snapshot(), original)

    def test_oversized_official_name_is_rejected_without_changes(self):
        original = self.snapshot()

        with self.assertRaises(ValueError):
            service.update_airline(
                self.db, self.airline_id, "ا" * 256, ["New alias"]
            )

        self.db.commit()
        self.assertEqual(self.snapshot(), original)

    def test_oversized_alias_is_rejected_without_changes(self):
        original = self.snapshot()

        with self.assertRaises(ValueError):
            service.update_airline(
                self.db,
                self.airline_id,
                "نام جدید",
                ["Valid alias", "ا" * 256],
            )

        self.db.commit()
        self.assertEqual(self.snapshot(), original)

    def test_255_character_names_are_valid_after_trimming(self):
        official_name = "ا" * 255
        alias_name = "A" * 255

        airline = service.update_airline(
            self.db,
            self.airline_id,
            f"  {official_name}  ",
            [f"  {alias_name}  "],
        )

        self.assertEqual(airline.official_name_fa, official_name)
        self.assertEqual([alias.alias_name for alias in airline.aliases], [alias_name])

    def test_duplicate_official_name_rolls_back_all_changes(self):
        original = self.snapshot()

        with self.assertRaises(service.AirlineAlreadyExistsError):
            service.update_airline(
                self.db, self.airline_id, "ماهان", ["Homa", "New alias"]
            )

        self.assertEqual(self.snapshot(), original)
        airline = service.update_airline(
            self.db, self.airline_id, "ایران‌ایر", ["Iran Air", "Homa"]
        )
        self.assertEqual(airline.official_name_fa, "ایران‌ایر")
        self.assertEqual(
            {alias.alias_name: alias.id for alias in airline.aliases},
            self.original_alias_ids,
        )

    def test_missing_airline_is_reported_without_changes(self):
        original = self.snapshot()

        with self.assertRaises(service.AirlineNotFoundError):
            service.get_airline(self.db, 99999)
        with self.assertRaises(service.AirlineNotFoundError):
            service.update_airline(self.db, 99999, "ایرلاین", ["Alias"])
        with self.assertRaises(service.AirlineNotFoundError):
            service.delete_airline(self.db, 99999)

        self.assertEqual(self.snapshot(), original)

    def test_create_persists_and_normalizes_airline_and_aliases(self):
        airline = service.create_airline(
            self.db, "  کیش ایر  ", [" Kish Air ", "", "Kish Air", "Y9"]
        )

        with Session(self.engine) as db:
            saved = db.get(Airline, airline.id)
            self.assertEqual(saved.official_name_fa, "کیش ایر")
            self.assertEqual({alias.alias_name for alias in saved.aliases}, {"Kish Air", "Y9"})
            self.assertIsNotNone(saved.created_at)

    def test_create_duplicate_rolls_back_and_session_remains_usable(self):
        original = self.snapshot()
        with self.assertRaises(service.AirlineAlreadyExistsError):
            service.create_airline(self.db, "  ماهان  ", ["New alias"])

        self.assertEqual(self.snapshot(), original)
        created = service.create_airline(self.db, "کیش ایر", [])
        self.assertEqual(created.aliases, [])

    def test_create_invalid_values_leave_database_unchanged(self):
        original = self.snapshot()
        for name, aliases in [
            (" ", []), ("ا" * 256, []), ("کیش ایر", ["x" * 256]),
            ("نام\x00جدید", []), ("کیش ایر", ["new\x00alias"]),
        ]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    service.create_airline(self.db, name, aliases)
                self.db.commit()
                self.assertEqual(self.snapshot(), original)

    def test_delete_removes_aliases_and_preserves_other_airlines(self):
        service.delete_airline(self.db, self.airline_id)

        with Session(self.engine) as db:
            self.assertIsNone(db.get(Airline, self.airline_id))
            self.assertEqual(
                list(db.scalars(select(AirlineAlias).where(AirlineAlias.airline_id == self.airline_id))),
                [],
            )
            other = db.get(Airline, self.other_airline_id)
            self.assertEqual(other.official_name_fa, "ماهان")
            self.assertEqual([alias.alias_name for alias in other.aliases], ["Mahan"])


if __name__ == "__main__":
    unittest.main()
