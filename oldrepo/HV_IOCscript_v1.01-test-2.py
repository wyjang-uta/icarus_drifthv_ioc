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

################################################################

import time
import glob
import os
from epics import PV

# function to find the name of the latest file.
def find_latest_file():
    list_of_files = glob.glob("*.txt")
    latest_file = max(list_of_files, key = os.path.getctime)
    return latest_file

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

# Initialize EPICS
volt_monitoring    = PV('icarus_cathodehv_monitor/volt')
current_monitoring = PV('icarus_cathodehv_monitor/current')
volt_set           = PV('icarus_cathodehv_set/volt')
current_set        = PV('icarus_cathodehv_set/current')
voltww_monitoring  = PV('icarus_cathodehv_monitor_ww/volt')
voltew_monitoring  = PV('icarus_cathodehv_monitor_ew/volt')
voltwe_monitoring  = PV('icarus_cathodehv_monitor_we/volt')
voltee_monitoring  = PV('icarus_cathodehv_monitor_ee/volt')

# Initialize local variables
filename = find_latest_file()
hv_f = open(filename, "r")
hv_f.seek(0, 2)                         # seek EOF
hv_nlines = hv_f.tell()                 # get # of lines
hv_f.seek(max(hv_nlines-1024, 0), 0)    # set position at the last n chars
hv_data = hv_f.readlines()              # read until encounter EOF
hv_lastline = hv_data[-1:][0]           # pick the last element
hv_struc = hv_lastline.split()
hv_timestamp = hv_struc[0]

print("\t\tTimestamp\tV_mon\tI_mon\tV_ww_m\tV_ew_m\tV_we_m\tV_ee_m\tV_set\tI_set\tDate")
print("Initial timestamp: ", hv_lastline)

# entry point of the main loop
while True:
    newfname = find_latest_file()
    if filename != newfname:                # when the date is changed,
        print("A new data file is created.")
        print("Old file: ", filename)
        filename = newfname
        print("New file: ", filename)
        hv_f.close()                        # close the old file,
        hv_f = open(filename, "r")          # and open the latest file

    # Update the data container
    hv_f.seek(0, 2)                         # seek EOF
    hv_nlines = hv_f.tell()                 # get # of lines
    hv_f.seek(max(hv_nlines-1024, 0), 0)    # set position at the last n chars
    hv_data = hv_f.readlines()              # read until EOF
    hv_lastline = hv_data[-1:][0]           # pick the last element
    hv_struc = hv_lastline.split()
    hv_new_timestamp = hv_struc[0]

    # Detect new record in the file by comparing timestamps
    if hv_timestamp != hv_new_timestamp:
        hv_timestamp = hv_struc[0]
        print("Updated record: ", hv_lastline)
        # Update the monitoring values
        volt_monitoring.put(int(hv_struc[2]))
        current_monitoring.put(int(hv_struc[3]))
        voltww_monitoring.put(int(hv_struc[4]))
        voltew_monitoring.put(int(hv_struc[5]))
        voltwe_monitoring.put(int(hv_struc[6]))
        voltee_monitoring.put(int(hv_struc[7]))
        volt_set.put(int(hv_struc[8]))
        current_set.put(int(hv_struc[9]))

    time.sleep(5)                           # data polling interval is 5 seconds
