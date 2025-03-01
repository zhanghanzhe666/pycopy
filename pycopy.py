#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import platform

from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QLineEdit, QPushButton,
    QProgressBar, QFileDialog, QSpinBox, QMessageBox, QWidget,
    QVBoxLayout, QHBoxLayout
)

# Windows 下用于操作注册表
if platform.system() == "Windows":
    import winreg

def register_context_menu():
    """
    自动注册右键菜单：
    - 对文件：在 HKCU\Software\Classes\*\shell 下添加 pycopy 项；
    - 对文件夹：在 HKCU\Software\Classes\Directory\shell 下添加 pycopy 项；
    调用菜单时，会将所选对象路径作为参数传递给本程序。
    """
    try:
        exe_path = sys.executable  # 打包后会返回 exe 路径
        command = f'"{exe_path}" "%1"'
        # 注册文件右键菜单
        key_path_file = r"Software\Classes\*\shell\pycopy"
        command_key_path_file = key_path_file + r"\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path_file) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "使用 pycopy 复制")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_key_path_file) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
        # 注册文件夹右键菜单
        key_path_dir = r"Software\Classes\Directory\shell\pycopy"
        command_key_path_dir = key_path_dir + r"\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path_dir) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "使用 pycopy 复制")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_key_path_dir) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
        print("已成功注册右键菜单")
    except Exception as e:
        print(f"注册失败: {e}")

def unregister_context_menu():
    """
    注销右键菜单，删除文件与文件夹下的注册信息
    """
    try:
        # 注销文件右键菜单
        key_path_file_command = r"Software\Classes\*\shell\pycopy\command"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path_file_command)
        key_path_file = r"Software\Classes\*\shell\pycopy"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path_file)
        # 注销文件夹右键菜单
        key_path_dir_command = r"Software\Classes\Directory\shell\pycopy\command"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path_dir_command)
        key_path_dir = r"Software\Classes\Directory\shell\pycopy"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path_dir)
        print("已成功注销右键菜单")
    except Exception as e:
        print(f"注销失败: {e}")

############################################
# 单个大文件的多线程分段复制（文件模式）
############################################
class CopyThread(QThread):
    # progress_update 发射 (线程编号, 本次复制字节数)
    progress_update = pyqtSignal(int, int)
    finished_signal = pyqtSignal(int)

    def __init__(self, thread_index, src, dst, start_pos, end_pos, block_size=1024*1024, parent=None):
        super().__init__(parent)
        self.thread_index = thread_index
        self.src = src
        self.dst = dst
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.block_size = block_size
        self.total_bytes = end_pos - start_pos

    def run(self):
        try:
            with open(self.src, 'rb') as f_src, open(self.dst, 'r+b') as f_dst:
                f_src.seek(self.start_pos)
                f_dst.seek(self.start_pos)
                bytes_to_copy = self.total_bytes
                while bytes_to_copy > 0:
                    read_size = self.block_size if bytes_to_copy >= self.block_size else bytes_to_copy
                    data = f_src.read(read_size)
                    if not data:
                        break
                    f_dst.write(data)
                    self.progress_update.emit(self.thread_index, len(data))
                    bytes_to_copy -= len(data)
        except Exception as e:
            print(f"线程 {self.thread_index} 错误: {e}")
        self.finished_signal.emit(self.thread_index)

