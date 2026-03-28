import logging

from .pyeball_helpers import parse_document_args

logger_name = 'pyeball'
logger = logging.getLogger(logger_name)
logging.basicConfig(filename=f'{logger_name}.log',
                        format='%(asctime)s.%(msecs)03d %(module)s.py: %(funcName)s(): [%(levelname)s] %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)

def run(args = None):
    logger.info('==================== Starting up pyeball ====================')
    doc1, doc2 = parse_document_args(args)
    logger.info('==================== Closing down pyeball ====================')