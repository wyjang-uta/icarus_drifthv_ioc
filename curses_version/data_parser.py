#parser.py
import re

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

