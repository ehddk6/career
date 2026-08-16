from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
ITEMS = [
    (ROOT / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610", ROOT / "tmp/rendered_final_20260718/hf/hf.pdf"),
    (ROOT / "career_runs/yongsan-2026-3-office8-official-20260717-20260717-121709-623609", ROOT / "tmp/rendered_final_20260718/yongsan/yongsan.pdf"),
    (ROOT / "career_runs/kinfa-2026-youth-intern-youtube-guidance-20260717-20260717-120439-677326", ROOT / "tmp/rendered_final_20260718/kinfa/kinfa.pdf"),
]

for run, pdf in ITEMS:
    docx = run / "06_자기소개서.docx"
    with zipfile.ZipFile(docx) as archive:
        bad_member = archive.testzip()
        required = {"word/document.xml", "[Content_Types].xml"}
        missing = sorted(required - set(archive.namelist()))
    manifest = json.loads((run / "12_최종산출물.json").read_text(encoding="utf-8"))
    sha = hashlib.sha256(docx.read_bytes()).hexdigest()
    pages = len(PdfReader(str(pdf)).pages)
    result = {
        "docx_zip_test": "PASS" if bad_member is None and not missing else "FAIL",
        "bad_zip_member": bad_member,
        "missing_required_members": missing,
        "manifest_sha256_match": sha == manifest["sha256"]["docx"],
        "pdf_exists": pdf.exists(),
        "pdf_pages": pages,
        "pdf_bytes": pdf.stat().st_size,
    }
    (run / "14_문서무결성검증.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(run.name, json.dumps(result, ensure_ascii=False))
