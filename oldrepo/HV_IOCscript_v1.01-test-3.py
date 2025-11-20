################################################################
# Programmed by: Hector Carranza Jr
# Institution: University of Texas at Arlington
#
# this program grabs the latest data row from the HV data files
# and sends it to the IOC if not already recorded
#
# History:
#   Jan. 1. 2022: 
#              (Wooyoung Jang; University of Texas at Arlington)
#   - Version 1.01-test-1
#      A test script to resolve program crashing issue due to 
#    too many opened threads. 
#   - Version 1.01-test-2
#      It seems the error is due to the recursive code structure
#    and so we revised the loop structure of the program.
#   - Version 1.01-test-3
#       Different code style has been used.
################################################################

import time
import glob
import os
from epics import PV

# find the name of the most recently created file.
def get_newest_fname():
    list_of_files = glob.glob("*.txt")
    latest_file = max(list_of_files, key = os.path.getctime)
    return latest_file

# check the given data file is newest one in current directory.
def is_newest_file(fname):
    return fname == get_newest_fname()

# string parser; seek to the last line of the file and return the line as a list.
def fill_container(stdio):
    offset=128
    stdio.seek(0,2)
    stdio.seek(max(stdio.tell()-offset,0),0)
    cont = stdio.readlines()
    return cont[-1:][0].split()

# function to find the number of lines in a file.
def buf_count_newlines_gen(fname):
    def _make_gen(reader):
        while True:
            b = reader(2 ** 16)
            if not b: break
            yield b
        
    with open(fname, "rb") as f:
            count = sum(buf.count(b"\n") for buf in _make_gen(f.raw.read))
    return count

# Initialize EPICS instances
volt_monitoring    = PV('icarus_cathodehv_monitor/volt')
current_monitoring = PV('icarus_cathodehv_monitor/current')
volt_set           = PV('icarus_cathodehv_set/volt')
current_set        = PV('icarus_cathodehv_set/current')
voltww_monitoring  = PV('icarus_cathodehv_monitor_ww/volt')
voltew_monitoring  = PV('icarus_cathodehv_monitor_ew/volt')
voltwe_monitoring  = PV('icarus_cathodehv_monitor_we/volt')
voltee_monitoring  = PV('icarus_cathodehv_monitor_ee/volt')

# Initialize local variables
polling_interval = 5   # unit is second
oldfname = ''
newfname = ''
hv_f = None
hv_container = []
hv_oldtime = ''
hv_newtime = ''

oldfname = get_newest_fname()
while True:                                                         # main loop
    newfname = get_newest_fname()
    while oldfname == newfname:
        with open(oldfname, 'r') as hv_f:
            while True:
                hv_container = fill_container(hv_f)
                hv_oldtime = hv_container[0]
                if hv_oldtime != hv_newtime:
                    hv_newtime = hv_container[0]
                    for i in range(2,9):
                        print(hv_container[i].strip())
                    # push the updated values to the EPICS instances
                    volt_monitoring.put(int(hv_container[2]))
                    current_monitoring.put(int(hv_container[3]))
                    voltww_monitoring.put(int(hv_container[4]))
                    voltew_monitoring.put(int(hv_container[5]))
                    voltwe_monitoring.put(int(hv_container[6]))
                    voltee_monitoring.put(int(hv_container[7]))
                    volt_set.put(int(hv_container[8]))
                    current_set.put(int(hv_container[9]))
                # sleep few seconds
                time.sleep(polling_interval)
                if True: continue
                break
    oldfname = newfname
    if True: continue
    break
