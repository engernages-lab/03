"""Notation API: grid + jianpu view models, combined sync payload, exporters."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.keyboard import KeyboardLayout
from app.schemas.music_document import MusicDocument
from app.services.keyboard.repository import get_layout as load_layout
from app.services.music_document import repository
from app.services.notation.grid import GridViewModel, compile_grid
from app.services.notation.jianpu import JianpuViewModel, compile_jianpu

router = APIRouter()


class DualNotationResponse(BaseModel):
    document: MusicDocument
    grid: GridViewModel
    jianpu: JianpuViewModel
    findings: List[Dict[str, Any]] = Field(default_factory=list)


def _resolve_layout(document: MusicDocument, layout_id: Optional[str], db: Session) -> KeyboardLayout:
    if not layout_id:
        return document.keyboard_layout
    layout = load_layout(db, layout_id)
    return layout


@router.get("/{document_id}/grid", response_model=GridViewModel)
def get_grid(
    document_id: str,
    divisions: int = Query(default=4, ge=1, le=16),
    layout_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> GridViewModel:
    document = repository.load_document(db, document_id)
    layout = _resolve_layout(document, layout_id, db)
    return compile_grid(document, layout, divisions)


@router.get("/{document_id}/jianpu", response_model=JianpuViewModel)
def get_jianpu(
    document_id: str,
    layout_id: Optional[str] = Query(default=None),
    key_signature: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> JianpuViewModel:
    document = repository.load_document(db, document_id)
    layout = _resolve_layout(document, layout_id, db)
    return compile_jianpu(document, layout, key_signature)


@router.get("/{document_id}/both", response_model=DualNotationResponse)
def get_both(
    document_id: str,
    divisions: int = Query(default=4, ge=1, le=16),
    layout_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> DualNotationResponse:
    """Both view models compiled from the same document (dual-format sync)."""
    from app.services import music_document as core

    document = repository.load_document(db, document_id)
    layout = _resolve_layout(document, layout_id, db)
    return DualNotationResponse(
        document=document,
        grid=compile_grid(document, layout, divisions),
        jianpu=compile_jianpu(document, layout),
        findings=core.validate_document(document),
    )


@router.get("/{document_id}/grid.svg")
def export_grid_svg(
    document_id: str,
    divisions: int = Query(default=4, ge=1, le=16),
    layout_id: Optional[str] = Query(default=None),
    cell: int = Query(default=26, ge=12, le=64),
    db: Session = Depends(get_db),
) -> Response:
    document = repository.load_document(db, document_id)
    layout = _resolve_layout(document, layout_id, db)
    view = compile_grid(document, layout, divisions)
    svg = render_grid_svg(view, cell)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'attachment; filename="grid.svg"'},
    )


@router.get("/{document_id}/jianpu.txt")
def export_jianpu_text(
    document_id: str,
    layout_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> Response:
    document = repository.load_document(db, document_id)
    layout = _resolve_layout(document, layout_id, db)
    view = compile_jianpu(document, layout)
    text = render_jianpu_text(view)
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="jianpu.txt"; '
                f"filename*=UTF-8''{_quote(document.title)}.txt"
            )
        },
    )


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(f"{value or 'jianpu'}")


FONT = "Inter, 'Segoe UI', 'Microsoft YaHei', sans-serif"


def render_grid_svg(view: GridViewModel, cell: int = 26) -> str:
    """Server-side SVG export of the grid score (same view model as the UI)."""
    label_width = 92
    header_height = 64
    row_height = cell
    rows = list(view.rows)
    if view.rest_row is not None:
        rows.append(view.rest_row)
    width = label_width + view.stats.slots * cell + 24
    height = header_height + len(rows) * row_height + 40

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT}">',
        '<rect width="100%" height="100%" fill="#0b0f18"/>',
        f'<text x="16" y="30" fill="#e2e8f2" font-size="16" font-weight="600">{_escape(view.title)}</text>',
        f'<text x="16" y="50" fill="#8b9bb5" font-size="11">'
        f'{_escape(view.artist)} · {view.tempo:g} BPM · {view.time_signature} · '
        f'{view.key_signature} · 键盘：{_escape(view.layout_name)}</text>',
    ]

    for measure in view.measures:
        x = label_width + measure.start_slot * cell
        parts.append(
            f'<line x1="{x}" y1="{header_height - 12}" x2="{x}" '
            f'y2="{height - 20}" stroke="#3a4a67" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x + 4}" y="{header_height - 16}" fill="#5b6d8c" '
            f'font-size="10">{measure.measure}</text>'
        )

    for row_index, row in enumerate(rows):
        y = header_height + row_index * row_height
        parts.append(
            f'<rect x="0" y="{y}" width="{width}" height="{row_height}" '
            f'fill="{"#0f1521" if row_index % 2 == 0 else "#0b0f18"}"/>'
        )
        parts.append(
            f'<text x="12" y="{y + row_height / 2 + 4}" fill="{row.color}" '
            f'font-size="11">{_escape(row.label)}</text>'
        )
        for slot, cell_value in enumerate(row.cells):
            x = label_width + slot * cell
            parts.append(
                f'<rect x="{x + 1}" y="{y + 2}" width="{cell - 2}" height="{row_height - 4}" '
                f'rx="3" fill="none" stroke="#1c2536" stroke-width="0.6"/>'
            )
            if cell_value.state == "empty":
                continue
            fill = row.color if cell_value.state != "rest" else "#27334a"
            opacity = 1.0 if cell_value.state in ("note", "rest") else 0.45
            parts.append(
                f'<rect x="{x + 1}" y="{y + 2}" width="{cell - 2}" height="{row_height - 4}" '
                f'rx="3" fill="{fill}" fill-opacity="{opacity * 0.55}" '
                f'stroke="{fill}" stroke-width="1"/>'
            )
            if cell_value.state in ("note", "rest"):
                mark = "休" if cell_value.state == "rest" else ""
                parts.append(
                    f'<text x="{x + cell / 2}" y="{y + row_height / 2 + 4}" fill="#07090f" '
                    f'font-size="10" text-anchor="middle">{mark}</text>'
                )

    if view.unmapped:
        parts.append(
            f'<text x="16" y="{height - 6}" fill="#fb7185" font-size="10">'
            f'超出键盘范围：{len(view.unmapped)} 个音符</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_jianpu_text(view: JianpuViewModel) -> str:
    """Plain-text jianpu export (monospace friendly)."""
    lines: List[str] = [
        f"{view.title} - {view.artist}",
        f"1={view.tonic} {'小调' if view.mode == 'minor' else '大调'}  "
        f"{view.time_signature}  ♩={view.tempo:g}  键盘：{view.layout_name}",
        "",
    ]
    current_system = -1
    for measure in view.measures:
        if measure.system_index != current_system:
            if current_system >= 0:
                lines.append("")
            current_system = measure.system_index
        tokens = []
        for note in measure.notes:
            prefix = "^" * max(0, note.octave) if note.octave > 0 else ""
            suffix = "." * max(0, -note.octave) if note.octave < 0 else ""
            dots = "." * note.dots
            # Plain text cannot draw underlines, so duration is appended:
            # `/` eighth, `//` sixteenth, `-` half, `- - -` whole.
            tail = {"_": "/", "=": "//", "-": " -", "—": " - - -"}.get(note.duration_label, "")
            tokens.append(f"{prefix}{note.token}{suffix}{dots}{tail}")
        lines.append(f"| {' '.join(tokens) if tokens else '—'} ")
    lines.append("|")
    lines.append("")
    lines.append(
        f"统计：音符 {view.stats.notes} · 休止 {view.stats.rests} · 和弦 {view.stats.chords} "
        f"· 小节 {view.stats.measures} · 变音 {view.stats.accidentals} · 连音 {view.stats.ties}"
    )
    if view.stats.unmapped:
        lines.append(f"注意：{view.stats.unmapped} 个音符超出当前键盘布局范围")
    return "\n".join(lines)


def _escape(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