############################################
# 文件夹复制——多线程从共享任务队列中取任务复制（文件夹模式）
############################################
import threading
class FolderCopyThread(QThread):
    # 用于更新当前线程正在复制的文件进度（百分比）
    thread_progress_update = pyqtSignal(int, int)  # 参数：(线程编号, 当前文件复制百分比)
    # 用于更新整体进度（累计字节数）
    overall_progress_update = pyqtSignal(int)
    finished_signal = pyqtSignal(int)

    def __init__(self, thread_index, files_queue, lock, block_size=1024*1024, parent=None):
        super().__init__(parent)
        self.thread_index = thread_index
        self.files_queue = files_queue
        self.lock = lock
        self.block_size = block_size

    def run(self):
        while True:
            with self.lock:
                if not self.files_queue:
                    break
                file_task = self.files_queue.pop(0)
            src_file, dst_file, file_size = file_task
            # 确保目标目录存在
            dst_dir = os.path.dirname(dst_file)
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir, exist_ok=True)
            try:
                with open(src_file, 'rb') as f_src, open(dst_file, 'wb') as f_dst:
                    copied = 0
                    while copied < file_size:
                        read_size = self.block_size if (file_size - copied) >= self.block_size else (file_size - copied)
                        data = f_src.read(read_size)
                        if not data:
                            break
                        f_dst.write(data)
                        copied += len(data)
                        percentage = int(copied / file_size * 100)
                        self.thread_progress_update.emit(self.thread_index, percentage)
                        self.overall_progress_update.emit(len(data))
            except Exception as e:
                print(f"线程 {self.thread_index} 复制文件 {src_file} 错误: {e}")
        self.finished_signal.emit(self.thread_index)

