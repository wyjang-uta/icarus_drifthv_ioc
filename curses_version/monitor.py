# monitor.py
from collections import deque
import curses
import time
import datetime
import wexpect
import sys
from decimal import Decimal

import ssh_connector
import data_parser
import display
import handle
import config

def monitor(stdscr):
    display.init_display(stdscr)

    running = False
    lines = deque()
    alarm_counter = 0
    last_update = time.time()

    ssh_session = ssh_connector.create_ssh_session(
                config.SSH_HOSTNAME,
                config.SSH_USERNAME,
                config.SSH_PASSWORD
            )

    try:
        while True:
            # ==== display menu and contents
            lines = display.render(stdscr, running, lines, alarm_counter)

            # ==== The main monitoring loop
            now = datetime.datetime.now()
            today_tag = datetime.date.today().strftime('%Y%m%d')

            if not ssh_connector.is_session_alive(ssh_session):
                print('[SSH {now:%m/%d/%Y %H:%M:%S}] Session dead. Reconnecting ... ', file=sys.stderr)
                ssh_session = ssh_connector.create_ssh_session(
                            config.SSH_HOSTNAME,
                            config.SSH_USERNAME,
                            config.SSH_PASSWORD
                        )
            if running:
                try:
                    ssh_connector.ensure_prompt(ssh_session)
                    output = ssh_connector.execute_command(ssh_session, config.SSH_DETSTATUS_CMD)

                    parsed = data_parser.parse_detstatus(output)
                    in_voltage_str = parsed["in_voltage"] or "0"
                    in_freq_str = parsed["in_freq"] or "0"
                    batt_soc = parsed["batt_soc"] or "0"

                    # determine ramp down status
                    voltage = Decimal(in_voltage_str)
                    rampdown_trigger = False
                    # uncomment below to send the ramp down trigger to EPICS
                    #ups_acinput_status.put(int(rampdown_trigger))
                    if voltage < 1 and alarm_counter < 3:
                        print(f'Ramp Down Trigger {rampdown_trigger}')
                        alarm_counter += 1
                        print(f'Warning! No ACinput power. Current alarm counter is ({alarm_counter}/{config.ALARM_THRESHOLD})')
                    elif alarm_counter == 3:
                        print(f'Alarm counter reached the threshold ({alarm_counter}/{config.ALARM_THRESHOLD}.')
                        print("Sending EMERGENCY Ramp Down Signal NOW!")
                        # uncomment below to send ramp down trigger to slow control program to activate the emergency ramp down feature
                        #ups_status_file = open("upsstatus.afd", "w")
                        #ups_status_file.write("1\n")
                        #ups_status_file.close()
                        #rampdown_trigger = True
                        #ups_acinput_status.put(int(rampdown_trigger))
                    else:
                        alarm_counter = 0

                    stat_params = {
                            "voltage": in_voltage_str,
                            "net_status": f'{"Online" if ssh_connector.is_session_alive(ssh_session) else "Offline"}',
                            "freq": in_freq_str,
                            "battery_charge": batt_soc,
                            "alarm_counter": alarm_counter,
                            "rampdown_trigger": rampdown_trigger
                            }
                
                    # curses log update
                    display.update(stdscr, stat_params, lines, ssh_session)

                    # console log
                    print(f'[UPS {now:%m/%d/%Y %H:%M:%S}] '
                          f'Network: {"Online" if stat_params['net_status'] else "Offline"} '
                          f'ACinput: {stat_params['voltage']} VAC '
                          f'Battery: {stat_params['battery_charge']} %'
                          f'Alarm counter: {alarm_counter} '
                          f'Ramp down trigger: {"Triggered" if rampdown_trigger else "Idle"}'
                          )

                    # file log
                    with open(f"upsstatus_v4_{today_tag}.txt", "a") as flog:
                        flog.write(f"{in_voltage_str} VAC @ {in_freq_str} Hz\t {batt_soc} %% {now:%m/%d/%Y}\t{now:%H:%M:%S}\n")

                    time.sleep(config.POLLING_INTERVAL/1000)

                except KeyboardInterrupt:
                    print('Stopping monitoring (Ctrl-C).')
                    with open(f"upsstatus_v4_{today_tag}.txt", "a") as flog:
                        flog.write("User stopped monitoring by giving quit command (Ctrl-c).")
                    break

                except Exception as e:
                    print(f'[ERR] Unexpected error: {e}', file=sys.stderr)
                    with open(f"upsstatus_v4_{today_tag}.err", "a") as flog:
                        flot.write(f"[ERR] {now:%d/%m/%Y %H:%M:%S} : Unexpected error occurred.")
                    
                    # Try a safe reconnect
                    try:
                        ssh_session.close()
                    except Exception:
                        pass
                    ssh_session = None
                    time.sleep(2)


            stdscr.refresh()

            running, should_quit = handle.handle_user_input(stdscr, running)

            if should_quit:
                print("User entered quit command (Ctrl-Q)")
                ssh_session.sendline('exit')
                break
    finally:
        if ssh_session and not ssh_session.closed:
            try:
                ssh_session.close()
            except Exception:
                pass
        print('SSH session closed.')
        print('End of program')
