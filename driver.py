import json
import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from file_workers.config_service import get_config
from logger import log_interface

def get_driver(ads_id, proxy=None, clean_cookies=False):

    config, accounts = get_config()
    print(config)
    if proxy is not None:
        json_proxy = {
            "proxy_soft": "other",
            "proxy_type": "http",
            "proxy_host": proxy.split("@")[1].split(":")[0],
            "proxy_port": proxy.split("@")[1].split(":")[1],
            "proxy_user": proxy.split("@")[0].split(":")[0],
            "proxy_password": proxy.split("@")[0].split(":")[1]
        }
        headers = {
            "content-type": "application/json",
        }
        body = {
            "user_id": ads_id,
            "user_proxy_config": json_proxy,
            "cookie": []
        }
        print("Changing proxy settings", requests.post(
            f"http://local.adspower.net:{config.get('ADS_PORT')}/api/v1/user/update?user_id={ads_id}",
            data=json.dumps(body), headers=headers).text)
    open_url = f"http://local.adspower.net:{config.get('ADS_PORT')}/api/v1/browser/start?user_id=" + ads_id + "&open_tabs=0&ip_tab=0"
    resp = requests.get(open_url).json()
    log_interface(f"ADS RESPONSE: {resp}", "info")

    if resp["code"] != 0:
        log_interface(f"Failed to start session in ADS BROWSER with id: {ads_id}", "error")
        return None

    if "data" not in resp or "webdriver" not in resp["data"] or "ws" not in resp["data"] or "selenium" not in resp["data"]["ws"]:
        log_interface(f"Invalid response structure: {resp}", "error")
        return None

    debugger_address = resp["data"]["ws"]["selenium"]
    if not debugger_address or ":" not in debugger_address:
        log_interface(f"Invalid debugger address for {ads_id}: {debugger_address}", "error")
        return None

    chrome_driver = resp["data"]["webdriver"]
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", debugger_address)
    chrome_options.add_argument("--disable-extensions")
    chrome_service = Service(executable_path=chrome_driver)

    log_interface(f"Starting Chrome driver for AdsPower ID: {ads_id}", "info")

    try:
        driver = webdriver.Chrome(options=chrome_options, service=chrome_service)
        log_interface(f"[ADS] [{ads_id}] - Browser started!", "success")
        if clean_cookies:
            driver.delete_all_cookies()

        return driver

    except Exception as e:
        log_interface(f"Error starting Chrome driver for {ads_id}: {e}", "error")
        return None


def close_driver(ads_id):

    config, accounts = get_config()
    close_url = f"http://local.adspower.net:{config['ADS_PORT']}/api/v1/browser/stop?user_id=" + ads_id
    close_resp = requests.get(close_url).json()
    log_interface(f"Close session response for {ads_id}: {close_resp}", "info")

    if close_resp['code'] != -1:
        log_interface(f"[ADS] [{ads_id}] - Closing browser!", "warn")
        time.sleep(10)
