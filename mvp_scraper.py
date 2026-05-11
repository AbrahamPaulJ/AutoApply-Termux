import os
import re
import time
import argparse
import subprocess
import threading
import http.server
import json
import socket
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

os.environ["DISPLAY"] = ":0"

PROFILE_PATH = "/data/data/com.termux/files/home/.firefox-profiles/seek"
GECKODRIVER = "/data/data/com.termux/files/usr/bin/geckodriver"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_JOBS_FILE = os.path.join(BASE_DIR, "job_ids.txt")

# Args
parser = argparse.ArgumentParser(description="AutoApply - Seek job scraper and auto-applier")
parser.add_argument("--force-apply", action="store_true", help="Apply to first Quick Apply regardless of suitability")
parser.add_argument("--no-gemini", action="store_true", help="Skip all Gemini calls")
parser.add_argument("--limit", type=int, default=None, help="Max number of cards to process")
parser.add_argument("--timeframe", type=str, default=".*", help="Regex for posted time e.g. '^\\d+[mh]$'")
parser.add_argument("--user", type=str, default="abraham", help="User profile to use")
parser.add_argument("--submit", action="store_true", help="Actually submit the application")
parser.add_argument("--clear-ids", action="store_true", help="Clear processed job IDs before running")
parser.add_argument("--debug-form", action="store_true", help="Save form HTML to debug_form.html")
args = parser.parse_args()

if args.clear_ids and os.path.exists(PROCESSED_JOBS_FILE):
    os.remove(PROCESSED_JOBS_FILE)
    print("🗑 Cleared job IDs.")

TIMEFRAME = re.compile(args.timeframe)
USER = args.user
JSONCV_DIR = os.path.join(BASE_DIR, "jsoncv")
MYCV_DIR = os.path.join(BASE_DIR, "Users", USER, "mycv")
os.makedirs(MYCV_DIR, exist_ok=True)

def init_driver():
    service = Service(executable_path=GECKODRIVER)
    options = Options()
    options.add_argument("-profile")
    options.add_argument(PROFILE_PATH)
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")
    driver = webdriver.Firefox(service=service, options=options)
    driver.set_window_size(1920, 1080)
    driver.set_page_load_timeout(15)
    return driver

def load_processed_ids():
    if os.path.exists(PROCESSED_JOBS_FILE):
        with open(PROCESSED_JOBS_FILE, "r") as f:
            return set(line.strip() for line in f)
    return set()

def save_job_id(job_id):
    with open(PROCESSED_JOBS_FILE, "a") as f:
        f.write(f"{job_id}\n")

def get_text(driver, css, wait, fallback=""):
    try:
        el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, css)))
        return el.text.strip()
    except:
        return fallback

