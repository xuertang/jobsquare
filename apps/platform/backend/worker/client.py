"""HTTP client for the API. The worker never touches the database."""
from __future__ import annotations

import json
from pathlib import Path

import httpx


class Api:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        """`token` is the worker token of a deployed API (COPILOT_WORKER_TOKEN).
        A local API without a login needs none."""
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.http = httpx.Client(base_url=base_url.rstrip("/") + "/api/worker",
                                 timeout=120, headers=headers)

    def _post(self, path: str, **kwargs) -> dict:
        r = self.http.post(path, **kwargs)
        r.raise_for_status()
        return r.json()

    def claim(self) -> dict | None:
        return self._post("/claim").get("task")

    def heartbeat(self, task_id: int) -> str:
        return self._post(f"/tasks/{task_id}/heartbeat").get("state", "")

    def plan(self, application_id: int, fields: list[dict]) -> list[dict]:
        return self._post(f"/applications/{application_id}/plan",
                          json={"fields": fields})["decisions"]

    def filled(self, application_id: int, decisions: list[dict], results: dict,
               report: dict) -> dict:
        return self._post(f"/applications/{application_id}/filled",
                          json={"decisions": decisions, "results": results, "report": report})

    def snapshot(self, application_id: int, values: dict[str, str]) -> None:
        self._post(f"/applications/{application_id}/snapshot", json=values)

    def submitted(self, application_id: int, values: dict[str, str],
                  screenshot: bytes | None) -> dict:
        files = {"screenshot": ("confirmation.png", screenshot, "image/png")} if screenshot else None
        return self._post(f"/applications/{application_id}/submitted",
                          data={"values": json.dumps(values)}, files=files)

    def released(self, application_id: int, task_id: int, reason: str,
                 needs_manual: bool = False) -> None:
        self._post(f"/applications/{application_id}/released",
                   json={"reason": reason, "needs_manual": needs_manual, "task_id": task_id})

    def download_resume(self, resume: dict, into: Path) -> Path:
        """Fetch the resume file for upload. It keeps its original filename
        (the employer sees it), so each variant gets its own directory."""
        folder = into / str(resume["id"])
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (Path(resume["filename"] or "resume").name or "resume")
        r = self.http.get(f"/resumes/{resume['id']}/file")
        r.raise_for_status()
        path.write_bytes(r.content)
        return path
