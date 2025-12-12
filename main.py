import logging
import os
import shutil
import time
import re
import random
import threading
import uuid
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import queue
import requests
import configparser
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import UnexpectedAlertPresentException, TimeoutException
from selenium.webdriver.common.alert import Alert
from pyairtable import Api
from dateutil import parser
import pytz
import urllib3
from driver import get_driver, close_driver
from file_workers.config_service import get_config
from image_lib import input_image_path
from image_text import add_text_with_rounded_background

urllib3.disable_warnings()
logging.basicConfig(level=logging.INFO)

post_cache = queue.Queue()
RECORDS = []
POSTS_ON_WORK = []
general_config, accounts_config = get_config()

AIRTABLE_API_KEY = general_config.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = general_config.get('AIRTABLE_BASE_ID')
AIRTABLE_TABLE_NAME = general_config.get('AIRTABLE_TABLE_NAME')

airtable_api = Api(AIRTABLE_API_KEY)
table = airtable_api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)


def load_config(file_path):
    config = {}
    try:
        with open(file_path, 'r') as file:
            for line in file:
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.strip().split('=', 1)
                    config[key.strip()] = value.strip()

    except FileNotFoundError:
        logging.error(f" {file_path} not found .")
    except Exception as e:
        logging.error(f"{file_path}: {e}")
    return config


def load_ads_accounts_config(file_path):
    config = configparser.ConfigParser()
    accounts_config = []
    try:
        config.read(file_path)
        if not config.sections():
            return accounts_config

        for section in config.sections():
            profile_serial_number = config.get(section, 'profile_serial_number', fallback=None)
            username = config.get(section, 'username', fallback=None)
            password = config.get(section, 'password', fallback=None)
            close = config.getboolean(section, 'close', fallback=False)
            accounts_config.append((section, profile_serial_number, username, password, close))


    except Exception as e:
        logging.error(f"Error {file_path}: {e}")

    return accounts_config


config = load_config('config.txt')

ads_accounts_config = load_ads_accounts_config('config_ads_account.txt')


class Account:
    def __init__(self, username, psswd):
        self.username = username
        self.psswd = psswd


class SessionManager:
    def __init__(self):
        self.active_sessions = {}

    def is_session_active(self, ads_id):
        return self.active_sessions.get(ads_id, False)

    def start_session(self, ads_id):
        if not self.is_session_active(ads_id):

            if not ads_id or not isinstance(ads_id, str):
                logging.error(f"AdsPower ID not corect: {ads_id}")
                return None

            try:
                driver = get_driver(ads_id)
            except Exception as e:
                return None

            if driver:
                self.active_sessions[ads_id] = True
                return driver
        return None

    def end_session(self, ads_id):
        self.active_sessions[ads_id] = False


session_manager = SessionManager()
def get_ads_account_data(account_name):
    for account in ads_accounts_config:
        if account[0] == account_name:
            profile_serial_number = account[1]
            password = account[3]
            return str(profile_serial_number), str(password)
    return None, None


def get_data_from_airtable():
    try:
        records = table.all()
        logging.info(f" {len(records)} in Airtable.") if records else logging.info("Error")
        return records
    except Exception as e:
        logging.error(f"Error Airtable: {e}")
        return []

def download_media(media_url):
    try:
        response = requests.get(media_url)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '')
        suffix = '.jpg' if 'image/' in content_type else '.mp4' if 'video/' in content_type else None

        if not suffix:
            logging.error(f"TypeError media: {content_type}")
            return None

        filename = f"temp/{uuid.uuid4()}{suffix}"
        os.makedirs("temp", exist_ok=True)
        with open(filename, "wb") as f:
            f.write(response.content)

        logging.info(f"Download media: {filename}")
        return os.path.abspath(filename)
    except Exception as e:
        return None


def process_image(image_path):
    try:
        return input_image_path(image_path)
    except Exception as e:
        return image_path


def login(driver, account):
    random_delay(2,4)
    # driver.maximize_window()
    random_delay(3, 6)

    if is_logged_in(driver):
        return

    random_delay(3, 6)

    if check_no_auth_needed(driver):
        driver.get('https://www.reddit.com/')
        return

    # logging.info(f {account.username}...")
    driver.get('https://www.reddit.com/login/')

    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, 'login-username')))
    random_delay(3, 6)

    username_field = driver.find_element(By.ID, 'login-username')
    username_field.clear()
    time.sleep(2)
    username_field.send_keys(account.username)

    random_delay(3, 6)

    password_field = driver.find_element(By.ID, 'login-password')
    password_field.clear()
    time.sleep(2)
    password_field.send_keys(account.psswd + Keys.ENTER)


