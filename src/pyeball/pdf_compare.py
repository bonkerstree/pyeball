"""
PDF comparison tool.

Accepts two PDF file paths, aligns their content at the line level,
computes word-level diffs, and produces:
  - A side-by-side output PDF with highlights (output.pdf)
  - One PNG image per page showing shifted content (output_page_N.png)

All outputs are saved to an "Output" folder in the current directory.
"""
import pymupdf
import difflib
import os
import sys
import shutil
from dataclasses import dataclass
from PIL import Image, ImageDraw


# ── Custom Exceptions ────────────────────────────────────────────────────────

class PDFDoesNotExistException(Exception):
    """Raised when a given PDF path does not exist on the filesystem."""
    def __init__(self, path: str):
        super().__init__(f"PDF file does not exist: '{path}'")
        self.path = path


class SamePDFBeingCompared(Exception):
    """Raised when both input paths point to the same PDF file."""
    def __init__(self, path: str):
        super().__init__(f"Both input paths point to the same PDF file: '{path}'")
        self.path = path


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class Word:
    """A single word extracted from a PDF page with its bounding box and origin."""
    x0:       float
    y0:       float
    x1:       float
    y1:       float
    text:     str
    block_no: int
    line_no:  int
    word_no:  int
    page_idx: int


# ── Validation ───────────────────────────────────────────────────────────────

def validate_pdf_paths(path_1: str, path_2: str) -> None:
    """
    Verify that both PDF paths exist and are not the same file.

    Raises PDFDoesNotExistException if either path does not exist.
    Raises SamePDFBeingCompared if both paths point to the same file.
    """
    for path in (path_1, path_2):
        if not os.path.exists(path):
            raise PDFDoesNotExistException(path)

    if os.path.abspath(path_1) == os.path.abspath(path_2):
        raise SamePDFBeingCompared(os.path.abspath(path_1))


# ── Output Folder ─────────────────────────────────────────────────────────────

def prepare_output_folder(output_dir: str) -> None:
    """
    Prepare the output folder by clearing it if it exists, then creating it.
    """
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)


# ── Text Extraction ───────────────────────────────────────────────────────────

def extract_all_words(doc: pymupdf.Document) -> list[Word]:
    """
    Extract all words from every page of a document into one flat list.

    PyMuPDF returns each word as a raw 8-tuple; this function converts
    each tuple into a Word dataclass and appends the page_idx so every
    word retains its original page origin for highlight placement.
    """
    all_words = []
    for page_idx, page in enumerate(doc):
        for raw in page.get_text("words"):   # each raw word is an 8-tuple
            all_words.append(Word(
                x0=raw[0], y0=raw[1], x1=raw[2], y1=raw[3],
                text=raw[4],
                block_no=raw[5], line_no=raw[6], word_no=raw[7],
                page_idx=page_idx,
            ))
    return all_words


def group_words_into_lines(all_words: list[Word]) -> list[list[Word]]:
    """
    Group a flat word list into lines using each Word's page_idx,
    block_no, and line_no fields.

    Words sharing the same (page_idx, block_no, line_no) are on the
    same line. Returns a list of lines in reading order.
    """
    lines_dict: dict[tuple, list[Word]] = {}
    for word in all_words:
        line_key = (word.page_idx, word.block_no, word.line_no)
        if line_key not in lines_dict:
            lines_dict[line_key] = []
        lines_dict[line_key].append(word)

    return [lines_dict[key] for key in sorted(lines_dict)]


def line_as_string(line: list[Word]) -> str:
    """Join all words in a line into a single string for alignment comparison."""
    return " ".join(word.text for word in line)


def is_bullet_line(line: list[Word]) -> bool:
    """
    Return True if the line consists of only a single bullet character.

    A bullet line is defined as a line with exactly one word that matches
    a known set of bullet characters, including:
      - Common Unicode bullets : •  ·  ‣  ▸  ▪  ▫  ◦
      - ASCII approximations   : -  *  –  —
      - Numbered bullets       : 1.  2.  a.  b.  etc.

    # TODO: Improve bullet handling — currently bullet lines are ignored
    #       during alignment. Future improvement should align bullet lines
    #       properly with their counterparts in the other document.
    """
    import re

    bullet_chars = {"•", "·", "‣", "▸", "▪", "▫", "◦", "-", "*", "–", "—"}
    numbered_bullet_pattern = re.compile(r"^(\d+|[a-zA-Z])\.$")

    if len(line) != 1:
        return False

    text = line[0].text
    return text in bullet_chars or bool(numbered_bullet_pattern.match(text))


def fuzzy_match(line_1: list[Word], line_2: list[Word], threshold: float = 0.8) -> bool:
    """
    Return True if the two lines are sufficiently similar.

    Uses difflib.SequenceMatcher.ratio() which returns a score between
    0 (completely different) and 1 (identical). Lines are considered a
    match if their ratio meets or exceeds the threshold.
    """
    ratio = difflib.SequenceMatcher(
        None, line_as_string(line_1), line_as_string(line_2)
    ).ratio()
    return ratio >= threshold


