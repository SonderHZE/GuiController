import time
import pyperclip
import pyautogui
from typing import Optional, Any

import win32gui
import win32con
from typing import Iterable, List
import contextlib


class PyAutoGUIWrapper:
    def __init__(self, pause: float = 0.5) -> None:
        """
        初始化 PyAutoGUIWrapper 类

        Args:
            pause: 每次操作后的延迟时间（秒），默认为0.5秒
        """
        self._set_pause(pause)
        self._current_hwnd = None 

    def move_to(self, x, y):
        """移动鼠标到指定位置"""
        pyautogui.moveTo(x, y)
        return True

    def _set_pause(self, pause: float) -> None:
        """设置操作间隔时间"""
        pyautogui.PAUSE = max(0.1, pause)  # 确保最小间隔0.1秒

    def screen_shot(self) -> Any:
        """截取当前屏幕截图（带缓存机制）"""
        if not hasattr(self, '_cached_screenshot') or time.time()-self._last_shot > 1:
            self._cached_screenshot = pyautogui.screenshot()
            self._last_shot = time.time()
        return self._cached_screenshot

    def press_enter(self) -> None:
        """模拟按下回车键"""
        pyautogui.press('enter')

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              button: str = 'left', clicks: int = 1, interval: float = 0.05) -> None:
        """
        模拟鼠标点击操作

        Args:
            x: 点击的x坐标（可选）
            y: 点击的y坐标（可选）
            button: 鼠标按钮（left/middle/right）
            clicks: 点击次数
            interval: 点击间隔时间（秒）
        """

        self._validate_coordinates(x, y)
        print(f"执行点击操作, x={x}, y={y}, 按钮={button}, 点击次数={clicks}")
        self._move_to_position(x, y)
        pyautogui.click(button=button, clicks=clicks, interval=interval)

    def open(self, x: Optional[int] = None, y: Optional[int] = None,
                     button: str = 'left', interval: float = 0.0) -> None:
        """
        模拟鼠标双击操作

        Args:
            x: 双击的x坐标（可选）
            y: 双击的y坐标（可选）
            button: 鼠标按钮（left/middle/right）
            interval: 点击间隔时间（秒）
        """
        self._validate_coordinates(x, y)
        print(f"执行双击操作, x={x}, y={y}")
        self._move_to_position(x, y)
        pyautogui.doubleClick(button=button, interval=interval)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """
        模拟鼠标滚轮滚动

        Args:
            clicks: 滚动次数（正数向上，负数向下）
            x: 滚动位置的x坐标（可选）
            y: 滚动位置的y坐标（可选）
        """
        self._validate_coordinates(x, y)
        print(f"执行滚动操作: {clicks}")
        self._move_to_position(x, y)
        pyautogui.scroll(clicks)

    def input(self, text: str, x: int, y: int, interval: float = 0.1) -> None:
        """
        模拟文本输入操作

        Args:
            text: 要输入的文本
            x: 输入框的x坐标
            y: 输入框的y坐标
            interval: 操作间隔时间（秒）

        Raises:
            ValueError: 如果坐标值为空
        """
        self._validate_coordinates(x, y, required=True)
        print(f"执行输入操作: {text}")
        self._clear_input(x, y, interval)
        self._safe_paste(text, interval)

    def hot_key(self, *keys: str, interval: float = 0.1) -> None:
        """
        执行系统级快捷键操作
        
        Args:
            *keys: 组合键序列（例如 'ctrl', 'shift', 'esc'）
            interval: 组合键之间的间隔时间（秒）
            
        Raises:
            ValueError: 无有效组合键输入
            TypeError: 组合键类型错误
            RuntimeError: 快捷键执行失败
        """
        try:
            # 尝试激活目标窗口，但即使失败也继续执行
            self._activate_target_window()
        except Exception as e:
            print(f"窗口激活失败，但将继续执行热键: {str(e)}")
        
        self._validate_hotkeys(keys)
        
        normalized_keys = self._normalize_keys(keys)
        print(f"准备执行组合键: {normalized_keys} (间隔: {interval}s)")
        try:
            with self._hotkey_error_handler():
                # 对于特殊的全局热键，不需要窗口焦点
                if keys[0].lower() in ['win', 'alt'] or len(keys) > 1 and keys[0].lower() in ['ctrl', 'shift'] and keys[1].lower() in ['alt', 'win']:
                    print("执行全局热键，不需要窗口焦点")
                
                pyautogui.hotkey(*normalized_keys, interval=interval)
        except pyautogui.FailSafeException as e:
            raise RuntimeError(f"安全模式触发: {str(e)}") from e

    def _activate_target_window(self) -> None:
        """激活目标窗口"""
        if self._current_hwnd:
            try:
                # 检查窗口句柄是否有效
                if not win32gui.IsWindow(self._current_hwnd):
                    print(f"警告: 窗口句柄 {self._current_hwnd} 已失效，尝试重新获取活动窗口")
                    self._current_hwnd = win32gui.GetForegroundWindow()
                
                self.set_foreground_window(self._current_hwnd)
            except WindowsError as e:
                print(f"窗口激活失败: {str(e)}")
                pass

    @staticmethod
    def _validate_hotkeys(keys: tuple) -> None:
        """验证组合键有效性"""
        if not keys:
            raise ValueError("必须提供至少一个组合键")
        if any(not isinstance(k, str) for k in keys):
            raise TypeError("组合键必须为字符串类型")

    @staticmethod
    def _normalize_keys(keys: Iterable[str]) -> List[str]:
        """规范化按键格式"""
        return [k.strip().lower() for k in keys]

    @contextlib.contextmanager
    def _hotkey_error_handler(self):
        """快捷键执行的异常处理上下文"""
        try:
            yield
        except pyautogui.PyAutoGUIException as e:
            print(f"快捷键执行失败: {str(e)}")
            raise RuntimeError("快捷键执行失败") from e

    def _move_to_position(self, x: Optional[int], y: Optional[int]) -> None:
        """移动鼠标到指定位置"""
        if x is not None and y is not None:
            pyautogui.moveTo(x, y)

    def _validate_coordinates(self, x: Optional[int], y: Optional[int], required: bool = False) -> None:
        """验证坐标有效性"""
        if required and (x is None or y is None):
            raise ValueError("坐标参数不能为空")
        if (x is None) != (y is None):
            raise ValueError("x和y坐标必须同时存在或同时为空")

    def _clear_input(self, x: int, y: int, interval: float) -> None:
        """清空输入框"""
        pyautogui.click(x, y)
        pyautogui.hotkey('ctrl', 'a', interval=interval)
        pyautogui.press('backspace')
    

    def _safe_paste(self, text: str, interval: float) -> None:
        """安全粘贴文本"""
        try:
            pyperclip.copy(text)
        except pyperclip.PyperclipException as e:
            raise RuntimeError("剪贴板操作失败") from e
        pyautogui.hotkey('ctrl', 'v', interval=interval)
        pyautogui.press('enter')

    def find_window_by_title(self, title: str, timeout: int = 5) -> int:
        """查找指定标题的窗口句柄"""
        def _find_win(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and title in win32gui.GetWindowText(hwnd):
                self._current_hwnd = hwnd
        start = time.time()
        while time.time() - start < timeout:
            win32gui.EnumWindows(_find_win, None)
            if self._current_hwnd:
                return self._current_hwnd
            time.sleep(0.5)
        raise RuntimeError(f"未找到包含'{title}'的窗口")

    def set_foreground_window(self, hwnd: Optional[int] = None) -> None:
        """将指定窗口置于前台"""
        target_hwnd = hwnd or self._current_hwnd
        if not target_hwnd:
            print("警告: 未指定窗口句柄，使用当前活动窗口")
            target_hwnd = win32gui.GetForegroundWindow()
            self._current_hwnd = target_hwnd
            
        # 验证窗口句柄是否有效
        if not win32gui.IsWindow(target_hwnd):
            print(f"警告: 窗口句柄 {target_hwnd} 无效，使用当前活动窗口")
            target_hwnd = win32gui.GetForegroundWindow()
            self._current_hwnd = target_hwnd
            
        try:
            # 尝试恢复窗口（如果最小化）
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
            # 尝试将窗口置于前台
            win32gui.SetForegroundWindow(target_hwnd)
        except Exception as e:
            print(f"设置前台窗口失败: {str(e)}")
            # 不抛出异常，允许操作继续

    def get_window_rect(self, hwnd: Optional[int] = None) -> tuple:
        """获取窗口坐标和尺寸 (left, top, right, bottom)"""
        hwnd = hwnd or self._current_hwnd
        if hwnd is None:
            raise ValueError("需要指定有效的窗口句柄")
        return win32gui.GetWindowRect(hwnd)

    def maximize_window(self, hwnd: Optional[int] = None) -> None:
        """最大化指定窗口"""
        hwnd = hwnd or self._current_hwnd
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)

    def minimize_window(self, hwnd: Optional[int] = None) -> None:
        """最小化指定窗口"""
        hwnd = hwnd or self._current_hwnd
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

    def set_window_position(self, x: int, y: int, width: int, height: int):
        """设置窗口位置和尺寸"""
        win32gui.SetWindowPos(
            # 确保当前窗口句柄不为 None
            (self._current_hwnd or win32gui.GetForegroundWindow()), win32con.HWND_TOP,
            x, y, width, height,
            win32con.SWP_SHOWWINDOW
        )
    
    def get_all_windows_titles(self) -> list:
        """获取所有窗口标题"""
        def _get_windows(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                self._windows.append(win32gui.GetWindowText(hwnd))
        self._windows = []
        win32gui.EnumWindows(_get_windows, None)
        return self._windows


    def get_active_window_title(self) -> str:
        """获取当前活动窗口的标题"""
        return win32gui.GetWindowText(win32gui.GetForegroundWindow())


    def find_icons(self, image_path: str, threshold: float = 0.9) -> tuple:
        """在屏幕上查找指定图标"""
        location = pyautogui.locateCenterOnScreen(image_path, confidence=threshold)
        if location:
            return location.x, location.y
        return ()
