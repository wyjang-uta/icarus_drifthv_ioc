# main.py
import curses

import monitor

def main():
    curses.wrapper(monitor.monitor)

if __name__ == "__main__":
    main()
