from flask import Flask, render_template, request, Response, jsonify
import subprocess
import threading
import os
import signal
import queue
import time

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRAPER_PATH = os.path.join(BASE_DIR, "mvp_scraper.py")

# Global state
process = None
process_lock = threading.Lock()
log_queue = queue.Queue()
scraper_running = False

def stream_process(proc):
    global scraper_running
    try:
        for line in iter(proc.stdout.readline, ''):
            if line:
                log_queue.put(line)
        proc.stdout.close()
        proc.wait()
    finally:
        scraper_running = False
        log_queue.put("__DONE__")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/run", methods=["POST"])
def run_scraper():
    global process, scraper_running

    with process_lock:
        if scraper_running:
            return jsonify({"error": "Scraper is already running"}), 400

        data = request.json
        cmd = ["python", SCRAPER_PATH]

        if data.get("submit"):      cmd.append("--submit")
        if data.get("force_apply"): cmd.append("--force-apply")
        if data.get("no_gemini"):   cmd.append("--no-gemini")
        if data.get("clear_ids"):   cmd.append("--clear-ids")
        if data.get("debug_form"):  cmd.append("--debug-form")

        if data.get("limit"):
            cmd += ["--limit", str(data["limit"])]
        if data.get("timeframe"):
            cmd += ["--timeframe", data["timeframe"]]
        if data.get("user"):
            cmd += ["--user", data["user"]]

        # Drain leftover queue items from previous run
        while not log_queue.empty():
            try: log_queue.get_nowait()
            except: break

        try:
            env = os.environ.copy()
            env["DISPLAY"] = ":0"

            # Ensure Termux:X11 is running
            x11_check = subprocess.run(
                ["pgrep", "-f", "termux.x11"],
                capture_output=True, text=True
            )
            if not x11_check.stdout.strip():
                subprocess.Popen(
                    ["termux-x11", ":0"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(2)

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=BASE_DIR,
                env=env
            )
            scraper_running = True
            t = threading.Thread(target=stream_process, args=(process,), daemon=True)
            t.start()
            return jsonify({"status": "started", "pid": process.pid})
        except Exception as e:
            scraper_running = False
            return jsonify({"error": str(e)}), 500

@app.route("/stop", methods=["POST"])
def stop_scraper():
    global process, scraper_running
    with process_lock:
        if process and scraper_running:
            try:
                os.kill(process.pid, signal.SIGTERM)
                scraper_running = False
                log_queue.put("[AutoApply] Scraper stopped by user.\n")
                return jsonify({"status": "stopped"})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        return jsonify({"status": "not_running"})

@app.route("/status")
def status():
    return jsonify({"running": scraper_running})

@app.route("/logs")
def logs():
    def generate():
        while True:
            try:
                line = log_queue.get(timeout=30)
                if line == "__DONE__":
                    yield f"data: __DONE__\n\n"
                    break
                yield f"data: {line.rstrip()}\n\n"
            except queue.Empty:
                yield f"data: __PING__\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