def generate_resume(job_id, title, raw_html):
    from gemini import call_gemini
    from utils import get_user_field

    print("  Generating tailored resume JSON...")
    resume_path = os.path.join(BASE_DIR, "Users", USER, "resume.txt")
    with open(resume_path, "r", encoding="utf-8") as f:
        json_resume = f.read()

    template = get_user_field(USER, "resume_prompt")
    prompt = template.format(
        json_resume=json_resume,
        job_title=title,
        raw_html=raw_html[:3000]
    )

    result = call_gemini(prompt)
    cleaned = result.replace("```json", "").replace("```", "").strip()
    resume_json = json.loads(cleaned)

    json_path = os.path.join(BASE_DIR, "Users", USER, "resume_tailored.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resume_json, f, indent=2)
    print("  Resume JSON saved.")

    print("  Building resume HTML...")
    env = os.environ.copy()
    env["DATA_FILENAME"] = json_path
    env["OUT_DIR"] = MYCV_DIR
    env["PATH"] = os.path.join(JSONCV_DIR, "node_modules/.bin") + ":" + env.get("PATH", "")
    subprocess.run(
        ["node", os.path.join(JSONCV_DIR, "node_modules/vite/bin/vite.js"), "build"],
        cwd=JSONCV_DIR, env=env, check=True
    )
    print("  Resume HTML built.")

    print("  Generating PDF...")
    orig_dir = os.getcwd()
    os.chdir(MYCV_DIR)

    class ReusableTCPServer(http.server.HTTPServer):
        allow_reuse_address = True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    server = ReusableTCPServer(("", port), http.server.SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    filename = re.sub(r'[\\/*?:"<>| ]', '_', f"{title[:20]}_{job_id}.pdf")
    pdf_path = os.path.join(MYCV_DIR, filename)

    subprocess.run([
        "chromium-browser", "--headless", "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        f"http://localhost:{port}/index.html"
    ], check=True)

    server.shutdown()
    os.chdir(orig_dir)
    print(f"  PDF ready: {pdf_path}")
    return pdf_path

def handle_quick_apply(driver, wait, job_id, title, advertiser, raw_html):
    print("  Opening Quick Apply form...")
    try:
        apply_btn = driver.find_element(By.CSS_SELECTOR, "[data-automation='job-detail-apply']")
        apply_btn.click()
        time.sleep(2)

        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            print(f"  Switched to new tab: {driver.current_url}")

        new_wait = WebDriverWait(driver, 10)
        long_wait = WebDriverWait(driver, 15)

        # Generate resume PDF
        if not args.no_gemini:
            pdf_path = generate_resume(job_id, title, raw_html)
        else:
            existing_pdfs = [f for f in os.listdir(MYCV_DIR) if f.endswith(".pdf")]
            if existing_pdfs:
                pdf_path = os.path.join(MYCV_DIR, existing_pdfs[0])
            else:
                pdf_path = os.path.join(MYCV_DIR, "test.pdf")
            print(f"  --no-gemini: using existing PDF: {pdf_path}")

        # --- Resume section ---
        try:
            dropdown = new_wait.until(EC.presence_of_element_located(
                (By.XPATH, "//select[@data-testid='select-input']")
            ))
            Select(dropdown).select_by_index(1)
            delete_btn = new_wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//button[@id='deleteResume']")
            ))
            delete_btn.click()
            confirm_btn = new_wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//button[@data-testid='delete-confirmation']")
            ))
            confirm_btn.click()
            print("  Existing resume deleted.")
            time.sleep(2)
        except Exception as e:
            print(f"  No existing resume to delete: {e}")

        # Select upload radio
        try:
            upload_radio = long_wait.until(EC.presence_of_element_located(
                (By.XPATH, "//input[@data-testid='resume-method-upload']")
            ))
            driver.execute_script("arguments[0].click();", upload_radio)
            time.sleep(1)
            print("  Upload radio selected.")
        except Exception as e:
            print(f"  Upload radio not found: {e}")

        # Upload PDF
        try:
            file_input = long_wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[@data-testid='resumeFileInput']/input[@id='resume-fileFile']")
            ))
            file_input.send_keys(pdf_path)
            print("  Resume uploaded.")
            time.sleep(2)
        except Exception as e:
            print(f"  Error uploading resume: {e}")

        # --- Cover letter ---
        if not args.no_gemini:
            print("  Generating cover letter...")
            from gemini import gen_cover_letter
            cover_letter, _ = gen_cover_letter(USER, job_id, title, advertiser, raw_html)
        else:
            cover_letter = "I am interested in this position and believe my experience makes me a strong candidate."
            print("  --no-gemini: using placeholder cover letter.")

        try:
            cl_radio = new_wait.until(EC.presence_of_element_located(
                (By.XPATH, "//input[@type='radio' and @data-testid='coverLetter-method-change']")
            ))
            driver.execute_script("arguments[0].click();", cl_radio)
            time.sleep(1)

            cl_textarea = new_wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//textarea[@data-testid='coverLetterTextInput']")
            ))
            cl_textarea.clear()
            cl_textarea.send_keys(cover_letter)
            print("  Cover letter filled.")
        except Exception as e:
            print(f"  Error filling cover letter: {e}")

        # --- Continue (first click) ---
        try:
            cont_btn = new_wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//button[@data-testid='continue-button']")
            ))
            cont_btn.click()
            time.sleep(2)
            print("  Clicked Continue.")
        except Exception as e:
            print(f"  Error clicking Continue: {e}")

        # --- Continue (second click) then check for Q&A ---
        try:
            cont_btn = new_wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//button[@data-testid='continue-button']")
            ))
            cont_btn.click()
            time.sleep(2)
            print("  Clicked Continue again.")

            # Check if career history page — Q&A bypassed
            try:
                career_history = driver.find_element(By.XPATH, "//h3[text()='Career history']")
                if career_history.is_displayed():
                    print("  Bypassed Q&A, on Career History page.")
            except:
                # Q&A page — get form and answer
                try:
                    form = driver.find_element(By.XPATH, "//form")
                    form_html = form.get_attribute("innerHTML")

                    if args.debug_form:
                        with open(os.path.join(BASE_DIR, "debug_form.html"), "w", encoding="utf-8") as f:
                            f.write(form_html)
                        print("  Form HTML saved to debug_form.html")

                    if not args.no_gemini:
                        from gemini import get_question_actions
                        print("  Extracting and answering questions...")
                        actions = get_question_actions(USER, form_html)
                        print(f"  {len(actions)} questions found.")

                        for act in actions:
                            try:
                                print(f"  Answering: {act['question']} → {act.get('chosen_label', act.get('value'))}")
                                el = WebDriverWait(driver, 5).until(
                                    EC.presence_of_element_located((By.XPATH, act["xpath"]))
                                )
                                if act["action"] == "select_option":
                                    Select(el).select_by_visible_text(act["chosen_label"])
                                elif act["action"] == "fill":
                                    el.clear()
                                    el.send_keys(act["value"])
                                elif act["action"] == "check":
                                    if not el.is_selected():
                                        driver.execute_script("arguments[0].click();", el)
                                elif act["action"] == "choose_radio":
                                    driver.execute_script("arguments[0].click();", el)
                                print(f"  ✔ Done")
                            except Exception as e:
                                print(f"  ❌ Failed: {act['question']} — {e}")

                        # Click Continue after answering
                        try:
                            cont_btn = new_wait.until(EC.presence_of_element_located(
                                (By.XPATH, "//button[@data-testid='continue-button']")
                            ))
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cont_btn)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", cont_btn)
                            time.sleep(2)
                            print("  Clicked Continue after Q&A.")
                        except:
                            print("  No continue after Q&A, likely on submit page.")

                        # Click Continue again (skills page)
                        try:
                            cont_btn = new_wait.until(EC.presence_of_element_located(
                                (By.XPATH, "//button[@data-testid='continue-button']")
                            ))
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cont_btn)
                            time.sleep(1)
                            driver.execute_script("arguments[0].click();", cont_btn)
                            time.sleep(2)
                            print("  Clicked Continue past skills page.")
                        except:
                            print("  No skills page continue, likely on submit page.")

                    else:
                        print("  --no-gemini: skipping question answering.")

                except Exception as e:
                    print(f"  Error getting form: {e}")

        except:
            pass

        # --- Privacy checkbox ---
        try:
            privacy = new_wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//input[@type='checkbox' and contains(@id,'privacyPolicy')]")
            ))
            if not privacy.is_selected():
                privacy.click()
            print("  Privacy checkbox checked.")
        except:
            print("  No privacy checkbox found.")

        # --- Submit ---
        if args.submit:
            from gemini import send_telegram_message
            submit_btn = new_wait.until(EC.visibility_of_element_located(
                (By.XPATH, "//button[@data-testid='review-submit-application']")
            ))
            submit_btn.click()
            print(f"  ✅ Applied to: {title} @ {advertiser}")
            send_telegram_message(USER, f"🎉 Applied!\n{title} @ {advertiser}")
        else:
            print("  --submit not set, skipping final submit.")
            input("  [DEBUG] Review the form then press Enter to close...")

        driver.close()
        driver.switch_to.window(driver.window_handles[0])

    except Exception as e:
        print(f"  Error in Quick Apply: {e}")
        import traceback
        traceback.print_exc()
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])

