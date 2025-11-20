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
#
################################################################

import threading, time
import glob
import os
from epics import PV

def initalize():
	global oldtime
	global lastest_file
	global directory
	global t
	directory = "*.txt"
	list_of_files = glob.glob(directory)
	lastest_file = max(list_of_files, key = os.path.getctime)
	print(lastest_file)
	HV_data = open(lastest_file, "r")
	HV_lines = HV_data.readlines()	
	last_line = len(HV_lines)-1
	HV_lines[last_line] = HV_lines[last_line].split()
	print(HV_lines[last_line])
	oldtime = HV_lines[last_line][0]
	HV_data.close()

def fetch_data():
	global oldtime
	global newtime
	global lastest_file
	global directory
	global t
	volt_monitoring = PV('icarus_cathodehv_monitor/volt')
	current_monitoring = PV('icarus_cathodehv_monitor/current')
	volt_set = PV('icarus_cathodehv_set/volt')
	current_set = PV('icarus_cathodehv_set/current')
	voltww_monitoring = PV('icarus_cathodehv_monitor_ww/volt')
	voltew_monitoring = PV('icarus_cathodehv_monitor_ew/volt')
	voltwe_monitoring = PV('icarus_cathodehv_monitor_we/volt')
	voltee_monitoring = PV('icarus_cathodehv_monitor_ee/volt')
	directory = "*.txt"
	list_of_files = glob.glob(directory)
	lastest_file = max(list_of_files, key = os.path.getctime)
	print(lastest_file)
	HV_data = open(lastest_file, "r")
	HV_lines = HV_data.readlines()	
	last_line = len(HV_lines)-1
	HV_lines[last_line] = HV_lines[last_line].split()
	newtime = HV_lines[last_line][0]
	if newtime != oldtime:
		print(HV_lines[last_line])
		volt_monitoring.put(int(HV_lines[last_line][2]))
		current_monitoring.put(int(HV_lines[last_line][3]))
		voltww_monitoring.put(int(HV_lines[last_line][4]))
		voltew_monitoring.put(int(HV_lines[last_line][5]))
		voltwe_monitoring.put(int(HV_lines[last_line][6]))
		voltee_monitoring.put(int(HV_lines[last_line][7]))
		volt_set.put(int(HV_lines[last_line][8]))
		current_set.put(int(HV_lines[last_line][9]))
		oldtime = newtime
	print(volt_monitoring.get())
	time.sleep(5)
	fetch_data()

initalize()
fetch_data()