def line_height(line: list[Word]) -> float:
    """Return the height of a line derived from its word bounding boxes."""
    return max(w.y1 for w in line) - min(w.y0 for w in line)


def line_width(line: list[Word]) -> float:
    """Return the width of a line derived from its word bounding boxes."""
    return max(w.x1 for w in line) - min(w.x0 for w in line)


# ── Alignment ─────────────────────────────────────────────────────────────────

def find_insertion_point(
    unmatched_pdf1_idx: int,
    lines_1:            list[list[Word]],
    aligned:            list[tuple[list[Word] | None, list[Word] | None]],
) -> int:
    """
    Find the correct insertion index in the aligned list for an unmatched
    PDF 1 line, using up to three predecessors then up to three successors
    to narrow down the position.

    Strategy:
      1. Start with 1 predecessor line from PDF 1 (the line just before
         the unmatched line). Find all positions in aligned where that
         predecessor appears on the left side.
      2. If exactly one match → insert right after it.
      3. If multiple matches → add another predecessor (up to 3 total)
         and narrow down by requiring all predecessors to appear
         consecutively in aligned.
      4. If still multiple matches after 3 predecessors → start adding
         successors (up to 3) and narrow down by requiring the successors
         to appear consecutively after the candidate position.
      5. If still multiple matches → insert at the first occurrence.
      6. If no predecessors exist → insert at position 0.
    """
    max_context   = 3
    aligned_lines = [pair[0] for pair in aligned]   # left side of each aligned pair

    # Gather available predecessors and successors from PDF 1
    predecessors = []
    for offset in range(1, max_context + 1):
        idx = unmatched_pdf1_idx - offset
        if idx >= 0:
            predecessors.append(lines_1[idx])
        else:
            break

    successors = []
    for offset in range(1, max_context + 1):
        idx = unmatched_pdf1_idx + offset
        if idx < len(lines_1):
            successors.append(lines_1[idx])
        else:
            break

    if not predecessors:
        # No predecessors available — insert at the very beginning
        return 0

    # Phase 1 — narrow down using predecessors
    candidate_positions = None

    for num_preds in range(1, len(predecessors) + 1):
        context = predecessors[:num_preds]   # oldest → most recent predecessor

        # Find all positions in aligned where this predecessor sequence ends
        positions = []
        for i in range(len(aligned_lines) - num_preds + 1):
            window = aligned_lines[i:i + num_preds]
            if window == list(reversed(context)):
                positions.append(i + num_preds)   # insert after this window

        if not positions:
            # Predecessors not found in aligned — fall back to end of list
            return len(aligned)

        candidate_positions = positions

        if len(candidate_positions) == 1:
            return candidate_positions[0]

    # Phase 2 — still multiple matches, narrow down using successors
    for num_succs in range(1, len(successors) + 1):
        context = successors[:num_succs]

        narrowed = []
        for pos in candidate_positions:
            # Check that successors appear consecutively starting at pos
            window = aligned_lines[pos:pos + num_succs]
            if window == context:
                narrowed.append(pos)

        if len(narrowed) == 1:
            return narrowed[0]

        if narrowed:
            candidate_positions = narrowed

    # Fall back to first occurrence among remaining candidates
    return candidate_positions[0]


