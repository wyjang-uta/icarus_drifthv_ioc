###############################################################################
# Script authors:
#       Hector Carranza Jr. (hector.carranza@mavs.uta.edu)
#       and Wooyoung Jang (wooyoung.jang@uta.edu)
#               University of Texas at Arlington
#
#    This script extract UPS status variables from UPS SSH service
#  using paramiko Python module (version 2 of this script.) or wexpect
#  subprocess spawning module to open a persistent SSH session.
#  Based on the extracted status values, it makes log file and also when
#  the status goes alarm status, it counts alarms of adjacent timestamps
#  and when it exceeds 5 times, the script sends ramp-down signal.
#
# History:
#  Nov.  8. 2024 (version 3.1)
#      Nov. 7. 2024, it was found that the script may unexpectedly terminate
#      if network instability occur for a short period of time. We added 
#      delay feature in the create_ssh_session() function to prevent this
#      kinds of situation.
#  Apr. 25. 2023 (version 3)
#       paramiko closes ssh connection everytime it gets result from a
#      single command finished. So we are switching it to use
#      wexpect which is a module spawning child process to create a
#      persistent ssh session to the UPS ssh server.
#  Apr.  5. 2023 (minor bugfix)
#       Fixed a mistake that time information in the error output 
#      was not printed correctly.
#       This was due to missing arguments in print error statement.
#  Mar. 26. 2023 (minor change)
#       exception handling code will now generate an error log file.
#  Mar. 19. 2023 (version 2)
#       Data extraction implemented based on SSH communication
#       via paramiko.
#
#  Mar. 28. 2022
#       First commit of test version. The program runs on 
#   Windows OS. (HV laptop)
#
###############################################################################

import curses
from collections import deque
import datetime
#from epics import PV
from decimal import Decimal
import random
import re
import sys
import time
import wexpect

#=====================================================================================================

SSH_HOST = '192.168.185.10'
SSH_USER = 'apc'
SSH_PASS = 'icarus'
SSH_PROMPT = 'apc>'
DETSTATUS_CMD = 'detstatus -all'

POLLING_INTERVAL = 5
CONNECT_RETRIES = 30
CONNECT_DELAY = 10
EXPECT_TIMEOUT = 15

# ===================[ SSH Utility Function ]======================
def create_ssh_session(hostname, username, password, retries = CONNECT_RETRIES, base_delay = CONNECT_DELAY):
    """
    Create a single SSH session. Retry when failed or closed connection.
    """
    now = datetime.datetime.now()
    for attempt in range(1, retries + 1):
        try:
            ssh_cmd = (
                f'ssh '
                f'-o BatchMode=no '
                f'-o ServerAliveInterval=30 '
                f'-o ServerAliveCountMax=3 '
                f'{username}@{hostname}'
            )
            # Create an SSH session using wexpect
            print(f'[SSH {now:%m/%d/%Y %H:%M:%S}] Connecting ({attempt}/{retries}) → {ssh_cmd}')
            ssh_session = wexpect.spawn(ssh_cmd, maxread=65535, timeout=EXPECT_TIMEOUT)

            i = ssh_session.expect([r"yes/no", rf"{username}@{hostname}'s password: ", SSH_PROMPT, wexpect.EOF, wexpect.TIMEOUT])
            if i == 0:
                ssh_session.sendline("yes")
                i = ssh_session.expect([rf"{username}@{hostname}'s password: ", SSH_PROMPT, wexpect.EOF, wexpect.TIMEOUT])
            if i == 1:
                ssh_session.sendline(password)
                ssh_session.expect(SSH_PROMPT)
            elif i == 2:
                pass
            else:
                raise RuntimeError("[SSH {now:%m/%d/%Y %H:%M:%S}] handshake failed (EOF/TIMEOUT)")

            ssh_session.sendline("") # match the prompt sync
            ssh_session.expect(SSH_PROMPT)
            print(f'[SSH {now:%m/%d/%Y %H:%M:%S}] Connected & prompt ready.')
            return ssh_session
        
        except Exception as e:
            delay = base_delay * (2 ** (attempt -1 ))
            print(f'[SSH {now:%m/%d/%Y %H:%M:%S}] Connect failed: {e} - retry in {delay}s', file=sys.stderr)
            time.sleep(delay)

    raise RuntimeError('[SSH {now:%m/%d/%Y %H:%M:%S}] Exceeded SSH connection retries')

def is_session_alive(session):
    try:
        return (session is not None) and (not session.closed) and session.isalive()
    except Exception:
        return False

def ensure_prompt(session):
    session.sendline("")
    session.expect(SSH_PROMPT, timeout=EXPECT_TIMEOUT)

def execute_command(session, cmd, prompt=SSH_PROMPT, timeout=EXPECT_TIMEOUT):
    session.sendline(cmd)
    session.expect(prompt, timeout=timeout)
    return session.before

# ============= [Parsing Utility Functions] ================
def _extract(regex, text, group=1, default=None, flags=0):
    m = re.search(regex, text, flags)
    return m.group(group) if m else default

