from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import PurePosixPath

import httpx

API_BASE = "https://api.github.com"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


@dataclass
class UploadResult:
    path: str
    branch: str
    sha: str


class GitHubClientError(Exception):
    pass


class GitHubClient:
    def __init__(self, token: str, owner: str, repo: str) -> None:
        self._owner = owner
        self._repo = repo
        self._http = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
        )

    @property
    def _repo_prefix(self) -> str:
        return f"{API_BASE}/repos/{self._owner}/{self._repo}"

    def ensure_branch(self, branch: str, base: str = "main") -> str:
        resp = self._http.get(
            f"{self._repo_prefix}/git/ref/heads/{branch}"
        )
        if resp.status_code == 200:
            return resp.json()["object"]["sha"]

        base_resp = self._http.get(
            f"{self._repo_prefix}/git/ref/heads/{base}"
        )
        if base_resp.status_code != 200:
            raise GitHubClientError(
                f"Base branch '{base}' not found: {base_resp.status_code}"
            )
        base_sha = base_resp.json()["object"]["sha"]

        create_resp = self._http.post(
            f"{self._repo_prefix}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
        )
        if create_resp.status_code not in (200, 201):
            raise GitHubClientError(
                f"Failed to create branch '{branch}': "
                f"{create_resp.status_code} {create_resp.text}"
            )
        return base_sha

    def upload_file(
        self,
        repo_path: str,
        content: bytes,
        branch: str,
        message: str = "",
    ) -> UploadResult:
        if not message:
            filename = PurePosixPath(repo_path).name
            message = f"upload {filename}"

        encoded = base64.b64encode(content).decode()

        existing_sha = self._get_file_sha(repo_path, branch)

        payload: dict = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        resp = self._http.put(
            f"{self._repo_prefix}/contents/{repo_path}",
            json=payload,
        )
        if resp.status_code not in (200, 201):
            raise GitHubClientError(
                f"Failed to upload '{repo_path}': "
                f"{resp.status_code} {resp.text}"
            )

        data = resp.json()
        return UploadResult(
            path=repo_path,
            branch=branch,
            sha=data["content"]["sha"],
        )

    def list_directory(self, dir_path: str, branch: str) -> list[str]:
        resp = self._http.get(
            f"{self._repo_prefix}/contents/{dir_path}",
            params={"ref": branch},
        )
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise GitHubClientError(
                f"Failed to list '{dir_path}': {resp.status_code}"
            )
        data = resp.json()
        if not isinstance(data, list):
            return []
        return [item["path"] for item in data if item["type"] == "file"]

    def _get_file_sha(self, repo_path: str, branch: str) -> str | None:
        resp = self._http.get(
            f"{self._repo_prefix}/contents/{repo_path}",
            params={"ref": branch},
        )
        if resp.status_code == 200:
            return resp.json().get("sha")
        return None

    def close(self) -> None:
        self._http.close()
