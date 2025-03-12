# main_window.py
import logging
import sys
import time
import json
from types import new_class
from PyQt5.QtCore import Qt, QPoint, QTimer, QEventLoop
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLineEdit,
                             QPushButton, QGraphicsDropShadowEffect, QDialog, QListWidget, QTextEdit)

from PyQt5.QtWidgets import QComboBox
import config
from utils import (log_operation, update_status, take_screenshot,
                   process_image, parse_data, parse_instruction,
                   execute_action, robust_json_extract)
import utils


class FloatingWindow(QMainWindow):
    def __init__(self, controller):
        app = QApplication(sys.argv)
        super().__init__()
        self.controller = controller
        self.stop_requested = False
        self.dragging = False
        self.old_pos = QPoint()
        self.initUI()
        self.show()
        sys.exit(app.exec_())

    def initUI(self):
        # 窗口基本设置
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setGeometry(200, 200, 560, 60)  # 调整窗口位置和宽度

        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(Qt.gray)
        self.setGraphicsEffect(shadow)

        # 输入框
        self.input_box = QLineEdit(self)
        self.input_box.setGeometry(20, 15, 180, 30)
        self.input_box.setPlaceholderText("输入指令...")
        self.input_box.setStyleSheet("""
            QLineEdit {
                border: 2px solid #cccccc;
                border-radius: 8px;
                padding: 5px;
                font-size: 14px;
            }
        """)

        # 历史下拉框
        self.history_combo = QComboBox(self)
        self.history_combo.setGeometry(210, 15, 90, 30)
        instructions = utils.load_instruction_history(config.PRE_ACTIONS_PATH)
        self.history_combo.addItems(instructions)
        # 一个置空的选项
        self.history_combo.addItem("")

        self.history_combo.setCurrentIndex(-1)  # 设置默认选中项为最后一个
        self.history_combo.setStyleSheet("""
            QComboBox {
                border: 2px solid #cccccc;
                border-radius: 8px;
                padding: 5px;
                font-size: 14px;
                background-color: white;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #cccccc;
                border-left-style: solid;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
            QComboBox::down-arrow {
                image: url(down_arrow.png); /* 替换为合适的箭头图标路径 */
                width: 10px;
                height: 10px;
            }
        """)

        # 执行按钮
        self.submit_btn = QPushButton("执行", self)
        self.submit_btn.setGeometry(310, 15, 80, 30)
        self.submit_btn.setToolTip("点击执行输入的指令")  # 添加工具提示
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)

        # 详情按钮
        self.detail_btn = QPushButton("详情", self)
        self.detail_btn.setGeometry(400, 15, 80, 30)
        self.detail_btn.clicked.connect(self.on_detail_clicked)
        self.detail_btn.setToolTip("点击查看具体操作步骤")  # 添加工具提示
        self.detail_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)

        self.submit_btn.clicked.connect(self.process_input)

        # 停止按钮
        self.stop_btn = QPushButton("停止", self)
        self.stop_btn.setGeometry(490, 15, 80, 30)
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.clicked.connect(self.on_stop_clicked)
        self.stop_btn.setToolTip("点击停止当前操作")  # 添加工具提示
        self.stop_btn.setStyleSheet("""
            QPushButton#stopButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 14px;
            }
            QPushButton#stopButton:hover {
                background-color: #d32f2f;
            }
            QPushButton#stopButton:pressed {
                background-color: #b71c1c;
            }
        """)

        # 按钮悬停效果增强
        button_stylesheet = """
            QPushButton:hover {
                border: 2px solid #ffffff;
                transform: scale(1.05);
            }
        """
        self.submit_btn.setStyleSheet(self.submit_btn.styleSheet() + button_stylesheet)
        self.detail_btn.setStyleSheet(self.detail_btn.styleSheet() + button_stylesheet)
        self.stop_btn.setStyleSheet(self.stop_btn.styleSheet() + button_stylesheet)

        # 输入框和下拉框焦点效果
        input_focus_stylesheet = """
            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #4CAF50;
            }
        """
        self.input_box.setStyleSheet(self.input_box.styleSheet() + input_focus_stylesheet)
        self.history_combo.setStyleSheet(self.history_combo.styleSheet() + input_focus_stylesheet)

    def on_stop_clicked(self):
        """停止按钮点击事件处理"""
        self.stop_requested = True
        update_status(self.input_box, "操作已停止")
        logging.info("用户请求停止当前操作")

    def keep_running(self):
        """开始执行时状态"""
        self.input_box.clear()
        self.stop_requested = False  # 重置停止标志
        update_status(self.input_box, "正在执行...")

    def finish_running(self):
        """完成执行时状态"""
        self.input_box.clear()
        update_status(self.input_box, "输入指令...")
        self.stop_requested = False

    def process_input(self):
        """处理用户输入（支持预存操作执行）"""
        # 获取输入内容或选中历史操作
        instruction = self.history_combo.currentText()

        # 尝试解析预存操作数据
        if instruction and instruction != "":
            try:
                history_data = utils.load_action_history(config.PRE_ACTIONS_PATH + f"/{instruction}")
                logging.info(f"开始执行预存操作: {instruction}")

                self.input_box.clear()
                update_status(self.input_box, f"开始执行预存操作: {instruction}")

                self._execute_pre_actions(history_data)
                print(history_data)

                update_status(self.input_box, f"预存操作 {instruction} 执行完成")
                logging.info(f"预存操作 {instruction} 执行完成")
                return

            except Exception as e:
                logging.error(f"预存操作解析失败: {str(e)}")
                update_status(self.input_box, "操作数据格式错误")
                return

        instruction = self.input_box.text()
        self.keep_running()
        start_time = time.time()
        pre_actions = []

        try:
            logging.info(f"开始处理指令: {instruction}")
            while not self.stop_requested:
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

                if result.get('status') == 'success':
                    # 保存标记图像
                    self._save_labeled_image(result)

                    # 解析数据
                    objs = self._parse_and_log_data(result)
                    curr_objs = self._extract_curr_objs(objs)

                    # 指令解析
                    agent_proposer = self._parse_and_log_instruction(instruction, pre_actions, curr_objs, type='omni')
                    print(agent_proposer)
                    action = self._parse_and_log_instruction(agent_proposer, pre_actions, curr_objs)

                    # 执行动作
                    if action is None:
                        continue
                    action_data = robust_json_extract(action)
                    action_result = execute_action(self.controller, action_data, objs)
                    if action_result is None:
                        break
                    action_type, target_icon, params, execute_duration, status = action_result
                    log_operation(action_type, target_icon, params, execute_duration, status)
                    if status == "success":
                        pre_actions.append(action_data)
        except Exception as e:
            logging.error(f"指令执行过程中出现异常: {str(e)}", exc_info=True)
            update_status(self.input_box, f"操作失败: {str(e)}")
            time.sleep(2)
        finally:
            total_duration = time.time() - start_time
            status_message = "操作已停止" if self.stop_requested else f"操作完成，总耗时: {total_duration:.2f}秒"
            update_status(self.input_box, status_message)

            # 保存历史操作
            if not self.stop_requested:
                with open(config.PRE_ACTIONS_PATH + "/" + f"{instruction}.jsonl", 'w', encoding='utf-8') as f:
                    for action in pre_actions:
                        f.write(json.dumps(action, ensure_ascii=False) + '\n')
                update_status(self.input_box, f"操作已保存至 {config.PRE_ACTIONS_PATH} + {instruction}.jsonl")

            self.finish_running()

    def on_detail_clicked(self):
        """详情按钮点击事件处理"""
        try:
            history_data = utils.load_action_history(config.PRE_ACTIONS_PATH + f"/{self.history_combo.currentText()}")
            self.show_detail_dialog(history_data)
        except Exception as e:
            logging.error(f"加载历史操作失败: {str(e)}")
            update_status(self.input_box, f"加载失败: {str(e)}")

    def show_detail_dialog(self, data):
        """显示具体操作步骤对话框"""
        print("显示详情对话框",data)
        dialog = QDialog(self)
        dialog.setWindowTitle("具体操作步骤")
        dialog.setFixedSize(600, 400)

        list_widget = QListWidget(dialog)
        list_widget.setGeometry(10, 10, 280, 340)
        for action in data:
            print(action)
            # 添加到每一项
            item_text = f"{action}"
            list_widget.addItem(item_text)

        list_widget.setCurrentRow(0)
        list_widget.setStyleSheet("""
            QListWidget {
                border: 2px solid #cccccc;
                border-radius: 8px;
                padding: 5px;
                font-size: 14px;
            }
        """)

        text_edit = QTextEdit(dialog)
        text_edit.setGeometry(300, 10, 280, 340)

        def on_list_item_clicked(item):
            text_edit.setText(item.text())

        list_widget.itemClicked.connect(on_list_item_clicked)

        def save_changes():
            current_item = list_widget.currentItem()
            if current_item:
                new_text = text_edit.toPlainText()
                # 找到需要更新的 action 并更新
                index = next((i for i, action in enumerate(data) if str(action) == current_item.text()), None)
                if index is not None:
                    try:
                        # 尝试将新文本解析为 JSON 对象
                        new_action = json.loads(new_text)
                        data[index] = new_action
                    except json.JSONDecodeError:
                        logging.error("新输入的文本不是有效的 JSON 格式")
                        update_status(self.input_box, "新输入的文本不是有效的 JSON 格式")
                        return

                    file_name = config.PRE_ACTIONS_PATH + f"/{self.history_combo.currentText()}"
                    try:
                        # 保存修改后的操作数据
                        with open(file_name, 'w', encoding='utf-8') as f:
                            for action in data:
                                f.write(json.dumps(action, ensure_ascii=False) + '\n')
                        update_status(self.input_box, f"操作已保存至 {file_name}")
                    except Exception as e:
                        logging.error(f"保存操作数据时出错: {str(e)}")
                        update_status(self.input_box, f"保存操作数据时出错: {str(e)}")
                        return

            dialog.accept()

        btn_save = QPushButton("保存修改", dialog)
        btn_save.setGeometry(300, 360, 120, 30)
        btn_save.clicked.connect(save_changes)

        btn_cancel = QPushButton("取消", dialog)
        btn_cancel.setGeometry(440, 360, 120, 30)
        btn_cancel.clicked.connect(dialog.reject)

        if dialog.exec_() == QDialog.Accepted:
            pass

    def _execute_pre_actions(self, actions):
        """执行预存操作序列"""
        self.keep_running()
        try:
            for action in actions:
                if self.stop_requested:
                    break
                
                print(f"执行动作: {action}")
                execute_action(self.controller, action, None)
                print(f"动作执行完成")

                # 延迟两秒
                time.sleep(2)
            update_status(self.input_box, "预存操作执行完成")
        except Exception as e:
            logging.error(f"预存操作执行失败: {str(e)}")
            update_status(self.input_box, f"执行错误: {str(e)}")
        finally:
            self.finish_running()

    def _wait_for_screenshot_delay(self):
        loop = QEventLoop()
        QTimer.singleShot(int(config.SCREENSHOT_DELAY * 1000), loop.quit)
        loop.exec_()

    def _take_and_log_screenshot(self):
        update_status(self.input_box, "正在截图...")
        screenshot_duration = take_screenshot(self.controller)
        log_operation("截图", "屏幕", {}, screenshot_duration, "success")

    def _process_and_log_image(self):
        update_status(self.input_box, "正在解析界面元素...")
        result, _ = process_image()
        log_operation("处理图像", "screen", {}, 0, "success")
        return result

    def _save_labeled_image(self, result):
        labeled_image = result.get('labeled_image')
        if labeled_image:
            try:
                labeled_image.save(config.LABELED_IMAGE_PATH)
            except Exception as e:
                logging.error(f"保存标记图像失败: {str(e)}", exc_info=True)
                update_status(self.input_box, f"保存标记图像失败: {str(e)}")
                time.sleep(2)

    def _parse_and_log_data(self, result):
        objs, _ = parse_data(result.get('parsed_content'))
        log_operation("解析数据", "screen", {}, 0, "success")
        return objs

    def _extract_curr_objs(self, objs):
        return [{"id": obj["id"], "type": obj["type"], "content": obj["content"]} for obj in objs]

    def _parse_and_log_instruction(self, instruction, pre_actions, curr_objs, type='text'):
        update_status(self.input_box, "正在解析指令...")
        action, _ = parse_instruction(instruction, pre_actions, curr_objs, type)
        log_operation("解析指令", "screen", {}, 0, "success")
        return action

    def mousePressEvent(self, a0):
        if a0.button() == Qt.LeftButton:
            self.dragging = True
            self.old_pos = a0.globalPos()

    def mouseMoveEvent(self, a0):
        if self.dragging:
            delta = a0.globalPos() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = a0.globalPos()

    def mouseReleaseEvent(self, a0):
        self.dragging = False