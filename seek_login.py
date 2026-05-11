from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
import os

os.environ["DISPLAY"] = ":0"

service = Service("/data/data/com.termux/files/usr/bin/geckodriver")
options = Options()
options.add_argument("-profile")
options.add_argument("/data/data/com.termux/files/home/.firefox-profiles/seek")

driver = webdriver.Firefox(service=service, options=options)
driver.get("https://www.seek.com.au/login")

input("Log in manually in X11 window, then press Enter to save and quit...")
driver.quit()
print("Session saved.")