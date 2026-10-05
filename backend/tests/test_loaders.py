import io

import pytest

from app.loaders import LoaderError, extract_urls, load_file, split_text, strip_urls


def test_extract_and_strip_urls():
    text = "Read https://example.com/a?b=1, and http://foo.org/x). Thanks"
    assert extract_urls(text) == ["https://example.com/a?b=1", "http://foo.org/x"]
    assert "http" not in strip_urls(text)


def test_load_docx():
    from docx import Document

    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("Hello from docx")
    doc.save(buf)
    assert "Hello from docx" in load_file("a.docx", buf.getvalue()).text


def test_load_csv_and_html():
    assert "a, b" in load_file("t.csv", b"a,b\n1,2").text
    html = b"<html><body><article><p>Main content paragraph here.</p></article></body></html>"
    assert "Main content" in load_file("p.html", html).text


def test_unsupported_and_empty():
    with pytest.raises(LoaderError):
        load_file("a.bin", b"x")
    with pytest.raises(LoaderError):
        load_file("a.txt", b"   ")


def test_split_text():
    chunks = split_text("word " * 1000, 200, 20)
    assert len(chunks) > 5


def test_pdf_filename_ignores_query():
    from app.loaders import _pdf_filename

    assert _pdf_filename("https://x.org/report.pdf?download=1") == "report.pdf"
    assert _pdf_filename("https://x.org/download?id=3") == "document.pdf"