def is_logged_in(driver):
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//button[@aria-label='User menu']")))
        return True
    except TimeoutException:
        return False


def check_no_auth_needed(driver):
    try:
        driver.find_element(By.ID, 'expand-user-drawer-button')
        return True
    except NoSuchElementException:
        return False


def get_shadow_element(driver, host_selector, element_selector):
    try:
        shadow_host = WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, host_selector))
        )
        shadow_root = driver.execute_script('return arguments[0].shadowRoot', shadow_host)
        if shadow_root is None:
            return None
        return shadow_root.find_element(By.CSS_SELECTOR, element_selector)

    except NoSuchElementException:
        return None
    except Exception as e:
        return None


def filter_bmp_characters(text):
    return ''.join(c for c in text if ord(c) <= 0xFFFF)

def close_extra_tabs(driver, max_allowed_tabs=1):

    try:
        open_tabs = driver.window_handles
        while len(open_tabs) > max_allowed_tabs:
            driver.switch_to.window(open_tabs[-1])
            driver.close()
            open_tabs = driver.window_handles
        driver.switch_to.window(open_tabs[0])
    except Exception as e:
        logging.error(f": {e}")


def add_content_to_post(driver, content):
    try:
        content_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[contenteditable='true'][aria-label='Post body text field']"))
        )
        content_element.click()
        time.sleep(1)

        driver.execute_script("""
            arguments[0].focus();
            document.execCommand("insertText", false, arguments[1]);
            const inputEvent = new Event('input', { bubbles: true });
            arguments[0].dispatchEvent(inputEvent);
        """, content_element, content)

        return True

    except TimeoutException:
        return False
    except Exception as e:
        return False

def add_title_to_post(driver, title, snap_value, char_value):
    try:
        shadow_host = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "faceplate-textarea-input"))
        )
        shadow_root = driver.execute_script('return arguments[0].shadowRoot', shadow_host)
        if shadow_root is None:
            return False

        title_input = WebDriverWait(shadow_root, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea#innerTextArea"))
        )

        full_title = f"{title} {char_value} {snap_value}".strip()

        filtered_title = filter_bmp_characters(full_title)

        title_input.clear()
        title_input.send_keys(filtered_title)

        return True
    except TimeoutException:
        return False
    except Exception as e:
        return False

def start_session(self, ads_id):
    if not self.is_session_active(ads_id):
        if not ads_id or not isinstance(ads_id, str):
            return None

        try:
            driver = get_driver(ads_id)
        except Exception as e:
            return None

        if driver:
            self.active_sessions[ads_id] = True
            close_extra_tabs(driver)
            return driver
        else:
            logging.error(f"Error AdsPower ID: {ads_id}")
    return None


def input_flair(driver, flair):
    try:
        shadow_host = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "r-post-flairs-modal"))
        )
        shadow_root = driver.execute_script('return arguments[0].shadowRoot', shadow_host)
        if shadow_root is None:
            return False

        search_input_host = shadow_root.find_element(By.CSS_SELECTOR, "faceplate-search-input")
        search_input_root = driver.execute_script('return arguments[0].shadowRoot', search_input_host)
        if search_input_root is None:
            return False

        all_elements = search_input_root.find_elements(By.CSS_SELECTOR, "*")

        try:
            input_filter = search_input_root.find_element(By.CSS_SELECTOR, "input")
            input_filter.clear()
            input_filter.send_keys(flair)
            return True
        except NoSuchElementException:
            return False

    except TimeoutException:
        return False
    except Exception as e:
        return False



def select_flair(driver, flair):
    try:
        shadow_host = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "r-post-flairs-modal"))
        )
        shadow_root = driver.execute_script('return arguments[0].shadowRoot', shadow_host)
        if shadow_root is None:
            return False

        add_flair_button = WebDriverWait(shadow_root, 20).until(
            EC.element_to_be_clickable((By.ID, "reddit-post-flair-button"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", add_flair_button)

        add_flair_button.click()
        shadow_host = WebDriverWait(driver, 40).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "r-post-flairs-modal"))
        )
        shadow_root = driver.execute_script('return arguments[0].shadowRoot', shadow_host)
        if shadow_root is None:
            return False
        time.sleep(3)

        flair_radio_button = WebDriverWait(shadow_root, 40).until(
            EC.element_to_be_clickable((By.ID, "post-flair-radio-input-0"))
        )


        input_flair(driver, flair)
        time.sleep(1)
        flair_radio_button.click()
        add_button = WebDriverWait(shadow_root, 40).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button#post-flair-modal-apply-button"))
        )
        add_button.click()
        random_delay()
        return True
    except TimeoutException:
        close_flair = get_shadow_element(driver, "r-post-flairs-modal", "button.button-small.button-secondary.icon.items-center.justify-center")
        close_flair.click()
        time.sleep(3)
        post_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "submit-post-button"))
        )
        time.sleep(1)
        post_button.click()
        return False
    except Exception as e:
        return False




