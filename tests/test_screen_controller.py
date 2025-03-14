import unittest
from unittest.mock import patch, MagicMock
from core.screen_controller import PyAutoGUIWrapper

class TestPyAutoGUIWrapper(unittest.TestCase):
    def setUp(self):
        self.wrapper = PyAutoGUIWrapper(pause=0.1)
        self.test_hwnd = 12345  # 模拟窗口句柄

    @patch('pyautogui.click')
    def test_click_with_coordinates(self, mock_click):
        """测试带坐标的点击操作"""
        self.wrapper.click(100, 200)
        mock_click.assert_called_with(button='left', clicks=1, interval=0.2, x=100, y=200)

    @patch('win32gui.EnumWindows')
    def test_find_window_success(self, mock_enum):
        """测试成功查找窗口"""
        # 设置模拟返回值
        mock_enum.side_effect = lambda func, _: func(self.test_hwnd, None)
        with patch('win32gui.IsWindowVisible', return_value=True), \
             patch('win32gui.GetWindowText', return_value="Test Window"):
            
            result = self.wrapper.find_window_by_title("Test")
            self.assertEqual(result, self.test_hwnd)

    @patch('win32gui.SetForegroundWindow')
    def test_activate_window(self, mock_set_foreground):
        """测试窗口激活功能"""
        self.wrapper._current_hwnd: int | None = self.test_hwnd
        self.wrapper.set_foreground_window()
        mock_set_foreground.assert_called_with(self.test_hwnd)

    @patch('win32gui.GetWindowRect')
    def test_window_dimensions(self, mock_rect):
        """测试获取窗口尺寸"""
        mock_rect.return_value = (100, 200, 800, 600)
        self.wrapper._current_hwnd = self.test_hwnd
        dimensions = self.wrapper.get_window_rect()
        self.assertEqual(dimensions, (100, 200, 800, 600))

    def test_coordinate_validation(self):
        """测试坐标验证逻辑"""
        # 有效坐标测试
        self.wrapper._validate_coordinates(100, 200)
        
        # 无效坐标测试
        with self.assertRaises(ValueError):
            self.wrapper._validate_coordinates(100, None)
        
        with self.assertRaises(ValueError):
            self.wrapper._validate_coordinates(None, 200)

    @patch('pyautogui.hotkey')
    def test_hotkey_combination(self, mock_hotkey):
        """测试组合键操作"""
        self.wrapper.hot_key('ctrl', 's')
        mock_hotkey.assert_called_with('ctrl', 's', interval=0.1)

if __name__ == '__main__':
    unittest.main()