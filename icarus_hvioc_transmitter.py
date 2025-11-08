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
#   Nov 7, 2025: GUI Upgrade (v2.10)
#   - Fixed v2.9 parsing bug, reverted X-axis to PC time.
#
#   Nov 7, 2025: GUI Upgrade (v2.11)
#   - Integrated 'reverse_readline' generator provided by user
#     for efficient pre-loading of last N lines.
#   - Added header skipping logic during reverse read.
#
################################################################

import sys
import time
import glob
import os # ❗️ reverse_readline에 필요
import random
import datetime
from epics import PV

#  GUI 및 플로팅 라이브러리 임포트
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QPlainTextEdit, QGroupBox, QLabel, QCheckBox, QFrame,
    QRadioButton, QButtonGroup
)
from PyQt6.QtCore import QTimer, QDateTime, Qt
from PyQt6.QtGui import QFont
import pyqtgraph as pg
from collections import deque

VERSION_MAJOR = 2
VERSION_MINOR = 11
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

# --- ❗️ (신규) 사용자 제공 함수 ---
def reverse_readline(filename, buf_size=8192):
  """A generator that returns the lines of a file in reverse order"""
  with open(filename, 'rb') as fh:
    segment = None
    offset = 0
    fh.seek(0, os.SEEK_END)
    file_size = remaining_size = fh.tell()
    while remaining_size > 0:
      offset = min(file_size, offset + buf_size)
      fh.seek(file_size - offset)
      buffer = fh.read(min(remaining_size, buf_size))
      # remove file's last "\n" if it exists, only for the first buffer
      if remaining_size == file_size and buffer and buffer[-1] == b'\n':
        buffer = buffer[:-1]
      remaining_size -= buf_size
      lines = buffer.split(b'\n') # ❗️ 바이트 단위로 분리
      # append last chunk's segment to this chunk's last line
      if segment is not None:
        lines[-1] += segment
      segment = lines[0]
      lines = lines[1:]
      # yield lines in this chunk except the segment
      for line in reversed(lines):
        # only decode on a parsed line, to avoid utf-8 decode error
        yield line # ❗️ 바이트(bytes)를 반환
    # Don't yield None if the file was empty
    if segment is not None:
      yield segment


# --- Main GUI Application Class ---

class HVUploaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ICARUS Drift HV EPICS Uploader v{VERSION_MAJOR}.{VERSION_MINOR}")
        self.setGeometry(100, 100, 800, 800)

        # --- State Variables ---
        self.current_filename = None
        self.current_file_handle = None
        self.last_timestamp = ""
        self.mode = "real" # "real", "readonly", "dry"
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
        
        # --- Plotting Variables ---
        self.max_data_points = (30 * 60) // POLLING_INTERVAL # 360
        self.time_data = deque(maxlen=self.max_data_points)
        # (Plot 1)
        self.volt_data = deque(maxlen=self.max_data_points)
        self.curr_data = deque(maxlen=self.max_data_points)
        self.volt_set_data = deque(maxlen=self.max_data_points)
        self.curr_set_data = deque(maxlen=self.max_data_points)
        # (Plot 2)
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
        self.radio_real = QRadioButton("Real Mode (File Read & EPICS Put)")
        self.radio_readonly = QRadioButton("Read-Only Mode (File Read Only)")
        self.radio_dryrun = QRadioButton("Dry-Run Mode (Simulation)")
        self.mode_button_group = QButtonGroup()
        
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
        """(v2.8) Set up the main user interface layout."""
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        # 1. Control Area (RadioButtons)
        control_group = QGroupBox("Controls")
        control_layout = QVBoxLayout(control_group)
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.radio_real)
        mode_layout.addWidget(self.radio_readonly)
        mode_layout.addWidget(self.radio_dryrun)
        control_layout.addLayout(mode_layout)
        self.mode_button_group.addButton(self.radio_real)
        self.mode_button_group.addButton(self.radio_readonly)
        self.mode_button_group.addButton(self.radio_dryrun)
        self.radio_real.setChecked(True)
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        control_layout.addLayout(button_layout)
        main_layout.addWidget(control_group)

        # 2. Live Monitor Plots
        plot_group = QGroupBox("Live Monitor - 30 min window")
        plot_layout = QVBoxLayout(plot_group)
        plot_layout.setSpacing(0)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self.plot_widget_vi = self.create_plot_widget_vi()
        plot_layout.addWidget(self.plot_widget_vi)
        self.plot_widget_divider = self.create_plot_widget_divider()
        plot_layout.addWidget(self.plot_widget_divider)
        self.plot_widget_divider.setXLink(self.plot_widget_vi.getPlotItem())
        main_layout.addWidget(plot_group, stretch=2)

        # 3. Log Area
        log_group = QGroupBox("Live Log")
        log_layout = QVBoxLayout(log_group)
        self.log_widget.setReadOnly(True)
        self.log_widget.setFont(QFont("Courier New", 9))
        log_layout.addWidget(self.log_widget)
        main_layout.addWidget(log_group, stretch=1)

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

        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
        self.stop_button.setEnabled(False)

    def set_led_style(self, led_widget, base_color):
        """(v2.5) (Helper) LED 위젯의 스타일시트를 설정합니다."""
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
        """(v2.5) 0.5초마다 호출되어 2개의 LED 색상을 업데이트합니다."""
        self.blink_state = not self.blink_state
        is_running = self.monitor_timer.isActive()
        base_color_monitor = "#00FF00" if is_running else "#FF0000"
        self.set_led_style(self.led_monitor_indicator, base_color_monitor)
        base_color_epics = "#00FF00" if self.epics_connected else "#FF0000"
        self.set_led_style(self.led_epics_indicator, base_color_epics)

    def create_plot_widget_vi(self):
        """(v2.7) 듀얼 Y축 (V/I) 플롯 위젯 (위쪽 X축 글자 숨김)"""
        plot_item = pg.PlotItem(axisItems={'bottom': pg.DateAxisItem()})
        plot_widget = pg.PlotWidget(plotItem=plot_item)
        
        axis = plot_item.getAxis('bottom')
        axis.setStyle(showValues=False)
        axis.setLabel(None)
        
        plot_widget.showGrid(x=True, y=True, alpha=0.3) 
        legend = plot_item.addLegend() 

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
        legend.addItem(self.curr_line, name="Current (Mon)")
        legend.addItem(self.curr_set_line, name="Current (Set)")
        # 3. X축 및 뷰박스 크기 동기화
        p2_viewbox.linkView(p2_viewbox.XAxis, plot_item.getViewBox())
        def update_p2_viewbox_geometry():
            p2_viewbox.setGeometry(plot_item.getViewBox().sceneBoundingRect())
        plot_item.getViewBox().sigResized.connect(update_p2_viewbox_geometry)
        return plot_widget 

    def create_plot_widget_divider(self):
        """(v2.7) 4개 전압 분배기 플롯 위젯 (범례 offset 수정)"""
        plot_item = pg.PlotItem(axisItems={'bottom': pg.DateAxisItem()})
        plot_widget = pg.PlotWidget(plotItem=plot_item)
        plot_item.setTitle("Voltage Dividers")
        plot_widget.showGrid(x=True, y=True, alpha=0.3)
        legend = plot_item.addLegend() 
        plot_item.setLabel('left', 'Voltage (V)', color="#000000")
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
        now = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        self.log_widget.appendPlainText(f"[{now}] {msg}")
        self.log_widget.verticalScrollBar().setValue(
            self.log_widget.verticalScrollBar().maximum()
        )

    def initialize_epics(self):
        """(v2.8) EPICS PV 초기화 및 'Real Mode' 활성화 여부 결정."""
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
            
        if not self.epics_connected:
            self.radio_real.setEnabled(False)
            self.radio_readonly.setChecked(True)
        self.update_led_blink_state()

    def start_monitoring(self):
        """❗️ (v2.11) 3가지 모드에 따라 모니터링 시작 (reverse_readline 사용)."""
        
        # 1. 모드 결정
        if self.radio_real.isChecked(): self.mode = "real"
        elif self.radio_readonly.isChecked(): self.mode = "readonly"
        else: self.mode = "dry"
        
        # 2. 버튼 상태 변경
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        for btn in self.mode_button_group.buttons():
            btn.setEnabled(False)
        
        # 3. 모드별 시작 로직
        if self.mode == "dry":
            # --- [Dry Run] 시작 ---
            self.log_message("--- Monitoring Started (Dry Run Mode) ---")
            self.status_label_monitor.setText("Status: Monitoring... (Dry Run)")
            self.last_timestamp = ""
            self.monitor_timer.start()
        else:
            # --- [Real Mode] 또는 [Read-Only Mode] 시작 ---
            log_msg = "Real Mode" if self.mode == "real" else "Read-Only Mode"
            self.log_message(f"--- Monitoring Started ({log_msg}) ---")
            self.status_label_monitor.setText(f"Status: Monitoring... ({log_msg})")
            try:
                self.current_filename = find_latest_file()
                if not self.current_filename:
                    self.log_message("[WARN] No *.txt files found. Waiting...")
                    self.monitor_timer.start()
                    return
                
                self.log_message(f"Monitoring file: {self.current_filename}")
                
                # ❗️ (v2.11) 마지막 N줄 사전 로드 (reverse_readline 사용)
                self.preload_file_data(self.current_filename)
                
                self.current_file_handle = open(self.current_filename, "r")
                
                self.monitor_timer.start()
                
            except Exception as e:
                self.log_message(f"[ERROR] Failed to start monitoring: {e}")
                self.stop_monitoring()
                
        self.update_led_blink_state()

    def stop_monitoring(self):
        """(v2.8) Stop the monitoring timer and close file."""
        self.monitor_timer.stop()
        if self.current_file_handle:
            try:
                self.current_file_handle.close()
            except Exception as e:
                self.log_message(f"[ERROR] Failed to close file: {e}")
        self.current_file_handle = None
        self.current_filename = None
        self.last_timestamp = ""
        self.clear_plot()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        for btn in self.mode_button_group.buttons():
            btn.setEnabled(True)
        if not self.epics_connected:
            self.radio_real.setEnabled(False)
        self.status_label_monitor.setText("Status: Stopped")
        self.log_message("--- Monitoring Stopped ---")
        self.update_led_blink_state()

    def clear_plot(self):
        """(v2.6) 플롯과 9개의 데이터 버퍼를 모두 비웁니다."""
        self.time_data.clear()
        self.volt_data.clear()
        self.curr_data.clear()
        self.volt_set_data.clear() 
        self.curr_set_data.clear() 
        self.voltww_data.clear()
        self.voltew_data.clear()
        self.voltwe_data.clear()
        self.voltee_data.clear()
        self.update_all_plot_lines() # 빈 데이터로 그래프 업데이트

    def read_last_line(self):
        """(v2.8) Helper function to read the very last line of the current file."""
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
        """(v2.8) 모드에 따라 데이터 소스를 분기합니다."""
        
        # 1. [Dry Run] 모드
        if self.mode == "dry":
            self.generate_dummy_data()
            return

        # 2. [Real] 또는 [Read-Only] 모드 (파일 읽기)
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
                
                # ❗️ 새 파일이므로, 마지막 N줄 사전 로드 (reverse_readline 사용)
                self.preload_file_data(self.current_filename)
                return
                
            hv_lastline, hv_new_timestamp = self.read_last_line()
            if not hv_new_timestamp:
                return

            if self.last_timestamp != hv_new_timestamp:
                self.log_message(f"Updated record: {hv_lastline}")
                self.last_timestamp = hv_new_timestamp
                hv_struc = hv_lastline.split()
                
                self.update_plot(hv_struc) # (공통) 플롯 업데이트
                self.put_to_epics(hv_struc) # (분기) EPICS Put
                
        except Exception as e:
            self.log_message(f"[FATAL LOOP ERROR] {e}. Check file access/format.")

    def generate_dummy_data(self):
        """(v2.8) Dry Run: V_set/I_set 가짜 데이터 생성"""
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

    def preload_file_data(self, filename):
        """❗️ (v2.12) 'reverse_readline' 및 '//' 헤더 감지 로직 사용."""
        self.log_message(f"Pre-loading last {self.max_data_points} data points from {filename}...")
        self.clear_plot() # 시작하기 전에 플롯 초기화
        
        preloaded_lines_reversed = []
        try:
            # (v2.11) 파일을 거꾸로 읽음
            for line_bytes in reverse_readline(filename):
                line_str = line_bytes.decode('utf-8', errors='ignore').strip()
                
                # ❗️ FIX (v2.12): 헤더를 명시적으로 확인합니다.
                if not line_str or line_str.startswith("//"):
                    if line_str: # 빈 줄이 아닌 경우에만 (즉, 헤더인 경우) 로그
                        self.log_message(f"[PRELOAD] Skipping header line: {line_str}")
                    continue
                    
                hv_struc = line_str.split()
                
                # ❗️ (추가) 타임스탬프 형식 확인 (데이터 무결성)
                if not hv_struc or ':' not in hv_struc[0]:
                    self.log_message(f"[PRELOAD] Skipping malformed line (no ':'): {line_str}")
                    continue

                preloaded_lines_reversed.append(line_str)
                
                # 360줄을 채우면 중단
                if len(preloaded_lines_reversed) >= self.max_data_points:
                    break
                    
        except FileNotFoundError:
            self.log_message(f"[PRELOAD ERROR] File not found: {filename}")
            return
        except Exception as e:
            self.log_message(f"[PRELOAD ERROR] Failed to reverse-read file: {e}")
            return

        if not preloaded_lines_reversed:
            self.log_message("[PRELOAD] File is empty or contains no valid data.")
            return

        # (v2.11) 읽은 데이터를 다시 뒤집어 시간 순서(오래된->최신)로 변경
        preloaded_lines = list(reversed(preloaded_lines_reversed))
        
        # (v2.10) X축을 위한 가상 타임라인 생성
        current_time = time.time()
        
        for i, line in enumerate(preloaded_lines):
            hv_struc = line.strip().split()
            if len(hv_struc) < 10:
                continue
                
            time_stamp = current_time - ((len(preloaded_lines) - 1) - i) * POLLING_INTERVAL
            
            try:
                # Deque 버퍼 채우기 (hv_struc 사용)
                self.time_data.append(time_stamp)
                self.volt_data.append(int(hv_struc[2]))
                self.curr_data.append(int(hv_struc[3]))
                self.voltww_data.append(int(hv_struc[4]))
                self.voltew_data.append(int(hv_struc[5]))
                self.voltwe_data.append(int(hv_struc[6]))
                self.voltee_data.append(int(hv_struc[7]))
                self.volt_set_data.append(int(hv_struc[8]))
                self.curr_set_data.append(int(hv_struc[9]))
            except (ValueError, IndexError):
                self.log_message(f"[PRELOAD WARN] Skipping malformed line: {line.strip()}")
                continue 

        # 마지막 타임스탬프 설정 (중복 방지용)
        last_struc = preloaded_lines[-1].strip().split()
        if last_struc:
            self.last_timestamp = last_struc[0]
        
        # 8개 라인을 한 번에 모두 플롯
        self.update_all_plot_lines()
        
        self.log_message(f"Pre-loaded {len(self.time_data)} records (Last TS: {self.last_timestamp})")

    def update_all_plot_lines(self):
        """❗️ (v2.9) 9개의 Deque 데이터를 8개의 플롯 라인에 모두 설정합니다."""
        time_list = list(self.time_data)
        
        # Plot 1
        if self.volt_line: self.volt_line.setData(x=time_list, y=list(self.volt_data))
        if self.curr_line: self.curr_line.setData(x=time_list, y=list(self.curr_data))
        if self.volt_set_line: self.volt_set_line.setData(x=time_list, y=list(self.volt_set_data))
        if self.curr_set_line: self.curr_set_line.setData(x=time_list, y=list(self.curr_set_data))
        # Plot 2
        if self.voltww_line: self.voltww_line.setData(x=time_list, y=list(self.voltww_data))
        if self.voltew_line: self.voltew_line.setData(x=time_list, y=list(self.voltew_data))
        if self.voltwe_line: self.voltwe_line.setData(x=time_list, y=list(self.voltwe_data))
        if self.voltee_line: self.voltee_line.setData(x=time_list, y=list(self.voltee_data))

    def update_plot(self, hv_struc):
        """❗️ (v2.10) X축을 PC 시간(time.time)으로 사용하여 8개 라인을 업데이트합니다."""
        
        try:
            # X축을 PC 시간으로 사용 (v2.8 로직으로 복원)
            current_time = time.time()
            
            # V_mon, I_mon
            volt_val = int(hv_struc[2])
            curr_val = int(hv_struc[3])
            
            # Vdiv 4개
            voltww_val = int(hv_struc[4])
            voltew_val = int(hv_struc[5])
            voltwe_val = int(hv_struc[6])
            voltee_val = int(hv_struc[7])
            
            # V_set, I_set
            volt_set_val = int(hv_struc[8])
            curr_set_val = int(hv_struc[9])

            # 9개 버퍼에 데이터 추가
            self.time_data.append(current_time)
            self.volt_data.append(volt_val)
            self.curr_data.append(curr_val)
            self.voltww_data.append(voltww_val)
            self.voltew_data.append(voltew_val)
            self.voltwe_data.append(voltwe_val)
            self.voltee_data.append(voltee_val)
            self.volt_set_data.append(volt_set_val)
            self.curr_set_data.append(curr_set_val)

            # 8개 라인 그래프 갱신
            self.update_all_plot_lines()
            
        except (IndexError, ValueError) as e:
            self.log_message(f"[PLOT ERROR] Invalid data for plot (need 10 columns): {e}")
        except Exception as e:
            self.log_message(f"[PLOT ERROR] Unexpected plot error: {e}")

    def put_to_epics(self, hv_struc):
        """(v2.8) 3가지 모드에 따라 EPICS Put 로직을 분기합니다."""

        # 1. [Dry Run] 모드
        if self.mode == "dry":
            self.log_message(f"  -> [DRY RUN] Simulating EPICS put for timestamp {hv_struc[0]}")
            return
        # 2. [Read-Only] 모드
        if self.mode == "readonly":
            self.log_message(f"  -> [READ-ONLY] EPICS Put skipped for timestamp {hv_struc[0]}")
            return

        # 3. [Real Mode]
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
