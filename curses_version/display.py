# display.py
import curses
import time
from collections import deque

import config

previous_size = (0, 0)

def init_display(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(config.POLLING_INTERVAL)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)

def resize(lines, height):
    max_lines = height - config.MENU_HEIGHT - 1
    return deque(list(lines)[-max_lines:], maxlen=max_lines)

def draw_header(stdscr, width):
    stdscr.addstr(1, 2, "ICARUS Cathode HV UPS Monitor", curses.A_BOLD)
    stdscr.addstr(3, 2, "[s] Start  [p] Pause  [Ctrl+q] Quit")
    stdscr.addstr(5, 2, "Timestamp\tOnline\tAC Input Voltage(V)\tBattery Level (%)\tAlarm Counter\tRamp down flag")

def draw_log(stdscr, running, lines, alarm_counter, width):
    if running:
        for idx, line_text in enumerate(lines):
            if alarm_counter != 0:
                stdscr.addstr(config.MENU_HEIGHT + idx, 2, line_text, curses.A_BOLD | curses.color_pair(2))
            else:
                stdscr.addstr(config.MENU_HEIGHT + idx, 2, line_text, curses.A_BOLD | curses.color_pair(1))
    else:
        stdscr.addstr(6, 2, "Monitoring stopped. Press 's' to start.", curses.A_DIM)

def draw_footer(stdscr, height):
    stdscr.addstr(height - 1, 2, "ICARUS Cathode HV UPS Monitor - Version 4.0", curses.A_BOLD)
        
def render(stdscr, running, lines, alarm_counter):
    global previous_size
    stdscr.clear()

    # 터미널 크기 변경 감지 시 lines 리사이즈
    height, width = stdscr.getmaxyx()
    if (height, width) != previous_size:
        lines = resize(lines, height)
        previous_size = (height, width)
        
    draw_header(stdscr, width)
    draw_log(stdscr, running, lines, alarm_counter, width)
    draw_footer(stdscr, height)
    
    return lines

def update(stdscr, stat_params, lines):
    current_time = time.strftime("%H:%M:%S")
    in_voltage_str = stat_params['voltage'] or "0"
    in_freq_str = stat_params['freq'] or "0"
    batt_soc = stat_params['battery_charge'] or "0"
    net_stat = stat_params['net_status']
    alarm_counter = stat_params['alarm_counter']
    rampdown_trigger = stat_params['rampdown_trigger']

    lines.append(
            f'{current_time}\t'
            f'{"Online" if net_stat else "Offline"}\t\t'
            f'{in_voltage_str}'
            f'\t\t{batt_soc}'
            f'\t\t\t({alarm_counter}/{config.ALARM_THRESHOLD})'
            f'\t\t{"Triggered" if rampdown_trigger else "Idle"}'
            )
    for idx, line_text in enumerate(lines):
        stdscr.addstr(config.MENU_HEIGHT + idx, 2, line_text, curses.A_BOLD | curses.color_pair(1))
