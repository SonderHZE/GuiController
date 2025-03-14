import time
import json
import logging
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal
import pygetwindow as gw
from pynput import mouse, keyboard
import config

class EventListener(QObject):
    recording_changed = pyqtSignal(bool)
    action_recorded = pyqtSignal(dict)
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.operations = []
        self.last_active_window_title = None
        self.click_detected = False
        self.current_sentence = ""
        self.recording = False
        self.action_counter = 0
        self.current_key_sequence = []
        self._init_listeners()

    def _init_listeners(self):
        """初始化输入监听器"""
        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.keyboard_listener = keyboard.Listener(on_press=self.on_press)
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def on_click(self, x, y, button, pressed):
        if not self.recording or self._is_in_qt_window(x, y):
            return
            
        window_title = self._get_active_window_title()
        if not window_title:
            return
            
        if pressed and not self.click_detected:
            action = {
                "id": self.action_counter,
                "action": "click",
                "target": window_title,
                "params": {
                    "button_type": str(button).split('.')[-1].lower(),
                    "clicks": 1,
                    "x": x,
                    "y": y
                }
            }
            self._record_action(action)
            self.action_counter += 1
            self.click_detected = True
        elif not pressed:
            self.click_detected = False

    def on_press(self, key):
        try:
            if self.recording:
                if hasattr(key, 'char'):
                    self.current_sentence += key.char
                else:
                    key_name = str(key).split('.')[-1].lower()
                    self.current_key_sequence.append(key_name)
                
                if key == keyboard.Key.enter:
                    if self.current_sentence.strip():
                        self._record_text_input()
                    if self.current_key_sequence:
                        self._record_hotkey()
        except Exception as e:
            logging.error(f"按键处理错误: {str(e)}")

    def _record_text_input(self):
        action = {
            "id": self.action_counter,
            "action": "input",
            "target": self._get_active_window_title(),
            "params": {
                "text_content": self.current_sentence.strip()
            }
        }
        self._record_action(action)
        self.current_sentence = ""
        self.action_counter += 1

    def _record_hotkey(self):
        action = {
            "id": self.action_counter,
            "action": "hotkey",
            "target": "system",
            "params": {
                "key_sequence": self.current_key_sequence.copy()
            }
        }
        self._record_action(action)
        self.current_key_sequence.clear()
        self.action_counter += 1

    def _record_action(self, action):
        self.operations.append(action)
        self.action_recorded.emit(action)
        logging.info(f"记录操作: {json.dumps(action, ensure_ascii=False)}")

    def _get_active_window_title(self):
        try:
            window = gw.getActiveWindow()
            return window.title if window else "unknown"
        except Exception as e:
            logging.error(f"获取窗口失败: {str(e)}")
            return "unknown"

    def _is_in_qt_window(self, x, y):
        """检测坐标是否在QT窗口范围内"""
        win_geo = self.main_window.geometry()
        return (win_geo.x() <= x <= win_geo.x() + win_geo.width() and 
                win_geo.y() <= y <= win_geo.y() + win_geo.height())

class ScreenRecorder:
    def __init__(self, controller):
        self.controller = controller
        self.listener = EventListener(controller)
        self._connect_signals()
        
    def _connect_signals(self):
        self.listener.recording_changed.connect(self._handle_recording_change)
        self.listener.action_recorded.connect(self.controller.update_recording_status)

    def start(self):
        self.listener.recording = True
        self.listener.operations.clear()
        logging.info("开始屏幕录制")

    def stop(self):
        self.listener.recording = False
        self._save_recording()
        logging.info("停止屏幕录制")

    def _handle_recording_change(self, is_recording):
        status = "正在录制..." if is_recording else "录制已停止"
        self.controller.update_status(status)

    def _save_recording(self):
        if not self.listener.operations:
            return
            
        try:
            save_dir = Path(config.DATA_DIR)
            save_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = save_dir / f"recording_{timestamp}.jsonl"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                for action in self.listener.operations:
                    standardized = {
                        "id": action["id"],
                        "action": action["action"],
                        "target": action["target"],
                        "params": self._format_params(action.get("params", {}))
                    }
                    f.write(json.dumps(standardized, ensure_ascii=False) + '\n')
                    
            self.controller.update_status(f"已保存录制文件: {file_path.name}")
            return file_path
            
        except Exception as e:
            logging.error(f"保存录制文件失败: {str(e)}")
            self.controller.update_status("录制文件保存失败")

    def _format_params(self, params):
        """过滤无效参数并转换坐标格式"""
        valid_params = {}
        for k, v in params.items():
            if k in ["button_type", "clicks", "text_content", "key_sequence", "x", "y"]:
                valid_params[k] = v
        return valid_params

    def terminate(self):
        self.listener.mouse_listener.stop()
        self.listener.keyboard_listener.stop()