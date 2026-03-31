import pytest

from ..src import pyeball

def test_given_no_document_arguments_when_parse_document_args_then_missing_document_args_exception_raised():
    args = ['py_module.py']

    with pytest.raises(pyeball.PyeballMissingDocumentArgs):
        pyeball.run(args)

def test_given_only_one_document_argument_when_parse_document_args_then_missing_document_args_exception_raised():
    args = ['py_module.py', 'pdfs/01_basic_paragraph_orig.pdf']

    with pytest.raises(pyeball.PyeballMissingDocumentArgs):
        pyeball.run(args)

def test_given_two_document_arguments_when_parse_document_args_then_the_document_paths_will_be_returned_as_a_tuple():
    args = ['py_module.py', 'pdfs/01_basic_paragraph_orig.pdf', 'pdfs/02_basic_paragraph_copy.pdf']

    pyeball.run(args)

def test_given_two_document_arguments_with_one_non_pdf_when_parse_document_args_then_wrong_format_exception_raised():
    args = ['py_module.py', 'pdfs/01_basic_paragraph_orig.pdf', 'pdfs/01_basic_paragraph_zcopy.doc']

    with pytest.raises(pyeball.PyeballWrongDocumentFormat):
        pyeball.run(args)

    args = ['py_module.py', 'pdfs/01_basic_paragraph.doc', 'pdfs/02_basic_paragraph_copy.pdf']

    with pytest.raises(pyeball.PyeballWrongDocumentFormat):
        pyeball.run(args)