def click_element_with_retry(driver, element, max_retries=3, scroll=True):
    retries = 0
    while retries < max_retries:
        try:
            if scroll:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)

            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e:
            retries += 1
            time.sleep(2)
    return False


def click_post_button_directly(driver):
    try:
        random_delay(3,5)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        post_button = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "submit-post-button"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post_button)
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable(post_button))
        time.sleep(10)
        post_button.click()
        return True
    except TimeoutException:
        return False
    except Exception as e:
        return False


def random_delay(min_seconds=5, max_seconds=10):
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


def on_cupid(driver):
    try:
        checkbox = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input.MuiSwitch-input"))
        )

        aria_checked_value = checkbox.get_attribute("aria-checked")

        if aria_checked_value == "false":
            checkbox.click()
            logging.info("Checkbox clicked to enable Cupid.")
        else:
            logging.info("Checkbox already enabled.")
    except Exception as e:
        logging.error(f"Error toggling Cupid switch: {e}")

def off_cupid(driver):
    try:
        checkbox = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input.MuiSwitch-input"))
        )

        aria_checked_value = checkbox.get_attribute("aria-checked")

        if aria_checked_value == "True":
            checkbox.click()
            logging.info("Checkbox clicked to enable Cupid.")
        else:
            logging.info("Checkbox already enabled.")
    except Exception as e:
        logging.error(f"Error toggling Cupid switch: {e}")


def post_to_reddit(driver, flair, title, content, media_path=None, subreddit_name="test", snap_value='', char_value=''):
    # off_cupid(driver)
    try:
        subreddit_url = f"https://www.reddit.com/r/{subreddit_name}/"
        driver.get(subreddit_url)

        create_post_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Create Post')]"))
        )
        create_post_button.click()
        random_delay()
        if not content and not media_path:
            add_title_to_post(driver, title, snap_value, char_value)
            random_delay(2,5)
            post_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "submit-post-button"))
            )
            time.sleep(2)
            post_button.click()
            random_delay(3,5)
            select_flair(driver, flair)
            random_delay(2, 5)
            post_button1 = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "submit-post-button"))
            )
            post_button1.click()

        if content:
            add_title_to_post(driver, title, snap_value, char_value)
            random_delay(2,5)
            add_content_to_post(driver, content)
            random_delay(2,5)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            post_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "submit-post-button"))
            )
            time.sleep(5)
            post_button.click()
            random_delay(4,7)
            select_flair(driver, flair)
            random_delay(4,7)
            post_button1 = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "submit-post-button"))
            )
            post_button1.click()
            random_delay(4,7)

        else:
            image_button = get_shadow_element(driver, 'r-post-type-select', 'button[data-select-value="IMAGE"]')
            if image_button and media_path and image_button.is_enabled():
                image_button.click()
                random_delay(5, 10)

                if not add_title_to_post(driver, title, snap_value, char_value):
                    return False

                random_delay(5, 10)
                upload_button = get_shadow_element(driver, "r-post-media-input", "input[type='file']")
                if upload_button:
                    upload_button.send_keys(media_path)
                    time.sleep(30)
                else:
                    return False

            else:
                if not add_title_to_post(driver, title, snap_value, char_value):
                    return False
            if not click_post_button_directly(driver):
                return False
            time.sleep(2)
            if not select_flair(driver, flair):
                return False

            random_delay(3, 5)

            if not click_post_button_directly(driver):
                return False

            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//a[contains(@href, '/r/') and contains(@href, '/comments/')]"))
            )
            return True

    except TimeoutException as te:
        return False
    except Exception as e:
        return False


def extract_media_url(media_data):
    if not media_data:
        return None
    if isinstance(media_data, str):
        return media_data
    if isinstance(media_data, list) and len(media_data) > 0:
        media_data = media_data[0]
    if isinstance(media_data, dict):
        return media_data.get('url')


