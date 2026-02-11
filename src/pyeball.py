import logging
logger_name = 'pyeball'
logger = logging.getLogger(logger_name)

def main():
    logging.basicConfig(filename=f'{logger_name}.log',
                        format='[%(levelname)s] %(asctime)s.%(msecs)03d %(module)s.py: %(funcName)s(): %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=logging.INFO)

    logger.info('Starting up pyeball')
    logger.info('Closing down pyeball')

if __name__ == "__main__":
    main()