def align_lines(
    lines_1: list[list[Word]],
    lines_2: list[list[Word]],
) -> list[tuple[list[Word] | None, list[Word] | None]]:
    """
    Align lines from two documents using a forward pass followed by a
    backward pass to handle unmatched PDF 1 lines.

    Forward pass (PDF 2 → PDF 1):
      For each PDF 2 line, compare it to the current PDF 1 line using
      fuzzy matching (threshold 0.8). If no match, scan ahead in PDF 1
      until a match is found or PDF 1 is exhausted.
        - Match found    → emit (matched_pdf1_line, pdf2_line); skipped
                           PDF 1 lines are handled by the backward pass
        - No match found → emit (None, pdf2_line), keep PDF 1 pointer

    Backward pass (PDF 1 → PDF 2):
      Find all PDF 1 lines never matched during the forward pass and
      insert them as (pdf1_line, None) at the correct position using
      find_insertion_point().

    Returns a list of pairs (line_1, line_2) where either side can be None:
        - (line, None) : line exists only in PDF 1 (deleted)
        - (None, line) : line exists only in PDF 2 (inserted)
        - (line, line) : line exists in both (may or may not differ)
    """
    aligned:      list[tuple[list[Word] | None, list[Word] | None]] = []
    matched_pdf1: set[int] = set()
    pdf1_pointer: int      = 0

    # ── Forward pass ──────────────────────────────────────────────────────────
    for pdf2_line in lines_2:

        if is_bullet_line(pdf2_line):
            # Skip bullet lines entirely
            continue

        if pdf1_pointer >= len(lines_1):
            # PDF 1 exhausted — remaining PDF 2 lines are all insertions
            aligned.append((None, pdf2_line))
            continue

        if fuzzy_match(lines_1[pdf1_pointer], pdf2_line):
            # Direct match at current pointer
            aligned.append((lines_1[pdf1_pointer], pdf2_line))
            matched_pdf1.add(pdf1_pointer)
            pdf1_pointer += 1
        else:
            # No direct match — scan ahead in PDF 1
            stored_pointer = pdf1_pointer
            match_found    = False

            for look_ahead in range(pdf1_pointer + 1, len(lines_1)):
                if fuzzy_match(lines_1[look_ahead], pdf2_line):
                    aligned.append((lines_1[look_ahead], pdf2_line))
                    matched_pdf1.add(look_ahead)
                    pdf1_pointer = look_ahead + 1
                    match_found  = True
                    break

            if not match_found:
                # No match found anywhere in PDF 1 — pure insertion
                aligned.append((None, pdf2_line))
                pdf1_pointer = stored_pointer

    # ── Backward pass ─────────────────────────────────────────────────────────
    for pdf1_idx, pdf1_line in enumerate(lines_1):
        if pdf1_idx in matched_pdf1:
            continue

        if is_bullet_line(pdf1_line):
            # Skip bullet lines entirely
            continue

        # Find where this unmatched PDF 1 line should be inserted
        insert_at = find_insertion_point(pdf1_idx, lines_1, aligned)
        aligned.insert(insert_at, (pdf1_line, None))

    return aligned


# ── Diffing ───────────────────────────────────────────────────────────────────

def compute_all_diffs(
    aligned: list[tuple[list[Word] | None, list[Word] | None]],
) -> list[dict]:
    """
    Derive diffs from the aligned line pairs.

    For each aligned pair:
      - If one side is None: all words on the non-None side are differences.
      - If both sides are present and identical: no differences.
      - If both sides are present but differ: use SequenceMatcher at word
        level to find exactly which words differ.

    Returns pdf_diffs: a list of dicts (one per aligned line pair) with keys:
        'words_1'       : list of Words for PDF 1's line, or None
        'words_2'       : list of Words for PDF 2's line, or None
        'diff_indices_1': set of differing word indices within words_1
        'diff_indices_2': set of differing word indices within words_2
    """
    pdf_diffs = []

    for line_1, line_2 in aligned:
        diff_indices_1: set[int] = set()
        diff_indices_2: set[int] = set()

        if line_1 is None:
            # All words in line_2 are insertions
            diff_indices_2 = set(range(len(line_2)))

        elif line_2 is None:
            # All words in line_1 are deletions
            diff_indices_1 = set(range(len(line_1)))

        else:
            plain_1 = [w.text for w in line_1]
            plain_2 = [w.text for w in line_2]

            if plain_1 != plain_2:
                # Use SequenceMatcher at word level to find exact differences
                matcher = difflib.SequenceMatcher(
                    None, plain_1, plain_2, autojunk=False
                )
                for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                    if tag == "equal":
                        continue
                    if tag in ("replace", "delete"):
                        diff_indices_1.update(range(i1, i2))
                    if tag in ("replace", "insert"):
                        diff_indices_2.update(range(j1, j2))

        pdf_diffs.append({
            "words_1":        line_1,
            "words_2":        line_2,
            "diff_indices_1": diff_indices_1,
            "diff_indices_2": diff_indices_2,
        })

    return pdf_diffs


# ── Output PDF Construction ───────────────────────────────────────────────────

def get_page_rect(
    doc: pymupdf.Document,
    page_idx: int,
    fallback_doc: pymupdf.Document,
) -> pymupdf.Rect:
    """
    Return the rect for page_idx in doc.
    If doc does not have that page, return the rect from fallback_doc instead.
    """
    if page_idx < len(doc):
        return doc[page_idx].rect
    return fallback_doc[page_idx].rect


def draw_highlight(
    out_page:  pymupdf.Page,
    words:     list[Word],
    indices:   set[int] | None,
    color:     tuple[float, float, float],
    opacity:   float,
    x_offset:  float = 0,
) -> None:
    """
    Draw highlights on out_page for the given words.

    If indices is None, a single highlight rect spanning all words in the
    line is drawn (used for fully inserted/deleted lines).
    If indices is a set, individual highlights are drawn for each word
    at the given indices (used for word-level diffs).

    x_offset is applied to all x coordinates to shift highlights to the
    correct side of the output page (0 for left side, rect_1.width for right).
    """
    if indices is None:
        # Single rect spanning the entire line
        x0 = min(w.x0 for w in words) + x_offset
        y0 = min(w.y0 for w in words)
        x1 = max(w.x1 for w in words) + x_offset
        y1 = max(w.y1 for w in words)
        annot = out_page.add_highlight_annot(pymupdf.Rect(x0, y0, x1, y1))
        annot.set_colors(stroke=color)
        annot.set_opacity(opacity)
        annot.update()
    else:
        # Individual rects per differing word
        for idx in indices:
            if idx < len(words):
                word = words[idx]
                annot = out_page.add_highlight_annot(
                    pymupdf.Rect(
                        word.x0 + x_offset, word.y0,
                        word.x1 + x_offset, word.y1,
                    )
                )
                annot.set_colors(stroke=color)
                annot.set_opacity(opacity)
                annot.update()


