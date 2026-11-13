"""Document IO, atomic autosave, session resume, and zero-dependency .docx exporter for Volmini."""

import json
import os
import struct
from volmini.compat import path_exists, makedirs_safe
from volmini.core.document_model import PageLayoutModel, DocumentMode
from volmini.core.header_footer import HeaderFooterModel
from volmini.core.rich_doc import RichDocument


def _crc32(data: bytes) -> int:
    """Pure-Python CRC32 computation for zero-dependency .docx ZIP generation on MicroPython."""
    try:
        import binascii
        if hasattr(binascii, "crc32"):
            return binascii.crc32(data) & 0xFFFFFFFF
    except Exception:
        pass
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
    return (~crc) & 0xFFFFFFFF


def _xml_escape(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _write_stored_zip(file_path: str, entries: list) -> None:
    """Writes a standard PKZIP archive (STORED method) without needing the `zipfile` module."""
    central_dir = []
    offset = 0
    with open(file_path, "wb") as f:
        for arcname, raw_bytes in entries:
            name_bytes = arcname.encode("utf-8")
            crc = _crc32(raw_bytes)
            size = len(raw_bytes)
            # Local file header (PK\x03\x04)
            lfh = struct.pack(
                "<4sHHHHHIIIHH",
                b"PK\x03\x04",
                20,         # version needed
                0,          # flags
                0,          # compression = 0 (STORED)
                0,          # mod time
                0,          # mod date
                crc,
                size,
                size,
                len(name_bytes),
                0,          # extra len
            )
            f.write(lfh)
            f.write(name_bytes)
            f.write(raw_bytes)

            # Central directory header (PK\x01\x02)
            cdh = struct.pack(
                "<4sHHHHHHIIIHHHHHII",
                b"PK\x01\x02",
                20,         # version made by
                20,         # version needed
                0,          # flags
                0,          # compression = STORED
                0,          # mod time
                0,          # mod date
                crc,
                size,
                size,
                len(name_bytes),
                0,          # extra len
                0,          # comment len
                0,          # disk start
                0,          # internal attr
                0,          # external attr
                offset,
            )
            central_dir.append(cdh + name_bytes)
            offset += len(lfh) + len(name_bytes) + size

        cd_offset = offset
        cd_data = b"".join(central_dir)
        f.write(cd_data)
        # End of central directory record (PK\x05\x06)
        eocd = struct.pack(
            "<4sHHHHIIH",
            b"PK\x05\x06",
            0,
            0,
            len(entries),
            len(entries),
            len(cd_data),
            cd_offset,
            0,
        )
        f.write(eocd)


class IOManager:
    """Handles .md, .txt, .story.json companion files, atomic autosave, and .docx export."""

    @staticmethod
    def get_companion_path(doc_path: str) -> str:
        if "." in doc_path:
            base = doc_path.rsplit(".", 1)[0]
        else:
            base = doc_path
        return f"{base}.story.json"

    @staticmethod
    def atomic_write_text(file_path: str, content: str) -> bool:
        """Writes to a temporary file first and renames atomically for power-loss safety."""
        tmp_path = file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            if path_exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            os.rename(tmp_path, file_path)
            return True
        except Exception as e:
            print(f"Atomic write error ({file_path}): {e}")
            return False

    @classmethod
    def save_document(
        cls,
        file_path: str,
        doc: RichDocument,
        layout: PageLayoutModel = None,
        hf_model: HeaderFooterModel = None,
        document_mode: str = DocumentMode.CREATIVE_FICTION,
        chapter_statuses: dict = None,
        story_title: str = "",
        story_author: str = "",
    ) -> bool:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "md"
        if ext == "txt":
            body = doc.to_plain_text()
        elif ext == "docx":
            ok = cls.export_docx(file_path, doc, layout)
            if not ok:
                return False
            body = None
        else:
            body = doc.to_markdown()

        if body is not None:
            if not cls.atomic_write_text(file_path, body):
                return False

        # Save companion .story.json metadata
        metadata = {
            "document_mode": document_mode,
            "story_title": story_title,
            "story_author": story_author,
            "cursor_para": doc.cursor_para,
            "cursor_offset": doc.cursor_offset,
            "layout": layout.to_dict() if layout else PageLayoutModel().to_dict(),
            "header_footer": hf_model.to_dict() if hf_model else HeaderFooterModel().to_dict(),
            "chapter_statuses": chapter_statuses or {},
        }
        comp_path = cls.get_companion_path(file_path)
        cls.atomic_write_text(comp_path, json.dumps(metadata))
        doc.dirty = False
        return True

    @classmethod
    def load_document(cls, file_path: str, doc: RichDocument) -> dict:
        """Loads a .md or .txt manuscript and returns its companion .story.json dict if present."""
        if not path_exists(file_path):
            return {}
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "md"
        with open(file_path, "r", encoding="utf-8") as f:
            raw = f.read()

        if ext == "txt":
            doc.from_plain_text(raw)
        else:
            doc.from_markdown(raw)

        comp_path = cls.get_companion_path(file_path)
        meta = {}
        if path_exists(comp_path):
            try:
                with open(comp_path, "r", encoding="utf-8") as mf:
                    meta = json.load(mf)
            except Exception:
                meta = {}

        if "cursor_para" in meta and "cursor_offset" in meta:
            doc.cursor_para = int(meta.get("cursor_para", 0))
            doc.cursor_offset = int(meta.get("cursor_offset", 0))
            doc._clamp_cursor()
            doc._sync_active_format()
        doc.dirty = False
        return meta

    @classmethod
    def save_session_state(cls, storage_root: str, active_file: str, cursor_para: int, cursor_offset: int) -> None:
        makedirs_safe(storage_root)
        session_file = f"{storage_root.rstrip('/')}/.volmini_session.json"
        payload = {
            "active_file": active_file,
            "cursor_para": cursor_para,
            "cursor_offset": cursor_offset,
        }
        cls.atomic_write_text(session_file, json.dumps(payload))

    @classmethod
    def load_session_state(cls, storage_root: str) -> dict:
        session_file = f"{storage_root.rstrip('/')}/.volmini_session.json"
        if not path_exists(session_file):
            return {}
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def export_docx(file_path: str, doc: RichDocument, layout: PageLayoutModel = None) -> bool:
        """Exports a compliant Word .docx file using zero external libraries."""
        if layout is None:
            layout = PageLayoutModel()
        try:
            w_in, h_in = layout.raw_dimensions_inches
            # Twips (1/1440 inch)
            pg_w = int(round(w_in * 1440))
            pg_h = int(round(h_in * 1440))
            m_top = int(round(layout.margins.top * 1440))
            m_bot = int(round(layout.margins.bottom * 1440))
            m_left = int(round(layout.margins.left * 1440))
            m_right = int(round(layout.margins.right * 1440))

            p_xml_list = []
            for idx, para in enumerate(doc.paragraphs):
                p_pr = []
                style_map = {
                    "title": "Title",
                    "h1": "Heading1",
                    "h2": "Heading2",
                    "h3": "Heading3",
                    "quote": "Quote",
                }
                if para.style in style_map:
                    p_pr.append(f'<w:pStyle w:val="{style_map[para.style]}"/>')
                if para.align in ("center", "right"):
                    p_pr.append(f'<w:jc w:val="{para.align}"/>')
                if para.page_break_before and idx > 0:
                    p_pr.append("<w:pageBreakBefore/>")

                p_pr_xml = f"<w:pPr>{''.join(p_pr)}</w:pPr>" if p_pr else ""

                r_xml_list = []
                for span in para.spans:
                    if not span.text:
                        continue
                    r_pr = []
                    if span.bold or para.style in ("title", "h1", "h2", "h3"):
                        r_pr.append("<w:b/>")
                    if span.italic or para.style == "quote":
                        r_pr.append("<w:i/>")
                    if span.underline:
                        r_pr.append('<w:u w:val="single"/>')
                    r_pr_xml = f"<w:rPr>{''.join(r_pr)}</w:rPr>" if r_pr else ""
                    escaped = _xml_escape(span.text)
                    r_xml_list.append(
                        f'<w:r>{r_pr_xml}<w:t xml:space="preserve">{escaped}</w:t></w:r>'
                    )

                p_xml_list.append(f"<w:p>{p_pr_xml}{''.join(r_xml_list)}</w:p>")

            document_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body>"
                + "".join(p_xml_list)
                + f'<w:sectPr><w:pgSz w:w="{pg_w}" w:h="{pg_h}"/>'
                + f'<w:pgMar w:top="{m_top}" w:right="{m_right}" w:bottom="{m_bot}" w:left="{m_left}"/>'
                + "</w:sectPr></w:body></w:document>"
            )

            content_types_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            )

            rels_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/>'
                "</Relationships>"
            )

            entries = [
                ("[Content_Types].xml", content_types_xml.encode("utf-8")),
                ("_rels/.rels", rels_xml.encode("utf-8")),
                ("word/document.xml", document_xml.encode("utf-8")),
            ]
            _write_stored_zip(file_path, entries)
            return True
        except Exception as e:
            print(f"Error exporting .docx: {e}")
            return False