def parse_detstatus(output):
    return {
        "cmd_status":      _extract(r'E000:\s*(\w+)', output) == 'Success',
        "ups_online":      _extract(r'Status of UPS:\s*(\w+)', output) == 'Online',
        "last_transfer":   _extract(r'Last Transfer:\s*(\w+)', output),
        "input_status":    _extract(r'Input Status:\s*(\w+)', output),
        "batt_replace_dt": _extract(r'Next Battery Replacement Date:\s*(\d{2}/\d{2}/\d{4})', output),
        "batt_soc":        _extract(r'Battery State Of Charge:\s*([0-9.]+)\s*%', output),
        "out_voltage":     _extract(r'Output Voltage:\s*([0-9.]+)\s*VAC', output),
        "out_freq":        _extract(r'Output Frequency:\s*([0-9.]+)\s*Hz', output),
        "out_watts_pct":   _extract(r'Output Watts Percent:\s*([0-9.]+)\s*%', output),
        "out_va_pct":      _extract(r'Output VA Percent:\s*([0-9.]+)\s*%', output),
        "out_current":     _extract(r'Output Current:\s*([0-9.]+)\s*A', output),
        "out_eff":         _extract(r'Output Efficiency:\s*([\w ]+)', output),
        "out_energy":      _extract(r'Output Energy:\s*([0-9.]+)\s*kWh', output),
        "in_voltage":      _extract(r'Input Voltage:\s*([0-9.]+)\s*VAC', output),
        "in_freq":         _extract(r'Input Frequency:\s*([0-9.]+)\s*Hz', output),
        "batt_voltage":    _extract(r'Battery Voltage:\s*([0-9.]+)\s*VDC', output),
        "batt_temp_c":     _extract(r'Battery Temperature:\s*([0-9.]+)\s*C,\s*([0-9.]+)\s*F', output, group=1),
        "batt_temp_f":     _extract(r'Battery Temperature:\s*([0-9.]+)\s*C,\s*([0-9.]+)\s*F', output, group=2),
    }


#============================== [ Main function ] =============================================================

def main():

    ## To do's in main function
    # 1. connect ssh
    # 2. start while True loop.
    # 3. 
    polling_interval = 5   # unit in seconds
    alarm_counter = 0

    ssh_hostname = '192.168.185.10'
    ssh_username = 'apc'
    ssh_password = 'icarus'
    ssh_detstatus_cmd = 'detstatus -all'
    ssh_session = None

    # EPICS HV AC Input
    #ups_acinput_status = PV('icarus_cathodehv_ups/acinput')

    print("Starting ICARUS Drift HV UPS status monitoring...\n")
    print(f'Polling interval: {polling_interval} secs')
    print(f'Actual monitoring time interval: ~{2*polling_interval} secs')
    print(f'UPS Host: {ssh_hostname}')
    print("Initializing upsstatus.afd file...")
    ups_status_file = open("upsstatus.afd", "w")
    ups_status_file.write("0\n")
    ups_status_file.close()
    print('DONE')

    ssh_session = create_ssh_session(SSH_HOST, SSH_USER, SSH_PASS)

    # The main loop
    try:
        while True:
            now = datetime.datetime.now()
            today_tag = datetime.date.today().strftime('%Y%m%d')

            if not is_session_alive(ssh_session):
                print('[SSH {now:%m/%d/%Y %H:%M:%S}] Session dead. Reconnecting...', file=sys.stderr)
                ssh_session = create_ssh_session(SSH_HOST, SSH_USER, SSH_PASS)

            try:
                ensure_prompt(ssh_session)
                output = execute_command(ssh_session, DETSTATUS_CMD)
                
                parsed = parse_detstatus(output)
                in_voltage_str = parsed["in_voltage"] or "0"
                in_freq_str = parsed["in_freq"] or "0"
                batt_soc = parsed["batt_soc"] or "0"

                # console log
                print(f'[UPS {now:%m/%d/%Y %H:%M:%S}] '
                      f'Network: {"Online" if is_session_alive(ssh_session) else "Offline"} '
                      f'ACinput: {in_voltage_str} VAC '
                      f'Battery: {batt_soc} %')
                # file log
                with open(f"upsstatus_v3_{today_tag}.txt", "a") as flog:
                    flog.write(f"{in_voltage_str} VAC @ {in_freq_str} Hz\t {batt_soc} %% {now:%m/%d/%Y}\t{now:%H:%M:%S}\n")

                ## ramp-down determination code must be placed here.

                time.sleep(POLLING_INTERVAL)

            except wexpect.wexpect_util.EOF:
                print('[SSH] EOF from remote. Will reconnect.', file=sys.stderr)
                try:
                    session.close()
                except Exception:
                    pass
                session = None
                time.sleep(2)

            except wexpect.wexpect_util.TIMEOUT:
                print('[SSH] TIMEOUT waiting for prompt/output. Will try to resync.', file=sys.stderr)
                # Try resync one time and then retry in the next loop
                try:
                    ensure_prompt(ssh_session)
                except Exception:
                    # When resync failed, try reconnect
                    try:
                        ssh_session.close()
                    except Exception:
                        pass
                    ssh_session = None
                    time.sleep(2)
            
            except KeyboardInterrupt:
                print('Stopping monitoring (Ctrl-C).')
                break

            except Exception as e:
                print(f'[ERR] Unexpected error: {e}', file=sys.stderr)
                # Try a safe reconnect
                try:
                    ssh_session.close()
                except Exception:
                    pass
                ssh_session = None
                time.sleep(2)
                
    finally:
        if ssh_session and not ssh_session.closed:
            try:
                ssh_session.close()
            except Exception:
                pass
        print('SSH session closed.')
        print('End of program')

if __name__ == "__main__":
    main()