# def should_post_now(post_time):
#     now = datetime.now(pytz.utc).replace(second=0, microsecond=0)
#     return abs((post_time - now).total_seconds()) <= 40

local_tz = pytz.timezone("Europe/London")
post_time = datetime(2024, 12, 10, 14, 30, tzinfo=local_tz)

def should_post_now(post_time, timezone_name="Europe/London"):
    try:
        local_tz = pytz.timezone(timezone_name)
        now = datetime.now(local_tz).replace(second=0, microsecond=0)

        if post_time.tzinfo is None:
            post_time = local_tz.localize(post_time)
        else:
            post_time = post_time.astimezone(local_tz)

        time_difference = abs((post_time - now).total_seconds())
        return time_difference <= 40
    except Exception as e:
        return False


def clear_temp_folder(folder_path='temp'):
    try:
        if not os.path.exists(folder_path):
            return
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)

            except Exception as e:
                logging.error(f" {file_path}: {e}")
    except Exception as e:
        logging.error(f"{folder_path}: {e}")


def schedule_daily_cleanup():
    while True:
        current_time = datetime.now().strftime("%H:%M")
        if current_time == "00:00":
            clear_temp_folder('temp')
            time.sleep(86400)
        time.sleep(60)


def add_posts_to_cache():
    global RECORDS, POSTS_ON_WORK
    while True:
        new_records = get_data_from_airtable()
        if new_records != RECORDS:
            RECORDS = new_records
            for record in RECORDS:
                record_id = record['id']
                fields = record['fields']
                if fields.get('Scheduled?', False) and record_id in POSTS_ON_WORK:
                    POSTS_ON_WORK.remove(record_id)

        time.sleep(20)


def screen_error(driver, account_name, subreddit_name, post_time,):
    try:
        driver.execute_script("window.scrollTo(0, 0);")

        time.sleep(1)

        create_post_button = WebDriverWait(driver, 40).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Create Post')]"))
        )
        time.sleep(15)
        return create_post_button
    except TimeoutException:
        take_screenshot(driver, account_name, subreddit_name, post_time)
        return None


def check_records():
    global RECORDS, POSTS_ON_WORK

    while True:
        for record in RECORDS:
            try:
                record_id = record['id']

                if record_id in POSTS_ON_WORK:
                    continue

                fields = record['fields']

                post_date = fields.get('Date')
                post_time_str = fields.get('Time')


                if not post_date:
                    continue

                if not post_time_str:
                    continue
                post_time = parse_datetime(post_date, post_time_str)

                if post_time is None:
                    continue
                if fields.get('Scheduled?') and should_post_now(post_time):
                    post_cache.put(record)
                    POSTS_ON_WORK.append(record_id)
                    table.update(record_id, {'Scheduled?': False})

            except TypeError as e:
                logging.error(f"TypeError encountered: {e}")
                logging.error(f"Record that caused error: {record}")

            except Exception as e:
                logging.error(f"Unexpected error: {e}")

        time.sleep(10)



def parse_datetime(date_str, time_str):

    try:

        date_str = date_str.strip()
        time_str = time_str.strip()

        time_str = re.sub(r'\s+', ' ', time_str)

        datetime_str = f"{date_str} {time_str}"

        parsed_time = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        return parsed_time
    except ValueError as e:
        logging.error(f"Parse date'{datetime_str}': {e}")
        return None


def take_screenshot(driver, account_name, subreddit_name, post_time):
    local_tz = pytz.timezone("Europe/Kiev")
    local_time = post_time.astimezone(local_tz)
    timestamp = local_time.strftime("%I-%M%p")

    folder_path = f"errors/{account_name}/"
    os.makedirs(folder_path, exist_ok=True)
    today = datetime.now().strftime("%d_%m")
    filename = f"{folder_path}/{today}/{subreddit_name}_{timestamp}.png"
    try:
        total_width = driver.execute_script("return document.body.scrollWidth")
        total_height = driver.execute_script("return document.body.scrollHeight")

        driver.set_window_size(total_width, total_height)

        driver.execute_script("window.scrollTo(0, 0);")
        driver.execute_script(f"window.scrollTo(0, {total_height // 2});")


        driver.save_screenshot(filename)
        logging.error(f"Screenshot {account_name} in time {timestamp}: {filename}")

    except Exception as e:
        logging.error(f" {account_name}: {e}")



