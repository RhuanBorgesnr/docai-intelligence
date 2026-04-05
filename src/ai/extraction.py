"""
PDF text extraction module.
"""
import fitz


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract plain text from a PDF file.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text concatenated from all pages.
    """
    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text("text", sort=True))
    return "\n".join(text_parts).strip()