def build_output_pdf(
    doc_1:       pymupdf.Document,
    doc_2:       pymupdf.Document,
    pdf_diffs:   list[dict],
    output_path: str,
) -> None:
    """
    Build a side-by-side output PDF.

    For each page index up to max(len(doc_1), len(doc_2)):
      - Create a new output page whose width = width_1 + width_2
        and whose height = max(height_1, height_2).
      - Render each document's page side by side. If one document has
        fewer pages, a blank page matching the other side's dimensions
        is used in its place.
      - Overlay highlights on differing words:
          * Yellow : word differs between the two documents
          * Blue   : entire line is highlighted when the other side is None
    """
    highlight_color_yellow = (1, 1, 0)     # yellow (R, G, B) in 0-1 range
    highlight_color_blue   = (0, 0.5, 1)   # blue   (R, G, B) in 0-1 range
    highlight_opacity      = 0.4

    out_doc    = pymupdf.open()
    page_count = max(len(doc_1), len(doc_2))

    for page_idx in range(page_count):
        rect_1 = get_page_rect(doc_1, page_idx, fallback_doc=doc_2)
        rect_2 = get_page_rect(doc_2, page_idx, fallback_doc=doc_1)

        out_width  = rect_1.width + rect_2.width
        out_height = max(rect_1.height, rect_2.height)
        x_offset   = rect_1.width   # shift PDF 2's coordinates to the right half

        # Create a blank output page of the combined size
        out_page = out_doc.new_page(width=out_width, height=out_height)

        # ── Render PDF 1 (left side) ──────────────────────────────────────
        if page_idx < len(doc_1):
            out_page.show_pdf_page(
                pymupdf.Rect(0, 0, rect_1.width, rect_1.height),
                doc_1, page_idx,
            )

        # ── Render PDF 2 (right side) ─────────────────────────────────────
        if page_idx < len(doc_2):
            out_page.show_pdf_page(
                pymupdf.Rect(rect_1.width, 0, out_width, rect_2.height),
                doc_2, page_idx,
            )

        # ── Draw a thin vertical divider between the two pages ────────────
        out_page.draw_line(
            pymupdf.Point(rect_1.width, 0),
            pymupdf.Point(rect_1.width, out_height),
            color=(0.5, 0.5, 0.5),
            width=1,
        )

        # ── Overlay highlights from pdf_diffs ─────────────────────────────
        for diff in pdf_diffs:
            words_1 = diff["words_1"]
            words_2 = diff["words_2"]

            # ── PDF 1 side (left) ─────────────────────────────────────────
            if words_1 is not None and words_1[0].page_idx == page_idx:
                color   = highlight_color_blue if words_2 is None else highlight_color_yellow
                indices = None if words_2 is None else diff["diff_indices_1"]
                draw_highlight(out_page, words_1, indices, color, highlight_opacity)

            # ── PDF 2 side (right) ────────────────────────────────────────
            if words_2 is not None and words_2[0].page_idx == page_idx:
                color   = highlight_color_blue if words_1 is None else highlight_color_yellow
                indices = None if words_1 is None else diff["diff_indices_2"]
                draw_highlight(out_page, words_2, indices, color, highlight_opacity, x_offset)

    out_doc.save(output_path)
    out_doc.close()
    print(f"PDF output saved to: {output_path}")


# ── Output PNG Construction ───────────────────────────────────────────────────

def page_to_pil(doc: pymupdf.Document, page_idx: int) -> Image.Image:
    """Render a single PDF page to a PIL image using PyMuPDF's pixmap."""
    pix = doc[page_idx].get_pixmap()
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def compute_page_margins(
    doc:        pymupdf.Document,
    pages_pil:  list[Image.Image],
    scale:      float,
) -> list[dict]:
    """
    Compute the top and bottom margins (in pixels) for each page.

    Top margin    = distance from y=0 to the y0 of the first line on the page.
    Bottom margin = distance from the y1 of the last line on the page to page height.
    If a page has no text, the full page height is treated as the margin.

    Returns a list of dicts (one per page) with keys:
        'top_px'    : top margin height in pixels
        'bottom_px' : bottom margin height in pixels
        'page_h_px' : total page height in pixels
    """
    all_words = []
    for page_idx, page in enumerate(doc):
        for raw in page.get_text("words"):
            all_words.append(Word(
                x0=raw[0], y0=raw[1], x1=raw[2], y1=raw[3],
                text=raw[4],
                block_no=raw[5], line_no=raw[6], word_no=raw[7],
                page_idx=page_idx,
            ))

    # Group words by page
    words_by_page: dict[int, list[Word]] = {}
    for word in all_words:
        if word.page_idx not in words_by_page:
            words_by_page[word.page_idx] = []
        words_by_page[word.page_idx].append(word)

    margins = []
    for page_idx, pil in enumerate(pages_pil):
        page_h_px = pil.height
        words     = words_by_page.get(page_idx, [])

        if not words:
            # No text — full page is margin
            margins.append({
                "top_px":    page_h_px,
                "bottom_px": page_h_px,
                "page_h_px": page_h_px,
            })
        else:
            top_px    = int(min(w.y0 for w in words) * scale)
            bottom_px = page_h_px - int(max(w.y1 for w in words) * scale)
            margins.append({
                "top_px":    top_px,
                "bottom_px": bottom_px,
                "page_h_px": page_h_px,
            })

    return margins


