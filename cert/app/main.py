from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import config
from app.services.auth import create_session_token, current_admin, current_user
from app.services.jobs import job_manager
from app.services.settings import SettingsStore
from app.services.users import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, User, UserStore


app = FastAPI(title="Certificate Generator")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)


@app.on_event("startup")
def initialize_app() -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    SettingsStore().ensure_initialized()
    UserStore().ensure_initialized()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "default_username": DEFAULT_ADMIN_USERNAME,
            "default_password": DEFAULT_ADMIN_PASSWORD,
        },
    )


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    user = UserStore().authenticate(username, password)
    if not user:
        return RedirectResponse("/login?error=1", status_code=303)

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        config.session_cookie_name,
        create_session_token(user.username),
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(config.session_cookie_name)
    return response


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(current_user)) -> HTMLResponse:
    settings = SettingsStore().load()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "settings": settings},
    )


@app.post("/api/jobs")
async def create_job(
    names_file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> dict[str, str]:
    content = await names_file.read()
    if not content.strip():
        raise HTTPException(status_code=400, detail="Uploaded names file is empty.")
    if len(content) > config.max_upload_bytes:
        raise HTTPException(status_code=400, detail="Uploaded names file is too large.")
    settings = SettingsStore().load()
    job = job_manager.submit(user.username, content, settings)
    return {"job_id": job.id, "status_url": f"/api/jobs/{job.id}"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(current_user)) -> dict:
    job = _get_authorized_job(job_id, user)
    return {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "download_url": job.download_url,
        "files": job.files,
    }


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str, user: User = Depends(current_user)) -> FileResponse:
    job = _get_authorized_job(job_id, user)
    if job.status != "complete" or not job.archive_path.exists():
        raise HTTPException(status_code=404, detail="Certificates are not ready yet.")
    return FileResponse(
        job.archive_path,
        media_type="application/zip",
        filename="certificates.zip",
    )


@app.post("/admin/settings")
async def update_settings(
    placeholder: str = Form(...),
    template_file: UploadFile | None = File(default=None),
    font_file: UploadFile | None = File(default=None),
    user: User = Depends(current_admin),
) -> RedirectResponse:
    del user
    template_bytes = await template_file.read() if template_file and template_file.filename else None
    font_bytes = await font_file.read() if font_file and font_file.filename else None
    try:
        SettingsStore().update(
            placeholder=placeholder,
            template_upload=template_bytes,
            template_filename=template_file.filename if template_file else None,
            font_upload=font_bytes,
            font_filename=font_file.filename if font_file else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse("/", status_code=303)


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": exc.status_code, "message": exc.detail},
        status_code=exc.status_code,
    )


def _get_authorized_job(job_id: str, user: User):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.owner != user.username and not user.is_admin:
        raise HTTPException(status_code=403, detail="You cannot access this job.")
    return job
