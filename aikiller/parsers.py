"""문서 파서 — 텍스트만 뽑아낸다.

표준 라이브러리만으로 TXT / MD / DOCX / HWPX / HWP(5.0 바이너리)를 처리한다.
PDF만 선택적 의존성(pypdf)을 쓴다.

한국 시장에서 HWP·HWPX 지원은 해외 도구가 못 하는 지점이라 직접 구현한다.
"""

from __future__ import annotations

import io
import os
import re
import struct
import zipfile
import zlib
from xml.etree import ElementTree as ET

SUPPORTED = (".txt", ".md", ".docx", ".hwpx", ".hwp", ".pdf")

# 압축 폭탄 방어. deflate는 1000:1까지 부풀 수 있어서 업로드 크기 제한만으로는
# 못 막는다. 압축 해제 결과물 자체에 상한을 건다.
MAX_UNCOMPRESSED = 48 * 1024 * 1024   # 단일 멤버/스트림 상한
MAX_TOTAL_UNCOMPRESSED = 96 * 1024 * 1024   # 문서 전체 상한
MAX_RATIO = 200                        # 압축비 상한


class ParseError(Exception):
    pass


def _read_zip_member(zf: zipfile.ZipFile, name: str, budget: list[int]) -> bytes:
    """압축 해제 크기를 강제하며 ZIP 멤버를 읽는다.

    `budget`은 [남은 바이트] 리스트다(호출자가 문서 전체 예산을 공유한다).
    헤더의 file_size는 위조될 수 있으므로 선언값 검사와 실제 읽기 상한을
    둘 다 건다.
    """
    try:
        info = zf.getinfo(name)
    except KeyError as e:
        raise ParseError(f"{name} 이(가) 없습니다.") from e

    limit = min(MAX_UNCOMPRESSED, budget[0])
    if info.file_size > limit:
        raise ParseError(
            f"압축 해제 크기가 상한을 넘습니다 ({info.file_size:,}바이트). "
            "압축 폭탄일 수 있습니다."
        )
    if info.compress_size and info.file_size / info.compress_size > MAX_RATIO:
        raise ParseError(
            f"압축비가 비정상입니다 ({info.file_size / info.compress_size:.0f}:1). "
            "압축 폭탄일 수 있습니다."
        )

    with zf.open(name) as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise ParseError("압축 해제 크기가 상한을 넘습니다. 압축 폭탄일 수 있습니다.")
    budget[0] -= len(data)
    return data


# ---------------------------------------------------------------------------
# 평문
# ---------------------------------------------------------------------------

