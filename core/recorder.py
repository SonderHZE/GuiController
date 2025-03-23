import time
import json
import os
import threading
import pyautogui
import keyboard
from pynput import mouse, keyboard as kb
import config

class ActionRecorder:
    """操作录制器，用于记录用户的鼠标和键盘操作"""
    
    def __init__(self):
        self.recording = False
        self.actions = []
        self.start_time = 0
        self.mouse_listener = None
        self.keyboard_listener = None
        self.last_action_time = 0
        self.record_thread = None
        self._pending_click_timer = None
        self._last_click_info = None
        self._pending_click = None
        
    def start_recording(self):
        """开始录制操作"""
        if self.recording:
            return False
            
        self.recording = True
        self.actions = []
        self.start_time = time.time()
        self.last_action_time = self.start_time
        self._last_click_info = None
        self._pending_click = None
        
        # 创建鼠标监听器
        self.mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll
        )
        
        # 创建键盘监听器
        self.keyboard_listener = kb.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        
        # 启动监听线程
        self.record_thread = threading.Thread(target=self._record_loop)
        self.record_thread.daemon = True
        
        self.mouse_listener.start()
        self.keyboard_listener.start()
        self.record_thread.start()
        
        return True
        
    def stop_recording(self):
        """停止录制操作"""
        if not self.recording:
            return False
            
        self.recording = False
        
        # 处理待定的点击操作
        if self._pending_click:
            self._process_pending_click()
            
        # 取消定时器
        if self._pending_click_timer and self._pending_click_timer.is_alive():
            self._pending_click_timer.cancel()
            
        # 停止监听器
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
            
        # 添加结束操作
        self._add_action("finish", {})
            
        return True
        
    def save_recording(self, name):
        """保存录制的操作序列"""
        if not self.actions:
            return False
            
        # 确保目录存在
        os.makedirs(config.RECORDINGS_PATH, exist_ok=True)
        
        # 构建文件路径
        file_path = os.path.join(config.RECORDINGS_PATH, f"{name}.jsonl")
        
        # 过滤和转换操作
        valid_actions = []
        for i, action in enumerate(self.actions):
            # 跳过不符合Schema的action类型
            if action["action"] not in ["open", "click", "scroll", "input", "hotkey", "press_enter", "finish"]:
                continue
                
            # 确保id是整数
            action["id"] = i
            
            # 确保params字段格式正确
            if "params" not in action:
                action["params"] = {}
                
            # 根据action类型验证必填字段
            if action["action"] == "input" and "text_content" not in action["params"]:
                action["params"]["text_content"] = ""
            elif action["action"] == "hotkey" and "key_sequence" not in action["params"]:
                action["params"]["key_sequence"] = []
            elif action["action"] == "scroll" and "direction" not in action["params"]:
                action["params"]["direction"] = "up"
                
            valid_actions.append(action)
        
        # 保存操作序列
        with open(file_path, 'w', encoding='utf-8') as f:
            for action in valid_actions:
                f.write(json.dumps(action, ensure_ascii=False) + '\n')
                
        return True
        
    def _record_loop(self):
        """录制循环，记录鼠标位置变化"""
        last_pos = pyautogui.position()
        while self.recording:
            time.sleep(0.1)  # 降低CPU使用率
            
            # 记录鼠标移动（仅当移动超过一定距离时）
            current_pos = pyautogui.position()
            if (abs(current_pos[0] - last_pos[0]) > 10 or 
                abs(current_pos[1] - last_pos[1]) > 10):
                self._add_action("move", {
                    "x": current_pos[0],
                    "y": current_pos[1]
                })
                last_pos = current_pos
    
    def _on_click(self, x, y, button, pressed):
        """鼠标点击事件处理"""
        if not self.recording:
            return
            
        if pressed:
            button_type = "left"
            if button == mouse.Button.right:
                button_type = "right"
            elif button == mouse.Button.middle:
                button_type = "middle"
                
            # 记录当前点击时间和位置
            current_time = time.time()
            
            # 取消之前的定时器（如果存在）
            if self._pending_click_timer and self._pending_click_timer.is_alive():
                self._pending_click_timer.cancel()
                self._pending_click_timer = None
            
            # 检查是否为双击
            if self._last_click_info:
                last_time, last_x, last_y, last_button = self._last_click_info
                time_diff = current_time - last_time
                distance = ((x - last_x) ** 2 + (y - last_y) ** 2) ** 0.5
                
                # 如果是短时间内在相近位置的相同按键点击，视为双击/打开操作
                if time_diff < 0.5 and distance < 10 and button_type == last_button:
                    # 如果有待处理的点击，先处理掉
                    if self._pending_click:
                        self._pending_click = None
                    
                    # 记录为open操作
                    self._add_action("open", {
                        "x": x,
                        "y": y,
                        "button_type": button_type
                    })
                    
                    # 重置点击信息
                    self._last_click_info = None
                    return
            
            # 记录点击信息，但延迟处理
            self._pending_click = {
                "time": current_time,
                "x": x,
                "y": y,
                "button_type": button_type
            }
            
            # 更新最后点击信息
            self._last_click_info = (current_time, x, y, button_type)
            
            # 启动定时器，延迟处理点击
            self._pending_click_timer = threading.Timer(0.5, self._process_pending_click)
            self._pending_click_timer.daemon = True
            self._pending_click_timer.start()
    
    def _process_pending_click(self):
        """处理待定的点击操作"""
        if self._pending_click and self.recording:
            # 记录为单击操作
            self._add_action("click", {
                "x": self._pending_click["x"],
                "y": self._pending_click["y"],
                "button_type": self._pending_click["button_type"],
                "clicks": 1
            })
            
            # 清除待处理状态
            self._pending_click = None

    def _on_scroll(self, x, y, dx, dy):
        """鼠标滚动事件处理"""
        if not self.recording:
            return
            
        direction = "up" if dy > 0 else "down"
        self._add_action("scroll", {
            "direction": direction
        })
    
    def _on_key_press(self, key):
        """键盘按键事件处理"""
        if not self.recording:
            return
            
        try:
            # 普通按键
            key_char = key.char
            self._add_action("input", {
                "text_content": key_char
            })
        except AttributeError:
            # 特殊按键
            key_name = str(key).replace("Key.", "")
            
            # 处理常见组合键
            if key_name in ["ctrl", "alt", "shift", "cmd"]:
                # 组合键处理在release中完成
                pass
            elif key_name == "enter":
                self._add_action("press_enter", {})
            else:
                self._add_action("hotkey", {
                    "key_sequence": [key_name]
                })
    
    def _on_key_release(self, key):
        """键盘释放事件处理"""
        # 这里可以处理组合键
        pass
    
    def _add_action(self, action_type, params):
        """添加一个操作到序列中"""
        current_time = time.time()
        delay = current_time - self.last_action_time
        
        # 只有当延迟超过阈值时才记录延迟
        if delay > 0.1 and action_type != "finish":
            action = {
                "action": "delay",
                "id": len(self.actions),
                "target": "等待",
                "params": {
                    "seconds": round(delay, 2)
                }
            }
            self.actions.append(action)
        
        # 记录实际操作
        action = {
            "action": action_type,
            "id": len(self.actions),
            "target": self._get_target_name(action_type, params),
            "params": params
        }
        self.actions.append(action)
        self.last_action_time = current_time
    
    def _get_target_name(self, action_type, params):
        """根据操作类型和参数生成目标名称"""
        if action_type == "click":
            return f"点击位置({params.get('x', 0)}, {params.get('y', 0)})"
        elif action_type == "open":
            return f"打开位置({params.get('x', 0)}, {params.get('y', 0)})"
        elif action_type == "move":
            return f"移动到({params.get('x', 0)}, {params.get('y', 0)})"
        elif action_type == "input":
            return "输入文本"
        elif action_type == "scroll":
            return f"滚动{params.get('direction', '上')}"
        elif action_type == "hotkey":
            return f"快捷键{'-'.join(params.get('key_sequence', []))}"
        elif action_type == "press_enter":
            return "按回车键"
        else:
            return "未知操作"
    