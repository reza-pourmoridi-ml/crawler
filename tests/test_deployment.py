import json
import logging
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

from app.infra.logging_config import JsonFormatter


ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def test_extractor_registers_all_related_sqlalchemy_models(self):
        subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import app.extractor.repo; "
                    "from sqlalchemy.orm import configure_mappers; "
                    "configure_mappers()"
                ),
            ],
            cwd=ROOT,
            check=True,
        )

    def test_each_long_running_role_has_exactly_one_replica(self):
        compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        for role in ("control", "orchestrator", "scraper", "learn", "extractor", "ollama"):
            with self.subTest(role=role):
                self.assertEqual(compose["services"][role]["deploy"]["replicas"], 1)

    def test_model_download_is_automatic_and_blocks_learn_startup(self):
        compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        model_pull = compose["services"]["model-pull"]
        self.assertNotIn("profiles", model_pull)
        self.assertEqual(model_pull["restart"], "on-failure")
        self.assertEqual(
            compose["services"]["learn"]["depends_on"]["model-pull"]["condition"],
            "service_completed_successfully",
        )

    def test_pipeline_artifacts_use_ignored_host_storage(self):
        compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        self.assertNotIn("crawler_storage", compose["volumes"])
        for role in ("orchestrator", "scraper", "learn", "extractor"):
            mounts = compose["services"][role]["volumes"]
            data_mount = next(mount for mount in mounts if mount["target"] == "/data")
            with self.subTest(role=role):
                self.assertEqual(data_mount["type"], "bind")
                self.assertIn("STORAGE_HOST_PATH", data_mount["source"])

        ollama_mount = next(
            mount for mount in compose["services"]["ollama"]["volumes"]
            if mount["target"] == "/root/.ollama"
        )
        self.assertEqual(ollama_mount["type"], "bind")
        self.assertIn("STORAGE_HOST_PATH", ollama_mount["source"])
        self.assertTrue(ollama_mount["source"].endswith("/ollama"))
        self.assertNotIn("ollama_models", compose.get("volumes", {}))

        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("storage/*", gitignore)
        self.assertIn("app/auth/auth.json", gitignore)
        self.assertFalse((ROOT / "app/auth/auth.json").exists())

    def test_local_and_production_models_come_from_their_env_files(self):
        local_env = (ROOT / ".env.docker.example").read_text(encoding="utf-8")
        production_env = (
            ROOT / ".env.production.example"
        ).read_text(encoding="utf-8")
        self.assertIn("OLLAMA_MODEL=qwen2.5-coder:7b", local_env)
        self.assertNotIn("OLLAMA_MODEL=qwen2.5-coder:14b", local_env)
        self.assertIn("OLLAMA_MODEL=qwen2.5-coder:14b", production_env)

    def test_production_ollama_limits_are_twice_local_limits(self):
        base = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
        local = yaml.safe_load(
            (ROOT / "compose.local.yaml").read_text(encoding="utf-8")
        )
        production = yaml.safe_load(
            (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
        )
        base_limits = base["services"]["ollama"]["deploy"]["resources"]["limits"]
        local_limits = {
            **base_limits,
            **local["services"]["ollama"]["deploy"]["resources"]["limits"],
        }
        production_limits = production["services"]["ollama"]["deploy"]["resources"]["limits"]

        self.assertEqual(float(production_limits["cpus"]), 2 * float(local_limits["cpus"]))
        self.assertEqual(production_limits["memory"], "20G")
        self.assertEqual(local_limits["memory"], "10G")

    def test_json_logs_redact_common_sensitive_values(self):
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            (
                "password=secret token=abc123 "
                "postgresql+psycopg://crawler:dbpass@postgres/crawler "
                "https://provider.test/flights/THR-MHD?phone=09121234567"
            ),
            (),
            None,
        )
        payload = json.loads(JsonFormatter().format(record))
        message = payload["message"]
        for secret in ("secret", "abc123", "dbpass", "THR-MHD", "09121234567"):
            self.assertNotIn(secret, message)


if __name__ == "__main__":
    unittest.main()
