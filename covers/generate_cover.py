"""Generate a KDP-ready full-wrap paperback cover (back | spine | front) as
a single PDF sized exactly to the bleed sheet computed by
common/kdp_specs.compute_cover_layout, with Arabic typography.

KDP always expects the flat cover file laid out back-cover-left,
spine-center, front-cover-right — this is a fixed print-production
convention independent of the interior's reading direction, so it applies
the same way to this Arabic (RTL-interior) title as it would to an
LTR book.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import kdp_specs
from lowcontent.common.pdf_render import svg_pages_to_pdf
from lowcontent.common.svg_utils import ARABIC_HEADING_FONT_STACK, SvgPage, PT_PER_IN

STYLE_PALETTES = {
    "classic": {"bg": "#0f2a3d", "accent": "#d9b26a", "text": "#f5efe3"},
    "modern": {"bg": "#f4f1ea", "accent": "#173a5e", "text": "#173a5e"},
    "warm": {"bg": "#6b2b1a", "accent": "#f2c14e", "text": "#fbf3e3"},
}


def _safe_rect(x0_in: float, x1_in: float, layout: kdp_specs.CoverLayout, trim_side: str) -> tuple[float, float, float, float]:
    """Safe (live) area in points for a panel spanning x0_in..x1_in, keeping
    `safety_margin_in` away from the trim edges (not the bleed edges)."""
    margin = layout.safety_margin_in
    top = (layout.bleed_in + margin) * PT_PER_IN
    bottom = (layout.sheet_height_in - layout.bleed_in - margin) * PT_PER_IN
    if trim_side == "back":
        left = (x0_in + layout.bleed_in + margin) * PT_PER_IN
        right = (x1_in - margin) * PT_PER_IN
    else:  # front: outer bleed is on the right
        left = (x0_in + margin) * PT_PER_IN
        right = (x1_in - layout.bleed_in - margin) * PT_PER_IN
    return left, top, right, bottom


def generate_cover_pdf(
    layout: kdp_specs.CoverLayout,
    title_ar: str,
    author_ar: str,
    subtitle_ar: str,
    blurb_ar: str,
    style: str,
    out_path: Path,
) -> Path:
    palette = STYLE_PALETTES.get(style, STYLE_PALETTES["classic"])
    w_pt = layout.sheet_width_in * PT_PER_IN
    h_pt = layout.sheet_height_in * PT_PER_IN
    p = SvgPage(w_pt, h_pt)

    # Full-bleed background.
    p.rect(0, 0, w_pt, h_pt, fill=palette["bg"])

    spine_x0 = layout.spine_x0_in * PT_PER_IN
    spine_x1 = layout.spine_x1_in * PT_PER_IN
    p.rect(spine_x0, 0, spine_x1 - spine_x0, h_pt, fill=palette["accent"], opacity=0.15)
    p.line(spine_x0, 0, spine_x0, h_pt, stroke=palette["accent"], stroke_width=0.75, opacity=0.6)
    p.line(spine_x1, 0, spine_x1, h_pt, stroke=palette["accent"], stroke_width=0.75, opacity=0.6)

    # ---------------- Front cover (right panel) ----------------
    fl, ft, fr, fb = _safe_rect(layout.front_x0_in, layout.front_x1_in, layout, "front")
    front_cx = (fl + fr) / 2
    p.rect(fl, ft, fr - fl, fb - ft, fill="none", stroke=palette["accent"], stroke_width=1.5, opacity=0.5)
    p.text(front_cx, ft + (fb - ft) * 0.38, title_ar, size=34, weight="bold",
           font=ARABIC_HEADING_FONT_STACK, fill=palette["text"])
    if subtitle_ar:
        p.text(front_cx, ft + (fb - ft) * 0.46, subtitle_ar, size=15,
               font=ARABIC_HEADING_FONT_STACK, fill=palette["accent"])
    if author_ar:
        p.text(front_cx, fb - (fb - ft) * 0.08, author_ar, size=17, weight="bold",
               font=ARABIC_HEADING_FONT_STACK, fill=palette["text"])

    # ---------------- Spine (center panel) ----------------
    if kdp_specs.spine_text_allowed(layout.page_count):
        spine_cx = (spine_x0 + spine_x1) / 2
        spine_cy = h_pt / 2
        p.group_start(transform=f"rotate(-90 {spine_cx:.2f} {spine_cy:.2f})")
        p.text(spine_cx, spine_cy - 4, title_ar, size=min(15, (spine_x1 - spine_x0) * 0.55),
               weight="bold", font=ARABIC_HEADING_FONT_STACK, fill=palette["text"])
        if author_ar:
            p.text(spine_cx, spine_cy + 14, author_ar, size=min(10, (spine_x1 - spine_x0) * 0.4),
                   font=ARABIC_HEADING_FONT_STACK, fill=palette["accent"])
        p.group_end()

    # ---------------- Back cover (left panel) ----------------
    bl, bt, br, bb = _safe_rect(layout.back_x0_in, layout.back_x1_in, layout, "back")
    back_cx = (bl + br) / 2
    p.rect(bl, bt, br - bl, bb - bt, fill="none", stroke=palette["accent"], stroke_width=1.5, opacity=0.5)
    if blurb_ar:
        _wrapped_text_block(p, blurb_ar, bl + 14, bt + 30, br - bl - 28, size=11.5,
                             fill=palette["text"], line_height=17)

    # Barcode placeholder — KDP overlays its own ISBN/price barcode here.
    barcode_w = 2.0 * PT_PER_IN
    barcode_h = 1.2 * PT_PER_IN
    bar_x = br - barcode_w
    bar_y = bb - barcode_h
    p.rect(bar_x, bar_y, barcode_w, barcode_h, fill="#ffffff", stroke="#999", stroke_width=0.75)
    p.text(bar_x + barcode_w / 2, bar_y + barcode_h / 2, "منطقة الباركود (تضعه KDP تلقائيًا)",
           size=7, fill="#999")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    return svg_pages_to_pdf([p], out_path)


def _wrapped_text_block(page: SvgPage, text: str, x: float, y: float, max_width_pt: float, size: float, fill: str, line_height: float) -> None:
    """Very simple greedy word-wrap for the back-cover blurb (approximates
    Arabic glyph width; good enough for a cover blurb at fixed font size)."""
    avg_char_w = size * 0.55
    max_chars = max(int(max_width_pt / avg_char_w), 10)
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    for i, line in enumerate(lines):
        page.text(x + max_width_pt, y + i * line_height, line, size=size, anchor="end", fill=fill)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a full-wrap KDP cover PDF")
    parser.add_argument("--trim-size", required=True)
    parser.add_argument("--page-count", type=int, required=True)
    parser.add_argument("--paper-type", default="white")
    parser.add_argument("--title", required=True)
    parser.add_argument("--author", default="")
    parser.add_argument("--subtitle", default="")
    parser.add_argument("--blurb", default="")
    parser.add_argument("--style", default="classic", choices=list(STYLE_PALETTES))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    layout = kdp_specs.compute_cover_layout(args.trim_size, args.page_count, args.paper_type)
    out = generate_cover_pdf(
        layout, args.title, args.author, args.subtitle, args.blurb, args.style, Path(args.out)
    )
    print(f"Wrote {out} (sheet {layout.sheet_width_in}in x {layout.sheet_height_in}in, spine {layout.spine_width_in}in)")


if __name__ == "__main__":
    main()
