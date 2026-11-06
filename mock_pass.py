import argparse, time, math, socket, random
import os
from datetime import datetime, timezone

#starts the parser
parser = argparse.ArgumentParser(description="My Script")

# arguments which can be modified by input
parser.add_argument("--port", type=int, default=8200)
parser.add_argument("--host", type=str, default="127.0.0.1")
parser.add_argument("--aos-delay", type=float, default=2.0)
parser.add_argument("--los-delay", type=float, default=20.0)
parser.add_argument("--time-scale", type=float, default=30.0)
parser.add_argument("--max-elev", type=float, default=45.0)
parser.add_argument("--min-elev", type=float, default=5.0)
parser.add_argument("--latency-ms", type=float, default=100.0)
parser.add_argument("--jitter-ms", type=float, default=20.0)
parser.add_argument("--drop-rate", type=float, default=0.0)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--log", type=str, default="mock_pass.log")
parser.add_argument("--once", action="store_true")

#takes what the user typed in
args = parser.parse_args()

# connects the port to 8200 unless it was changed to sth different by the user
port = args.port
host = args.host


server_start = time.time()      #has the time when server switdched on

file_address = os.path.dirname(os.path.abspath(__file__))  #saves the adress of this file so it can save the .log file into the same place, because otherwise it appeared in a random C: directory

#this function checks the state of the satelite and the command sent and received
def st(cmd):
    real_now = time.time()       #takes current time
    aos_delay = args.aos_delay      #all of these take the variables from the parser
    time_scale = args.time_scale
    los_delay = args.los_delay
    max_elev = args.max_elev
    min_elev = args.min_elev

    t_sim = round((real_now - server_start - aos_delay) * time_scale, 1) #time since AOS
    duration_sim = (los_delay - aos_delay) * time_scale


    if t_sim<0:                 #checks where the satellite is rn
        state = "PRE"
        elev_deg = 0.0
    elif 0<=t_sim<=duration_sim:
        state = "IN_PASS"
        elev_deg = round(max_elev*math.sin(math.pi*t_sim/duration_sim),1)
    else:
        state = "POST"
        elev_deg = 0.0


    #rx(received) = cmd, tx(sent) = answer
    if cmd == "PASS?\r":        #checks the commands from user
        answer = f'PASS {state} {elev_deg} {t_sim}\r'
    elif state!="IN_PASS" or elev_deg<min_elev:
        answer="ERR+NOLINK\r"
    elif cmd == "ES+R2200\r":
        answer = "OK+A001031A2B\r"
    elif cmd == "ES+R2301\r":
        answer = "OK+1A2B00030102030405060708090A0B0C0D0E0F10\r"
    else:
        answer = "ERR\r"

    return answer, elev_deg, state, t_sim

def log(t_sim, state, elev_deg, rx, tx, dropped):  #used to log the data  into separate .log file
    now = datetime.now(timezone.utc).isoformat()
    rx = rx.strip("\r")
    tx = tx.strip("\r")
    f = os.path.join(file_address, args.log)   #to make the .log file save into the same place as this .py file
    event = f"{now}|| t_sim = {t_sim}|| state = {state}|| elevation = {elev_deg}|| RX = {rx}|| TX = {tx}|| dropped = {dropped}\n"
    if f:
        with open(f, "a") as f:
            f.write(event)
    print(event, end="")

#creates a socket for communication (af_inet is for ipv4, sockstream is for tcp)
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((host, port))   #binds the socket to the right port and adress
s.listen(1)  #takes only 1 user for waiting??

while True: # runs once if (--once) is set to True, waits for more users if its set to False
    c, addr = s.accept()  #after the other file connects, c will be a socket for it, addr will be its ip adress
    random.seed(args.seed)
    while True: #sees if the returned command isnt empty
        data = c.recv(1024)
        if not data:
            c.close() #if no data is received it closes the communication socket
            break
        data = data.decode("ascii")
        ans, elev_deg, state, t_sim = st(data)
        ans_enc = ans.encode("ascii")
        p = random.random()  #chance that package will be lost, in range (0,1)
        if data=="PASS?\r":
            time.sleep(0)
            c.sendall(ans_enc)
            log(t_sim, state, elev_deg, data, ans, "NO")
        else:
            if p > args.drop_rate:
                sec = (random.uniform(-args.jitter_ms, args.jitter_ms) + args.latency_ms)/1000
                time.sleep(sec)
                c.sendall(ans_enc)
                log(t_sim, state, elev_deg, data, ans, "NO")

            else:
                log(t_sim, state, elev_deg, data, "dropped\r",  "YES")
                continue
    if args.once:
        break
s.close()