def compute_combined_y(
    words:      list[Word],
    scale:      float,
    pages_pil:  list[Image.Image],
) -> tuple[int, int]:
    """
    Convert a line's word coordinates to combined image coordinates by
    adding the cumulative height of all preceding pages.

    Returns (combined_y0, combined_y1) in pixels.
    """
    page_idx   = words[0].page_idx
    cumulative = sum(pil.height for pil in pages_pil[:page_idx])
    y0         = int(min(w.y0 for w in words) * scale) + cumulative
    y1         = int(max(w.y1 for w in words) * scale) + cumulative
    return y0, y1


def group_diffs_into_blocks(
    pdf_diffs: list[dict],
) -> list[list[dict]]:
    """
    Group consecutive aligned diff pairs into blocks.

    A block is a maximal sequence of pairs where both sides are present
    (neither words_1 nor words_2 is None). A pair with either side None
    starts a new single-entry block of its own.

    Returns a list of blocks, each block being a list of diff dicts.
    """
    blocks: list[list[dict]] = []
    current_block: list[dict] = []

    for diff in pdf_diffs:
        if diff["words_1"] is not None and diff["words_2"] is not None:
            # Both sides present — accumulate into current block
            current_block.append(diff)
        else:
            # One side is None — flush current block, then add this as its own block
            if current_block:
                blocks.append(current_block)
                current_block = []
            blocks.append([diff])

    if current_block:
        blocks.append(current_block)

    return blocks


