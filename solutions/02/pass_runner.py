import argparse, json, sys, socket, time, logging
from datetime import datetime, timezone
from collections import Counter

parser = argparse.ArgumentParser(description="My Script")

# arguments which can be modified by input
parser.add_argument("--port", type=int, default=8200)
parser.add_argument("--host", type=str, default="127.0.0.1")
parser.add_argument("--plan", type=str, default="fixtures/pass_plan.json")
parser.add_argument("--operator", type=str, default="Jan Kowalski")
parser.add_argument("--log", type=str, default="pass.log")
parser.add_argument("--report-json", type=str, default="pass_report.json")
parser.add_argument("--report-md", type=str, default="pass_report.md")
parser.add_argument("--start-timeout", type=float, default=30.0)
parser.add_argument("--poll-ms", type = float, default = 100.0)

#takes what the user typed in
args = parser.parse_args()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(args.log, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

# connects the port to 8200 unless it was changed to sth different by the user
port = args.port
host = args.host

global status, parts2

#this one receives the message from the satellite and converts it to a string after finding "\r"
def recv_l(sock):
    st = b""
    while True:
        sck = sock.recv(1024)
        st += sck
        if b"\r" in st:
            return st.decode("ascii").strip()

#saves the reason for abort and inputs it into .md and .json files, closes socket and returns exit code 2
def abort(reason):
    logging.error(f"ABORT: {reason}")
    print(f"ABORT: {reason}", file=sys.stderr)
    save_reports("ABORT", 2, reason=reason)
    try:
        s.close()
    except Exception:
        pass
    sys.exit(2)

#if an activity fails, code ends with code 1 and it is recorded in the json report and .md report too, also closes the socket
def fail(reason):
    logging.error(f"FAIL: {reason}")
    print(f"FAIL: {reason}", file=sys.stderr)
    save_reports("FAIL", 1, reason=reason)
    try:
        s.close()
    except Exception:
        pass
    sys.exit(1)


#saves each report to both files (.json and .md)
def save_reports(result_status, exit_code, reason=None, sim_duration=0.0):
    ended_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    acts = report if "report" in globals() else []
    #makes the .json report
    report_data = {
        "pass_id": plan.get("pass_id") if "plan" in globals() else None,
        "satellite": plan.get("satellite") if "plan" in globals() else None,
        "station": plan.get("station") if "plan" in globals() else None,
        "operator": args.operator,
        "started_utc": started_utc_str if "started_utc_str" in globals() else ended_utc,
        "ended_utc": ended_utc,
        "result": result_status,
        "exit_code": exit_code,
        "reason": reason,
        "min_elev_deg": min_elev_deg if "min_elev_deg" in globals() else None,
        "sim_duration_s": sim_duration,
        "activities": acts,
        "summary": {
            "planned": len(act) if "act" in globals() else 0,
            "ok": sum(1 for a in acts if a.get("status") == "ok"),
            "warn": sum(1 for a in acts if a.get("status") == "warn"),
            "failed": sum(1 for a in acts if a.get("status") == "failed"),
            "skipped": sum(1 for a in acts if a.get("error") == "SKIPPED_UNSAFE"),
            "aborted": result_status == "ABORT",
        }
    }
    with open(args.report_json, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    # creates the ,md report
    with open(args.report_md, "w", encoding="utf-8") as f2:
        pass_name = plan.get("pass_id") if "plan" in globals() else "Unknown Pass"
        f2.write(f"# Pass Report: {pass_name}\n\n")
        f2.write(f"- **Result**: {result_status}\n")
        f2.write(f"- **Exit Code**: {exit_code}\n")
        if reason:
            f2.write(f"- **Reason**: {reason}\n")
        f2.write(f"- **Operator**: {args.operator}\n")
        f2.write(f"- **Duration**: {sim_duration}s\n\n")

        f2.write("## Activities\n\n")
        if acts:
            f2.write("| ID | Type | Status | Attempts | RTT (ms) |\n")
            f2.write("|---|---|---|---|---|\n")
            for a_rep in acts:
                rtt_str = ", ".join(f"{t:.1f}" for t in a_rep.get("rtt_ms", []))
                f2.write(
                    f"| {a_rep.get('id')} | {a_rep.get('type')} | {a_rep.get('status')} | {a_rep.get('attempts')} | {rtt_str} |\n")
        else:
            f2.write("No activities executed.\n")

        f2.write("\n## Next Steps\n")
        if result_status == "PASS":
            f2.write("Session completed successfully. Telemetry and logs are archived.\n")
        else:
            f2.write(f"Review session logs ({args.log}) and investigate the issue: {reason}.\n")


#1. PREFLIGHT====================================

#load the plan of the pass
with open(args.plan, "r", encoding="utf-8") as f:
    plan = json.load(f)

min_elev_deg = plan.get("min_elev_deg")
act = plan.get("activities")   #contains the separate jsons with planned activities

logging.info(f"Loaded plan {plan.get('pass_id')} for {plan.get('satellite')} with {len(act)} activities")

#checks if elevation is good, if not preflight fails
if min_elev_deg is None or not (0.0 <= min_elev_deg <= 90.0):
    abort("preflight_failed")

ids = []   #for checking if all ids are unique
ats = [-0.1]  #for checking if time is increasing

#checking the other preflight conditions
for bracket in act:
    id = bracket["id"]
    at_s = bracket["at_s"]
    type = bracket["type"]
    timeout_s = bracket["timeout_s"]
    retries = bracket["retries"]

    if id in ids:
        abort("preflight_failed")
    else:
        ids.append(id)

    if at_s <= ats[-1]:
        abort("preflight_failed")
    else:
        ats.append(at_s)

    if type != "ping" and type != "telemetry":
        abort("preflight_failed")

    if timeout_s <= 0.0 or retries < 0:
        abort("preflight_failed")

#makes the socket tcp connection, preflight fails if the connection cannot be made
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    logging.info(f"Connected to satellite mock on {host}:{port}")

    #sends the first command, sends to receiving function and splits into a list
    s.sendall(b"PASS?\r")
    answer = recv_l(s)
    parts = answer.split(" ")

    #check if the received data has the right format and converts str into floats
    if len(parts) != 4 or parts[0] != "PASS":
        abort("preflight_failed")
    if parts[1] not in ("PRE", "IN_PASS", "POST"):
        abort("preflight_failed")

    parts[2] = float(parts[2])
    parts[3] = float(parts[3])

except Exception:
    abort("preflight_failed")


#2. WAITING FOR THE WINDOW ======================================

#asks PASS?, and until elevation and state conditions are satified it keeps waiting
#after conditions are good, the loop breaks and the plan activities can be made
start_time = time.time()
telemetry_ok = True
started_uts = datetime.now(timezone.utc)
started_utc_str = started_uts.strftime("%Y-%m-%dT%H:%M:%SZ")

logging.info("Waiting for pass window...")

while True:
    #checks if the start timeout expired
    if time.time() - start_time > args.start_timeout:
        if not telemetry_ok:
            abort("telemetry_unavailable")
        else:
            abort("window_not_reached")

    #checks if the reply is ok
    try:
        s.settimeout(args.poll_ms / 1000.0 + 1.0)
        s.sendall(b"PASS?\r")
        answer2 = recv_l(s)
        parts2 = answer2.split(" ")
        if len(parts2) != 4 or parts2[0] != "PASS":
            telemetry_ok = False
            time.sleep(args.poll_ms / 1000.0)
            continue

        state = parts2[1]
        elev = float(parts2[2])
        telemetry_ok = True
    except Exception:
        telemetry_ok = False
        time.sleep(args.poll_ms / 1000.0)
        continue

    #aborts if the satelite is below the required elevation
    if state == "POST":
        abort("window_missed")

    if state == "IN_PASS" and elev >= min_elev_deg:
        logging.info(f"Entered pass window: state={state}, elev={elev}° >= {min_elev_deg}°")
        break  #if the conditions are satisfied it breaks the waiting loop and allows the activities to start

    time.sleep(args.poll_ms / 1000.0)


#executed once its in pass, above required elevation
current = float(parts2[3])  #the time when activity is started
report = []  #will have reports from all activites in json format
pass_ended = False

#loops thru activities in the list that is taken from the .json plan
for a in act:
    if not pass_ended:
        required = a.get("required")
        scheduled = float(a.get("at_s"))
        round_times = []   #will store the time it takes to complete every attempt at each activity
        while scheduled > current:  #checks if the time isnt reaching the time specified for an activity. if not, it only asks PASS?. if yes, the while loop breaks and lets the activity happen
            s.sendall(b"PASS?\r")
            answer3 = recv_l(s)
            parts3 = answer3.split(" ")
            current = float(parts3[3])
            if parts3[1] == "POST":   #checks the current status and aborts if its in POST
                if required:
                    abort("los_before_activity")
                else:
                    pass_ended = True
                    break
            time.sleep(args.poll_ms / 1000.0)

        if pass_ended:
            break

        command = a.get("type")
        s.settimeout(float(a.get("timeout_s")))
        total_tries = int(a.get("retries"))+1   #1st try plus the number of retries allowed

        result = False
        answer4 = None
        tries = 0
        for i in range(total_tries):
            tries += 1
            s.sendall(b"PASS?\r")      #asks for initial info
            ans = recv_l(s)
            parts5 = ans.split(" ")
            state = parts5[1]
            if state=="POST":        #aborts if state is POST
                if required:
                    abort("los_before_activity")
                else:
                    pass_ended = True
                    break
            elev = float(parts5[2])
            if pass_ended:
                break

            if state != "IN_PASS" or elev < min_elev_deg:  #aborts if the state or elevation are wrong
                result = "SKIPPED_UNSAFE"
                logging.warning(f"Activity {a.get('id')} skipped: gate closed (state={state}, elev={elev}°)")
                if required:
                    abort("SKIPPED_UNSAFE")
                else:
                    break

            try:               #after all conditions are satisfied, the activities can be attempted
                start = time.perf_counter()
                if command == "telemetry":
                    s.sendall(b"ES+R2301\r")
                elif command == "ping":
                    s.sendall(b"ES+R2200\r")
                answer4 = recv_l(s)
                finish = time.perf_counter()
                rtt = (finish - start) * 1000
                round_times.append(rtt)

                logging.info(f"Activity {a.get('id')} ({command}) attempt {tries}: reply='{answer4}', rtt={rtt:.1f}ms")
                
                if "OK+" in answer4:       #if the satellite answered in the correct way, the checking loop can break and report can be made
                    result = "OK"
                    break
                elif answer4 == "ERR+NOLINK":
                    result = "ERR_NOLINK"
                    logging.warning(f"Activity {a.get('id')} received ERR+NOLINK on attempt {tries}")
                    continue
                else:
                    result = "PROTOCOL_ERR"
                    logging.error(f"Activity {a.get('id')} protocol error: {answer4}")
                    break

            except (socket.timeout, OSError):
                result = "TIMEOUT"
                logging.warning(f"Activity {a.get('id')} timed out on attempt {tries}")
                continue


        if result=="OK":
            status = "ok"
            result = None
        elif required:
            if result == "PROTOCOL_ERR":
                fail("protocol_error")
            else:
                abort(result)
        else:
            status = "warn"

        #an intermediate dictionary with all activities, will be used by the save_reports function to get data
        report_line = {
            "id": a.get("id"),
            "type": command,
            "required": required,
            "planned_at_s": scheduled,
            "started_at_s": current,
            "status": status,
            "attempts": tries,
            "rtt_ms": round_times,
            "response": answer4,
            "error": result}
        report.append(report_line)

    else:
        break

while True:
    s.sendall(b"PASS?\r")
    answer = recv_l(s)
    parts = answer.split(" ")
    if parts[1] == "POST":
        T_S = float(parts[3])
        s.close()
        break
    time.sleep(args.poll_ms / 1000.0)

ended_uts = datetime.now(timezone.utc)
ended_utc_str = ended_uts.strftime("%Y-%m-%dT%H:%M:%SZ")

logging.info(f"Pass session ended normally at T_S={T_S}s")

#save reports and exit with zero (successful)
save_reports("PASS", 0, sim_duration=T_S)
sys.exit(0)

