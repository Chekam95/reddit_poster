import configparser
import logging

CONFIG = None
ACCOUNTS = None


def get_config():
    global CONFIG
    global ACCOUNTS
    if CONFIG is None or ACCOUNTS is None:
        CONFIG = configparser.ConfigParser()
        with open('config.txt', 'r', encoding='utf-8') as configfile:
            CONFIG.read_file(configfile)
        ACCOUNTS = {section: dict(CONFIG.items(section)) for section in CONFIG.sections() if section != 'DEFAULT'}
    return CONFIG['DEFAULT'], ACCOUNTS


def load_ads_accounts_config(file_path):
    config = configparser.ConfigParser()
    accounts_config = {}
    try:
        config.read(file_path)
        for section in config.sections():
            accounts_config[section] = {
                'profile_serial_number': config.get(section, 'profile_serial_number'),
                'password': config.get(section, 'password')
            }
    except FileNotFoundError:
        logging.error(f"Файл {file_path} не знайдено.")
    except Exception as e:
        logging.error(f"Помилка при читанні файлу {file_path}: {e}")
    return accounts_config
