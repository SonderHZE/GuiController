import base64
import io

import pyautogui
import requests
from PIL import Image

import main_window
import screen_controller
import config


def process_image(
        image_path: str,
        api_url: str = "http://localhost:1145/process_image",
        box_threshold: float = 0.05,
        iou_threshold: float = 0.1,
        use_paddleocr: bool = True,
        imgsz: int = 640
):
    files = {
        'file': ('image.png', open(image_path, 'rb'), 'image/png')
    }

    params = {
        'box_threshold': box_threshold,
        'iou_threshold': iou_threshold,
        'use_paddleocr': use_paddleocr,
        'imgsz': imgsz
    }

    print(f"发送请求至 {api_url}")

    response = requests.post(api_url, files=files, params=params)

    if response.status_code == 200:
        result = response.json()

        if result['status'] == 'success':
            labeled_image = Image.open(io.BytesIO(base64.b64decode(result['labeled_image'])))
            return {
                'status': 'success',
                'labeled_image': labeled_image,
                'parsed_content': result['parsed_content'],
                'label_coordinates': result['label_coordinates']
            }
        else:
            return {'status': 'error', 'message': result.get('message', 'Unknown error')}
    else:
        return {'status': 'error', 'message': f'HTTP error {response.status_code}'}

def bbox_to_coords(bbox):
    """将 bbox 坐标转换为屏幕坐标."""
    screen_width, screen_height = pyautogui.size()

    xmin, ymin, xmax, ymax = bbox

    # 向上偏移以避免点击到文件名
    y_offset = 0

    # 计算相对坐标
    x_center = (xmin + xmax) / 2 * screen_width
    y_center = (ymin + ymax) / 2 * screen_height - y_offset


    # 添加调试信息
    print(f"\n坐标转换详情:")
    print(f"屏幕尺寸: {screen_width} x {screen_height}")
    print(f"原始bbox: {bbox}")
    print(f"x轴变换: {xmin:.4f} -> {xmax:.4f} 中点: {(xmin + xmax) / 2:.4f}")
    print(f"y轴变换: {ymin:.4f} -> {ymax:.4f} 中点: {(ymin + ymax) / 2:.4f}")
    print(f"向上偏移: {y_offset}px")
    print(f"计算结果: x={x_center}, y={y_center}")

    # 确保坐标在屏幕范围内
    x_center = max(0, min(x_center, screen_width))
    y_center = max(0, min(y_center, screen_height))

    return x_center, y_center

def find_coordinates(icons, target_icon):
    """在解析内容中查找指定的图标."""
    # 将target_icon转换为数据类型
    target_icon = int(target_icon)
    return icons[target_icon]['bbox']

if __name__ == "__main__":
    # 获取并打印屏幕分辨率
    screen_width, screen_height = pyautogui.size()
    print(f"当前屏幕分辨率: {screen_width}x{screen_height}")

    # 打开主窗口
    pyAutoWrapper = screen_controller.PyAutoGUIWrapper(pause=1.0)
    floatingWindow = main_window.FloatingWindow(pyAutoWrapper)
    floatingWindow.show()


    img = pyAutoWrapper.screen_shot()
    img.save("screenshot.png")

    result = process_image(
        image_path="screenshot.png",
        box_threshold=config.BOX_THRESHOLD,
        iou_threshold=config.IOU_THRESHOLD,
        use_paddleocr=config.USE_PADDLEOCR,
        imgsz=config.IMGSZ
    )


