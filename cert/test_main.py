import io
import json
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from http.cookiejar import CookieJar
from pathlib import Path
from unittest.mock import patch

import uvicorn

from app.config import DEFAULT_PLACEHOLDER
from app.main import app
from app.services import jobs
from app.services import certificates
from app.services.auth import create_session_token, verify_session_token
from app.services.settings import SettingsStore
from app.services.users import UserStore


class CertificateGeneratorTests(unittest.TestCase):
    def test_load_names_skips_blank_lines_and_utf8_bom(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            names_file = Path(temporary_directory) / "names.txt"
            names_file.write_text("\ufeff Alice \n\nBob\n  \n", encoding="utf-8")

            self.assertEqual(certificates.load_names(names_file), ["Alice", "Bob"])

    def test_unique_pdf_name_sanitizes_and_handles_duplicates(self):
        used_names = set()

        self.assertEqual(
            certificates._unique_pdf_name(" Ali/Reza ", used_names),
            "Ali_Reza.pdf",
        )
        self.assertEqual(
            certificates._unique_pdf_name("Ali/Reza", used_names),
            "Ali_Reza_2.pdf",
        )
        self.assertEqual(
            certificates._unique_pdf_name(" . ", used_names),
            "certificate.pdf",
        )

    def test_write_docx_with_name_replaces_document_xml_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            work_dir = Path(temporary_directory)
            template = work_dir / "template.docx"
            output = work_dir / "output.docx"

            with zipfile.ZipFile(template, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<xml />")
                archive.writestr(
                    certificates.DOCUMENT_XML,
                    "<w:document><w:t>PLACEHOLDER</w:t></w:document>",
                )

            certificates._write_docx_with_name(template, output, "PLACEHOLDER", "Ali & Reza")

            with zipfile.ZipFile(output) as archive:
                document_xml = archive.read(certificates.DOCUMENT_XML).decode("utf-8")

            self.assertIn("Ali &amp; Reza", document_xml)
            self.assertNotIn("PLACEHOLDER", document_xml)

    def test_write_docx_with_name_updates_placeholder_font_family(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            work_dir = Path(temporary_directory)
            template = work_dir / "template.docx"
            output = work_dir / "output.docx"
            document_xml = (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body>'
                '<w:p><w:r><w:rPr><w:rFonts w:ascii="Other Font" w:hAnsi="Other Font" w:cs="Other Font"/></w:rPr><w:t>UNCHANGED</w:t></w:r></w:p>'
                '<w:p><w:r><w:rPr><w:rFonts w:ascii="Abar High" w:hAnsi="Abar High" w:cs="Abar High"/></w:rPr><w:t>PLACEHOLDER</w:t></w:r></w:p>'
                "</w:body></w:document>"
            )

            with zipfile.ZipFile(template, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(certificates.DOCUMENT_XML, document_xml)

            certificates._write_docx_with_name(
                template,
                output,
                "PLACEHOLDER",
                "Ali",
                "Uploaded Font",
            )

            with zipfile.ZipFile(output) as archive:
                updated_xml = archive.read(certificates.DOCUMENT_XML).decode("utf-8")

            self.assertIn('w:ascii="Uploaded Font"', updated_xml)
            self.assertIn('w:hAnsi="Uploaded Font"', updated_xml)
            self.assertIn('w:cs="Uploaded Font"', updated_xml)
            self.assertIn('w:ascii="Other Font"', updated_xml)
            self.assertNotIn("Abar High", updated_xml)

    def test_convert_docx_to_pdf_builds_libreoffice_command(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            work_dir = Path(temporary_directory)
            docx_path = work_dir / "certificate.docx"
            output_dir = work_dir / "out"
            output_dir.mkdir()
            docx_path.write_text("not a real docx", encoding="utf-8")

            with patch("app.services.certificates.subprocess.run") as run:
                run.return_value.returncode = 0
                pdf_path = certificates._convert_docx_to_pdf(
                    docx_path=docx_path,
                    output_dir=output_dir,
                    libreoffice="/usr/bin/soffice",
                    env={"HOME": str(work_dir)},
                )

            self.assertEqual(pdf_path, output_dir / "certificate.pdf")
            command = run.call_args.args[0]
            self.assertEqual(command[0], "/usr/bin/soffice")
            self.assertIn("--headless", command)
            self.assertIn("--convert-to", command)
            self.assertIn("pdf", command)
            self.assertIn("--outdir", command)
            self.assertIn(str(output_dir), command)
            self.assertIn(str(docx_path), command)
            self.assertTrue(
                any(part.startswith("-env:UserInstallation=") for part in command)
            )

    def test_convert_docx_files_to_pdf_batches_libreoffice_command(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            work_dir = Path(temporary_directory)
            first_docx = work_dir / "first.docx"
            second_docx = work_dir / "second.docx"
            output_dir = work_dir / "out"
            output_dir.mkdir()
            first_docx.write_text("not a real docx", encoding="utf-8")
            second_docx.write_text("not a real docx", encoding="utf-8")

            with patch("app.services.certificates.subprocess.run") as run:
                run.return_value.returncode = 0
                pdf_paths = certificates._convert_docx_files_to_pdf(
                    docx_paths=[first_docx, second_docx],
                    output_dir=output_dir,
                    libreoffice="/usr/bin/soffice",
                    env={"HOME": str(work_dir)},
                    work_dir=work_dir,
                )

            self.assertEqual(
                pdf_paths,
                {
                    first_docx: output_dir / "first.pdf",
                    second_docx: output_dir / "second.pdf",
                },
            )
            self.assertEqual(run.call_count, 1)
            command = run.call_args.args[0]
            self.assertIn(str(first_docx), command)
            self.assertIn(str(second_docx), command)

    def test_generate_certificates_fast_path_does_not_require_libreoffice(self):
        template = Path("data/templates/certificate.docx")
        font = Path("data/fonts/AbarHigh-SemiBold.ttf")
        if not template.exists() or not font.exists():
            self.skipTest("Default runtime certificate assets are not available")

        with tempfile.TemporaryDirectory() as temporary_directory:
            work_dir = Path(temporary_directory)
            names_file = work_dir / "names.txt"
            output_dir = work_dir / "out"
            names_file.write_text("علی\nSara\n", encoding="utf-8")

            with patch(
                "app.services.certificates._find_libreoffice",
                side_effect=AssertionError("fast path should not use LibreOffice"),
            ):
                pdfs = certificates.generate_certificates(
                    names_file=names_file,
                    output_dir=output_dir,
                    template_path=template,
                    font_path=font,
                    placeholder=DEFAULT_PLACEHOLDER,
                )

            self.assertEqual([pdf.name for pdf in pdfs], ["علی.pdf", "Sara.pdf"])
            self.assertTrue(all(pdf.stat().st_size > 0 for pdf in pdfs))

    def test_font_verification_uses_uploaded_font_family_name(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            copied_font = Path(temporary_directory) / "uploaded.ttf"
            copied_font.write_bytes(b"font")

            with patch.object(certificates, "_font_query_names") as query_names, patch.object(
                certificates, "_run_checked"
            ) as run_checked:
                query_names.return_value = ["Uploaded Family"]
                run_checked.return_value = subprocess.CompletedProcess(
                    ["fc-match"],
                    0,
                    stdout=str(copied_font) + "\n",
                    stderr="",
                )

                certificates._verify_font_is_available(copied_font, {})

        command = run_checked.call_args.args[0]
        self.assertEqual(command[-1], "Uploaded Family")
        self.assertNotIn("Abar High", command)

    def test_prepare_font_environment_accepts_current_uploaded_font(self):
        font_path = Path("data/fonts/certificate-font.ttf")
        if not font_path.exists():
            self.skipTest("No uploaded runtime font exists")

        with tempfile.TemporaryDirectory() as temporary_directory:
            env = certificates._prepare_font_environment(font_path, Path(temporary_directory))

        self.assertIn("FONTCONFIG_FILE", env)
        self.assertEqual(env["CERTIFICATE_FONT_FAMILY"], "Abar Low")

    def test_settings_store_updates_placeholder_template_and_font(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            work_dir = Path(temporary_directory)
            settings_path = work_dir / "settings.json"

            store = SettingsStore(settings_path)
            settings = store.update(
                placeholder="NAME",
                template_upload=b"new-docx",
                template_filename="new.docx",
                font_upload=b"new-font",
                font_filename="new.ttf",
            )

            self.assertEqual(settings.placeholder, "NAME")
            self.assertEqual(settings.current_template_name, "new.docx")
            self.assertEqual(settings.current_font_name, "new.ttf")
            self.assertEqual(Path(settings.template_path).read_bytes(), b"new-docx")
            self.assertEqual(Path(settings.font_path).read_bytes(), b"new-font")

    def test_user_store_authenticates_default_admin(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = UserStore(Path(temporary_directory) / "users.json")

            user = store.authenticate("admin", "admin123")

            self.assertIsNotNone(user)
            self.assertTrue(user.is_admin)
            self.assertIsNone(store.authenticate("admin", "wrong"))

    def test_session_token_round_trip(self):
        token = create_session_token("admin")
        username_part, _signature_part = token.split(".", 1)

        self.assertEqual(verify_session_token(token), "admin")
        self.assertIsNone(verify_session_token(f"{username_part}.AAAA"))


class FastApiAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=cls.port, log_level="warning")
        cls.server = uvicorn.Server(config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        cls.cookie_jar = CookieJar()
        cls.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(cls.cookie_jar),
        )
        for _ in range(50):
            try:
                with cls.opener.open(cls.base_url + "/healthz", timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        else:
            cls.server.should_exit = True
            raise RuntimeError("Uvicorn did not become healthy.")

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)

    def setUp(self):
        self.login()

    def login(self):
        response = self.post_form(
            "/login",
            {"username": "admin", "password": "admin123"},
        )
        self.assertEqual(response.status, 200)

    def get(self, path: str):
        return self.opener.open(self.base_url + path, timeout=30)

    def post_form(self, path: str, data: dict[str, str], follow_redirects: bool = True):
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=encoded,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if follow_redirects:
            return self.opener.open(request, timeout=30)
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            _NoRedirectHandler(),
        )
        try:
            return opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                return exc
            raise

    def test_login_required_for_dashboard(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirectHandler())
        try:
            response = opener.open(self.base_url + "/", timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc

        self.assertEqual(response.status, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_dashboard_loads_frontend_and_admin_settings(self):
        with self.get("/") as response:
            body = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn("Batch PDFs", body)
        self.assertIn("Admin settings", body)
        self.assertIn("Certificate DOCX", body)
        self.assertIn("Certificate font", body)
        self.assertIn("/static/styles.css", body)

    def test_static_frontend_assets_are_served(self):
        with self.get("/static/styles.css") as css:
            css_body = css.read().decode("utf-8")
        with self.get("/static/app.js") as js:
            js_body = js.read().decode("utf-8")

        self.assertEqual(css.status, 200)
        self.assertIn(".spinner", css_body)
        self.assertIn("[hidden]", css_body)
        self.assertEqual(js.status, 200)
        self.assertIn("pollJob", js_body)
        self.assertIn("setSpinnerVisible(false)", js_body)
        self.assertIn("setSpinnerVisible(true)", js_body)

    def test_admin_can_update_placeholder(self):
        response = self.post_form(
            "/admin/settings",
            {"placeholder": "NEW_NAME"},
            follow_redirects=False,
        )

        self.assertEqual(response.status, 303)
        self.assertEqual(SettingsStore().load().placeholder, "NEW_NAME")

    def test_job_manager_runs_generation_in_background(self):
        def fake_generate(names_file, output_dir, **kwargs):
            self.assertEqual(Path(names_file).read_text(encoding="utf-8"), "علی\nSara\n")
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            first = output_path / "علی.pdf"
            second = output_path / "Sara.pdf"
            first.write_bytes(b"first pdf")
            second.write_bytes(b"second pdf")
            return [first, second]

        manager = jobs.JobManager(Path(tempfile.mkdtemp()))
        with patch("app.services.jobs.generate_certificates", side_effect=fake_generate):
            job = manager.submit(
                "admin",
                "علی\nSara\n".encode("utf-8"),
                SettingsStore().load(),
            )
            for _ in range(30):
                job = manager.get(job.id)
                if job.status == "complete":
                    break
                time.sleep(0.05)

        self.assertEqual(job.status, "complete")
        self.assertTrue(job.archive_path.exists())

    def test_api_job_flow_returns_downloadable_zip(self):
        SettingsStore().update(DEFAULT_PLACEHOLDER)
        def fake_generate(names_file, output_dir, **kwargs):
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            pdf = output_path / "علی.pdf"
            pdf.write_bytes(b"pdf")
            return [pdf]

        boundary = "----cert-test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="names_file"; filename="names.txt"\r\n'
            "Content-Type: text/plain; charset=utf-8\r\n\r\n"
            "علی\n"
            f"\r\n--{boundary}--\r\n"
        ).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/api/jobs",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with patch("app.services.jobs.generate_certificates", side_effect=fake_generate):
            with self.opener.open(request, timeout=30) as response:
                self.assertEqual(response.status, 200)
                status_url = json.loads(response.read().decode("utf-8"))["status_url"]

            payload = None
            for _ in range(30):
                with self.get(status_url) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload["status"] == "complete":
                    break
                if payload["status"] == "failed":
                    self.fail(payload["message"])
                time.sleep(0.05)

        self.assertEqual(payload["status"], "complete")
        with self.get(payload["download_url"]) as response:
            self.assertEqual(response.status, 200)
            archive_bytes = response.read()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            self.assertEqual(archive.namelist(), ["علی.pdf"])


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


if __name__ == "__main__":
    unittest.main()
