# parser.py
# CV/JD Parser tool: converts PDF and Word files into plain text
#
# Created by: Maksym Sharai
# Date: 03/11/2026

from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Union

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


FileSource = Union[str, Path, BinaryIO, BytesIO]


def pdf_to_text(file_path: FileSource) -> str:
    """
    Extracts plain text content from a PDF file path or file-like stream.

    Args:
        file_path: Path string, Path object, or open binary stream (e.g.
          BytesIO).

    Returns:
        Extracted plain text across all pages. Returns an empty string if no
        extractable text is found.
    """

    # PdfReader accepts either a filesystem path or an already-open binary
    # stream, so callers can use the same function for both input types.
    reader = PdfReader(file_path)
    pages_text: list[str] = []

    for page in reader.pages:
        # Some PDF pages contain no extractable text. Ignore those pages
        # instead of adding empty lines to the final result.
        text = page.extract_text()
        if text:
            cleaned = text.strip()
            if cleaned:
                pages_text.append(cleaned)

    # Join pages cleanly with double newlines
    return "\n\n".join(pages_text)


def docx_to_text(file_path: FileSource) -> str:
    """
    Extracts text from paragraphs and tables in a DOCX file.

    Args:
        file_path: Path to a DOCX file or an open binary stream.

    Returns:
        Paragraph and table text joined by blank lines. Cells in each table
        row are separated by tabs, and empty paragraphs or rows are omitted.
    """

    # python-docx loads a DOCX from either a path or a binary stream.
    document = Document(file_path)  # type: ignore
    blocks: list[str] = []

    # Iterate over the document XML directly so paragraphs and tables remain
    # in the same order as they appear in the original document.
    for element in document.element.body.iterchildren():
        if element.tag.endswith("}p"):
            text = Paragraph(element, document).text.strip()
        elif element.tag.endswith("}tbl"):
            table = Table(element, document)
            rows = []
            for row in table.rows:
                seen_cells: set[int] = set()
                cells = []
                for cell in row.cells:
                    # A horizontally merged cell can appear more than once
                    # in row.cells, even though it has one XML element.
                    cell_id = id(cell._tc)
                    if cell_id in seen_cells:
                        continue
                    seen_cells.add(cell_id)

                    # Keep every table row on one physical line. split()
                    # also collapses repeated spaces and internal newlines.
                    cells.append(" ".join(cell.text.split()))
                if any(cells):
                    rows.append("\t".join(cells))
            text = "\n".join(row for row in rows if row)
        else:
            # Ignore document-body elements that are not paragraphs or tables.
            continue

        if text:
            blocks.append(text)

    # Blank lines separate document blocks while table rows stay line-based.
    return "\n\n".join(blocks)


def file_to_text(file_path: FileSource) -> str:
    """
    Extracts text from a supported PDF or DOCX file.

    Paths are validated before parsing. For file-like streams, the format is
    identified from the file signature without changing the stream position.

    Raises:
        FileNotFoundError: If a path does not exist.
        ValueError: If the input is not a file, or has an unsupported format.
    """

    if isinstance(file_path, (str, Path)):
        path = Path(file_path)
        # Validate paths before trying to infer their file format.
        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {path}")
        if not path.is_file():
            raise ValueError(f"Expected a file, got: {path}")

        # Extensions are case-insensitive, so both ".pdf" and ".PDF" work.
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            result = pdf_to_text(path)
        elif suffix == ".docx":
            result = docx_to_text(path)
        else:
            raise ValueError(
                f"Unsupported file type '{path.suffix}'. Expected a .pdf or .docx file."
            )

        if not result.strip():
            raise ValueError(
                "The file was parsed successfully, but contains no extractable text."
            )
        return result

    if not hasattr(file_path, "read"):
        raise TypeError("file_path must be a path or an open binary stream")

    try:
        # Read only the signature and restore the original position so the
        # parser receives the stream from the same position as the caller.
        position = file_path.tell()
        signature = file_path.read(4)
        file_path.seek(position)
    except (AttributeError, OSError) as error:
        raise ValueError("The binary stream must support tell(), read(), and seek()") from error

    # PDF files begin with "%PDF"; DOCX files are ZIP containers beginning
    # with "PK", which is the ZIP file signature.
    if signature.startswith(b"%PDF"):
        result = pdf_to_text(file_path)
    elif signature.startswith(b"PK"):
        result = docx_to_text(file_path)
    else:
        raise ValueError("Unsupported stream format. Expected a PDF or DOCX stream.")

    if not result.strip():
        raise ValueError(
            "The file was parsed successfully, but contains no extractable text."
        )
    return result


if __name__ == "__main__":
    """Run this module directly to manually test a parser function."""