def build_output_pngs(
    doc_1:      pymupdf.Document,
    doc_2:      pymupdf.Document,
    pdf_diffs:  list[dict],
    output_dir: str,
) -> None:
    """
    Build one side-by-side PNG per output page showing shifted content.

    Algorithm:
      1. Render all pages of both documents to PIL images.
      2. Derive a consistent scale factor from the first page of doc_1.
      3. Compute top and bottom margins for each page of both documents.
      4. Combine all page images into one tall combined image per document.
      5. Collect unmatched diff pairs (one side None) as blank space blocks.
      6. For each output page:
           a. Place top margins (blue highlight equalises shorter to taller).
           b. Process aligned diff pairs as line strips from the combined
              images. Unmatched pairs get a blue highlight on the blank side.
              Lines must not overlay the bottom margin — overflow to next page.
           c. Place bottom margins (blue highlight equalises shorter to taller).
      7. Save each output page as output_page_N.png.
      8. If content overflows the last page, keep adding pages using the
         last page's margins until all content is rendered.
    """
    blue_rgba    = (0, 128, 255, 100)   # semi-transparent blue (RGBA)
    blue_rgb     = (0, 128, 255)         # opaque blue (RGB) for full-page fill
    divider_rgb  = (128, 128, 128)

    # ── Step 1: Render all pages to PIL images ────────────────────────────
    pages_pil_1 = [page_to_pil(doc_1, i) for i in range(len(doc_1))]
    pages_pil_2 = [page_to_pil(doc_2, i) for i in range(len(doc_2))]

    # ── Step 2: Derive consistent scale from first page of doc_1 ──────────
    scale_1 = pages_pil_1[0].width / doc_1[0].rect.width if pages_pil_1 else 1.0
    scale_2 = pages_pil_2[0].width / doc_2[0].rect.width if pages_pil_2 else 1.0
    w1      = pages_pil_1[0].width  if pages_pil_1 else (pages_pil_2[0].width  if pages_pil_2 else 0)
    w2      = pages_pil_2[0].width  if pages_pil_2 else (pages_pil_1[0].width  if pages_pil_1 else 0)
    canvas_width = w1 + w2

    # ── Step 3: Compute page margins ──────────────────────────────────────
    margins_1 = compute_page_margins(doc_1, pages_pil_1, scale_1)
    margins_2 = compute_page_margins(doc_2, pages_pil_2, scale_2)

    # Last page margins for overflow pages
    last_margins_1 = margins_1[-1] if margins_1 else {"top_px": 0, "bottom_px": 0, "page_h_px": 0}
    last_margins_2 = margins_2[-1] if margins_2 else {"top_px": 0, "bottom_px": 0, "page_h_px": 0}

    # ── Step 4: Combine page images into one tall combined image per doc ───
    combined_h_1 = sum(p.height for p in pages_pil_1)
    combined_h_2 = sum(p.height for p in pages_pil_2)
    combined_1   = Image.new("RGB", (w1, combined_h_1), "white")
    combined_2   = Image.new("RGB", (w2, combined_h_2), "white")

    y_off = 0
    for pil in pages_pil_1:
        combined_1.paste(pil, (0, y_off))
        y_off += pil.height

    y_off = 0
    for pil in pages_pil_2:
        combined_2.paste(pil, (0, y_off))
        y_off += pil.height

    # Cumulative page offsets for combined image coordinate conversion
    cum_offsets_1 = [0]
    for pil in pages_pil_1[:-1]:
        cum_offsets_1.append(cum_offsets_1[-1] + pil.height)

    cum_offsets_2 = [0]
    for pil in pages_pil_2[:-1]:
        cum_offsets_2.append(cum_offsets_2[-1] + pil.height)

    # ── Step 5: Build ordered list of line strips to render ───────────────
    # Each entry is a dict describing one row to place on the output:
    #   type        : 'matched' | 'unmatched_1' | 'unmatched_2'
    #   combined_y0 : top of strip in combined image (side that has content)
    #   combined_y1 : bottom of strip in combined image
    #   side        : 'left' | 'right' | 'both' (which side has real content)
    strips: list[dict] = []

    for diff_idx, diff in enumerate(pdf_diffs):
        words_1 = diff["words_1"]
        words_2 = diff["words_2"]

        if words_1 is not None and words_2 is not None:
            # Matched pair — both sides have content
            page_idx_1  = words_1[0].page_idx
            page_idx_2  = words_2[0].page_idx
            cum_y0_1    = int(min(w.y0 for w in words_1) * scale_1) + cum_offsets_1[page_idx_1]
            cum_y0_2    = int(min(w.y0 for w in words_2) * scale_2) + cum_offsets_2[page_idx_2]

            # Bottom: top of next line or start of bottom margin for last line on page
            def next_combined_y(words: list[Word], diff_idx: int, side: str,
                                 scale: float, cum_offsets: list[int],
                                 margins: list[dict], pages_pil: list[Image.Image]) -> int:
                page_idx = words[0].page_idx
                # Look for the next diff on the same side
                for next_idx in range(diff_idx + 1, len(pdf_diffs)):
                    next_words = pdf_diffs[next_idx][f"words_{side}"]
                    if next_words is not None:
                        next_page = next_words[0].page_idx
                        if next_page == page_idx:
                            return int(min(w.y0 for w in next_words) * scale) + cum_offsets[next_page]
                        else:
                            break
                # No next line on same page — use start of bottom margin
                page_h_px  = pages_pil[page_idx].height
                bottom_px  = margins[page_idx]["bottom_px"]
                return cum_offsets[page_idx] + page_h_px - bottom_px

            cum_y1_1 = next_combined_y(words_1, diff_idx, "1", scale_1, cum_offsets_1, margins_1, pages_pil_1)
            cum_y1_2 = next_combined_y(words_2, diff_idx, "2", scale_2, cum_offsets_2, margins_2, pages_pil_2)

            strips.append({
                "type":        "matched",
                "cum_y0_1":    cum_y0_1,
                "cum_y1_1":    cum_y1_1,
                "cum_y0_2":    cum_y0_2,
                "cum_y1_2":    cum_y1_2,
                "row_h":       max(cum_y1_1 - cum_y0_1, cum_y1_2 - cum_y0_2),
            })

        elif words_2 is not None:
            # Unmatched — only PDF 2 has content; PDF 1 side is blue
            page_idx_2 = words_2[0].page_idx
            cum_y0_2   = int(min(w.y0 for w in words_2) * scale_2) + cum_offsets_2[page_idx_2]
            cum_y1_2   = int(max(w.y1 for w in words_2) * scale_2) + cum_offsets_2[page_idx_2]
            strips.append({
                "type":     "unmatched_2",
                "cum_y0_2": cum_y0_2,
                "cum_y1_2": cum_y1_2,
                "row_h":    cum_y1_2 - cum_y0_2,
                "lw_2":     int(line_width(words_2) * scale_2),
            })

        elif words_1 is not None:
            # Unmatched — only PDF 1 has content; PDF 2 side is blue
            page_idx_1 = words_1[0].page_idx
            cum_y0_1   = int(min(w.y0 for w in words_1) * scale_1) + cum_offsets_1[page_idx_1]
            cum_y1_1   = int(max(w.y1 for w in words_1) * scale_1) + cum_offsets_1[page_idx_1]
            strips.append({
                "type":     "unmatched_1",
                "cum_y0_1": cum_y0_1,
                "cum_y1_1": cum_y1_1,
                "row_h":    cum_y1_1 - cum_y0_1,
                "lw_1":     int(line_width(words_1) * scale_1),
            })

    # ── Step 6: Render output pages ───────────────────────────────────────
    def get_margins(margins: list[dict], page_idx: int, last_margins: dict) -> dict:
        """Return margins for a given output page index, falling back to last page."""
        return margins[page_idx] if page_idx < len(margins) else last_margins

    def make_page_canvas(page_h: int) -> tuple[Image.Image, Image.Image, ImageDraw.ImageDraw]:
        """Create a blank RGB canvas and RGBA overlay for one output page."""
        canvas  = Image.new("RGB",  (canvas_width, page_h), "white")
        overlay = Image.new("RGBA", (canvas_width, page_h), (0, 0, 0, 0))
        draw    = ImageDraw.Draw(overlay)
        return canvas, overlay, draw

    def save_page(canvas: Image.Image, overlay: Image.Image,
                  page_num: int, page_h: int) -> None:
        """Composite overlay, draw divider, and save the output page PNG."""
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
        draw   = ImageDraw.Draw(canvas)
        draw.line([(w1, 0), (w1, page_h)], fill=divider_rgb, width=1)
        png_path = os.path.join(output_dir, f"output_page_{page_num}.png")
        canvas.save(png_path)
        print(f"PNG output saved to: {png_path}")

    strip_idx  = 0
    out_page_n = 1
    max_pages  = max(len(doc_1), len(doc_2))

    while strip_idx < len(strips) or out_page_n == 1:
        out_page_idx = out_page_n - 1   # 0-based index for margin lookup

        # ── Get margins for this output page ──────────────────────────────
        m1 = get_margins(margins_1, out_page_idx, last_margins_1)
        m2 = get_margins(margins_2, out_page_idx, last_margins_2)

        top_1    = m1["top_px"]
        top_2    = m2["top_px"]
        bottom_1 = m1["bottom_px"]
        bottom_2 = m2["bottom_px"]
        top_h    = max(top_1, top_2)
        bottom_h = max(bottom_1, bottom_2)

        # Page height = top margin + content area + bottom margin
        # Content area is bounded by what fits between margins
        content_h  = m1["page_h_px"] - top_1 - bottom_1   # use PDF 1's page for content height
        page_h     = top_h + content_h + bottom_h
        canvas, overlay, draw = make_page_canvas(page_h)

        # ── Check if PDF 1 has no counterpart for this page ───────────────
        pdf1_has_page = out_page_idx < len(doc_1)
        pdf2_has_page = out_page_idx < len(doc_2)

        if not pdf1_has_page and pdf2_has_page:
            # Full blue page on PDF 1 side
            draw.rectangle([(0, 0), (w1, page_h)], fill=(*blue_rgb, 255))
            # Paste PDF 2's page on the right
            if out_page_idx < len(pages_pil_2):
                canvas.paste(pages_pil_2[out_page_idx], (w1, 0))
            save_page(canvas, overlay, out_page_n, page_h)
            out_page_n += 1
            if out_page_idx >= max(len(doc_1), len(doc_2)) - 1 and strip_idx >= len(strips):
                break
            continue

        # ── Place top margins ──────────────────────────────────────────────
        # Paste top margin from combined images
        if pages_pil_1 and out_page_idx < len(pages_pil_1):
            top_strip_1 = combined_1.crop((0, cum_offsets_1[out_page_idx],
                                           w1, cum_offsets_1[out_page_idx] + top_1))
            canvas.paste(top_strip_1, (0, top_h - top_1))

        if pages_pil_2 and out_page_idx < len(pages_pil_2):
            top_strip_2 = combined_2.crop((0, cum_offsets_2[out_page_idx],
                                           w2, cum_offsets_2[out_page_idx] + top_2))
            canvas.paste(top_strip_2, (w1, top_h - top_2))

        # Blue highlight equalises shorter top margin to taller
        if top_1 < top_2:
            draw.rectangle([(0, top_h - top_2), (w1, top_h - top_1)],
                           fill=blue_rgba)
        elif top_2 < top_1:
            draw.rectangle([(w1, top_h - top_1), (canvas_width, top_h - top_2)],
                           fill=blue_rgba)

        # ── Place bottom margins ───────────────────────────────────────────
        bottom_start = top_h + content_h   # y position where bottom margin begins

        if pages_pil_1 and out_page_idx < len(pages_pil_1):
            pil_h_1     = pages_pil_1[out_page_idx].height
            bot_y0_1    = cum_offsets_1[out_page_idx] + pil_h_1 - bottom_1
            bot_strip_1 = combined_1.crop((0, bot_y0_1, w1, bot_y0_1 + bottom_1))
            canvas.paste(bot_strip_1, (0, bottom_start + (bottom_h - bottom_1)))

        if pages_pil_2 and out_page_idx < len(pages_pil_2):
            pil_h_2     = pages_pil_2[out_page_idx].height
            bot_y0_2    = cum_offsets_2[out_page_idx] + pil_h_2 - bottom_2
            bot_strip_2 = combined_2.crop((0, bot_y0_2, w2, bot_y0_2 + bottom_2))
            canvas.paste(bot_strip_2, (w1, bottom_start + (bottom_h - bottom_2)))

        # Blue highlight equalises shorter bottom margin to taller
        if bottom_1 < bottom_2:
            draw.rectangle([(0, bottom_start), (w1, bottom_start + (bottom_h - bottom_1))],
                           fill=blue_rgba)
        elif bottom_2 < bottom_1:
            draw.rectangle([(w1, bottom_start), (canvas_width, bottom_start + (bottom_h - bottom_2))],
                           fill=blue_rgba)

        # ── Place line strips in content area ─────────────────────────────
        y_cursor      = top_h   # current y position within this output page
        content_limit = top_h + content_h   # must not exceed this (bottom margin starts here)

        while strip_idx < len(strips):
            strip = strips[strip_idx]
            row_h = strip["row_h"]

            # Check if this strip fits in the remaining content area
            if y_cursor + row_h > content_limit:
                break   # overflow to next page

            if strip["type"] == "matched":
                # Crop and paste from both combined images
                s1 = combined_1.crop((0, strip["cum_y0_1"], w1, strip["cum_y0_1"] + row_h))
                s2 = combined_2.crop((0, strip["cum_y0_2"], w2, strip["cum_y0_2"] + row_h))
                canvas.paste(s1, (0, y_cursor))
                canvas.paste(s2, (w1, y_cursor))

            elif strip["type"] == "unmatched_2":
                # PDF 2 content on right; blue highlight on left
                s2 = combined_2.crop((0, strip["cum_y0_2"], w2, strip["cum_y1_2"]))
                canvas.paste(s2, (w1, y_cursor))
                draw.rectangle(
                    [(0, y_cursor), (strip["lw_2"], y_cursor + row_h)],
                    fill=blue_rgba,
                )

            elif strip["type"] == "unmatched_1":
                # PDF 1 content on left; blue highlight on right
                s1 = combined_1.crop((0, strip["cum_y0_1"], w1, strip["cum_y1_1"]))
                canvas.paste(s1, (0, y_cursor))
                draw.rectangle(
                    [(w1, y_cursor), (w1 + strip["lw_1"], y_cursor + row_h)],
                    fill=blue_rgba,
                )

            y_cursor  += row_h
            strip_idx += 1

        save_page(canvas, overlay, out_page_n, page_h)
        out_page_n += 1

        # Stop if all strips rendered and we've covered all original pages
        if strip_idx >= len(strips) and out_page_idx >= max(len(doc_1), len(doc_2)) - 1:
            break


