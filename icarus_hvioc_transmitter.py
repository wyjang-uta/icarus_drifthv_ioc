################################################################
# Programmed by:
#       Hector Carranza Jr. (hector.carranza@mavs.uta.edu)
#       and Wooyoung Jang (wooyoung.jang@uta.edu)
# Institution: University of Texas at Arlington
#
# GUI Upgrade by: Gemini (Based on original logic)
#
# History:
#   (Original script history...)
#
#   Nov 7, 2025: GUI Upgrade (v2.5)
#   - Added second blinking LED for EPICS connection status.
#
#   Nov 7, 2025: GUI Upgrade (v2.6)
#   - Added a second plot for 4 Voltage Dividers (WW, EW, WE, EE)
#   - Linked X-axis (time) between the two plots.
#
################################################################

import sys
import time
import glob
import os
import random
import datetime
from epics import PV

#  GUI 및 플로팅 라이브러리 임포트
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QGroupBox, QLabel, QCheckBox, QFrame
)
from PyQt6.QtCore import QTimer, QDateTime, Qt # Qt 추가 (점선용)
from PyQt6.QtGui import QFont
import pyqtgraph as pg              # pyqtgraph 추가
from collections import deque       # deque 추가

VERSION_MAJOR = 2
VERSION_MINOR = 6
POLLING_INTERVAL = 5  # unit in seconds (5000 ms)
BLINK_INTERVAL = 500  # LED 깜빡임 간격 (ms)

# pyqtgraph 기본 설정
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

# --- Original Helper Function (unchanged) ---
def find_latest_file():
    """ function to find the name of the latest file. """
    list_of_files = glob.glob("*.txt")
    if not list_of_files:
        return None
    latest_file = max(list_of_files, key=os.path.getctime)
    return latest_file

# --- Main GUI Application Class ---

class HVUploaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ICARUS Drift HV EPICS Uploader v{VERSION_MAJOR}.{VERSION_MINOR}")
        self.setGeometry(100, 100, 800, 800) # ❗️ 창 세로 크기 증가

        # --- State Variables ---
        self.current_filename = None
        self.current_file_handle = None
        self.last_timestamp = ""
        self.is_dry_run = False
        self.epics_connected = False
        self.blink_state = False

        # --- EPICS PVs ---
        self.volt_monitoring = None
        self.current_monitoring = None
        self.volt_set = None
        self.current_set = None
        self.voltww_monitoring = None
        self.voltew_monitoring = None
        self.voltwe_monitoring = None
        self.voltee_monitoring = None
        
        # --- ❗️ Plotting Variables (Vdiv 4개 추가) ---
        self.max_data_points = (30 * 60) // POLLING_INTERVAL
        self.time_data = deque(maxlen=self.max_data_points)
        # Plot 1 (V/I)
        self.volt_data = deque(maxlen=self.max_data_points)
        self.curr_data = deque(maxlen=self.max_data_points)
        self.volt_set_data = deque(maxlen=self.max_data_points)
        self.curr_set_data = deque(maxlen=self.max_data_points)
        # Plot 2 (Vdiv)
        self.voltww_data = deque(maxlen=self.max_data_points)
        self.voltew_data = deque(maxlen=self.max_data_points)
        self.voltwe_data = deque(maxlen=self.max_data_points)
        self.voltee_data = deque(maxlen=self.max_data_points)
        
        # Plot 1 Lines
        self.volt_line = None
        self.curr_line = None
        self.volt_set_line = None
        self.curr_set_line = None
        # Plot 2 Lines
        self.voltww_line = None
        self.voltew_line = None
        self.voltwe_line = None
        self.voltee_line = None
        
        # --- GUI Widgets ---
        self.dry_run_checkbox = QCheckBox("Dry Run Mode (Simulate data, no EPICS put)")
        self.start_button = QPushButton("Start Monitoring")
        self.stop_button = QPushButton("Stop Monitoring")
        self.log_widget = QPlainTextEdit()
        
        self.status_label_monitor = QLabel("Status: Idle")
        self.led_monitor_indicator = QLabel() 
        self.status_label_epics = QLabel("EPICS: Initializing...")
        self.led_epics_indicator = QLabel()
        
        # --- QTimer ---
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(POLLING_INTERVAL * 1000)
        self.monitor_timer.timeout.connect(self.check_file_update)
        
        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(BLINK_INTERVAL)
        self.blink_timer.timeout.connect(self.update_led_blink_state)

        self.init_ui()
        self.log_message(f"Starting HV Uploader v{VERSION_MAJOR}.{VERSION_MINOR}...")
        self.initialize_epics()
        self.blink_timer.start()
        
    def init_ui(self):
        """Set up the main user interface layout."""
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # 1. Control Area
        control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout(control_group)
        control_layout.addWidget(self.dry_run_checkbox)
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        control_layout.addLayout(button_layout)
        main_layout.addWidget(control_group)

        # 2. ❗️ Live Monitor Plots (V/I와 Vdiv 분리)
        plot_group = QGroupBox("Live Monitor - 30 min window")
        plot_layout = QVBoxLayout(plot_group) # ❗️ 수직 레이아웃
        
        # ❗️ V/I Plot (상단)
        self.plot_widget_vi = self.create_plot_widget_vi()
        plot_layout.addWidget(self.plot_widget_vi)
        
        # ❗️ Vdiv Plot (하단)
        self.plot_widget_divider = self.create_plot_widget_divider()
        plot_layout.addWidget(self.plot_widget_divider)

        # ❗️ (핵심) X축 연결: Vdiv 플롯의 X축을 V/I 플롯의 X축에 연결
        self.plot_widget_divider.setXLink(self.plot_widget_vi.getPlotItem())
        
        main_layout.addWidget(plot_group, stretch=2) # ❗️ 플롯 영역에 더 많은 공간(stretch=2)

        # 3. Log Area
        log_group = QGroupBox("Live Log")
        log_layout = QVBoxLayout(log_group)
        self.log_widget.setReadOnly(True)
        self.log_widget.setFont(QFont("Courier New", 9))
        log_layout.addWidget(self.log_widget)
        main_layout.addWidget(log_group, stretch=1) # ❗️ 로그 영역은 stretch=1

        # 4. Status Bar (LED 포함)
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(5, 5, 5, 5)
        self.led_monitor_indicator.setFixedSize(12, 12)
        status_layout.addWidget(self.led_monitor_indicator)
        status_layout.addWidget(self.status_label_monitor)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        status_layout.addWidget(line)
        self.led_epics_indicator.setFixedSize(12, 12)
        status_layout.addWidget(self.led_epics_indicator)
        status_layout.addWidget(self.status_label_epics)
        status_layout.addStretch()
        main_layout.addLayout(status_layout)
        
        self.setCentralWidget(central_widget)

        # Connect signals
        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)

        # Set initial state
        self.stop_button.setEnabled(False)

    def set_led_style(self, led_widget, base_color):
        """(Helper) LED 위젯의 스타일시트를 설정합니다."""
        if self.blink_state:
            color = base_color # On
        else:
            color = "#E0E0E0" # Off (회색)
        style = (
            f"background-color: {color};"
            "border-radius: 6px;"
            "border: 1px solid #777;"
        )
        led_widget.setStyleSheet(style)

    def update_led_blink_state(self):
        """0.5초마다 호출되어 2개의 LED 색상을 업데이트합니다."""
        self.blink_state = not self.blink_state # 상태 뒤집기
        
        # 1. 모니터링 LED (녹색=실행, 빨간색=정지)
        is_running = self.monitor_timer.isActive()
        base_color_monitor = "#00FF00" if is_running else "#FF0000"
        self.set_led_style(self.led_monitor_indicator, base_color_monitor)

        # 2. EPICS LED (녹색=연결됨, 빨간색=끊김)
        base_color_epics = "#00FF00" if self.epics_connected else "#FF0000"
        self.set_led_style(self.led_epics_indicator, base_color_epics)

    def create_plot_widget_vi(self):
        """❗️ (이름 변경) 듀얼 Y축 (V/I) 플롯 위젯을 생성합니다."""
        
        plot_item = pg.PlotItem(axisItems={'bottom': pg.DateAxisItem()})
        plot_widget = pg.PlotWidget(plotItem=plot_item)

        axis = plot_item.getAxis('bottom')
        axis.setStyle(showValues=False)
        axis.setLabel(None)
        
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        legend = plot_item.addLegend() # 범례 객체 가져오기

        # 1. 왼쪽 Y축 (전압)
        plot_item.setLabel('left', 'Voltage (V)', color="#FF0000")
        self.volt_line = plot_item.plot(
            pen=pg.mkPen("#FF0000", width=2), name="Voltage (Mon)"
        )
        self.volt_set_line = plot_item.plot(
            pen=pg.mkPen("#FF0000", width=2, style=Qt.PenStyle.DashLine), name="Voltage (Set)"
        )

        # 2. 오른쪽 Y축 (전류)
        plot_item.showAxis('right') 
        p2_viewbox = pg.ViewBox()
        plot_item.getAxis('right').linkToView(p2_viewbox)
        plot_item.getAxis('right').setLabel('Current (uA)', color="#0000FF")
        plot_item.scene().addItem(p2_viewbox)
        
        self.curr_line = pg.PlotCurveItem(
            pen=pg.mkPen("#0000FF", width=2), name="Current (Mon)"
        )
        self.curr_set_line = pg.PlotCurveItem(
            pen=pg.mkPen("#0000FF", width=2, style=Qt.PenStyle.DashLine), name="Current (Set)"
        )
        p2_viewbox.addItem(self.curr_line)
        p2_viewbox.addItem(self.curr_set_line)

        # ❗️ (범례 수정) 전류 라인을 범례에 수동 추가
        legend.addItem(self.curr_line, name="Current (Mon)")
        legend.addItem(self.curr_set_line, name="Current (Set)")

        # 3. X축 및 뷰박스 크기 동기화
        p2_viewbox.linkView(p2_viewbox.XAxis, plot_item.getViewBox())
        def update_p2_viewbox_geometry():
            p2_viewbox.setGeometry(plot_item.getViewBox().sceneBoundingRect())
        plot_item.getViewBox().sigResized.connect(update_p2_viewbox_geometry)

        return plot_widget # ❗️ 위젯만 반환 (PlotItem은 .getPlotItem()으로 접근)

    def create_plot_widget_divider(self):
        """❗️ (신규) 4개 전압 분배기 플롯 위젯을 생성합니다."""
        
        # ❗️ X축 라벨을 비워둠 (상단 플롯과 공유하므로)
        plot_item = pg.PlotItem(axisItems={'bottom': pg.DateAxisItem()})
        plot_widget = pg.PlotWidget(plotItem=plot_item)
        
        #plot_item.setTitle("Voltage Dividers")
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        legend = plot_item.addLegend(offset=(70, 10))

        # Y축 설정 (단일)
        plot_item.setLabel('left', 'Voltage Dividers (V)', color="#000000")

        # ❗️ 4개의 라인 추가 (색상과 스타일을 다르게 지정)
        self.voltww_line = plot_item.plot(
            pen=pg.mkPen("#E60000", width=2), name="V_WW (West-West)"
        )
        self.voltew_line = plot_item.plot(
            pen=pg.mkPen("#4D8000", width=2), name="V_EW (East-West)"
        )
        self.voltwe_line = plot_item.plot(
            pen=pg.mkPen("#005C99", width=2, style=Qt.PenStyle.DashLine), name="V_WE (West-East)"
        )
        self.voltee_line = plot_item.plot(
            pen=pg.mkPen("#6600CC", width=2, style=Qt.PenStyle.DashLine), name="V_EE (East-East)"
        )
        
        return plot_widget

    def log_message(self, msg):
        # (v2.5와 동일)
        now = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        self.log_widget.appendPlainText(f"[{now}] {msg}")
        self.log_widget.verticalScrollBar().setValue(
            self.log_widget.verticalScrollBar().maximum()
        )

    def initialize_epics(self):
        # (v2.5와 동일)
        self.log_message("Initializing EPICS variables...")
        try:
            self.volt_monitoring = PV('icarus_cathodehv_monitor/volt')
            self.current_monitoring = PV('icarus_cathodehv_monitor/current')
            self.volt_set = PV('icarus_cathodehv_set/volt')
            self.current_set = PV('icarus_cathodehv_set/current')
            self.voltww_monitoring = PV('icarus_cathodehv_monitor_ww/volt')
            self.voltew_monitoring = PV('icarus_cathodehv_monitor_ew/volt')
            self.voltwe_monitoring = PV('icarus_cathodehv_monitor_we/volt')
            self.voltee_monitoring = PV('icarus_cathodehv_monitor_ee/volt')
            
            if self.volt_monitoring.wait_for_connection(timeout=2.0):
                self.log_message("EPICS connection successful.")
                self.epics_connected = True
                self.status_label_epics.setText("EPICS: Connected")
                self.status_label_epics.setStyleSheet("color: green;")
            else:
                self.log_message("[WARN] EPICS connection test timeout.")
                self.epics_connected = False
                self.status_label_epics.setText("EPICS: DISCONNECTED")
                self.status_label_epics.setStyleSheet("color: red;")
                
        except Exception as e:
            self.log_message(f"[FATAL ERROR] Failed to initialize EPICS PVs: {e}")
            self.epics_connected = False
            self.status_label_epics.setText("EPICS: FATAL ERROR")
            self.status_label_epics.setStyleSheet("color: red;")
            
        self.update_led_blink_state()

    def start_monitoring(self):
        # (v2.5와 동일)
        self.is_dry_run = self.dry_run_checkbox.isChecked()
        if not self.is_dry_run and not self.epics_connected:
            self.log_message("[ERROR] Cannot start in Real Mode: EPICS is not connected.")
            self.log_message("Start in 'Dry Run Mode' or check network/IOC.")
            return
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.dry_run_checkbox.setEnabled(False)
        if self.is_dry_run:
            self.log_message("--- Monitoring Started (Dry Run Mode) ---")
            self.status_label_monitor.setText("Status: Monitoring... (Dry Run)")
            self.last_timestamp = ""
            self.monitor_timer.start()
        else:
            self.log_message("--- Monitoring Started (Real Mode) ---")
            self.status_label_monitor.setText("Status: Monitoring... (Real Mode)")
            try:
                self.current_filename = find_latest_file()
                if not self.current_filename:
                    self.log_message("[WARN] No *.txt files found. Waiting...")
                    self.monitor_timer.start()
                    return
                self.log_message(f"Monitoring file: {self.current_filename}")
                self.current_file_handle = open(self.current_filename, "r")
                hv_lastline, self.last_timestamp = self.read_last_line()
                if not hv_lastline:
                    self.log_message("[WARN] File is empty. Waiting for new data...")
                else:
                    self.log_message(f"Initial timestamp: {self.last_timestamp}")
                self.monitor_timer.start()
            except Exception as e:
                self.log_message(f"[ERROR] Failed to start monitoring: {e}")
                self.stop_monitoring()
        self.update_led_blink_state()

    def stop_monitoring(self):
        # (v2.5와 동일)
        self.monitor_timer.stop()
        if self.current_file_handle:
            try:
                self.current_file_handle.close()
            except Exception as e:
                self.log_message(f"[ERROR] Failed to close file: {e}")
        self.current_file_handle = None
        self.current_filename = None
        self.last_timestamp = ""
        self.is_dry_run = False
        self.clear_plot() # 플롯 데이터 클리어
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.dry_run_checkbox.setEnabled(True)
        self.status_label_monitor.setText("Status: Stopped")
        self.log_message("--- Monitoring Stopped ---")
        self.update_led_blink_state()

    def clear_plot(self):
        """❗️ 플롯과 9개의 데이터 버퍼를 모두 비웁니다."""
        self.time_data.clear()
        self.volt_data.clear()
        self.curr_data.clear()
        self.volt_set_data.clear() 
        self.curr_set_data.clear() 
        self.voltww_data.clear() # ❗️
        self.voltew_data.clear() # ❗️
        self.voltwe_data.clear() # ❗️
        self.voltee_data.clear() # ❗️
        
        # 8개 라인 초기화
        if self.volt_line: self.volt_line.setData([], [])
        if self.curr_line: self.curr_line.setData([], [])
        if self.volt_set_line: self.volt_set_line.setData([], []) 
        if self.curr_set_line: self.curr_set_line.setData([], []) 
        if self.voltww_line: self.voltww_line.setData([], []) # ❗️
        if self.voltew_line: self.voltew_line.setData([], []) # ❗️
        if self.voltwe_line: self.voltwe_line.setData([], []) # ❗️
        if self.voltee_line: self.voltee_line.setData([], []) # ❗️

    def read_last_line(self):
        # (v2.5와 동일)
        try:
            self.current_file_handle.seek(0, 2)
            file_size = self.current_file_handle.tell()
            if file_size == 0: return "", ""
            self.current_file_handle.seek(max(file_size - 1024, 0), 0)
            hv_data = self.current_file_handle.readlines()
            if not hv_data: return "", ""
            hv_lastline = hv_data[-1].strip()
            if not hv_lastline: return "", ""
            hv_struc = hv_lastline.split()
            hv_timestamp = hv_struc[0]
            return hv_lastline, hv_timestamp
        except Exception as e:
            self.log_message(f"[ERROR] Failed to read last line: {e}")
            return "", ""

    def check_file_update(self):
        # (v2.5와 동일)
        if self.is_dry_run:
            self.generate_dummy_data()
            return
        try:
            new_filename = find_latest_file()
            if not new_filename:
                self.log_message("[WARN] No *.txt files found. Waiting...")
                return
            if self.current_filename != new_filename:
                self.log_message("A new data file is created.")
                self.log_message(f"Old file: {self.current_filename}")
                self.current_filename = new_filename
                self.log_message(f"New file: {self.current_filename}")
                if self.current_file_handle:
                    self.current_file_handle.close()
                self.current_file_handle = open(self.current_filename, "r")
                _, self.last_timestamp = self.read_last_line()
                self.log_message(f"New file's last timestamp: {self.last_timestamp}")
                return
            hv_lastline, hv_new_timestamp = self.read_last_line()
            if not hv_new_timestamp:
                return
            if self.last_timestamp != hv_new_timestamp:
                self.log_message(f"Updated record: {hv_lastline}")
                self.last_timestamp = hv_new_timestamp
                hv_struc = hv_lastline.split()
                self.update_plot(hv_struc)
                self.put_to_epics(hv_struc)
        except Exception as e:
            self.log_message(f"[FATAL LOOP ERROR] {e}. Check file access/format.")

    def generate_dummy_data(self):
        # (v2.5와 동일)
        hv_new_timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        if self.last_timestamp != hv_new_timestamp:
            self.last_timestamp = hv_new_timestamp
            volt_set_val = -50000
            curr_set_val = 10
            hv_struc = [
                hv_new_timestamp, # [0] Timestamp
                datetime.datetime.now().strftime('%Y-%m-%d'), # [1] Date
                random.randint(-50100, -49900), # [2] volt_monitoring
                random.randint(0, 5),           # [3] current_monitoring
                random.randint(-50100, -49900), # [4] voltww
                random.randint(-50100, -49900), # [5] voltew
                random.randint(-50100, -49900), # [6] voltwe
                random.randint(-50100, -49900), # [7] voltee
                volt_set_val,                   # [8] volt_set
                curr_set_val                    # [9] current_set
            ]
            hv_struc_str = [str(x) for x in hv_struc]
            self.log_message(f"Dry Run: Generated record: {' '.join(hv_struc_str)}")
            self.update_plot(hv_struc_str)
            self.put_to_epics(hv_struc_str)

    def update_plot(self, hv_struc):
        """❗️ Vdiv 4개 값을 포함하여 8개 라인을 모두 업데이트합니다."""
        try:
            current_time = time.time()
            
            # V_mon, I_mon
            volt_val = int(hv_struc[2])
            curr_val = int(hv_struc[3])
            
            # ❗️ Vdiv 4개
            voltww_val = int(hv_struc[4])
            voltew_val = int(hv_struc[5])
            voltwe_val = int(hv_struc[6])
            voltee_val = int(hv_struc[7])
            
            # V_set, I_set
            volt_set_val = int(hv_struc[8])
            curr_set_val = int(hv_struc[9])

            # ❗️ 9개 버퍼에 데이터 추가
            self.time_data.append(current_time)
            self.volt_data.append(volt_val)
            self.curr_data.append(curr_val)
            self.volt_set_data.append(volt_set_val)
            self.curr_set_data.append(curr_set_val)
            self.voltww_data.append(voltww_val)
            self.voltew_data.append(voltew_val)
            self.voltwe_data.append(voltwe_val)
            self.voltee_data.append(voltee_val)

            # ❗️ 8개 라인 그래프 갱신
            # Plot 1
            self.volt_line.setData(x=list(self.time_data), y=list(self.volt_data))
            self.curr_line.setData(x=list(self.time_data), y=list(self.curr_data))
            self.volt_set_line.setData(x=list(self.time_data), y=list(self.volt_set_data))
            self.curr_set_line.setData(x=list(self.time_data), y=list(self.curr_set_data))
            # Plot 2
            self.voltww_line.setData(x=list(self.time_data), y=list(self.voltww_data))
            self.voltew_line.setData(x=list(self.time_data), y=list(self.voltew_data))
            self.voltwe_line.setData(x=list(self.time_data), y=list(self.voltwe_data))
            self.voltee_line.setData(x=list(self.time_data), y=list(self.voltee_data))
            
        except (IndexError, ValueError) as e:
            self.log_message(f"[PLOT ERROR] Invalid data for plot (need 10 columns): {e}")
        except Exception as e:
            self.log_message(f"[PLOT ERROR] Unexpected plot error: {e}")

    def put_to_epics(self, hv_struc):
        # (v2.5와 동일)
        if self.is_dry_run:
            self.log_message(f"  -> [DRY RUN] Simulating EPICS put for timestamp {hv_struc[0]}")
            return
        try:
            self.volt_monitoring.put(int(hv_struc[2]))
            self.current_monitoring.put(int(hv_struc[3]))
            self.voltww_monitoring.put(int(hv_struc[4]))
            self.voltew_monitoring.put(int(hv_struc[5]))
            self.voltwe_monitoring.put(int(hv_struc[6]))
            self.voltee_monitoring.put(int(hv_struc[7]))
            self.volt_set.put(int(hv_struc[8]))
            self.current_set.put(int(hv_struc[9]))
            self.log_message(f"  -> EPICS put OK for timestamp {hv_struc[0]}")
        except IndexError:
            self.log_message(f"[PUT ERROR] Data line has < 10 columns: {hv_struc}")
        except ValueError:
            self.log_message(f"[PUT ERROR] Cannot convert value to int: {hv_struc}")
        except Exception as e:
            self.log_message(f"[EPICS PUT ERROR] {e}")

    def closeEvent(self, event):
        """Ensure timer and file are closed when window is shut."""
        self.stop_monitoring() # Stop timer and close file handle
        event.accept()

# --- Application Entry Point ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = HVUploaderGUI()
    window.show()
    sys.exit(app.exec())
