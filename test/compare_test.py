import pytest
from ..src import pyeball

def test_given_one_pdf_compare_same_pdf_to_itself_then_same_document_exception_is_raised():
    with pytest.raises(pyeball.PyeballSameDocumentIsBeingCompared):
        pyeball.compare_documents('pdfs/01_basic_paragraph_orig.pdf', 'pdfs/01_basic_paragraph_orig.pdf')

def test_given_two_pdfs_with_same_content_compare_them_then_return_zero_diffs():
    output = pyeball.compare_documents('pdfs/01_basic_paragraph_orig.pdf', 'pdfs/02_basic_paragraph_copy.pdf')
    assert output.diffs == 0

def test_given_two_pdfs_with_a_diff_on_upper_left_corner_of_paragraph_compare_them_then_return_one_diff():
    output = pyeball.compare_documents('pdfs/01_basic_paragraph_orig.pdf', 'pdfs/03_basic_paragraph_diff_upper_left_corner.pdf')
    assert output.diffs == 1

def test_given_two_pdfs_with_a_diff_on_upper_right_corner_of_paragraph_compare_them_then_return_one_diff():
    output = pyeball.compare_documents('pdfs/01_basic_paragraph_orig.pdf', 'pdfs/04_basic_paragraph_diff_upper_right_corner.pdf')
    assert output.diffs == 1

def test_given_two_pdfs_with_a_diff_on_bottom_left_corner_of_paragraph_compare_them_then_return_one_diff():
    output = pyeball.compare_documents('pdfs/01_basic_paragraph_orig.pdf', 'pdfs/05_basic_paragraph_diff_bottom_left_corner.pdf')
    assert output.diffs == 1

def test_given_two_pdfs_with_a_diff_on_bottom_right_corner_of_paragraph_compare_them_then_return_one_diff():
    output = pyeball.compare_documents('pdfs/01_basic_paragraph_orig.pdf', 'pdfs/06_basic_paragraph_diff_upper_right_corner.pdf')
    assert output.diffs == 1