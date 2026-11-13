"""Установщик проверяется под Bash с подставным Docker, без рабочих данных и Telegram."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSION = "v1.8.0"
PREVIOUS = "v1.7.2"
FAKE_DOCKER = r"""#!/usr/bin/env bash
set -euo pipefail
printf '%s | %s\n' "${XTIME_TAG:-unset}" "$*" >> "$HARNESS_LOG"
case "$*" in
  'compose version'|'info'|image\ inspect\ *) exit 0 ;;
  'compose ps -q web') echo fake-web ;;
  'compose ps -q api') echo fake-api ;;
  compose\ up\ *)
    if [ "${HARNESS_FAIL_UP:-0}" = 1 ]; then
      echo 'API migration failed (fixture)' >&2
      exit 1
    fi
    ;;
  'compose stop bot') ;;
  inspect\ -f\ *) echo healthy ;;
  'compose exec -T api teamtime version') echo "${HARNESS_ACTUAL_VERSION:-$XTIME_TAG}" ;;
  run\ --rm\ --network\ none\ --entrypoint\ python\ *) echo fictional-generated-value ;;
  *) echo "Unexpected fake Docker operation: $*" >&2; exit 70 ;;
esac
"""
TEMPLATE = """POSTGRES_PASSWORD=
SESSION_SECRET=
BOT_TOKEN=
BOT_USERNAME=
ADMIN_PASSWORD=
WEB_PORT=8090
PUBLIC_URL=http://localhost:8090
"""


def bash_path() -> str | None:
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base and (candidate := Path(base) / "Git/bin/bash.exe").is_file():
                return str(candidate)
        return None
    return shutil.which("bash")


def shell_path(path: Path) -> str:
    value = path.as_posix()
    return f"/{value[0].lower()}{value[2:]}" if os.name == "nt" else value


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bash = bash_path()
        if not self.bash:
            self.skipTest("Нужен Bash, на Windows — Git Bash")
        self.temp = tempfile.TemporaryDirectory(prefix="xtime-install-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "release"
        self.destination = root / "installed"
        self.bin = root / "bin"
        self.log = root / "docker.log"
        for directory in (self.source, self.destination, self.bin):
            directory.mkdir()
        self.write(self.bin / "docker", FAKE_DOCKER)
        (self.bin / "docker").chmod(0o755)
        self.write(self.bin / "hostname", "#!/usr/bin/env bash\necho 127.0.0.1\n")
        (self.bin / "hostname").chmod(0o755)
        self.write(self.source / "install.sh", (ROOT / "deploy/install.sh").read_text(encoding="utf-8"))
        self.write(self.source / "VERSION", VERSION + "\n")
        self.write(self.source / ".env.example", TEMPLATE)
        for filename in ("docker-compose.yml", "README.md", "backup.sh"):
            self.write(self.source / filename, "# Демонстрационный файл теста\n")

    @staticmethod
    def write(path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8", newline="\n")

    def existing_install(self) -> str:
        configuration = TEMPLATE.replace("POSTGRES_PASSWORD=", "POSTGRES_PASSWORD=fictional-db")
        configuration = configuration.replace("SESSION_SECRET=", "SESSION_SECRET=fictional-session")
        configuration += f"XTIME_TAG={PREVIOUS}\n"
        self.write(self.destination / ".env", configuration)
        self.write(self.destination / "VERSION", PREVIOUS + "\n")
        return configuration

    def run_installer(self, *, installed: bool = False, **settings: str) -> subprocess.CompletedProcess[str]:
        script = (self.destination if installed else self.source) / "install.sh"
        # Абсолютные пути аргументов подходят и POSIX, и Git Bash; PATH меняется только
        # внутри дочернего процесса, поэтому настоящий Docker никогда не вызывается.
        command = (
            f"export PATH={shlex.quote(shell_path(self.bin))}:\"$PATH\"; "
            f"[ \"$(command -v docker)\" = {shlex.quote(shell_path(self.bin / 'docker'))} ] || exit 71; "
            f"bash {shlex.quote(shell_path(script))} {shlex.quote(shell_path(self.destination))}"
        )
        environment = {**os.environ, "HARNESS_LOG": shell_path(self.log), **settings}
        environment.pop("XTIME_TAG", None)
        return subprocess.run(
            [self.bash, "--noprofile", "--norc", "-c", command],
            env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def test_update_uses_bundle_tag_instead_of_old_pin(self) -> None:
        self.existing_install()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.log.read_text(encoding="utf-8")
        self.assertIn(f"{VERSION} | compose up -d --remove-orphans db api web", log)
        self.assertIn(f"image inspect xtime-backend:{VERSION}", log)
        self.assertIn(f"{VERSION} | compose exec -T api teamtime version", log)
        self.assertNotIn("prune", log)
        self.assertNotIn(":current", log)
        self.assertEqual((self.destination / "VERSION").read_text().strip(), VERSION)
        self.assertIn(f"XTIME_TAG={VERSION}\n", (self.destination / ".env").read_text())

    def test_first_install_can_resume_from_destination(self) -> None:
        prepared = self.run_installer()
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertFalse((self.destination / "VERSION").exists())
        self.assertEqual((self.destination / "RELEASE_VERSION").read_text().strip(), VERSION)
        self.assertNotIn("compose up", self.log.read_text(encoding="utf-8"))
        resumed = self.run_installer(installed=True)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual((self.destination / "VERSION").read_text().strip(), VERSION)
        self.assertIn(f"{VERSION} | compose up", self.log.read_text(encoding="utf-8"))

    def test_migration_failure_preserves_confirmed_version_and_configuration(self) -> None:
        original = self.existing_install()
        failed = self.run_installer(HARNESS_FAIL_UP="1")
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("API migration failed (fixture)", failed.stderr)
        self.assertEqual((self.destination / "VERSION").read_text().strip(), PREVIOUS)
        self.assertEqual((self.destination / ".env").read_text(), original)
        self.assertNotIn("работает:", failed.stdout)
        resumed = self.run_installer(installed=True)
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual((self.destination / "VERSION").read_text().strip(), VERSION)

    def test_runtime_version_mismatch_is_not_reported_as_success(self) -> None:
        original = self.existing_install()
        result = self.run_installer(HARNESS_ACTUAL_VERSION=PREVIOUS)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.destination / "VERSION").read_text().strip(), PREVIOUS)
        self.assertEqual((self.destination / ".env").read_text(), original)
        self.assertNotIn("работает:", result.stdout)


if __name__ == "__main__":
    unittest.main()
