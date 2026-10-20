"""Page thumbnails for the PDF popup; pure Python (PyMuPDF + Pillow), no GTK."""

import fitz
import pytest

from kumquat.pdf_preview import default_order, load_thumbnails, order_from_text


def _pdf(path, pages=3, encrypt=False):
    doc = fitz.open()
    for number in range(1, pages + 1):
        page = doc.new_page(width=300, height=400)
        page.insert_text((40, 120), str(number), fontsize=150)
    if encrypt:
        doc.save(
            path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner"
        )
    else:
        doc.save(path)
    doc.close()
    return path


def test_thumbnails_one_per_page_within_the_size_limit(tmp_path):
    total, thumbs = load_thumbnails(_pdf(tmp_path / "a.pdf", 3), thumb_px=120)
    assert total == 3 and len(thumbs) == 3
    assert all(max(t.size) <= 120 and t.mode == "RGB" for t in thumbs)
    assert thumbs[0].size == (90, 120)  # keeps the 3:4 page shape


def test_thumbnails_really_show_different_pages(tmp_path):
    _, thumbs = load_thumbnails(_pdf(tmp_path / "a.pdf", 3))
    assert thumbs[0].tobytes() != thumbs[1].tobytes() != thumbs[2].tobytes()


def test_thumbnail_count_is_capped_but_total_is_true(tmp_path):
    total, thumbs = load_thumbnails(_pdf(tmp_path / "big.pdf", 12), limit=5)
    assert total == 12 and len(thumbs) == 5


def test_unreadable_and_locked_pdfs_raise_value_error(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-nonsense")
    with pytest.raises(ValueError):
        load_thumbnails(broken)
    with pytest.raises(ValueError, match="password"):
        load_thumbnails(_pdf(tmp_path / "locked.pdf", 2, encrypt=True))
    with pytest.raises(FileNotFoundError):
        load_thumbnails(tmp_path / "missing.pdf")


def test_default_order_lists_every_page():
    assert default_order(3) == "1, 2, 3"
    assert default_order(1) == "1"


@pytest.mark.parametrize(
    ("text", "pages", "expected"),
    [
        ("3, 1, 2", 3, [3, 1, 2]),
        ("1,2", 2, [1, 2]),
        ("3,1", 3, None),  # missing page 2
        ("1,1,2", 3, None),  # duplicate
        ("1,2,x", 3, None),  # not a number
        ("", 3, None),
        ("1,2,3,4", 3, None),  # page that does not exist
    ],
)
def test_order_from_text_accepts_only_a_full_permutation(text, pages, expected):
    assert order_from_text(text, pages) == expected
