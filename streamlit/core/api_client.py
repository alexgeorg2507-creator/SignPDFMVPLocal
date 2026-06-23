"""SignFinder HTTP-клиент v1.9 Часть 4.

Заменяет прямые вызовы core/* в Streamlit-страницах.
Все методы синхронные — Streamlit не async.

Известные ограничения схем API (документировано, TODO v1.9 Ч.5):
  - SignerProfileUpdate принимает только {display_name, position}.
    company_aliases / signer_aliases недоступны через GET/PUT /signers.
  - PartyResponse — плоская схема {name, patterns, language},
    без иерархии languages: {ru: {aliases, patterns}}.
  - GET /v1/templates/{id} не возвращает anchors — только метаданные.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import httpx


class SignFinderAPIClient:

    def __init__(self) -> None:
        self.base_url = os.environ.get("SIGNFINDER_API_URL", "http://localhost:8000").rstrip("/")
        self.api_key = os.environ.get("SIGNFINDER_API_KEY", "")
        self.timeout = 120.0  # LLM может идти долго

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}/v1{path}"

    def _raise(self, resp: httpx.Response) -> None:
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            sys.stderr.write(
                f"[api_client] HTTP {resp.status_code} {resp.url}: {resp.text[:500]}\n"
            )
            raise

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def analyze(
        self,
        pdf_bytes: bytes,
        language: Optional[str] = None,
        filename: str = "document.pdf",
        with_review: bool = False,
    ) -> dict:
        """POST /v1/analyze → AnalysisResponse dict.

        Возвращает: {traffic_light, anchors, matches, matched_template,
                     applied_template_id, our_side, error, pipeline_debug, review}
        """
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        data: dict = {}
        if language:
            data["language"] = language
        if with_review:
            data["with_review"] = "true"
        with httpx.Client(timeout=self.timeout) as c:
            resp = c.post(self._url("/analyze"), headers=self._headers, files=files, data=data)
        self._raise(resp)
        return resp.json()

    def analyze_batch(
        self,
        files: list[tuple[str, bytes]],
        language: Optional[str] = None,
    ) -> dict:
        """POST /v1/analyze/batch → BatchAnalysisResponse dict.

        files — list[(filename, pdf_bytes)].
        Возвращает: {total, succeeded, failed, items: [{filename, elapsed_ms, analysis, error}]}
        """
        multipart = [
            ("files", (fname, data, "application/pdf"))
            for fname, data in files
        ]
        form: dict = {}
        if language:
            form["language"] = language
        # батч может идти долго — LLM на каждый файл
        with httpx.Client(timeout=self.timeout * 5) as c:
            resp = c.post(self._url("/analyze/batch"), headers=self._headers,
                          files=multipart, data=form)
        self._raise(resp)
        return resp.json()

    def review(
        self,
        pdf_bytes: bytes,
        language: Optional[str] = None,
        filename: str = "document.pdf",
    ) -> dict:
        """POST /v1/review → ReviewResponse dict.

        Ревью договора БЕЗ поиска подписи.
        Возвращает: {traffic_light, summary, findings: [{axis, severity, note, clause}],
                     error, truncated}
        """
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        data: dict = {}
        if language:
            data["language"] = language
        with httpx.Client(timeout=self.timeout) as c:
            resp = c.post(self._url("/review"), headers=self._headers, files=files, data=data)
        self._raise(resp)
        return resp.json()

    def sign(
        self,
        pdf_bytes: bytes,
        anchors: list,
        signer_id: str = "default",
        filename: str = "document.pdf",
        signature_scale: float = 1.0,
    ) -> bytes:
        """POST /v1/sign → подписанный PDF bytes.

        anchors — list[dict] с полями TextAnchor.
        PNG подписи загружается из storage: signers/{signer_id}/signature.png
        signature_scale — масштаб подписи (1.0 = 15мм высота, 42pt).
        """
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        data = {
            "anchors_json": json.dumps(anchors),
            "signer_id": signer_id,
            "signature_scale": str(signature_scale),
        }
        with httpx.Client(timeout=self.timeout) as c:
            resp = c.post(self._url("/sign"), headers=self._headers, files=files, data=data)
        self._raise(resp)
        return resp.content

    def build_anchor_from_click(
        self,
        pdf_bytes: bytes,
        page: int,
        x: float,
        y: float,
        language: str = "ru",
        filename: str = "document.pdf",
    ) -> Optional[dict]:
        """POST /v1/anchor/from-click → anchor dict or None (422 = не нашёл текст)."""
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        data = {"page": str(page), "x": str(x), "y": str(y), "language": language}
        with httpx.Client(timeout=30.0) as c:
            resp = c.post(
                self._url("/anchor/from-click"), headers=self._headers, files=files, data=data
            )
        if resp.status_code == 422:
            return None
        self._raise(resp)
        return resp.json()

    def preview_page(
        self,
        pdf_bytes: bytes,
        page: int = 0,
        scale: float = 1.5,
        filename: str = "document.pdf",
    ) -> bytes:
        """POST /v1/preview → PNG bytes (без highlights, только рендер)."""
        files = {"file": (filename, pdf_bytes, "application/pdf")}
        data = {"page": str(page), "scale": str(scale)}
        with httpx.Client(timeout=60.0) as c:
            resp = c.post(self._url("/preview"), headers=self._headers, files=files, data=data)
        self._raise(resp)
        return resp.content

    # ── Templates ─────────────────────────────────────────────────────────────

    def list_templates(self, language: Optional[str] = None) -> list:
        """GET /v1/templates → list[dict] — метаданные шаблонов."""
        params: dict = {}
        if language:
            params["language"] = language
        with httpx.Client(timeout=30.0) as c:
            resp = c.get(self._url("/templates"), headers=self._headers, params=params)
        self._raise(resp)
        return resp.json().get("templates", [])

    def get_template(self, template_id: str) -> Optional[dict]:
        """GET /v1/templates/{id} → dict or None."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.get(self._url(f"/templates/{template_id}"), headers=self._headers)
        if resp.status_code == 404:
            return None
        self._raise(resp)
        return resp.json()

    def create_template(self, template: dict) -> str:
        """POST /v1/templates → template_id (str)."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.post(self._url("/templates"), headers=self._headers, json=template)
        self._raise(resp)
        return resp.json().get("id", "")

    def update_template(self, template_id: str, update: dict) -> dict:
        """PATCH /v1/templates/{id} — обновляет только {name, status, language}."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.patch(
                self._url(f"/templates/{template_id}"), headers=self._headers, json=update
            )
        self._raise(resp)
        return resp.json()

    def delete_template(self, template_id: str) -> bool:
        """DELETE /v1/templates/{id}."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.delete(self._url(f"/templates/{template_id}"), headers=self._headers)
        return resp.status_code in (200, 204)

    # ── Signers ───────────────────────────────────────────────────────────────

    def get_signer(self, signer_id: str = "default") -> dict:
        """GET /v1/signers/{id} → {id, display_name, position, has_signature}.

        TODO v1.9 Ч.5: схема не включает company_aliases / signer_aliases.
        Для полных данных расширить SignerProfileResponse в API.
        """
        with httpx.Client(timeout=30.0) as c:
            resp = c.get(self._url(f"/signers/{signer_id}"), headers=self._headers)
        self._raise(resp)
        return resp.json()

    def update_signer(self, signer_id: str, data: dict) -> dict:
        """PUT /v1/signers/{id}.

        TODO v1.9 Ч.5: SignerProfileUpdate принимает только {display_name, position}.
        company_aliases / signer_aliases игнорируются.
        """
        with httpx.Client(timeout=30.0) as c:
            resp = c.put(
                self._url(f"/signers/{signer_id}"), headers=self._headers, json=data
            )
        self._raise(resp)
        return resp.json()

    def get_signature_png(self, signer_id: str = "default") -> Optional[bytes]:
        """GET /v1/signers/{id}/signature → bytes or None (404 = нет подписи)."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.get(self._url(f"/signers/{signer_id}/signature"), headers=self._headers)
        if resp.status_code == 404:
            return None
        self._raise(resp)
        return resp.content

    def upload_signature_png(self, signer_id: str, png_bytes: bytes) -> bool:
        """PUT /v1/signers/{id}/signature → True if 204."""
        files = {"file": ("signature.png", png_bytes, "image/png")}
        with httpx.Client(timeout=30.0) as c:
            resp = c.put(
                self._url(f"/signers/{signer_id}/signature"),
                headers=self._headers,
                files=files,
            )
        return resp.status_code in (200, 204)

    # ── Parties ───────────────────────────────────────────────────────────────

    def list_parties(self) -> list:
        """GET /v1/parties → list[{name, patterns, language}].

        TODO v1.9: плоская схема. Иерархия languages:{ru:{aliases,patterns}} недоступна.
        Данные из старого parties.json (GCS) нужно мигрировать вручную.
        """
        with httpx.Client(timeout=30.0) as c:
            resp = c.get(self._url("/parties"), headers=self._headers)
        self._raise(resp)
        return resp.json()

    def create_party(
        self,
        name: str,
        patterns: Optional[list] = None,
        language: str = "ru",
    ) -> dict:
        """POST /v1/parties → {name, patterns, language}."""
        body = {"name": name, "patterns": patterns or [], "language": language}
        with httpx.Client(timeout=30.0) as c:
            resp = c.post(self._url("/parties"), headers=self._headers, json=body)
        self._raise(resp)
        return resp.json()

    def update_party(self, name: str, data: dict) -> dict:
        """PATCH /v1/parties/{name}."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.patch(self._url(f"/parties/{name}"), headers=self._headers, json=data)
        self._raise(resp)
        return resp.json()

    def delete_party(self, name: str) -> bool:
        """DELETE /v1/parties/{name}."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.delete(self._url(f"/parties/{name}"), headers=self._headers)
        return resp.status_code in (200, 204)

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_traffic_light_config(self) -> dict:
        """GET /v1/settings/traffic-light → {green_threshold, yellow_threshold}."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.get(self._url("/settings/traffic-light"), headers=self._headers)
        self._raise(resp)
        return resp.json()

    def update_traffic_light_config(self, config: dict) -> dict:
        """PUT /v1/settings/traffic-light."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.put(self._url("/settings/traffic-light"), headers=self._headers, json=config)
        self._raise(resp)
        return resp.json()

    def get_sign_mode(self) -> dict:
        """GET /v1/settings/sign-mode → {use_signature, use_marker, sign_above_line, default_page, ...}."""
        with httpx.Client(timeout=10.0) as c:
            resp = c.get(self._url("/settings/sign-mode"), headers=self._headers)
        self._raise(resp)
        return resp.json()

    def get_markers_config(self) -> dict:
        """GET /v1/settings/markers → {ru: [...], en: [...], pl: [...]}."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.get(self._url("/settings/markers"), headers=self._headers)
        self._raise(resp)
        return resp.json()

    def update_markers_config(self, config: dict) -> dict:
        """PUT /v1/settings/markers."""
        with httpx.Client(timeout=30.0) as c:
            resp = c.put(self._url("/settings/markers"), headers=self._headers, json=config)
        self._raise(resp)
        return resp.json()


# ── Синглтон ──────────────────────────────────────────────────────────────────

_client: Optional[SignFinderAPIClient] = None


def get_api_client() -> SignFinderAPIClient:
    """Возвращает синглтон клиента. Читает env при первом вызове."""
    global _client
    if _client is None:
        _client = SignFinderAPIClient()
    return _client