def scrape_jobs(driver):
    from utils import get_user_field
    from gemini import is_suitable, send_telegram_message

    jobs_url = get_user_field(USER, "filter")
    driver.get(jobs_url)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='job-card']")))

    job_cards = driver.find_elements(By.CSS_SELECTOR, "[data-testid='job-card']")
    print(f"\nFound {len(job_cards)} job cards")

    processed_ids = load_processed_ids()
    new_count = skipped_processed = skipped_old = 0
    force_apply_done = False

    cards_to_process = job_cards[:args.limit] if args.limit else job_cards

    for card in cards_to_process:
        try:
            job_id = card.get_attribute("data-job-id")

            if job_id and job_id in processed_ids:
                skipped_processed += 1
                print(f"⏭ Already processed | {job_id}")
                continue

            if job_id:
                save_job_id(job_id)
                processed_ids.add(job_id)

            # Check timeframe
            try:
                time_badge = card.find_element(
                    By.CSS_SELECTOR, "[data-automation='jobListingDate']"
                ).text.strip()
                if not TIMEFRAME.match(time_badge):
                    skipped_old += 1
                    print(f"⏰ Too old ({time_badge}) | skipping")
                    continue
            except:
                skipped_old += 1
                continue

            title = card.find_element(By.CSS_SELECTOR, "[data-automation='jobTitle']").text

            driver.execute_script("arguments[0].click();", card)
            time.sleep(1.5)

            # Detect Quick Apply
            try:
                wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-automation='job-detail-apply']")
                ))
                apply_btn = driver.find_element(By.CSS_SELECTOR, "[data-automation='job-detail-apply']")
                btn_text = apply_btn.text.strip().lower()
                is_quick = "quick apply" in btn_text
            except:
                is_quick = False

            apply_type = "✅ Quick Apply" if is_quick else "— Standard Apply"
            print(f"\n{apply_type} | {title}")

            if not is_quick:
                continue

            # Extract details
            advertiser = get_text(driver, "[data-automation='advertiser-name']", wait)
            job_type = get_text(driver, "[data-automation='job-detail-classifications']", wait)
            location = get_text(driver, "[data-automation='job-detail-location']", wait)
            work_type = get_text(driver, "[data-automation='job-detail-work-type']", wait)

            try:
                raw_html = driver.find_element(
                    By.CSS_SELECTOR, "[data-automation='jobAdDetails']"
                ).get_attribute("innerHTML")
            except:
                raw_html = ""

            print(f"  Advertiser : {advertiser}")
            print(f"  Location   : {location}")
            print(f"  Work type  : {work_type}")

            # Force apply
            if args.force_apply and not force_apply_done:
                print("  --force-apply: skipping suitability check")
                handle_quick_apply(driver, wait, job_id, title, advertiser, raw_html)
                force_apply_done = True
                continue

            # Suitability check
            if not args.no_gemini:
                print("  Checking suitability...")
                result = is_suitable(USER, title, advertiser, job_type, location, work_type, raw_html)
                suitable = result.get("suitable", False)
                reason = result.get("reason", "")
                confidence = result.get("confidence", 0)

                if suitable:
                    print(f"  ✅ Suitable ({confidence}%) — {reason}")
                    send_telegram_message(USER, f"✅ Suitable ({confidence}%)\n{title} @ {advertiser}\n{reason}")
                    handle_quick_apply(driver, wait, job_id, title, advertiser, raw_html)
                else:
                    print(f"  ❌ Not suitable ({confidence}%) — {reason}")
                    send_telegram_message(USER, f"❌ Not suitable ({confidence}%)\n{title} @ {advertiser}\n{reason}")
            else:
                print("  --no-gemini: skipping suitability check")

            new_count += 1

        except Exception as e:
            print(f"Error reading card: {e}")

    print(f"\nSummary: {new_count} new | {skipped_processed} already processed | {skipped_old} too old")

driver = init_driver()
try:
    scrape_jobs(driver)
    input("\nDone. Press Enter to quit...")
finally:
    driver.quit()