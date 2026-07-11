from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def iter_block_items(document: Document):
    body = document.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def main() -> None:
    source = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    document = Document(source)
    records: list[dict[str, object]] = []
    plain_lines: list[str] = []

    for block_index, block in enumerate(iter_block_items(document)):
        if isinstance(block, Paragraph):
            text = block.text
            records.append(
                {
                    "kind": "paragraph",
                    "block": block_index,
                    "style": block.style.name if block.style else None,
                    "text": text,
                    "runs": [run.text for run in block.runs],
                }
            )
            if text:
                plain_lines.append(text)
        else:
            for row_index, row in enumerate(block.rows):
                for cell_index, cell in enumerate(row.cells):
                    for paragraph_index, paragraph in enumerate(cell.paragraphs):
                        text = paragraph.text
                        records.append(
                            {
                                "kind": "table_paragraph",
                                "block": block_index,
                                "row": row_index,
                                "cell": cell_index,
                                "paragraph": paragraph_index,
                                "style": paragraph.style.name if paragraph.style else None,
                                "text": text,
                                "runs": [run.text for run in paragraph.runs],
                            }
                        )
                        if text:
                            plain_lines.append(text)

    (out_dir / "inventory.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "01_input.txt").write_text("\n".join(plain_lines), encoding="utf-8")
    print(f"records={len(records)} nonempty={len(plain_lines)}")
    for index, record in enumerate(records):
        text = str(record["text"])
        if text:
            print(f"[{index:03d}] {record['kind']} | {record.get('style')} | {text}")


if __name__ == "__main__":
    main()
