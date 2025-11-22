import signal
import time
import sys
import os

def on_sighup(signum, frame):
    now = time.time()
    readable_time = time.ctime(now)
    print(f"\n[Alert] SIGHUP signal received at: {readable_time}")

def on_sigint(signum, frame):
    print("\n[Alert] You pressed CTRL+C! Press CTRL+\\ to actually exit.")

def on_sigquit(signum, frame):
    print("\n[Alert] SIGQUIT received. Good bye!")
    sys.exit(0)

if __name__ == "__main__":
    my_pid = os.getpid()
    print(f"Program Running. PID is: {my_pid}")
    print("Try pressing CTRL+C or CTRL+\\")
    print(f"To test SIGHUP, open a new terminal and type: kill -HUP {my_pid}")

    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGQUIT, on_sigquit)
    signal.signal(signal.SIGHUP, on_sighup)
    while True:
        time.sleep(1)