from pathlib import Path

p = Path(__file__).resolve().parent.parent / "extract" / "search_params.py"
raw = p.read_bytes()
fixed = (
    raw.replace(b"\x97", b"-")
    .replace(b"\x96", b"-")
    .replace(b"\x91", b"'")
    .replace(b"\x92", b"'")
    .replace(b"\x93", b'"')
    .replace(b"\x94", b'"')
    .replace(b"\x85", b"...")
)
text = fixed.decode("utf-8", errors="replace").replace("\ufffd", "-")
p.write_text(text, encoding="utf-8")
print("OK", p)
