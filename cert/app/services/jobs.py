from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.config import config
from app.services.certificates import create_certificates_zip, generate_certificates
from app.services.settings import CertificateSettings


JobStatus = Literal["queued", "running", "complete", "failed"]


@dataclass
class CertificateJob:
    id: str
    owner: str
    names_file: Path
    output_dir: Path
    archive_path: Path
    settings: CertificateSettings
    status: JobStatus = "queued"
    message: str = "Waiting to start"
    download_url: str | None = None
    files: list[str] = field(default_factory=list)


class JobManager:
    def __init__(self, root: Path = config.job_dir):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, CertificateJob] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)

    def submit(self, owner: str, names: bytes, settings: CertificateSettings) -> CertificateJob:
        job_id = uuid.uuid4().hex
        job_dir = self.root / job_id
        output_dir = job_dir / "pdfs"
        job_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir()
        names_file = job_dir / "names.txt"
        names_file.write_bytes(names)
        archive_path = job_dir / "certificates.zip"
        job = CertificateJob(
            id=job_id,
            owner=owner,
            names_file=names_file,
            output_dir=output_dir,
            archive_path=archive_path,
            settings=settings,
        )
        with self._lock:
            self._jobs[job_id] = job
        self._executor.submit(self._run_job, job_id)
        return job

    def get(self, job_id: str) -> CertificateJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run_job(self, job_id: str) -> None:
        job = self.get(job_id)
        if not job:
            return
        self._update(job_id, status="running", message="Generating certificates")
        try:
            pdfs = generate_certificates(
                names_file=job.names_file,
                output_dir=job.output_dir,
                template_path=job.settings.template,
                font_path=job.settings.font,
                placeholder=job.settings.placeholder,
            )
            create_certificates_zip(pdfs, job.archive_path)
            self._update(
                job_id,
                status="complete",
                message="Certificates are ready",
                download_url=f"/api/jobs/{job_id}/download",
                files=[pdf.name for pdf in pdfs],
            )
        except Exception as exc:
            self._update(job_id, status="failed", message=str(exc))

    def _update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for name, value in changes.items():
                setattr(job, name, value)


job_manager = JobManager()