# ── Main ──────────────────────────────────────────────────────────────────────

def compare_pdfs(path_1: str, path_2: str) -> list[dict]:
    output_dir = os.path.join(os.path.dirname(os.path.abspath(path_1)), "Output")

    # 1. Validate paths
    validate_pdf_paths(path_1, path_2)

    # 2. Prepare output folder
    prepare_output_folder(output_dir)

    # 3. Open documents
    doc_1 = pymupdf.open(path_1)
    doc_2 = pymupdf.open(path_2)

    # 4. Extract all words from each document into one flat sequence
    all_words_1 = extract_all_words(doc_1)
    all_words_2 = extract_all_words(doc_2)

    # 5. Group flat word lists into lines
    lines_1 = group_words_into_lines(all_words_1)
    lines_2 = group_words_into_lines(all_words_2)

    # 6. Align lines between the two documents
    aligned = align_lines(lines_1, lines_2)

    # 7. Compute diffs from aligned line pairs (stored in pdf_diffs for later access)
    pdf_diffs = compute_all_diffs(aligned)

    # 8. Build side-by-side output PDF with highlights
    pdf_path = os.path.join(output_dir, "output.pdf")
    build_output_pdf(doc_1, doc_2, pdf_diffs, pdf_path)

    # 9. Build per-page PNG outputs with shifted content
    build_output_pngs(doc_1, doc_2, pdf_diffs, output_dir)

    doc_1.close()
    doc_2.close()

    return pdf_diffs   # expose for further use if needed


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python pdf_compare.py <path_to_pdf_1> <path_to_pdf_2>")
        sys.exit(1)

    path_1 = sys.argv[1]
    path_2 = sys.argv[2]

    try:
        pdf_diffs = compare_pdfs(path_1, path_2)
        print(f"Comparison complete. {len(pdf_diffs)} aligned line(s) processed.")
    except PDFDoesNotExistException as e:
        print(f"[Error] {e}")
        sys.exit(1)
    except SamePDFBeingCompared as e:
        print(f"[Error] {e}")
        sys.exit(1)