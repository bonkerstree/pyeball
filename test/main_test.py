import pytest

from ..src import pyeball

def test_given_no_document_arguments_when_parse_document_args_then_missing_document_args_exception_raised():
    args = ['py_module.py']

    with pytest.raises(pyeball.PyeballMissingDocumentArgs):
        pyeball._parse_document_args(args)

def test_given_only_one_document_argument_when_parse_document_args_then_missing_document_args_exception_raised():
    args = ['py_module.py', 'doc1.pdf']

    with pytest.raises(pyeball.PyeballMissingDocumentArgs):
        pyeball._parse_document_args(args)

def test_given_two_document_arguments_when_parse_document_args_then_the_document_paths_will_be_returned_as_a_tuple():
    args = ['py_module.py', 'doc1.pdf', 'doc2.pdf']

    doc1, doc2 = pyeball._parse_document_args(args)
    assert doc1 == 'doc1.pdf'
    assert doc2 == 'doc2.pdf'

def test_given_two_document_arguments_with_one_non_pdf_when_parse_document_args_then_wrong_format_exception_raised():
    args = ['py_module.py', 'doc1.doc', 'doc2.pdf']

    with pytest.raises(pyeball.PyeballWrongDocumentFormat):
        pyeball._parse_document_args(args)

    args = ['py_module.py', 'doc1.pdf', 'doc2.doc']

    with pytest.raises(pyeball.PyeballWrongDocumentFormat):
        pyeball._parse_document_args(args)