def process_post_cache_selenium():
    while True:
        try:
            if not post_cache.empty():
                record = post_cache.get()
                record_id = record['id']
                fields = record.get('fields', {})

                flair = fields.get('Flair', '')
                char_value = fields.get('CHAR', '')
                snap_value = fields.get('SNAP', '')
                title = fields.get('Title', 'No title')
                content = fields.get('Text', '')
                subreddit_name = fields.get('Subreddit', 'test')
                account_name = fields.get('Account', None)

                post_date = fields.get('Date')
                post_time_str = fields.get('Time')

                if post_date and post_time_str:
                    post_time = parse_datetime(post_date, post_time_str)
                    if post_time is None:
                        post_cache.task_done()
                        continue
                else:
                    post_cache.task_done()
                    continue
                if isinstance(account_name, list):
                    account_name = account_name[0]
                if not account_name:
                    post_cache.task_done()
                    continue

                profile_serial_number, password = get_ads_account_data(account_name)

                if not profile_serial_number:
                    post_cache.task_done()
                    continue

                media_data = fields.get('IMG or Video', None)
                media_path = None
                try:
                    if not media_data:
                        text_overlay = f"{char_value}  {snap_value}"
                        threading.Thread(
                            target=try_posting_to_reddit_selenium,
                            args=(account_name, post_time, profile_serial_number, flair, subreddit_name, title, content,
                                  media_path, account_name, password, text_overlay),
                            daemon=True
                        ).start()

                    else:
                        media_url = extract_media_url(media_data)
                        media_path = download_media(media_url)
                        text_overlay = f"{char_value}  {snap_value}"
                        if fields.get('snap post title'):
                            media_path = process_image(media_path)
                            threading.Thread(
                                target=try_posting_to_reddit_selenium,
                                args=(account_name, post_time, profile_serial_number, flair, subreddit_name, title, content,
                                      media_path, account_name, password, text_overlay),
                                daemon=True
                            ).start()
                            time.sleep(5)
                        else:
                            media_path = process_image(media_path)
                            media_path = add_text_with_rounded_background(text_overlay, media_path)
                            threading.Thread(
                                target=try_posting_to_reddit_selenium,
                                args=(account_name, post_time, profile_serial_number, flair, subreddit_name, title, content,
                                      media_path, account_name, password),
                                daemon=True
                            ).start()


                except Exception as e:
                    logging.error(f"Error processing post for record {record_id}: {e}")

                finally:
                    pass


                time.sleep(random.uniform(10, 20))
            else:
                time.sleep(5)

        except TypeError as e:
            logging.error(f"TypeError in processing record: {e}")
            time.sleep(2)

        except Exception as e:
            logging.error(f"Error in processing post: {e}")
            time.sleep(2)



def try_posting_to_reddit_selenium(account_name, post_time, ads_id, flair, subreddit_name, title, content, media_path=None, username=None,
                                   password=None, snap_value='', char_value=''):
    while session_manager.is_session_active(ads_id):
        time.sleep(2)

    account_close_config = next((account[4] for account in ads_accounts_config if account[0] == account_name), "True")
    close_browser = str(account_close_config).lower() == "true"
    try:
        driver = session_manager.start_session(ads_id)
        if driver is None:
            logging.error(f" AdsPower ID: {ads_id}")
            return None

        account = Account(username, password)
        login(driver, account)
        time.sleep(2)

        try:
            success = post_to_reddit(driver, flair, title, content, media_path, subreddit_name, snap_value, char_value)
        except UnexpectedAlertPresentException:
            alert = Alert(driver)
            logging.error(f"Unexpected alert open: {alert.text}")
            alert.accept()

        if success:
            screen_error(driver, account_name, subreddit_name, post_time)
        else:
            screen_error(driver, account_name, subreddit_name, post_time)

    except TimeoutException as te:
        logging.error(f"Timeout{subreddit_name}: {te}")
    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        if close_browser:
            if driver:
                close_driver(ads_id)
            session_manager.end_session(ads_id)
        else:
            driver.quit()
            session_manager.end_session(ads_id)
            # on_cupid(driver)
            logging.info(f"Wait {account_name}.")

if __name__ == '__main__':
    if not os.path.exists("temp"):
        os.mkdir("temp")
    for f in os.listdir("temp/"):
        try:
            shutil.rmtree(os.path.join("temp/", f))
        except Exception:
            try:
                os.remove(os.path.join("temp/", f))
            except Exception as e:
                pass
    threading.Thread(target=add_posts_to_cache, daemon=True).start()
    threading.Thread(target=check_records, daemon=True).start()
    threading.Thread(target=schedule_daily_cleanup, daemon=True).start()
    process_post_cache_selenium()
