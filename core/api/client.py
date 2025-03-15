import base64
import io
from typing import Any, Dict, NamedTuple, Optional

from PIL import Image
from numpy import result_type
import pyautogui
import requests
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
import config
import cv2


class ProcessResult(NamedTuple):
    status: str
    labeled_image: Optional[Image.Image] = None
    parsed_content: Optional[Dict[str, Any]] = None
    label_coordinates: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class APIClient:
    """封装图像处理API客户端操作"""
    
    def __init__(self, base_url: str = "http://localhost:1145"):
        self.base_url = base_url.rstrip('/')
        self.default_timeout = 50  # 默认超时时间

    def process_image(
        self,
        image_path: str,
        box_threshold: float = config.BOX_THRESHOLD,
        iou_threshold: float = config.IOU_THRESHOLD,
        use_paddleocr: bool = config.USE_PADDLEOCR,
        imgsz: int = config.IMGSZ
    ) -> ProcessResult:
        """
        处理图像并返回结构化结果
        :param image_path: 要处理的图像路径
        :param box_threshold: 检测框阈值
        :param iou_threshold: IOU阈值
        :param use_paddleocr: 是否使用PaddleOCR
        :param imgsz: 图像尺寸
        """
        api_url = f"{self.base_url}/process_image"
        
        try:
            with open(image_path, 'rb') as image_file:
                files = {'file': ('image.png', image_file, 'image/png')}
                params = {
                    'box_threshold': box_threshold,
                    'iou_threshold': iou_threshold,
                    'use_paddleocr': use_paddleocr,
                    'imgsz': imgsz
                }

                print(f"发送请求至 {api_url}")
                response = requests.post(
                    api_url,
                    files=files,
                    params=params,
                    timeout=self.default_timeout
                )

                return self._handle_response(response)

        except (IOError, FileNotFoundError) as e:
            return ProcessResult(status='error', message=f"文件错误: {str(e)}")
        except Exception as e:
            return ProcessResult(status='error', message=f"未预期错误: {str(e)}")

    def _handle_response(self, response: requests.Response) -> ProcessResult:
        """统一处理API响应"""
        if response.status_code != 200:
            return ProcessResult(
                status='error',
                message=f'HTTP错误 {response.status_code}'
            )

        try:
            result = response.json()
        except ValueError:
            return ProcessResult(
                status='error',
                message='无效的JSON响应'
            )

        if result['status'] != 'success':
            return ProcessResult(
                status='error',
                message=result.get('message', '未知错误')
            )

        try:
            labeled_image = Image.open(
                io.BytesIO(base64.b64decode(result['labeled_image']))
            )
            return ProcessResult(
                status='success',
                labeled_image=labeled_image,
                parsed_content=result.get('parsed_content'),
                label_coordinates=result.get('label_coordinates')
            )
        except KeyError as e:
            return ProcessResult(
                status='error',
                message=f"响应数据解析失败: {str(e)}"
            )

    def smart_locate(self, template_image, threshold=0.8):
        """
        基于OpenCV的智能元素定位
        :param template_image: 要查找的元素截图路径
        :param threshold: 匹配阈值
        :return: (x, y) 中心坐标
        """
        screenshot = pyautogui.screenshot()
        # 将截图转换为OpenCV格式
        import numpy as np  # 添加对numpy库的导入
        screenshot_cv = cv2.cvtColor(np.array(screenshot).astype('uint8'), cv2.COLOR_RGB2BGR)

        # 处理模板图像
        if isinstance(template_image, str):
            template_image_cv = cv2.imread(template_image, cv2.IMREAD_COLOR)
            if template_image_cv is None:
                raise FileNotFoundError(f"模板图像未找到: {template_image}")
        elif isinstance(template_image, Image.Image):
            template_image_cv = cv2.cvtColor(np.array(template_image).astype('uint8'), cv2.COLOR_RGB2BGR)
        elif isinstance(template_image, np.ndarray):
            template_image_cv = template_image
        else:
            raise ValueError(f"不支持的模板图像类型: {type(template_image)}")

        # 添加尺寸校验
        if screenshot_cv.shape[0] < template_image_cv.shape[0] or screenshot_cv.shape[1] < template_image_cv.shape[1]:
            raise ValueError("模板图像尺寸大于屏幕截图")

        # 使用更鲁棒的模板匹配方法
        result = cv2.matchTemplate(screenshot_cv, template_image_cv, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        print(f"匹配结果: {result}")
        if max_val > threshold:
            h, w = template_image_cv.shape[:2]
            return (max_loc[0] + w//2, max_loc[1] + h//2)
        return None

def bbox_to_coords(bbox: tuple) -> tuple[float, float]:
    """将 bbox 坐标转换为屏幕坐标"""
    screen_width, screen_height = pyautogui.size()
    xmin, ymin, xmax, ymax = bbox

    # 计算相对坐标
    x_center = (xmin + xmax) / 2 * screen_width
    y_center = (ymin + ymax) / 2 * screen_height

    # 坐标边界检查
    x_center = max(0, min(x_center, screen_width))
    y_center = max(0, min(y_center, screen_height))

    # 调试日志优化
    debug_info = (
        f"\n坐标转换详情："
        f"屏幕尺寸: {screen_width}x{screen_height}\n"
        f"原始bbox: {bbox}\n"
        f"计算结果: ({x_center:.1f}, {y_center:.1f})"
    )
    print(debug_info)

    return x_center, y_center

def find_coordinates(icons: list, target_icon: str) -> tuple:
    """在解析内容中查找指定的图标坐标"""
    try:
        index = int(target_icon)
        return icons[index]['bbox']
    except (ValueError, IndexError, KeyError) as e:
        raise ValueError(f"无效的图标索引: {target_icon}") from e

if __name__ == "__main__":
    client = APIClient()
    # 测试smart_locate
    result = client.smart_locate('core\\api\\test.png')
    print("需要点击的坐标:", result)

    pyautogui.click(result)