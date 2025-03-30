# main_window.py
import json
import logging
import os
import sys
import time
import re
import shutil
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import Qt, QPoint
import PyQt5.QtCore as QtCore
from PyQt5.QtGui import QPixmap, QPainter, QColor, QMouseEvent, QPen
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QGraphicsDropShadowEffect, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QPushButton, QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget, QMessageBox, QGridLayout
)

import config
from core import screen_controller
from core.recorder import ActionRecorder
from core.api.client import APIClient
import utils

class HistoryComboBox(QComboBox):
    """带历史记录功能的下拉框组件"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_style()
        self.load_history()

    def _setup_style(self) -> None:
        self.setStyleSheet("""
            QComboBox {
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 16px;
                background: white;
                min-width: 180px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid #e0e0e0;
            }
            QComboBox::down-arrow {
                image: url(icons/down-arrow.svg);
                width: 16px;
                height: 16px;
            }
            QComboBox:hover { border-color: #bdbdbd; }
            QComboBox:focus { border-color: #2196F3; }
        """)


    def load_history(self) -> None:
        """加载历史指令"""
        self.clear()
        instructions = utils.load_instruction_history(config.PRE_ACTIONS_PATH)
        self.addItems(instructions)
        self.addItem("无")
        self.setCurrentIndex(-1)

class ControlButton(QPushButton):
    """统一风格的控制按钮"""
    
    def __init__(self, text, color="#4CAF50", parent=None):
        super().__init__(text, parent)
        self._base_color = color
        self._setup_style()
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def _setup_style(self) -> None:
        self.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self._base_color}, stop:1 {self._darken_color()});
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                min-width: 100px;
                padding: 8px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{ 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {self._darken_color()}, stop:1 {self._base_color});
            }}
            QPushButton:pressed {{
                background: {self._darken_color()};
                padding: 7px 15px;
            }}
        """)
    def _darken_color(self) -> str:
        """生成加深颜色"""
        return f"hsl({self._base_color.lstrip('#')}, 80%, 35%)" if '#' in self._base_color else self._base_color

class FloatingWindow(QMainWindow):
    """主悬浮窗口"""
    
    def __init__(self, controller: screen_controller.PyAutoGUIWrapper):
        app = QApplication(sys.argv)
        super().__init__()
        self.controller = controller
        self.api_client = APIClient()
        self.recorder = ActionRecorder()
        
        # 初始化属性
        self._init_properties()
        
        # 设置窗口和UI
        self._setup_window()
        self._setup_ui()
        
        self.show()
        sys.exit(app.exec_())

    # ===== 初始化和设置方法 =====
    
    def _init_properties(self) -> None:
        """初始化窗口属性"""
        self.stop_requested = False
        self.dragging = False
        self.old_pos = QPoint()
        self._pending_click_timer = None

    def _setup_window(self) -> None:
        """窗口基本设置"""
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        
        # 获取屏幕尺寸
        desktop = QApplication.desktop()
        if desktop is not None:
            screen_geo = desktop.availableGeometry()
        else:
            logging.error("QApplication.desktop() 返回 None，无法获取屏幕可用区域。")
            screen_geo = None
            
        window_width = 580
        window_height = 70

        # 置顶
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # 计算居中底部位置
        if screen_geo is not None:
            x = (screen_geo.width() - window_width) // 2
            y = screen_geo.height() - window_height
            self.setGeometry(x, y, window_width, window_height)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setWindowOpacity(0.98)  # 轻微透明效果
            self.setStyleSheet("background-color: rgba(255, 255, 255, 0.7); border-radius: 14px;")
    
    def _add_shadow_effect(self) -> None:
        """添加阴影效果"""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(4, 4)
        self.setGraphicsEffect(shadow)

    def _setup_ui(self) -> None:
        """初始化界面组件"""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        # 创建UI组件
        self._create_ui_components()
        
        # 布局管理
        self._arrange_ui_components(layout)
        
        # 根据模式更新UI
        self.mode_combo.currentIndexChanged.connect(self._update_ui_by_mode)

    def _create_ui_components(self) -> None:
        """创建UI组件"""
        # 模式选择框
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("🛠️ 单步执行")
        self.mode_combo.addItem("🔧 工作流生成")
        self.mode_combo.addItem("📹 操作录制") 
        self.mode_combo.setCurrentIndex(0)
        self._setup_mode_combo_style()

        # 输入组件
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("🖋️ 输入指令...")
        self.input_box.setMinimumWidth(200)
        self._setup_input_style()

        # 历史下拉框
        self.history_combo = HistoryComboBox()

        # 功能按钮
        self.submit_btn = ControlButton("执行", "#4CAF50")
        self.detail_btn = ControlButton("详情", "#4CAF50")
        self.stop_btn = ControlButton("停止", "#f44336")
        self.submit_btn.setToolTip("执行当前指令（Enter）")
        self.detail_btn.setToolTip("查看操作历史详情")
        self.stop_btn.setToolTip("停止当前操作（Esc）")

        # 录制按钮
        self.record_btn = ControlButton("录制", "#4CAF50")
        self.stop_record_btn = ControlButton("停止录制", "#f44336")
        self.record_btn.setToolTip("开始录制操作")
        self.stop_record_btn.setToolTip("停止录制操作")
        self.stop_record_btn.setVisible(False)  # 初始隐藏停止按钮

        # 信号连接
        self._connect_signals()

    def _connect_signals(self) -> None:
        """连接信号和槽"""
        self.submit_btn.clicked.connect(self.process_input)
        self.detail_btn.clicked.connect(self.on_detail_clicked)
        self.stop_btn.clicked.connect(self.on_stop_clicked)
        self.record_btn.clicked.connect(self.on_record_clicked)
        self.stop_record_btn.clicked.connect(self.on_stop_record_clicked)

    def _arrange_ui_components(self, layout: QHBoxLayout) -> None:
        """布局UI组件"""
        layout.addWidget(self.mode_combo) 
        layout.addWidget(self.input_box)
        layout.addWidget(self.history_combo)
        layout.addWidget(self.submit_btn)
        layout.addWidget(self.detail_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.record_btn)
        layout.addWidget(self.stop_record_btn)

    def _setup_mode_combo_style(self) -> None:
        """设置模式选择框样式"""
        self.mode_combo.setStyleSheet("""
            QComboBox {
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 14px;
                background: white;
                min-width: 120px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid #e0e0e0;
            }
            QComboBox:hover { border-color: #bdbdbd; }
            QComboBox:focus { border-color: #2196F3; }
        """)

    def _setup_input_style(self) -> None:
        """设置输入框样式"""
        self.input_box.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e0e0e0;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 16px;
                background: white;
            }
            QLineEdit:focus {
                border: 2px solid #2196F3;
                background: #f5fdff;
            }
            QLineEdit:hover { border-color: #bdbdbd; }
        """)

    # ===== UI更新方法 =====
    
    def _update_ui_by_mode(self, index: int) -> None:
        """根据当前模式更新UI显示"""
        # 录制模式
        if index == 2:  # 录制模式
            self.input_box.setPlaceholderText("输入录制名称...")
            self.record_btn.setVisible(True)
            self.submit_btn.setVisible(False)
            self.detail_btn.setVisible(False)
            self.stop_btn.setVisible(False)
        else:  # 其他模式
            self.input_box.setPlaceholderText("🖋️ 输入指令...")
            self.record_btn.setVisible(False)
            self.stop_record_btn.setVisible(False)
            self.submit_btn.setVisible(True)
            self.detail_btn.setVisible(True)
            self.stop_btn.setVisible(True)

    def keep_running(self) -> None:
        """开始执行时状态"""
        self.input_box.clear()
        self.stop_requested = False  # 重置停止标志
        utils.update_status(self.input_box, "正在执行...")

    def finish_running(self) -> None:
        """完成执行时状态"""
        self.input_box.clear()
        utils.update_status(self.input_box, "输入指令...")
        self.stop_requested = False

    # ===== 事件处理方法 =====
    
    def on_stop_clicked(self) -> None:
        """停止按钮点击事件处理"""
        self.stop_requested = True
        utils.update_status(self.input_box, "操作已停止")
        logging.info("用户请求停止当前操作")

    def on_detail_clicked(self) -> None:
        """详情按钮点击事件处理"""
        try:
            history_data = utils.load_action_history(config.PRE_ACTIONS_PATH + f"/{self.history_combo.currentText()}")
            self.show_detail_dialog(history_data)
        except Exception as e:
            logging.error(f"加载历史操作失败: {str(e)}")
            utils.update_status(self.input_box, f"加载失败: {str(e)}")
    
    def on_record_clicked(self) -> None:
        """开始录制按钮点击事件"""
        recording_name = self.input_box.text().strip()
        if not recording_name:
            utils.update_status(self.input_box, "请输入录制名称")
            return
            
        # 开始录制
        if self.recorder.start_recording():
            utils.update_status(self.input_box, f"正在录制: {recording_name}")
            self.record_btn.setVisible(False)
            self.stop_record_btn.setVisible(True)
            logging.info(f"开始录制: {recording_name}")
        else:
            utils.update_status(self.input_box, "录制启动失败")
    
    def on_stop_record_clicked(self) -> None:
        """停止录制按钮点击事件"""
        recording_name = self.input_box.text().strip()
        
        # 停止录制
        if self.recorder.stop_recording():
            # 保存录制结果
            if self.recorder.save_recording(recording_name):
                utils.update_status(self.input_box, f"录制已保存: {recording_name}")
                logging.info(f"录制已保存: {recording_name}")
                
                # 刷新历史记录
                self.history_combo.load_history()
            else:
                utils.update_status(self.input_box, "录制保存失败")
                
            self.record_btn.setVisible(True)
            self.stop_record_btn.setVisible(False)
        else:
            utils.update_status(self.input_box, "录制停止失败")

    def mousePressEvent(self, event: Optional[QMouseEvent]) -> None:
        """鼠标按下事件处理"""
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.old_pos = event.globalPos()
            event.accept()

    def mouseMoveEvent(self, event: Optional[QMouseEvent]) -> None:
        """处理窗口拖动事件"""
        if event and self.dragging:
            # 计算位置偏移量时转换为相对坐标
            delta = event.globalPos() - self.old_pos
            new_pos = self.pos() + delta
            self.move(new_pos)
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, a0):
        self.dragging = False

    # ===== 文件和数据处理方法 =====

    def _create_backup(self) -> None:
        """创建带时间戳的备份文件"""
        try:
            backup_dir = os.path.join(config.PRE_ACTIONS_PATH, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copyfile(
                os.path.join(config.PRE_ACTIONS_PATH, self.history_combo.currentText()),
                os.path.join(backup_dir, f"{time.strftime('%Y%m%d%H%M%S')}.bak")
            )
        except Exception as e:
            logging.error(f"创建备份文件失败: {str(e)}")

    def show_detail_dialog(self, data):
        """显示简洁版操作详情对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("📋 操作详情")
        dialog.setFixedSize(1000, 600)  # 调整对话框尺寸以容纳更多参数
        dialog.setStyleSheet("""
            QDialog { background: #f8f9fa; }
            QListWidget { 
                background: white; 
                border-radius: 6px;
                border: 1px solid #dee2e6;
                font-size: 14px;
            }
            QPushButton {
                background: #4a90e2;
                color: white;
                border-radius: 4px;
                padding: 8px 16px;
                min-width: 80px;
                font-size: 14px;
            }
            QPushButton:hover { background: #357abd; }
            QGroupBox { 
                border: 1px solid #dee2e6; 
                border-radius: 6px;
                margin-top: 1ex;
                font-size: 14px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                padding: 6px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                min-height: 28px;
            }
        """)

        # 主布局
        main_layout = QHBoxLayout(dialog)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 左侧操作列表
        list_widget = QListWidget()
        list_widget.setFixedWidth(220)
        list_widget.setStyleSheet("""
            QListWidget::item { 
                padding: 12px;
                border-bottom: 1px solid #eee; 
            }
            QListWidget::item:selected { 
                background: #e9ecef; 
                color: #495057;
            }
        """)
        main_layout.addWidget(list_widget)

        # 右侧编辑区域
        edit_area = QVBoxLayout()
        edit_area.setSpacing(15)

        # 操作类型和目标输入
        top_row = QHBoxLayout()
        type_combo = QComboBox()
        type_combo.addItems(['click', 'open', 'scroll', 'input', 'hotkey', 'press_enter', 'finish'])
        target_edit = QLineEdit()
        top_row.addWidget(QLabel("类型:"), 1)
        top_row.addWidget(type_combo, 3)
        top_row.addWidget(QLabel("目标:"), 1)
        top_row.addWidget(target_edit, 5)
        edit_area.addLayout(top_row)

        # 参数设置分组
        param_group = QGroupBox("参数设置（空值将保存为null）")
        param_layout = QFormLayout(param_group)
        param_layout.setRowWrapPolicy(QFormLayout.DontWrapRows)
        param_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        param_layout.setLabelAlignment(Qt.AlignRight)
        
        # 坐标参数
        x_edit = QDoubleSpinBox()
        x_edit.setRange(0, 9999.99)
        y_edit = QDoubleSpinBox()
        y_edit.setRange(0, 9999.99)
        param_layout.addRow("X坐标:", x_edit)
        param_layout.addRow("Y坐标:", y_edit)

        # 点击参数
        clicks_edit = QSpinBox()
        clicks_edit.setRange(1, 5)
        button_combo = QComboBox()
        button_combo.addItems(["left", "right", "middle"])
        param_layout.addRow("点击次数:", clicks_edit)
        param_layout.addRow("按钮类型:", button_combo)

        # 输入参数
        text_edit = QLineEdit()
        param_layout.addRow("输入文本:", text_edit)

        # 滚动参数
        direction_combo = QComboBox()
        direction_combo.addItems(["up", "down", "left", "right"])
        param_layout.addRow("滚动方向:", direction_combo)

        # 快捷键参数
        key_edit = QLineEdit()
        key_edit.setPlaceholderText("用英文逗号分隔，例如：ctrl,c")
        param_layout.addRow("组合键序列:", key_edit)

        edit_area.addWidget(param_group)

        # 按钮布局
        btn_layout = QHBoxLayout()
        trail_btn = QPushButton("轨迹预览")
        btn_save = QPushButton("保存修改")
        btn_cancel = QPushButton("关闭")
        btn_layout.addWidget(trail_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        edit_area.addLayout(btn_layout)

        main_layout.addLayout(edit_area)

        # 初始化列表数据
        for i, action in enumerate(data, 1):
            item_text = f"操作{i}: {action.get('action', '未知')}"
            list_widget.addItem(item_text)

        def update_form(index):
            """更新表单内容"""
            action = data[index]
            action_type = action.get('action', '点击')
            params = action.get('params', {})
            
            # 设置基础字段
            type_combo.setCurrentText(action_type)
            target_edit.setText(action.get('target', ''))
            
            # 设置所有参数控件
            x_edit.setValue(params.get('x', 0.0))
            y_edit.setValue(params.get('y', 0.0))
            clicks_edit.setValue(params.get('clicks', 1))
            button_combo.setCurrentText(params.get('button_type', 'left'))
            text_edit.setText(params.get('text_content', ''))
            direction_combo.setCurrentText(params.get('direction', 'up'))
            key_edit.setText(','.join(params.get('key_sequence', [])) if params.get('key_sequence') else "")

        def save_changes():
            try:
                current_row = list_widget.currentRow()
                if 0 <= current_row < len(data):
                    # 收集所有参数
                    new_params = {
                        'x': x_edit.value() or None,
                        'y': y_edit.value() or None,
                        'clicks': clicks_edit.value() if clicks_edit.value() > 1 else None,
                        'button_type': button_combo.currentText() or None,
                        'text_content': text_edit.text().strip() or None,
                        'direction': direction_combo.currentText() or None,
                        'key_sequence': [k.strip() for k in key_edit.text().split(',')] if key_edit.text() else None
                    }
                    
                    # 转换空值为"null"
                    final_params = {k: v if v is not None and v != [] else "null" for k, v in new_params.items()}
                    
                    # 创建备份
                    backup_path = os.path.join(config.PRE_ACTIONS_PATH, "backups")
                    os.makedirs(backup_path, exist_ok=True)
                    shutil.copyfile(
                        os.path.join(config.PRE_ACTIONS_PATH, self.history_combo.currentText()),
                        os.path.join(backup_path, f"{time.strftime('%Y%m%d%H%M%S')}.bak")
                    )

                    # 更新数据
                    data[current_row].update({
                        "action": type_combo.currentText(),
                        "target": target_edit.text().strip(),
                        "params": final_params
                    })

                    # 读取原始文件内容
                    file_path = os.path.join(config.PRE_ACTIONS_PATH, self.history_combo.currentText())
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()

                    # 只修改当前操作行
                    if current_row < len(lines):
                        # 构建新行并保留末尾换行符
                        new_line = json.dumps(data[current_row], ensure_ascii=False)
                        new_line += '\n'
                        lines[current_row] = new_line

                    # 写回文件（保留其他行不变）
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.writelines(lines)

                    # 异步备份（保持原备份逻辑不变）
                    QtCore.QTimer.singleShot(0, lambda: self._create_backup())

                    QMessageBox.information(dialog, "保存成功", "修改已保存")
                    logging.info("修改已保存")
                    
            except Exception as e:
                QMessageBox.critical(dialog, "保存错误", f"保存失败: {str(e)}")
                logging.exception("保存操作时发生异常")

        # 信号连接
        list_widget.currentRowChanged.connect(
            lambda i: update_form(i) if 0 <= i < len(data) else None)
        btn_save.clicked.connect(save_changes)
        btn_cancel.clicked.connect(dialog.reject)
        trail_btn.clicked.connect(lambda: self.show_trail(data))

        # 初始化显示
        if data:
            list_widget.setCurrentRow(0)
            update_form(0)
            
        return dialog.exec_()

    def _save_data(self, data):
        """异步保存数据"""
        try:
            with open(f"{config.PRE_ACTIONS_PATH}/{self.history_combo.currentText()}", 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            utils.update_status(self.input_box, "✅ 修改已保存")
        except Exception as e:
            utils.update_status(self.input_box, f"❌ 保存失败: {str(e)}")   

    def _save_execution_time(self, instruction, total_time, is_workflow=False):
        """保存指令执行时间记录"""
        try:
            mode = "workflow" if is_workflow else "single_step"
            record = {
                "instruction": instruction,
                "time": round(total_time, 2),
                "mode": mode,
            }
            
            # 以jsonl格式保存到当前目录
            with open("execution_times.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                
            logging.info(f"已记录执行时间: {instruction} - {round(total_time, 2)}秒")
        except Exception as e:
            logging.error(f"保存执行时间记录失败: {str(e)}")

    def show_trail(self, data):
        """显示轨迹窗口"""
        valid_actions = [a for a in data if a.get('coord')]
        if valid_actions:
            trail_window = OperationTrailWindow(valid_actions, self)
            trail_window.exec_()
        else:
            utils.update_status(self.input_box, "当前操作无有效坐标记录")

    def _execute_pre_actions(self, actions):
        """执行预存操作序列"""
        self.keep_running()
        try:
            for action in actions:
                if self.stop_requested:
                    break
                
                print(f"执行动作: {action}")
                hwnd_titles = utils.get_all_windows_titles()

                utils.execute_action(self.controller, action, None)

                # 比较hwnd_titles
                new_hwnd_titles = utils.get_all_windows_titles()
                # 获得新打开的窗口标题
                new_windows = set(new_hwnd_titles) - set(hwnd_titles)
                if new_windows:
                    # 获取第一个新窗口的句柄
                    new_window_title = next(iter(new_windows))
                    try:
                        hwnd = self.controller.find_window_by_title(new_window_title)
                        self.controller.maximize_window(hwnd)
                    except Exception as e:
                        logging.error(f"窗口最大化失败: {str(e)}")
                print(f"动作执行完成")

                # 延迟两秒
                time.sleep(2)
            utils.update_status(self.input_box, "预存操作执行完成")
        except Exception as e:
            logging.error(f"预存操作执行失败: {str(e)}")
            utils.update_status(self.input_box, f"执行错误: {str(e)}")
        finally:
            self.finish_running()

    def _wait_for_screenshot_delay(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(int(config.SCREENSHOT_DELAY * 1000), loop.quit)
        loop.exec_()

    def _take_and_log_screenshot(self, image_path=config.SCREENSHOT_PATH):
        utils.update_status(self.input_box, "正在截图...")
        screenshot_duration = utils.take_screenshot(self.controller, image_path)
        utils.log_operation("截图", "屏幕", {}, screenshot_duration, "success")

    def _extract_curr_objs(self, objs):
        return [{"id": obj["id"], "type": obj["type"], "content": obj["content"]} for obj in objs]

    def _parse_and_log_instruction(self, instruction, pre_actions, curr_objs, analysis="", type='text'):
        utils.update_status(self.input_box, "正在解析指令...")
        action, _ = utils.parse_instruction(instruction, pre_actions, curr_objs, analysis, type)
        utils.log_operation("解析指令", "screen", {}, 0, "success")
        return action

    def _process_and_log_image(self):
        utils.update_status(self.input_box, "正在解析界面元素...")
        result, _ = utils.process_image()
        utils.log_operation("处理图像", "screen", {}, 0, "success")
        return result

    def _save_labeled_image(self, result):
        labeled_image = result.labeled_image
        if labeled_image:
            try:
                labeled_image.save(config.LABELED_IMAGE_PATH)
            except Exception as e:
                logging.error(f"保存标记图像失败: {str(e)}", exc_info=True)
                utils.update_status(self.input_box, f"保存标记图像失败: {str(e)}")
                time.sleep(2)

    def _parse_and_log_data(self, result):
            objs, _ = utils.parse_data(result.parsed_content) 
            utils.log_operation("解析数据", "screen", {}, 0, "success")
            return objs

    def process_input(self):
        """处理用户输入（支持预存操作执行）"""
        # 获取输入内容或选中历史操作
        is_workflow_mode = self.mode_combo.currentIndex() == 1
        is_record_mode = self.mode_combo.currentIndex() == 2

        # 录制模式下不处理输入
        if is_record_mode:
            return

        instruction = self.history_combo.currentText()
        start_time = time.time()  # 记录开始时间

        # 尝试解析预存操作数据
        if instruction and instruction != "" and instruction != "无":
            try:
                history_data = utils.load_action_history(config.PRE_ACTIONS_PATH + f"/{instruction}")
                logging.info(f"开始执行预存操作: {instruction}")

                self.input_box.clear()
                utils.update_status(self.input_box, f"开始执行预存操作: {instruction}")

                self._execute_pre_actions(history_data)
                print(history_data)

                utils.update_status(self.input_box, f"预存操作 {instruction} 执行完成，耗时: {total_time:.2f}秒")
                logging.info(f"预存操作 {instruction} 执行完成，耗时: {total_time:.2f}秒")

                # 记录执行时间
                self._save_execution_time(instruction, total_time)
                return

            except Exception as e:
                logging.error(f"预存操作解析失败: {str(e)}")
                utils.update_status(self.input_box, "操作数据格式错误")
                return

        instruction = self.input_box.text()
        self.keep_running()
        start_time = time.time()
        pre_actions = []

        if is_workflow_mode:
            try:
                # 调用大模型生成工作流
                utils.update_status(self.input_box, "正在生成工作流...")
                workflow,_ = utils.generate_workflow(instruction)
                utils.update_status(self.input_box, f"工作流生成完成，耗时 {time.time() - start_time:.2f} 秒")
                
                # 弹出确认对话框
                confirm_dialog = QDialog(self)
                confirm_dialog.setWindowTitle("工作流确认")
                confirm_dialog.setFixedSize(400, 300)
                
                layout = QVBoxLayout(confirm_dialog)
                layout.addWidget(QLabel(f"生成 {len(workflow)} 个步骤："))
                print("生成工作流：", workflow)
                
                # 显示工作流步骤
                list_widget = QListWidget()
                for step, action in enumerate(workflow, 1):
                    list_widget.addItem(f"步骤 {step}: {action}")
                layout.addWidget(list_widget)
                
                # 确认按钮
                btn_box = QHBoxLayout()
                btn_confirm = QPushButton("执行工作流")
                btn_cancel = QPushButton("取消")
                btn_box.addWidget(btn_confirm)
                btn_box.addWidget(btn_cancel)
                
                # 传递指令和开始时间给执行函数
                btn_confirm.clicked.connect(lambda: self._execute_workflow(workflow, confirm_dialog, instruction, start_time))
                btn_cancel.clicked.connect(confirm_dialog.reject)
                
                layout.addLayout(btn_box)
                
                confirm_dialog.exec_()
            except Exception as e:
                print(e)
                utils.update_status(self.input_box, f"工作流生成失败: {str(e)}")
            return

        try:
            if not instruction:
                utils.update_status(self.input_box, "指令不能为空")
                raise ValueError("指令不能为空")
            logging.info(f"开始处理指令: {instruction}")

            while not self.stop_requested:
                hwnd_titles = utils.get_all_windows_titles()

                self._take_and_log_screenshot(config.PRE_DESKTOP_PATH)
                self._wait_for_screenshot_delay()
                if self.stop_requested:
                    break

                # 截图操作
                self._take_and_log_screenshot()

                if self.stop_requested:
                    break

                # 图像处理
                result = self._process_and_log_image()
                if self.stop_requested:
                    break

                if result.status == 'success': 
                    # 保存标记图像
                    self._save_labeled_image(result)

                    # 解析数据
                    objs = self._parse_and_log_data(result)
                    curr_objs = self._extract_curr_objs(objs)

                    # 指令解析
                    utils.update_status(self.input_box, "分析者正在分析...")
                    analysis = self._parse_and_log_instruction(instruction, pre_actions, curr_objs, type='omni')
                    print("分析者输出：", analysis)
                    utils.update_status(self.input_box, "总结者正在总结...")
                    action = self._parse_and_log_instruction(instruction, pre_actions, curr_objs, analysis=analysis) 
                    print("总结者输出：", action)

                    # 执行动作
                    utils.update_status(self.input_box, "正在执行操作...")
                    if action is None:
                        continue
                    action_data = utils.robust_json_extract(action)
                    print()
                    action_result = utils.execute_action(self.controller, action_data, objs)
                    if action_result is None:
                        break
                    action_type, target_icon, params, execute_duration, status, action_data = action_result
                    print("执行对象：", action_data)
                    utils.log_operation(action_type, target_icon, params, execute_duration, status)
                    if status == "success" and self.check_desktop_stabilized(action_type):
                        pre_actions.append(action_data)

                        # 比较hwnd_titles
                        new_hwnd_titles = utils.get_all_windows_titles()
                        # 获得新打开的窗口标题
                        new_windows = set(new_hwnd_titles) - set(hwnd_titles)
                        if new_windows:
                            # 获取第一个新窗口的句柄
                            new_window_title = next(iter(new_windows))
                            try:
                                hwnd = self.controller.find_window_by_title(new_window_title)
                                self.controller.maximize_window(hwnd)
                            except Exception as e:
                                logging.error(f"窗口最大化失败: {str(e)}")
                    else:
                        # 当前执行并没有改变状态，需要重新执行
                        continue

                else:   
                    utils.update_status(self.input_box, f"操作失败: {result.message}")
                    break
            # 保存操作记录
            if not self.stop_requested:
                os.remove(config.SCREENSHOT_PATH)
                os.remove(config.LABELED_IMAGE_PATH)
                os.remove(config.PRE_DESKTOP_PATH)
                with open(config.PRE_ACTIONS_PATH + "/" + f"{instruction}.jsonl", 'w', encoding='utf-8') as f:
                    for action in pre_actions:
                        f.write(json.dumps(action, ensure_ascii=False) + '\n')

        except Exception as e:
            logging.error(f"指令执行过程中出现异常: {str(e)}", exc_info=True)
            utils.update_status(self.input_box, f"操作失败: {str(e)}")
            time.sleep(2)
        finally:
            total_duration = time.time() - start_time
            status_message = "操作已停止" if self.stop_requested else f"操作完成，总耗时: {total_duration:.2f}秒"
            utils.update_status(self.input_box, status_message)
            
            # 记录执行时间
            if not self.stop_requested:
                self._save_execution_time(instruction, total_duration)

            self.finish_running()

    def _execute_workflow(self, workflow, dialog, instruction, start_time=None):
        """执行生成的工作流（带失败降级处理）"""
        dialog.accept()
        if start_time is None:
            start_time = time.time()  # 如果没有传入开始时间，则记录当前时间
            
        try:
            pre_actions = []
            for step_idx, step in enumerate(workflow, 1):
                if self.stop_requested:
                    break
                
                try:
                    hwnd_titles = utils.get_all_windows_titles()

                    # 工作流模式执行
                    utils.update_status(self.input_box, f"正在执行工作流步骤{step_idx}...")
                    result = utils.execute_action(self.controller, step, None, True)

                    # 比较hwnd_titles
                    new_hwnd_titles = utils.get_all_windows_titles()
                    # 获得新打开的窗口标题
                    new_windows = set(new_hwnd_titles) - set(hwnd_titles)
                    if new_windows:
                        # 获取第一个新窗口的句柄
                        new_window_title = next(iter(new_windows))
                        try:
                            hwnd = self.controller.find_window_by_title(new_window_title)
                            self.controller.maximize_window(hwnd)
                        except Exception as e:
                            logging.error(f"窗口最大化失败: {str(e)}")

                    if self.check_desktop_stabilized(step["action"]):
                        pre_actions.append(step)

                    pre_actions.append(step)
                    time.sleep(1)  # 步骤间间隔


                except Exception as e:
                    logging.error(f"工作流步骤{step_idx}执行失败，启动降级处理: {str(e)}")
                    # 失败时切换为单步执行模式
                    success = self._handle_failed_step(instruction, pre_actions, step, step_idx)
                    if not success:
                        raise RuntimeError(f"步骤{step_idx}降级执行失败") from e
                
                time.sleep(1)  # 步骤间间隔
            
            total_time = time.time() - start_time
            print("工作流执行完成，耗时:", total_time)
            utils.update_status(self.input_box, f"✅ 工作流执行完成，耗时: {total_time:.2f}秒")
            
            # 记录工作流执行时间
            self._save_execution_time(instruction, total_time, is_workflow=True)
            
        except Exception as e:
            print(e)
            total_time = time.time() - start_time
            utils.update_status(self.input_box, f"❌ 工作流执行失败: {str(e)}，耗时: {total_time:.2f}秒")
            
            self._save_execution_time(instruction, total_time, is_workflow=True)

    def _handle_failed_step(self, instruction, pre_actions, failed_step, step_number):
        """处理失败的工作流步骤"""
        try:
            # 保存原始模式并切换为单步模式
            original_mode = self.mode_combo.currentIndex()
            self.mode_combo.setCurrentIndex(0)  # 切换到单步模式
            
            # 使用常规流程执行步骤
            utils.update_status(self.input_box, f"AI介入{failed_step}")
            print("AI介入：", failed_step)
            # 截图、处理图像、解析数据
            while True:
                hwnd_titles = utils.get_all_windows_titles()

                self._take_and_log_screenshot(config.PRE_DESKTOP_PATH)
                self._wait_for_screenshot_delay()
                self._take_and_log_screenshot()
                result = self._process_and_log_image()
                self._save_labeled_image(result)
                objs = self._parse_and_log_data(result)
                curr_objs = self._extract_curr_objs(objs)
                
                instruction = failed_step
                analasis = self._parse_and_log_instruction(instruction, [], curr_objs, type='omni')
                print("分析者输出：", analasis)
                action = self._parse_and_log_instruction(instruction, [], curr_objs, analysis=analasis)
                # 执行动作
                utils.update_status(self.input_box, "正在执行操作...")
                if action is None:
                    return False
                action_data = utils.robust_json_extract(action)
                action_result = utils.execute_action(self.controller, action_data, objs)
                if action_result is None:
                    return True
                action_type, target_icon, params, execute_duration, status, action_data = action_result
                print("执行对象：", action_data)
                utils.log_operation(action_type, target_icon, params, execute_duration, status)
                if status == "success" and self.check_desktop_stabilized(action_type):
                        pre_actions.append(action_data)

                        # 比较hwnd_titles
                        new_hwnd_titles = utils.get_all_windows_titles()
                        # 获得新打开的窗口标题
                        new_windows = set(new_hwnd_titles) - set(hwnd_titles)
                        if new_windows:
                            # 获取第一个新窗口的句柄
                            new_window_title = next(iter(new_windows))
                            try:
                                hwnd = self.controller.find_window_by_title(new_window_title)
                                self.controller.maximize_window(hwnd)
                            except Exception as e:
                                logging.error(f"窗口最大化失败: {str(e)}")
                else:
                    # 当前执行并没有改变状态，需要重新执行
                    continue
        finally:
            self.mode_combo.setCurrentIndex(original_mode)

    def _retry_with_omni(self, step, step_number):
        """使用完整流程重试步骤"""
        try:
            # 构造模拟指令
            fake_instruction = json.dumps(step, ensure_ascii=False)
            self.input_box.setText(fake_instruction)
            
            # 执行完整处理流程
            self.process_input()
            return not self.stop_requested
        except Exception as e:
            logging.error(f"步骤{step_number}完整流程重试失败: {str(e)}")
            return False

    def check_desktop_stabilized(self, action_type):
        """检查桌面状态是否发生变化
        返回True表示发生了变化，False表示没有变化
        """
        if action_type not in ["click", "open","scroll"]:
            # 不进行桌面状态检查的操作
            return True

        try:
            if not os.path.exists(config.PRE_DESKTOP_PATH):
                logging.warning("缺少历史桌面截图")
                return False
                
            for attempt in range(4):
                # 截取当前桌面
                self._take_and_log_screenshot(config.CURRENT_DESKTOP_PATH)
                
                # 比较相似度
                similarity = utils.compare_image_similarity(
                    config.PRE_DESKTOP_PATH,
                    config.CURRENT_DESKTOP_PATH
                )
                
                if similarity["ssim"] < 0.98 and similarity["mse"] > 100:
                    print("桌面状态发生变化")
                    if os.path.exists(config.PRE_DESKTOP_PATH):
                        os.remove(config.PRE_DESKTOP_PATH)
                    os.rename(config.CURRENT_DESKTOP_PATH, config.PRE_DESKTOP_PATH)
                    return True
                    
                attempt += 1
                time.sleep(1)  # 等待1秒后重试
                
            logging.warning("桌面状态未在4秒内发生变化")
            return False
            
        except FileNotFoundError as e:
            logging.error(f"截图文件缺失: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"稳定性检查异常: {str(e)}")
            return False

class OperationTrailWindow(QDialog):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.actions = actions
        self.setWindowTitle("操作轨迹可视化")
        self.setFixedSize(1200, 800)
        self.scale_factor = 1.0
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # 画布区域
        self.canvas = QLabel(self)
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setStyleSheet("background: white; border: 1px solid #ddd;")
        
        # 控制面板
        control_panel = QHBoxLayout()
        self.zoom_in_btn = QPushButton("放大+")
        self.zoom_out_btn = QPushButton("缩小-")
        self.reset_btn = QPushButton("重置视图")
        control_panel.addWidget(self.zoom_in_btn)
        control_panel.addWidget(self.zoom_out_btn)
        control_panel.addWidget(self.reset_btn)
        
        main_layout.addLayout(control_panel)
        main_layout.addWidget(self.canvas)
        
        # 连接信号
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.reset_btn.clicked.connect(self.reset_view)
        
        # 初始绘制
        self.draw_trail()
        
    def zoom_in(self):
        """放大视图"""
        self.scale_factor *= 1.2
        self.draw_trail()
        
    def zoom_out(self):
        """缩小视图"""
        self.scale_factor *= 0.8
        self.draw_trail()
        
    def reset_view(self):
        """重置视图"""
        self.scale_factor = 1.0
        self.draw_trail()
        
    def draw_trail(self):
        """绘制操作轨迹"""
        # 创建空白画布
        canvas_width, canvas_height = 1180, 740
        pixmap = QPixmap(canvas_width, canvas_height)
        pixmap.fill(Qt.white)
        
        # 创建绘图对象
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 计算坐标范围
        x_coords = [a.get('params', {}).get('x', 0) for a in self.actions if 'params' in a and 'x' in a.get('params', {})]
        y_coords = [a.get('params', {}).get('y', 0) for a in self.actions if 'params' in a and 'y' in a.get('params', {})]
        
        if not x_coords or not y_coords:
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "没有有效的坐标数据")
            painter.end()
            self.canvas.setPixmap(pixmap)
            return
            
        # 计算边界和缩放
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)
        
        # 添加边距
        margin = 50
        width = max(max_x - min_x, 100)
        height = max(max_y - min_y, 100)
        
        # 计算缩放比例
        scale_x = (canvas_width - 2 * margin) / width * self.scale_factor
        scale_y = (canvas_height - 2 * margin) / height * self.scale_factor
        scale = min(scale_x, scale_y)
        
        # 计算中心点
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        
        # 绘制坐标轴
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawLine(margin, canvas_height//2, canvas_width-margin, canvas_height//2)
        painter.drawLine(canvas_width//2, margin, canvas_width//2, canvas_height-margin)
        
        # 绘制轨迹线
        last_x, last_y = None, None
        for i, action in enumerate(self.actions):
            params = action.get('params', {})
            if 'x' in params and 'y' in params:
                # 转换坐标
                x = canvas_width/2 + (params['x'] - center_x) * scale
                y = canvas_height/2 + (params['y'] - center_y) * scale
                
                # 绘制点
                action_type = action.get('action', '')
                if action_type == 'click':
                    painter.setPen(QPen(QColor(255, 0, 0), 3))
                    painter.drawEllipse(x-5, y-5, 10, 10)
                elif action_type == 'open':
                    painter.setPen(QPen(QColor(0, 128, 0), 3))
                    painter.drawEllipse(x-7, y-7, 14, 14)
                else:
                    painter.setPen(QPen(QColor(0, 0, 255), 3))
                    painter.drawEllipse(x-3, y-3, 6, 6)
                
                # 绘制连线
                if last_x is not None and last_y is not None:
                    painter.setPen(QPen(QColor(100, 100, 100), 1, Qt.DashLine))
                    painter.drawLine(last_x, last_y, x, y)
                
                # 绘制序号
                painter.setPen(QColor(50, 50, 50))
                painter.drawText(x+10, y-10, str(i+1))
                
                last_x, last_y = x, y
        
        painter.end()
        self.canvas.setPixmap(pixmap)

def main():
    """主函数"""
    controller = screen_controller.PyAutoGUIWrapper()
    FloatingWindow(controller)

if __name__ == "__main__":
    main()