# -*- coding: utf-8 -*-
#
# Copyright (C) 2024 Your Name
#
# This file is part of # TD.
#
# # TD is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# # TD is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with YourProject. If not, see <http://www.gnu.org/licenses/>.


import os
import sys
import json
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QFormLayout, \
    QHBoxLayout, QGridLayout, QComboBox, QCheckBox, QTextEdit, QGroupBox, QSizePolicy, QMessageBox, QPlainTextEdit, \
    QFontDialog, QSpinBox
from PyQt5.QtCore import Qt, QRegExp, pyqtSlot, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QRegExpValidator, QIcon, QFont, QTextCursor

import serial
import serial.tools.list_ports

# 获取当前脚本的路径
if getattr(sys, 'frozen', False):
    # 如果是打包后的可执行文件
    application_path = os.path.dirname(sys.executable)
else:
    # 如果是未打包的脚本文件
    application_path = os.path.dirname(os.path.abspath(__file__))

# 构建文件路径
config_path = os.path.join(application_path, 'config.json')
image_path = os.path.join(application_path, 'xxx.png')
log_path = os.path.join(application_path, 'log.txt')

# 重定向输出到文件
log_file = open(log_path, "w")
sys.stdout = log_file
sys.stderr = log_file


class SerialThread(QThread):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(Exception)

    def __init__(self, serial_port):
        super().__init__()
        self.serial_port = serial_port
        self.running = True

    def run(self):
        while self.running:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    if data:
                        self.data_received.emit(data)
            except Exception as e:
                self.error_occurred.emit(e)
                self.running = False

    def stop(self):
        self.running = False
        self.wait()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.voltage_displays = []
        self.current_displays = []
        self.temp_displays = []
        self.current_inputs = []  # 保存电流输入框以记忆值
        self.serial_thread = None
        self.serial_port = None  # 初始化串口为None
        self.rx_count = 0
        self.tx_count = 0
        self.buffer = ''  # 缓冲区，用于存储未完成的行
        self.is_manual_command = False  # 标记是否为手动命令

        self.initUI()
        self.setup_timers()
        self.load_config()

    def initUI(self):
        main_layout = QHBoxLayout()

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.create_pump_section('主放', ['HIPUMP 1', 'HIPUMP 2'], unit='A'))
        left_layout.addWidget(self.create_pump_section('预放', ['PUMP 1', 'PUMP 2', 'PUMP 3', 'PUMP 4'], unit='mA'))
        left_layout.addLayout(self.create_comm_section())
        left_layout.addLayout(self.create_status_section())
        main_layout.addLayout(left_layout)

        right_layout = QVBoxLayout()
        right_layout.addWidget(self.create_serial_section())
        right_layout.addWidget(self.create_config_section())
        main_layout.addLayout(right_layout)

        self.setLayout(main_layout)
        self.setWindowTitle('泵浦控制软件 V0.1')
        self.resize(1920, 1440)

        # 设置图标
        self.setWindowIcon(QIcon(image_path))

        # 设置默认全局字体
        self.set_default_font()

    def setup_timers(self):
        self.port_refresh_timer = QTimer(self)
        self.port_refresh_timer.timeout.connect(self.refresh_ports)
        self.port_refresh_timer.start(1000)  # 每秒刷新一次串口列表

        self.sampling_timer = QTimer(self)
        self.sampling_timer.timeout.connect(self.send_sampling_command)
        self.sampling_timer.start(1000)  # 默认采样率为1000ms

    def set_default_font(self):
        font = QFont()
        font.setFamily("Courier New")
        font.setPointSize(12)
        font.setBold(True)
        QApplication.instance().setFont(font)

    def create_pump_section(self, title, pump_names, unit):
        section_widget = QGroupBox(title)
        layout = QVBoxLayout()

        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(12)
        form_layout.setContentsMargins(10, 10, 10, 10)
        form_layout.addWidget(QLabel(f'设置电流 ({unit})'), 0, 1)
        form_layout.addWidget(QLabel(''), 0, 2)
        form_layout.addWidget(QLabel('实时电压 (V)'), 0, 3)
        form_layout.addWidget(QLabel(f'实时电流 ({unit})'), 0, 4)
        form_layout.addWidget(QLabel('实时温度 (°C)'), 0, 5)

        for i, pump_name in enumerate(pump_names):
            form_layout.addWidget(QLabel(pump_name), i + 1, 0)
            current_input = QLineEdit()
            current_input.setValidator(QRegExpValidator(QRegExp(r'^\d*\.?\d*$')))
            self.current_inputs.append(current_input)  # 保存电流输入框
            confirm_button = QPushButton('确认')
            confirm_button.clicked.connect(lambda checked, ci=current_input, pn=pump_name, u=unit: self.confirm_current(ci, pn, u))
            form_layout.addWidget(current_input, i + 1, 1)
            form_layout.addWidget(confirm_button, i + 1, 2, alignment=Qt.AlignLeft)

            voltage_display = QLineEdit('00.00')
            current_display = QLineEdit('00.00')
            temp_display = QLineEdit('00.00')

            voltage_display.setReadOnly(True)
            current_display.setReadOnly(True)
            temp_display.setReadOnly(True)

            voltage_display.setStyleSheet("background-color: #F0F0F0;")
            current_display.setStyleSheet("background-color: #F0F0F0;")
            temp_display.setStyleSheet("background-color: #F0F0F0;")

            form_layout.addWidget(voltage_display, i + 1, 3)
            form_layout.addWidget(current_display, i + 1, 4)
            form_layout.addWidget(temp_display, i + 1, 5)

            self.voltage_displays.append(voltage_display)
            self.current_displays.append(current_display)
            self.temp_displays.append(temp_display)

        layout.addLayout(form_layout)
        section_widget.setLayout(layout)
        return section_widget

    def confirm_current(self, current_input, pump_name, unit):
        try:
            current_value = float(current_input.text())
            if unit == 'A':
                if not (0 <= current_value <= 11.5):
                    QMessageBox.warning(self, '失败', '电流设置失败，必须在 0 到 11.5A 之间！')
                    current_input.clear()  # 清除输入框的数值
                    return
            elif unit == 'mA' and pump_name == 'PUMP 4':
                current_value /= 1000.0  # 转换为安培进行处理
                if not (0.0 <= current_value <= 11.5):
                    QMessageBox.warning(self, '失败', '电流设置失败，必须在 0 到 11.5A 之间！')
                    current_input.clear()  # 清除输入框的数值
                    return
            if pump_name == 'PUMP 4':
                QMessageBox.information(self, '成功', f'电流设置为 {current_value * 1000.0}mA 成功！')
            else:
                QMessageBox.information(self, '成功', f'电流设置为 {current_value}{unit} 成功！')
            self.send_set_current_command(current_value, pump_name, unit)
            self.save_config()  # 保存设置值
        except ValueError:
            QMessageBox.warning(self, '失败', '电流设置失败，请输入有效的数字！')
            current_input.clear()  # 清除输入框的数值

    def send_set_current_command(self, current_value, pump_name, unit):
        if self.serial_port and self.serial_port.is_open:
            try:
                command_map = {
                    'HIPUMP 1': [
                        "key 3\r\n",
                        "hipump 1 MODE M\r\n",
                        f"hipump 1 isp {current_value}\r\n"
                    ],
                    'HIPUMP 2': [
                        "key 3\r\n",
                        "hipump 2 MODE M\r\n",
                        f"hipump 2 isp {current_value}\r\n"
                    ],
                    'PUMP 1': [
                        "key 3\r\n",
                        "pump 1 MODE M\r\n",
                        f"pump 1 isp {current_value}\r\n"
                    ],
                    'PUMP 2': [
                        "key 3\r\n",
                        "pump 2 MODE M\r\n",
                        f"pump 2 isp {current_value}\r\n"
                    ],
                    'PUMP 3': [
                        "key 3\r\n",
                        "pump 3 MODE M\r\n",
                        f"pump 3 isp {current_value}\r\n"
                    ],
                    'PUMP 4': [
                        "key 3\r\n",
                        "hipump 3 MODE M\r\n",
                        f"hipump 3 isp {current_value}\r\n"
                    ]
                }

                command_sequence = command_map.get(pump_name)
                if not command_sequence:
                    raise ValueError(f"未知的泵名称: {pump_name}")

                for command in command_sequence:
                    self.serial_port.write(command.encode('utf-8'))
                    self.tx_count += len(command)
                    self.tx_label.setText(f'TX: {self.tx_count}')
            except (serial.SerialException, ValueError) as e:
                QMessageBox.warning(self, '错误', f'发送设置电流指令失败: {e}')

    def create_serial_section(self):
        section_widget = QGroupBox("")

        layout = QVBoxLayout()
        layout.setSpacing(40)
        layout.setContentsMargins(20, 20, 20, 20)

        serial_layout = QFormLayout()

        self.port_selector = QComboBox()
        self.baudrate_selector = QComboBox()
        self.baudrate_selector.addItems(["115200", "9600", "14400", "19200", "38400", "57600"])

        self.stopbits_selector = QComboBox()
        self.stopbits_selector.addItems(["1", "1.5", "2"])

        self.databits_selector = QComboBox()
        self.databits_selector.addItems(["8", "7", "6", "5"])

        self.Paritybits_selector = QComboBox()
        self.Paritybits_selector.addItems(["None", "Odd", "Even"])

        self.encoding_selector = QComboBox()
        self.encoding_selector.addItems(["UTF-8", "ASCII", "Unicode", "UTF-32", "BigEndianUnicode", "GBK", "GB2312"])

        serial_layout.addRow('串口选择', self.port_selector)
        serial_layout.addRow('波特率', self.baudrate_selector)
        serial_layout.addRow('停止位', self.stopbits_selector)
        serial_layout.addRow('数据位', self.databits_selector)
        serial_layout.addRow('校验位', self.Paritybits_selector)

        self.serial_button = QPushButton('打开串口', self)
        self.serial_button.setFixedHeight(222)
        self.serial_button.setCheckable(True)
        self.serial_button.clicked.connect(self.toggle_serial)
        serial_layout.addRow(self.serial_button)

        layout.addLayout(serial_layout)
        section_widget.setLayout(layout)
        return section_widget

    def create_config_section(self):
        config_widget = QGroupBox("")

        cfg_layout = QVBoxLayout()
        cfg_layout.setSpacing(40)
        cfg_layout.setContentsMargins(20, 20, 20, 20)

        sys_layout = QFormLayout()

        font_btn = QPushButton('设置字体')
        font_btn.clicked.connect(self.choose_font)
        sys_layout.addRow(font_btn)

        reset_btn = QPushButton('恢复默认配置')
        reset_btn.clicked.connect(self.reset_config)
        sys_layout.addRow(reset_btn)

        self.encoding_selector = QComboBox()
        self.encoding_selector.addItems(["UTF-8", "ASCII", "GBK", "GB2312"])
        sys_layout.addRow('编码方式', self.encoding_selector)

        self.sampling_rate_spinbox = QSpinBox()
        self.sampling_rate_spinbox.setRange(100, 5000)  # 设置范围为100ms到5000ms
        self.sampling_rate_spinbox.setSingleStep(100)  # 设置步长为100ms
        self.sampling_rate_spinbox.setValue(1000)  # 默认值为1000ms
        self.sampling_rate_spinbox.valueChanged.connect(self.update_sampling_rate)
        sys_layout.addRow('采样率 (ms)', self.sampling_rate_spinbox)

        cfg_layout.addLayout(sys_layout)
        config_widget.setLayout(cfg_layout)
        return config_widget

    def choose_font(self):
        font, ok = QFontDialog.getFont()
        if ok:
            QApplication.instance().setFont(font)
            QMessageBox.information(self, '字体设置', '字体设置成功！')

    def refresh_ports(self):
        self.port_selector.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            description = f"{port.device}: {port.description}"
            self.port_selector.addItem(description)

    def create_comm_section(self):
        comm_layout = QVBoxLayout()

        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text_area.customContextMenuRequested.connect(self.show_context_menu)
        comm_layout.addWidget(self.text_area)

        bottom_layout = QHBoxLayout()
        self.send_input = QPlainTextEdit()
        self.send_input.setFixedHeight(100)
        self.send_input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.send_input.installEventFilter(self)

        send_btn = QPushButton('发送')
        send_btn.setMaximumWidth(200)
        send_btn.setMinimumHeight(100)
        send_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        send_btn.clicked.connect(self.send_message)

        bottom_layout.addWidget(self.send_input)
        bottom_layout.addWidget(send_btn)
        comm_layout.addLayout(bottom_layout)
        return comm_layout

    def show_context_menu(self, position):
        menu = self.text_area.createStandardContextMenu()
        clear_action = menu.addAction("Clear")
        clear_action.triggered.connect(self.clear_text_area)
        menu.exec_(self.text_area.mapToGlobal(position))

    def clear_text_area(self):
        self.text_area.clear()

    def create_status_section(self):
        status_layout = QHBoxLayout()
        self.hex_send_checkbox = QCheckBox('十六进制发送')
        self.hex_send_checkbox.stateChanged.connect(self.toggle_hex_send)
        self.add_newline_checkbox = QCheckBox('发送新行')
        self.rx_label = QLabel('RX: 0')
        self.tx_label = QLabel('TX: 0')
        checkbox_layout = QHBoxLayout()
        checkbox_layout.addWidget(self.hex_send_checkbox)
        checkbox_layout.addWidget(self.add_newline_checkbox)
        checkbox_layout.addWidget(self.rx_label)
        checkbox_layout.addWidget(self.tx_label)
        status_layout.addLayout(checkbox_layout)
        return status_layout

    def toggle_hex_send(self, state):
        if state == Qt.Checked:
            text = self.send_input.toPlainText()
            hex_text = ' '.join(format(ord(c), '02x') for c in text)
            self.send_input.setPlainText(hex_text)
        else:
            hex_text = self.send_input.toPlainText().strip()
            try:
                bytes_text = bytes.fromhex(hex_text.replace(' ', ''))
                text = bytes_text.decode('utf-8', errors='replace')
                self.send_input.setPlainText(text)
            except ValueError:
                QMessageBox.warning(self, '错误', '无效的十六进制格式')
                self.send_input.clear()

    @pyqtSlot()
    def send_message(self):
        message = self.send_input.toPlainText()
        encoding = self.encoding_selector.currentText()
        if self.hex_send_checkbox.isChecked():
            try:
                message = bytes.fromhex(message.replace(' ', ''))
            except ValueError:
                QMessageBox.warning(self, '错误', '十六进制格式错误')
                return
        else:
            if self.add_newline_checkbox.isChecked():
                message += '\r\n'  # 仅在用户选择时添加换行符
            message = message.encode(encoding)

        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.write(message)
                self.tx_count += len(message)
                self.tx_label.setText(f'TX: {self.tx_count}')

                self.is_manual_command = True
                self.sampling_timer.stop()

                QTimer.singleShot(3000, self.reset_manual_command_flag)  # 延时3秒
            except serial.SerialException as e:
                QMessageBox.warning(self, '错误', f'发送串口数据失败: {e}')
            except Exception as e:
                QMessageBox.warning(self, '错误', f'发生未知错误: {e}')

    def reset_manual_command_flag(self):
        self.is_manual_command = False
        self.sampling_timer.start(self.sampling_rate_spinbox.value())  # 恢复实时采集

    def eventFilter(self, source, event):
        if event.type() == event.KeyPress and source is self.send_input:
            if event.key() == Qt.Key_Return and not (event.modifiers() & Qt.ShiftModifier):
                self.send_message()
                return True
        return super(MainWindow, self).eventFilter(source, event)

    def toggle_serial(self):
        if self.serial_button.isChecked():
            self.open_serial()
        else:
            self.close_serial()

    def open_serial(self):
        port_description = self.port_selector.currentText()
        port = port_description.split(":")[0]  # 从描述中提取端口号
        baudrate = int(self.baudrate_selector.currentText())

        # 如果串口已经打开，先关闭它
        if self.serial_port and self.serial_port.is_open:
            self.close_serial()

        if port:
            try:
                self.serial_port = serial.Serial(port, baudrate, timeout=1)
                self.serial_button.setText('关闭串口')
                self.serial_button.setStyleSheet("background-color: green;")
                self.start_serial_thread()
                QMessageBox.information(self, '成功', f'串口 {port} 打开成功！')
            except serial.SerialException as e:
                self.handle_serial_open_error(e, port)
            except Exception as e:
                self.handle_unknown_error(e)
        else:
            QMessageBox.warning(self, '失败', '未选择串口')
            self.refresh_ports()  # 刷新串口列表

    def handle_serial_open_error(self, error, port):
        self.serial_button.setChecked(False)
        self.serial_button.setText('打开串口')
        self.serial_button.setStyleSheet("background-color: grey;")
        QMessageBox.warning(self, '失败', f'打开串口 {port} 失败: {error}')
        self.refresh_ports()  # 刷新串口列表

    def handle_unknown_error(self, error):
        self.serial_button.setChecked(False)
        self.serial_button.setText('打开串口')
        self.serial_button.setStyleSheet("background-color: grey;")
        QMessageBox.warning(self, '失败', f'发生未知错误: {error}')
        self.refresh_ports()  # 刷新串口列表

    def close_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.stop_serial_thread()
            self.serial_port.close()
            self.serial_button.setText('打开串口')
            self.serial_button.setStyleSheet("background-color: grey;")
            QMessageBox.information(self, '成功', '串口关闭成功')
        self.serial_port = None

    def start_serial_thread(self):
        self.serial_thread = SerialThread(self.serial_port)
        self.serial_thread.data_received.connect(self.on_data_received)
        self.serial_thread.error_occurred.connect(self.handle_serial_error)
        self.serial_thread.start()
        self.sampling_timer.start()

    def stop_serial_thread(self):
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread = None

    def handle_serial_error(self, e):
        QMessageBox.warning(self, '串口错误', f'串口通信出现错误: {e}')
        self.close_serial()

    @pyqtSlot(bytes)
    def on_data_received(self, data):
        self.rx_count += len(data)
        self.rx_label.setText(f'RX: {self.rx_count}')
        encoding = self.encoding_selector.currentText()
        self.buffer += data.decode(encoding, errors='replace')
        self.process_serial_data()

    def process_serial_data(self):
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            line = line.rstrip('\r')
            if self.is_manual_command:
                self.text_area.moveCursor(QTextCursor.End)
                self.text_area.insertPlainText(line + '\n')
            else:
                self.parse_pump_data(line)
        if self.buffer.endswith('>'):
            if self.is_manual_command:
                self.text_area.moveCursor(QTextCursor.End)
                self.text_area.insertPlainText(self.buffer)
            self.buffer = ''

    def parse_pump_data(self, line):
        try:
            parts = line.split()
            if len(parts) >= 3:
                pump_num = int(parts[1]) - 1
                attribute = parts[2].rstrip(':')
                value = parts[3] if len(parts) > 3 else None

                if line.startswith("HIPUMP"):
                    if pump_num < 0 or pump_num >= 2:
                        return
                    if attribute == "ILD":
                        self.current_displays[pump_num].setText(value)
                    elif attribute == "TMP":
                        self.temp_displays[pump_num].setText(value)
                    elif attribute == "VPPS":
                        self.voltage_displays[pump_num].setText(value)
                elif line.startswith("PUMP"):
                    if pump_num < 0 or pump_num >= 4:
                        return
                    pump_num += 2  # 偏移以适应显示列表中的位置
                    if attribute == "ILD":
                        self.current_displays[pump_num].setText(value)
                    elif attribute == "TMP":
                        self.temp_displays[pump_num].setText(value)
                    elif attribute == "VPPS":
                        self.voltage_displays[pump_num].setText(value)
        except Exception as e:
            print(f'解析泵数据时出错: {e}')

    def send_sampling_command(self):
        if self.serial_port and self.serial_port.is_open:
            try:
                if not self.is_manual_command:
                    self.serial_port.write(b'hipump\r\n')
                    self.serial_port.write(b'pump\r\n')
                    self.tx_count += 12  # 每条指令包括'hipump'或'pump'加上'\r\n'
                    self.tx_label.setText(f'TX: {self.tx_count}')
            except serial.SerialException as e:
                QMessageBox.warning(self, '错误', f'发送采样指令失败: {e}')
                self.close_serial()

    def save_config(self):
        config = {
            'hex_send': self.hex_send_checkbox.isChecked(),
            'add_newline': self.add_newline_checkbox.isChecked(),
            'currents': [input.text() for input in self.current_inputs],
            'sampling_rate': self.sampling_rate_spinbox.value(),
            'encoding': self.encoding_selector.currentText(),
            'window_size': {'width': self.width(), 'height': self.height()}
        }
        with open(config_path, 'w') as f:
            json.dump(config, f)

    def load_config(self):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.hex_send_checkbox.setChecked(config.get('hex_send', False))
                self.add_newline_checkbox.setChecked(config.get('add_newline', False))
                currents = config.get('currents', [])
                for input, value in zip(self.current_inputs, currents):
                    input.setText(value)
                self.sampling_rate_spinbox.setValue(config.get('sampling_rate', 1000))
                self.encoding_selector.setCurrentText(config.get('encoding', 'UTF-8'))
                window_size = config.get('window_size', {})
                self.resize(window_size.get('width', 1920), window_size.get('height', 1440))
        except FileNotFoundError:
            self.resize(1920, 1440)

    def reset_config(self):
        self.hex_send_checkbox.setChecked(False)
        self.add_newline_checkbox.setChecked(False)
        for input in self.current_inputs:
            input.clear()
        self.sampling_rate_spinbox.setValue(1000)
        self.encoding_selector.setCurrentText("UTF-8")
        self.resize(1920, 1440)
        self.set_default_font()
        self.save_config()

    def update_sampling_rate(self, value):
        self.sampling_timer.setInterval(value)
        self.save_config()

    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MainWindow()
    ex.show()
    sys.exit(app.exec_())

# 关闭文件
log_file.close()
