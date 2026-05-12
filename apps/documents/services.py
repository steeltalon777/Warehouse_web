"""
Document rendering service for client-side DOCX→PDF pipeline.

This module provides the rendering logic that:
1. Receives a document dict (with payload) from SyncServer.
2. Builds a safe Jinja2 context from document + payload fields.
3. Locates a DOCX template by name (with fallback).
4. Renders the DOCX via docxtpl into a temporary file.
5. Converts the DOCX to PDF via LibreOffice headless.
6. Returns PDF bytes (or optionally debug DOCX bytes).

Template lookup order:
  1. document["template_name"] (if set)
  2. document["document_type"] + "_v1" (fallback)

Expected template path: {DOCUMENT_TEMPLATE_DIR}/{template_name}.docx
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


class DocumentTemplateNotFound(FileNotFoundError):
    """
    Raised when a DOCX template file is not found at the expected path.

    Attributes:
        template_name: The template name that was looked up.
        expected_path: The full filesystem path where the file was expected.
    """

    def __init__(self, template_name: str, expected_path: str) -> None:
        self.template_name = template_name
        self.expected_path = expected_path
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        return (
            f"DOCX-шаблон '{self.template_name}' не найден. "
            f"Ожидаемый путь: {self.expected_path}. "
            f"Поместите файл шаблона в указанную директорию."
        )


def _resolve_template_path(template_name: str) -> Path:
    """
    Resolve the full filesystem path for a given template name.

    Args:
        template_name: Template name without extension (e.g. "waybill_v1").

    Returns:
        Path object pointing to the .docx file.

    Raises:
        DocumentTemplateNotFound: If the file does not exist.
    """
    template_dir = Path(settings.DOCUMENT_TEMPLATE_DIR)
    template_path = template_dir / f"{template_name}.docx"

    if not template_path.exists():
        raise DocumentTemplateNotFound(
            template_name=template_name,
            expected_path=str(template_path),
        )

    return template_path


def _build_render_context(document: dict[str, Any]) -> dict[str, Any]:
    """
    Build a safe Jinja2 render context from a SyncServer document dict.

    The document payload (JSONB) typically contains:
        document, operation, sender, receiver, recipient,
        issued_to, basis, lines, total_lines, signatures

    Args:
        document: Document dict from SyncServer API response.

    Returns:
        dict: Flat context suitable for docxtpl rendering.
    """
    payload = document.get("payload") or {}

    context: dict[str, Any] = {
        # Document-level fields
        "document_id": document.get("id"),
        "document_number": document.get("document_number") or "",
        "document_type": document.get("document_type") or "",
        "document_status": document.get("status") or "",
        "template_name": document.get("template_name") or "",
        "created_at": document.get("created_at") or "",
        "finalized_at": document.get("finalized_at") or "",
        # Nested payload sections (may be empty dicts/lists)
        "document": payload.get("document", {}),
        "operation": payload.get("operation", {}),
        "sender": payload.get("sender", {}),
        "receiver": payload.get("receiver", {}),
        "recipient": payload.get("recipient", {}),
        "issued_to": payload.get("issued_to", {}),
        "basis": payload.get("basis", {}),
        "lines": payload.get("lines", []),
        "total_lines": payload.get("total_lines", {}),
        "signatures": payload.get("signatures", {}),
        # Raw payload for advanced templates
        "payload": payload,
    }

    return context


def render_docx_to_bytes(
    document: dict[str, Any],
    template_name: Optional[str] = None,
) -> bytes:
    """
    Render a DOCX template with document data and return the DOCX as bytes.

    This is useful for debugging or if you need the intermediate DOCX.

    Args:
        document: Document dict from SyncServer API.
        template_name: Optional override for template name.
                      If None, uses document["template_name"] or fallback.

    Returns:
        bytes: Rendered DOCX file content.

    Raises:
        DocumentTemplateNotFound: If no template file is found.
        ImportError: If docxtpl is not installed.
    """
    from docxtpl import DocxTemplate

    resolved_name = _resolve_template_name(document, template_name)
    template_path = _resolve_template_path(resolved_name)
    context = _build_render_context(document)

    logger.debug(
        "Rendering DOCX template",
        extra={
            "template_name": resolved_name,
            "template_path": str(template_path),
            "document_id": document.get("id"),
        },
    )

    doc = DocxTemplate(str(template_path))
    doc.render(context)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = tmp.name
        doc.save(tmp_path)

    try:
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        _safe_cleanup(tmp_path)


def render_document_to_pdf(
    document: dict[str, Any],
    template_name: Optional[str] = None,
) -> bytes:
    """
    Full pipeline: render DOCX from template, convert to PDF via LibreOffice.

    Args:
        document: Document dict from SyncServer API (must include payload).
        template_name: Optional template name override.

    Returns:
        bytes: PDF file content.

    Raises:
        DocumentTemplateNotFound: If no template file is found.
        RuntimeError: If LibreOffice conversion fails.
        ImportError: If docxtpl is not installed.
    """
    from docxtpl import DocxTemplate

    resolved_name = _resolve_template_name(document, template_name)
    template_path = _resolve_template_path(resolved_name)
    context = _build_render_context(document)

    logger.debug(
        "Rendering document to PDF",
        extra={
            "template_name": resolved_name,
            "template_path": str(template_path),
            "document_id": document.get("id"),
        },
    )

    # Step 1: Render DOCX to temp file
    doc = DocxTemplate(str(template_path))
    doc.render(context)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
        docx_path = tmp_docx.name
        doc.save(docx_path)

    try:
        # Step 2: Convert DOCX → PDF via LibreOffice headless
        pdf_path = _convert_docx_to_pdf(docx_path)
    except Exception:
        _safe_cleanup(docx_path)
        raise

    try:
        with open(pdf_path, "rb") as f:
            return f.read()
    finally:
        _safe_cleanup(docx_path)
        _safe_cleanup(pdf_path)


def _resolve_template_name(
    document: dict[str, Any],
    template_name: Optional[str] = None,
) -> str:
    """
    Resolve the effective template name.

    Priority:
      1. Explicit template_name argument.
      2. document["template_name"] from SyncServer.
      3. document["document_type"] + "_v1" (fallback).

    Args:
        document: Document dict from SyncServer.
        template_name: Optional explicit override.

    Returns:
        str: Resolved template name (without .docx extension).
    """
    if template_name:
        return template_name
    if document.get("template_name"):
        return str(document["template_name"])
    doc_type = document.get("document_type", "waybill")
    return f"{doc_type}_v1"


def _convert_docx_to_pdf(docx_path: str) -> str:
    """
    Convert a DOCX file to PDF using LibreOffice headless.

    Args:
        docx_path: Absolute path to the input .docx file.

    Returns:
        str: Absolute path to the generated .pdf file.

    Raises:
        RuntimeError: If LibreOffice is not found or conversion fails.
        subprocess.TimeoutExpired: If conversion exceeds timeout.
    """
    libreoffice_path = settings.LIBREOFFICE_PATH
    timeout = settings.DOCUMENT_RENDER_TIMEOUT

    output_dir = tempfile.mkdtemp()

    try:
        result = subprocess.run(
            [
                libreoffice_path,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                output_dir,
                docx_path,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.error(
                "LibreOffice conversion failed",
                extra={
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                },
            )
            raise RuntimeError(
                f"LibreOffice conversion failed (exit code {result.returncode}): "
                f"{result.stderr or result.stdout or 'unknown error'}"
            )

        # LibreOffice outputs PDF with same basename in output_dir
        docx_stem = Path(docx_path).stem
        pdf_path = os.path.join(output_dir, f"{docx_stem}.pdf")

        if not os.path.exists(pdf_path):
            raise RuntimeError(
                f"LibreOffice did not produce expected PDF at {pdf_path}. "
                f"stdout: {result.stdout}, stderr: {result.stderr}"
            )

        return pdf_path

    except FileNotFoundError as exc:
        raise RuntimeError(
            f"LibreOffice not found at '{libreoffice_path}'. "
            f"Install LibreOffice or set LIBREOFFICE_PATH env var."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"LibreOffice conversion timed out after {timeout}s."
        ) from exc


def _safe_cleanup(path: str) -> None:
    """Safely remove a temporary file, logging any errors."""
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError as exc:
        logger.warning("Failed to clean up temp file %s: %s", path, exc)