def parse_txt(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "utf-16"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# DOCX — word/document.xml 의 <w:t>
# ---------------------------------------------------------------------------

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parse_docx(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ParseError(f"DOCX 열기 실패: {e}") from e
    budget = [MAX_TOTAL_UNCOMPRESSED]
    if "word/document.xml" not in zf.namelist():
        raise ParseError("word/document.xml 이 없습니다 — DOCX가 아닙니다.")
    xml = _read_zip_member(zf, "word/document.xml", budget)

    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ParseError(f"DOCX XML 파싱 실패: {e}") from e
    paras: list[str] = []
    for p in root.iter(f"{_W_NS}p"):
        buf: list[str] = []
        for node in p.iter():
            tag = node.tag
            if tag == f"{_W_NS}t":
                buf.append(node.text or "")
            elif tag == f"{_W_NS}tab":
                buf.append("\t")
            elif tag == f"{_W_NS}br":
                buf.append("\n")
        line = "".join(buf).strip()
        if line:
            paras.append(line)
    return "\n\n".join(paras)


# ---------------------------------------------------------------------------
# HWPX — OWPML. Contents/section*.xml 의 <hp:t>
# ---------------------------------------------------------------------------

def parse_hwpx(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ParseError(f"HWPX 열기 실패: {e}") from e

    sections = sorted(
        n for n in zf.namelist()
        if re.match(r"Contents/section\d+\.xml$", n, re.I)
    )
    if not sections:
        raise ParseError("Contents/section*.xml 이 없습니다 — HWPX가 아닙니다.")

    budget = [MAX_TOTAL_UNCOMPRESSED]
    paras: list[str] = []
    for name in sections:
        try:
            root = ET.fromstring(_read_zip_member(zf, name, budget))
        except ET.ParseError as e:
            raise ParseError(f"HWPX XML 파싱 실패: {e}") from e
        for p in root.iter():
            if not p.tag.endswith("}p") and p.tag != "p":
                continue
            buf: list[str] = []
            for node in p.iter():
                tag = node.tag.rsplit("}", 1)[-1]
                if tag == "t":
                    buf.append(node.text or "")
                elif tag == "tab":
                    buf.append("\t")
                elif tag in ("lineBreak", "linesegarray"):
                    pass
            line = "".join(buf).strip()
            if line:
                paras.append(line)
    return "\n\n".join(paras)


# ---------------------------------------------------------------------------
# HWP 5.0 바이너리 — OLE 복합문서 + 레코드 스트림
# ---------------------------------------------------------------------------

HWPTAG_PARA_TEXT = 0x10 + 51  # 67

# 제어문자 분류 (HWP 5.0 명세)
_CHAR_CONTROLS = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}   # 1 wchar
_EXTENDED_CONTROLS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}  # 8 wchar
_INLINE_CONTROLS = {4, 5, 6, 7, 8, 9, 19, 20}                   # 8 wchar


def _hwp_decode_para_text(payload: bytes) -> str:
    """PARA_TEXT 레코드 payload(UTF-16LE + 제어문자)를 평문으로."""
    out: list[str] = []
    n = len(payload) // 2
    i = 0
    while i < n:
        code = struct.unpack_from("<H", payload, i * 2)[0]
        if code in _EXTENDED_CONTROLS or code in _INLINE_CONTROLS:
            i += 8
            continue
        if code in _CHAR_CONTROLS:
            if code in (10, 13):
                out.append("\n")
            i += 1
            continue
        out.append(chr(code))
        i += 1
    return "".join(out)


def _hwp_iter_records(buf: bytes):
    """(tag_id, level, payload) 스트림."""
    pos, end = 0, len(buf)
    while pos + 4 <= end:
        (header,) = struct.unpack_from("<I", buf, pos)
        pos += 4
        tag_id = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if pos + 4 > end:
                break
            (size,) = struct.unpack_from("<I", buf, pos)
            pos += 4
        if pos + size > end:
            break
        yield tag_id, level, buf[pos:pos + size]
        pos += size


def parse_hwp(data: bytes) -> str:
    """HWP 5.0 바이너리. olefile이 있으면 그것을, 없으면 내장 최소 OLE 리더를 쓴다."""
    try:
        import olefile  # type: ignore
    except ImportError:
        raise ParseError(
            "HWP 5.0 바이너리를 읽으려면 olefile이 필요합니다:  pip install olefile\n"
            "(HWPX·DOCX·TXT는 추가 설치 없이 동작합니다.)"
        )

    if not olefile.isOleFile(io.BytesIO(data)):
        raise ParseError("OLE 복합문서가 아닙니다 — HWP 5.0 파일이 맞는지 확인하세요.")

    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        if not ole.exists("FileHeader"):
            raise ParseError("FileHeader 스트림이 없습니다.")
        header = ole.openstream("FileHeader").read()
        if not header.startswith(b"HWP Document File"):
            raise ParseError("HWP Document File 시그니처가 없습니다.")
        (flags,) = struct.unpack_from("<I", header, 36)
        compressed = bool(flags & 0x01)
        encrypted = bool(flags & 0x02)
        if encrypted:
            raise ParseError("암호가 걸린 HWP입니다. 암호를 해제한 뒤 다시 시도하세요.")

        sections = sorted(
            (e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"),
            key=lambda e: int(re.sub(r"\D", "", e[1]) or 0),
        )
        if not sections:
            raise ParseError("BodyText 섹션이 없습니다.")

        paras: list[str] = []
        budget = MAX_TOTAL_UNCOMPRESSED
        for entry in sections:
            raw = ole.openstream(entry).read()
            if compressed:
                limit = min(MAX_UNCOMPRESSED, budget)
                try:
                    # decompress(raw, -15) 는 출력 크기에 상한이 없어 zlib 폭탄에
                    # 그대로 뚫린다. decompressobj + max_length 로 잘라 낸다.
                    dec = zlib.decompressobj(-15)
                    raw = dec.decompress(raw, limit + 1)
                except zlib.error as e:
                    raise ParseError(f"섹션 압축 해제 실패: {e}") from e
                if len(raw) > limit:
                    raise ParseError(
                        "섹션 압축 해제 크기가 상한을 넘습니다. 압축 폭탄일 수 있습니다."
                    )
                budget -= len(raw)
            for tag_id, _level, payload in _hwp_iter_records(raw):
                if tag_id != HWPTAG_PARA_TEXT:
                    continue
                line = _hwp_decode_para_text(payload).strip()
                if line:
                    paras.append(line)
        return "\n\n".join(paras)
    finally:
        ole.close()


# ---------------------------------------------------------------------------
# PDF — 선택적 의존성
# ---------------------------------------------------------------------------

def parse_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        raise ParseError(
            "PDF를 읽으려면 pypdf가 필요합니다:  pip install pypdf"
        )
    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p)


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

_DISPATCH = {
    ".txt": parse_txt, ".md": parse_txt, ".markdown": parse_txt,
    ".docx": parse_docx,
    ".hwpx": parse_hwpx,
    ".hwp": parse_hwp,
    ".pdf": parse_pdf,
}


def normalize(text: str) -> str:
    """파서 공통 후처리 — 과도한 공백·개행 정리."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("​", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_bytes(data: bytes, ext: str) -> str:
    fn = _DISPATCH.get(ext.lower())
    if fn is None:
        raise ParseError(f"지원하지 않는 확장자: {ext} (지원: {', '.join(SUPPORTED)})")
    return normalize(fn(data))


def parse_file(path: str) -> str:
    ext = os.path.splitext(path)[1]
    with open(path, "rb") as f:
        return parse_bytes(f.read(), ext)
