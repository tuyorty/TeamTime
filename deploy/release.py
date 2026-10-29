"""Сборка автономного релиза на Linux, macOS и Windows; секреты в архив не попадают."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def output(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True, encoding="utf-8").strip()


def archive_entry(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Права Linux задаём явно: файловая система Windows не хранит executable bit."""
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    info.mode = 0o755 if info.isdir() or info.name.endswith(".sh") else 0o644
    info.pax_headers = {}
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Тег текущего коммита; по умолчанию определяется из Git")
    parser.add_argument("--platform", choices=["linux/amd64", "linux/arm64"], default="linux/amd64")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    version = args.version or output("git", "describe", "--tags", "--exact-match")
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        parser.error("Версия должна быть тегом вида v1.2.0")
    if output("git", "status", "--porcelain"):
        parser.error(
            "Сначала сохраните изменения в коммиты: релиз собирается из чистой рабочей копии"
        )
    if output("git", "rev-parse", f"{version}^{{commit}}") != output("git", "rev-parse", "HEAD"):
        parser.error("Тег версии должен указывать на текущий коммит")
    destination = args.output_dir.resolve()
    name = f"xtime-{version}"
    release = destination / name
    archive = destination / f"{name}.tar.gz"
    checksum = destination / f"{name}.tar.gz.sha256"
    if any(path.exists() for path in (release, archive, checksum)):
        parser.error("Каталог или архив релиза уже существует; выберите другой --output-dir")
    run("docker", "info", "--format", "{{.OSType}}")
    images = []
    for component, context in (("backend", "backend"), ("web", "frontend"), ("db", "deploy")):
        tagged, current = f"xtime-{component}:{version}", f"xtime-{component}:current"
        command = ["docker", "buildx", "build", "--platform", args.platform, "--load"]
        if component == "backend":
            command += ["--build-arg", f"XTIME_VERSION={version}"]
        if component == "db":
            command += ["-f", "deploy/db.Dockerfile"]
        run(*command, "-t", tagged, "-t", current, context)
        if (
            output("docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", tagged)
            != args.platform
        ):
            raise RuntimeError(f"Неверная архитектура образа {tagged}")
        images.extend((tagged, current))
    actual_version = output(
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        "python",
        f"xtime-backend:{version}",
        "-c",
        "import teamtime; print(teamtime.__version__)",
    )
    if actual_version != version:
        raise RuntimeError(f"Версия внутри образа {actual_version!r} не совпадает с тегом")
    release.mkdir(parents=True)
    for filename in (
        "docker-compose.yml",
        ".env.example",
        "install.sh",
        "backup.sh",
        "README.md",
        "xtime-tg-tunnel.service",
    ):
        text = (ROOT / "deploy" / filename).read_text(encoding="utf-8")
        (release / filename).write_text(text, encoding="utf-8", newline="\n")
    (release / "VERSION").write_text(version + "\n", encoding="utf-8", newline="\n")
    notes = ROOT / "docs" / "releases" / f"{version}.md"
    if notes.exists():
        (release / "UPDATE.md").write_text(
            notes.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
        )
    # Поток Docker сжимаем напрямую: PowerShell 5 не должен преобразовать бинарные данные в текст.
    with subprocess.Popen(["docker", "save", *images], stdout=subprocess.PIPE, cwd=ROOT) as process:
        assert process.stdout is not None
        with gzip.open(release / "images.tar.gz", "wb") as compressed:
            shutil.copyfileobj(process.stdout, compressed)
        if process.wait() != 0:
            raise RuntimeError("Не удалось сохранить образы Docker")
    with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as bundle:
        bundle.add(release, arcname=name, filter=archive_entry)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii", newline="\n")
    print(f"Готово: {archive} ({archive.stat().st_size / 1024**2:.1f} МБ)")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    main()
