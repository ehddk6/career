from __future__ import annotations

import sys
from pathlib import Path

import fitz


def main() -> None:
    pdf_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    output_dir.mkdir(parents=True, exist_ok=True)
    document = fitz.open(pdf_path)
    zoom = 150 / 72
    matrix = fitz.Matrix(zoom, zoom)
    for index, page in enumerate(document):
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        output = output_dir / f"page-{index + 1}.png"
        pixmap.save(output)
        print(output)
    print(f"pages={len(document)}")


if __name__ == "__main__":
    main()
