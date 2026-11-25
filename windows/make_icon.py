"""Gera ``windows/registrale.ico`` e as imagens do assistente do instalador a partir de ``rodou_dashboard/static/icon.svg``.

Tamanhos embutidos no .ico: 16, 24, 32, 48, 64, 128 e 256 px.
Usa ``cairosvg`` ou ``rsvg-convert`` se disponíveis; caso contrário, renderiza o
desenho do ``icon.svg`` via Pillow (funciona offline sem dependências nativas).
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _render_via_cairosvg(svg_path: Path, size: int = 512) -> Image.Image | None:
    try:
        import cairosvg  # type: ignore

        png_bytes = cairosvg.svg2png(url=str(svg_path), output_width=size, output_height=size)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    except Exception:
        return None


def _render_via_rsvg(svg_path: Path, size: int = 512) -> Image.Image | None:
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        return None
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(
            [rsvg, "-w", str(size), "-h", str(size), str(svg_path), "-o", str(tmp_path)],
            check=True,
            capture_output=True,
        )
        return Image.open(tmp_path).convert("RGBA")
    except Exception:
        return None
    finally:
        tmp_path.unlink(missing_ok=True)


def _render_svg_fallback_pillow(svg_path: Path, size: int = 512) -> Image.Image:
    """Renderiza o ícone vetorial do site (``icon.svg``) via Pillow com supersampling 4x."""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    ns = {"svg": "http://www.w3.org/2000/svg"}
    rect = root.find("svg:rect", ns) or root.find("rect")
    bg_hex = (rect.attrib.get("fill") if rect is not None else None) or "#1c1917"
    rx_val = int(float((rect.attrib.get("rx") if rect is not None else None) or 96))

    scale_up = 4
    canvas = size * scale_up
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fundo arredondado (#1c1917, rx=96 em viewBox 512)
    radius = int(rx_val * (canvas / 512))
    draw.rounded_rectangle([0, 0, canvas - 1, canvas - 1], radius=radius, fill=bg_hex)

    # Transform do icon.svg: translate(256,256) scale(12) translate(-12,-12)
    factor = canvas / 512.0

    def tx(x: float) -> float:
        return (256.0 + 12.0 * (x - 12.0)) * factor

    def ty(y: float) -> float:
        return (256.0 + 12.0 * (y - 12.0)) * factor

    stroke = int(round(2.0 * 12.0 * factor))
    fg = "#ffffff"

    def line(pts: list[tuple[float, float]]) -> None:
        mapped = [(tx(x), ty(y)) for x, y in pts]
        draw.line(mapped, fill=fg, width=stroke, joint="curve")
        r = stroke / 2.0
        for px, py in mapped:
            draw.ellipse([px - r, py - r, px + r, py + r], fill=fg)

    # <path d="M12 6V2H8"/>
    line([(12, 6), (12, 2), (8, 2)])
    # <path d="m8 18-4 4V8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2Z"/>
    line([(8, 18), (4, 22), (4, 7.5), (5.5, 6), (18.5, 6), (20, 7.5), (20, 16.5), (18.5, 18), (8, 18)])
    # <path d="M2 12h2"/>, <path d="M9 11v2"/>, <path d="M15 11v2"/>, <path d="M20 12h2"/>
    line([(2, 12), (4, 12)])
    line([(9, 11), (9, 13)])
    line([(15, 11), (15, 13)])
    line([(20, 12), (22, 12)])

    return img.resize((size, size), Image.Resampling.LANCZOS)


def generate_ico(svg_path: Path, ico_path: Path) -> Path:
    """Converte ``svg_path`` para ``ico_path`` com todos os tamanhos de ``ICON_SIZES``."""
    if not svg_path.is_file():
        raise FileNotFoundError(f"SVG de origem não encontrado: {svg_path}")

    base_img = (
        _render_via_cairosvg(svg_path, size=512)
        or _render_via_rsvg(svg_path, size=512)
        or _render_svg_fallback_pillow(svg_path, size=512)
    )
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    base_img.save(ico_path, format="ICO", sizes=ICON_SIZES)
    return ico_path


def generate_wizard_images(svg_path: Path, out_dir: Path) -> list[Path]:
    """Gera ``wizard-small-55.bmp`` e ``wizard-small-110.bmp`` (canto do assistente do Inno Setup)."""
    base_img = (
        _render_via_cairosvg(svg_path, size=512)
        or _render_via_rsvg(svg_path, size=512)
        or _render_svg_fallback_pillow(svg_path, size=512)
    )
    paths = []
    for size in (55, 110):
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        img = base_img.resize((size, size), Image.Resampling.LANCZOS)
        canvas.paste(img, (0, 0), img)
        path = out_dir / f"wizard-small-{size}.bmp"
        canvas.save(path, format="BMP")
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Gera windows/registrale.ico a partir de icon.svg.")
    parser.add_argument(
        "--svg",
        type=Path,
        default=repo_root / "rodou_dashboard" / "static" / "icon.svg",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=repo_root / "windows" / "registrale.ico",
    )
    args = parser.parse_args(argv)
    out = generate_ico(args.svg, args.out)
    print(f"Ícone gerado: {out} ({out.stat().st_size} bytes)")
    for bmp in generate_wizard_images(args.svg, args.out.parent):
        print(f"Imagem do assistente gerada: {bmp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
