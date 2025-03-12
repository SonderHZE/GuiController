import time
import pyperclip
import pyautogui


class PyAutoGUIWrapper:
    def __init__(self, pause=0.5):
        """
        初始化 PyAutoGUIWrapper 类。

        :param pause: 每次操作后的延迟时间（秒），默认为 0.5 秒。
        """
        pyautogui.PAUSE = pause  # 设置 PyAutoGUI 的操作延迟

    def screen_shot(self):
        """
        截取当前屏幕的截图。
        """
        return pyautogui.screenshot()

    def press_enter(self):
        """
        模拟按下回车键。
        """
        pyautogui.press('enter')

    def click(self, x=None, y=None, button='left', clicks=1, interval=0.0):
        """
        模拟鼠标点击操作。

        :param x: 点击的 x 坐标（可选）。
        :param y: 点击的 y 坐标（可选）。
        :param button: 点击的鼠标按钮，'left'、'middle' 或 'right'，默认为 'left'。
        :param clicks: 点击次数，默认为 1。
        :param interval: 每次点击之间的间隔时间（秒），默认为 0.0。
        """
        print(f"执行点击操作, x={x}, y={y}")
        if x is not None and y is not None:
            pyautogui.moveTo(x, y)
        pyautogui.click(button=button, clicks=clicks, interval=interval)

    def double_click(self, x=None, y=None, button='left', interval=0.0):
        """
        模拟鼠标双击操作。

        :param x: 双击的 x 坐标（可选）。
        :param y: 双击的 y 坐标（可选）。
        :param button: 双击的鼠标按钮，'left'、'middle' 或 'right'，默认为 'left'。
        :param interval: 两次点击之间的间隔时间（秒），默认为 0.0。
        """
        print(f"执行双击操作, x={x}, y={y}")
        if x is not None and y is not None:
            pyautogui.moveTo(x, y)
        pyautogui.doubleClick(button=button, interval=interval)

    def scroll(self, clicks, x=None, y=None):
        """
        模拟鼠标滚轮滚动操作。

        :param clicks: 滚动的次数，正数向上滚动，负数向下滚动。
        :param x: 滚动的 x 坐标（可选）。
        :param y: 滚动的 y 坐标（可选）。
        """
        print(f"执行滚动操作: {clicks}")
        if x is not None and y is not None:
            pyautogui.moveTo(x, y)
        pyautogui.scroll(clicks)

    def input(self, text, x, y, interval=0.1):
        """
        模拟键盘输入文本。

        :param text: 要输入的文本。
        :param interval: 每个字符之间的输入间隔时间（秒），默认为 0.1 秒。
        :param x: 输入的 x 坐标。
        :param y: 输入的 y 坐标。
        """

        print(f"执行输入操作: {text}")
        pyautogui.click(x, y)
        pyautogui.hotkey('ctrl', 'a', interval=interval)
        pyautogui.press('delete')
        pyperclip.copy(text)
        pyautogui.hotkey('ctrl', 'v', interval=interval)
        pyautogui.press('enter')

    def hot_key(self, *args, interval=0.1):
        """
        模拟键盘组合快捷键。

        :param args: 要按下的键，如 'ctrl', 'c'。
        :param interval: 每个按键之间的间隔时间（秒），默认为 0.1 秒。
        """
        pyautogui.hotkey(*args, interval=interval)


if __name__ == "__main__":
    wrapper = PyAutoGUIWrapper(pause=1.0)  # 设置每次操作后延迟 1 秒

    wrapper.input("华工", 48, 189)  # 在 (100, 100) 处输入 "Hello, World!"
