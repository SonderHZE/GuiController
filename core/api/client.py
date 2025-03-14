import base64
import io
from typing import NamedTuple, Dict, Any, Optional

import pyautogui
import requests
from PIL import Image

import config


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