############################################
# 主窗口：根据源路径（文件或文件夹）启动对应复制模式
############################################
class MainWindow(QMainWindow):
    def __init__(self, preselected_path=None):
        super().__init__()
        self.setWindowTitle("pycopy - 快速复制")
        self.setGeometry(100, 100, 650, 550)
        self.initUI(preselected_path)
        # 用于文件模式
        self.threads = []
        # 用于文件夹模式
        self.folder_threads = []
        self.thread_progress = {}  # 存储各线程累计复制字节或当前文件进度
        self.total_bytes_copied = 0
        self.total_file_size = 0
        self.start_time = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)

    def initUI(self, preselected_path):
        widget = QWidget(self)
        self.setCentralWidget(widget)
        layout = QVBoxLayout()

        # 注册/注销右键菜单（仅限 Windows）
        reg_layout = QHBoxLayout()
        self.reg_button = QPushButton("注册右键菜单", self)
        self.reg_button.clicked.connect(lambda: register_context_menu() if platform.system()=="Windows" else QMessageBox.information(self, "提示", "仅支持Windows平台"))
        self.unreg_button = QPushButton("注销右键菜单", self)
        self.unreg_button.clicked.connect(lambda: unregister_context_menu() if platform.system()=="Windows" else QMessageBox.information(self, "提示", "仅支持Windows平台"))
        reg_layout.addWidget(self.reg_button)
        reg_layout.addWidget(self.unreg_button)
        layout.addLayout(reg_layout)

        # 源路径选择（支持文件或文件夹）
        src_layout = QHBoxLayout()
        self.src_line = QLineEdit(self)
        self.src_line.setPlaceholderText("选择源文件或文件夹")
        self.src_button = QPushButton("浏览", self)
        self.src_button.clicked.connect(self.browse_src)
        src_layout.addWidget(QLabel("源路径:"))
        src_layout.addWidget(self.src_line)
        src_layout.addWidget(self.src_button)
        layout.addLayout(src_layout)

        # 如果预选路径有效，则填充并锁定
        if preselected_path and os.path.exists(preselected_path):
            self.src_line.setText(preselected_path)
            self.src_line.setReadOnly(True)

        # 目标文件夹选择
        dst_layout = QHBoxLayout()
        self.dst_line = QLineEdit(self)
        self.dst_line.setPlaceholderText("选择目标文件夹")
        self.dst_button = QPushButton("浏览", self)
        self.dst_button.clicked.connect(self.browse_dst)
        dst_layout.addWidget(QLabel("目标路径:"))
        dst_layout.addWidget(self.dst_line)
        dst_layout.addWidget(self.dst_button)
        layout.addLayout(dst_layout)

        # 用户自定义线程数量
        thread_layout = QHBoxLayout()
        thread_layout.addWidget(QLabel("线程数量:"))
        self.thread_spin = QSpinBox(self)
        self.thread_spin.setRange(1, 64)
        self.thread_spin.setValue(4)
        thread_layout.addWidget(self.thread_spin)
        layout.addLayout(thread_layout)

        # 信息标签：显示文件/文件夹总大小、复制速度、剩余时间等
        self.info_label = QLabel("总大小: 0 字节 | 复制速度: 0 B/s | 剩余时间: 0 s", self)
        layout.addWidget(self.info_label)

        # 整体进度条
        self.overall_progress = QProgressBar(self)
        layout.addWidget(self.overall_progress)

        # 每个线程的进度条（动态添加）
        self.thread_progress_bars = {}
        self.thread_progress_layout = QVBoxLayout()
        layout.addLayout(self.thread_progress_layout)

        # 开始复制按钮
        self.start_button = QPushButton("开始复制", self)
        self.start_button.clicked.connect(self.start_copy)
        layout.addWidget(self.start_button)

        widget.setLayout(layout)

        # 设置深色主题 CSS 及按钮悬停动画
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; }
            QLabel { color: #ffffff; font-size: 14px; }
            QLineEdit { background-color: #3c3f41; border: 1px solid #6c6c6c; color: #ffffff; padding: 4px; border-radius: 4px; }
            QPushButton { background-color: #3c3f41; color: #ffffff; border: 1px solid #6c6c6c; padding: 4px 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #4c5052; }
            QProgressBar { border: 1px solid #6c6c6c; border-radius: 5px; text-align: center; }
            QProgressBar::chunk { background-color: #05B8CC; width: 20px; }
        """)

    def browse_src(self):
        # 同时支持文件和文件夹选择
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not path:
            # 如果选择文件夹失败，则尝试文件选择
            path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if path:
            self.src_line.setText(path)

    def browse_dst(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择目标文件夹")
        if folder_path:
            self.dst_line.setText(folder_path)

    def start_copy(self):
        src = self.src_line.text().strip()
        dst_dir = self.dst_line.text().strip()
        thread_count = self.thread_spin.value()

        if not os.path.exists(src):
            QMessageBox.warning(self, "错误", "请选择有效的源路径！")
            return
        if not os.path.isdir(dst_dir):
            QMessageBox.warning(self, "错误", "请选择有效的目标文件夹！")
            return

        # 如果是文件复制模式
        if os.path.isfile(src):
            # 目标文件路径保持原文件名
            dst = os.path.join(dst_dir, os.path.basename(src))
            self.total_file_size = os.path.getsize(src)
            self.overall_progress.setMaximum(self.total_file_size)
            self.total_bytes_copied = 0

            # 创建目标文件并预分配空间
            with open(dst, "wb") as f:
                f.truncate(self.total_file_size)

            # 初始化每个线程的进度条
            for i in range(thread_count):
                prog_bar = QProgressBar(self)
                prog_bar.setMaximum(100)
                prog_bar.setValue(0)
                self.thread_progress_layout.addWidget(QLabel(f"线程 {i+1} 进度:"))
                self.thread_progress_layout.addWidget(prog_bar)
                self.thread_progress_bars[i] = prog_bar
                self.thread_progress[i] = 0

            # 按文件大小均分任务，每个线程复制一段数据
            part_size = self.total_file_size // thread_count
            self.threads = []
            for i in range(thread_count):
                start_pos = i * part_size
                end_pos = (i+1)*part_size if i != thread_count - 1 else self.total_file_size
                t = CopyThread(i, src, dst, start_pos, end_pos)
                t.progress_update.connect(self.handle_file_progress)
                t.finished_signal.connect(self.thread_finished)
                self.threads.append(t)

            self.start_time = time.time()
            self.timer.start(500)
            self.start_button.setEnabled(False)
            for t in self.threads:
                t.start()

        # 如果是文件夹复制模式
        elif os.path.isdir(src):
            # 目标文件夹：在用户选择目标目录下创建一个同名文件夹
            folder_name = os.path.basename(os.path.normpath(src))
            dst_base = os.path.join(dst_dir, folder_name)
            # 扫描源目录，构建任务队列：每项 (源文件, 目标文件, 文件大小)
            files_queue = []
            total_size = 0
            for root, dirs, files in os.walk(src):
                for file in files:
                    src_file = os.path.join(root, file)
                    rel_path = os.path.relpath(src_file, src)
                    dst_file = os.path.join(dst_base, rel_path)
                    try:
                        file_size = os.path.getsize(src_file)
                    except Exception:
                        file_size = 0
                    total_size += file_size
                    files_queue.append((src_file, dst_file, file_size))
            if total_size == 0:
                QMessageBox.warning(self, "错误", "源文件夹为空或文件大小为0！")
                return
            self.total_file_size = total_size
            self.overall_progress.setMaximum(self.total_file_size)
            self.total_bytes_copied = 0

            # 初始化共享任务队列与线程锁
            self.files_queue = files_queue
            self.queue_lock = threading.Lock()

            # 初始化每个线程的进度条（显示当前文件复制百分比）
            for i in range(thread_count):
                prog_bar = QProgressBar(self)
                prog_bar.setMaximum(100)
                prog_bar.setValue(0)
                self.thread_progress_layout.addWidget(QLabel(f"线程 {i+1} 当前文件进度:"))
                self.thread_progress_layout.addWidget(prog_bar)
                self.thread_progress_bars[i] = prog_bar
                self.thread_progress[i] = 0

            self.folder_threads = []
            for i in range(thread_count):
                t = FolderCopyThread(i, self.files_queue, self.queue_lock)
                t.thread_progress_update.connect(self.handle_folder_thread_progress)
                t.overall_progress_update.connect(self.handle_folder_overall_progress)
                t.finished_signal.connect(self.thread_finished)
                self.folder_threads.append(t)

            self.start_time = time.time()
            self.timer.start(500)
            self.start_button.setEnabled(False)
            for t in self.folder_threads:
                t.start()
        else:
            QMessageBox.warning(self, "错误", "无效的源路径！")

    # 文件模式进度更新槽
    def handle_file_progress(self, thread_index, bytes_copied):
        self.thread_progress[thread_index] += bytes_copied
        self.total_bytes_copied += bytes_copied
        thread_total = self.threads[thread_index].total_bytes
        percent = int((self.thread_progress[thread_index] / thread_total) * 100)
        self.thread_progress_bars[thread_index].setValue(percent)
        self.overall_progress.setValue(self.total_bytes_copied)

    # 文件夹模式：更新当前线程复制文件的进度百分比
    def handle_folder_thread_progress(self, thread_index, percentage):
        self.thread_progress_bars[thread_index].setValue(percentage)

    # 文件夹模式：更新整体进度（累计字节数）
    def handle_folder_overall_progress(self, bytes_copied):
        self.total_bytes_copied += bytes_copied
        self.overall_progress.setValue(self.total_bytes_copied)

    def update_status(self):
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            speed = self.total_bytes_copied / elapsed  # B/s
            remaining_bytes = self.total_file_size - self.total_bytes_copied
            remaining_time = remaining_bytes / speed if speed > 0 else 0
        else:
            speed = 0
            remaining_time = 0

        self.info_label.setText(
            f"总大小: {self.total_file_size} 字节 | 复制速度: {self.format_size(speed)}/s | 剩余时间: {int(remaining_time)} s"
        )
        if self.total_bytes_copied >= self.total_file_size:
            self.timer.stop()
            self.start_button.setEnabled(True)
            QMessageBox.information(self, "完成", "复制任务已完成！")

    def thread_finished(self, thread_index):
        print(f"线程 {thread_index} 完成复制。")

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f}{unit}"
            size /= 1024
        return f"{size:.2f}PB"

if __name__ == "__main__":
    # 命令行参数解析：
    # --register：注册右键菜单
    # --unregister：注销右键菜单
    # 其他参数视为预选的源路径
    preselected_path = None
    if len(sys.argv) > 1:
        if "--register" in sys.argv:
            if platform.system() == "Windows":
                register_context_menu()
            else:
                print("仅支持Windows平台的右键菜单注册")
            sys.exit(0)
        elif "--unregister" in sys.argv:
            if platform.system() == "Windows":
                unregister_context_menu()
            else:
                print("仅支持Windows平台的右键菜单注销")
            sys.exit(0)
        else:
            preselected_path = sys.argv[1]

    app = QApplication(sys.argv)
    window = MainWindow(preselected_path)
    window.show()
    sys.exit(app.exec_())
