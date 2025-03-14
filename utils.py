# utils.py
# 工具函数模块，包含日志记录、状态更新等常用函数
import ast
import json
import logging
import re
import time
from datetime import datetime
from jsonschema import validate
from PyQt5.QtWidgets import QApplication
import os
import pyautogui

import config

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "action": {"type": "string"},
        "target": {"type": "string"},
        "value": {
            "type": "object",
            "properties": {
                "button_type": {"type": "string"},
                "text_content": {"type": "string"},
                "key_sequence": {"type": "array"}
            },
        }
    },
    "required": ["id", "action", "target"]
}


JSON_PATTERN = re.compile(r'```json(.*?)```', re.DOTALL)
def log_operation(action_type: str, target: str, params: dict, duration: float, status: str):
    """记录操作日志（新增坐标记录）"""
    # 从参数中提取坐标信息
    coord = {
        'x': params.get('x'),
        'y': params.get('y'),
        'screen_width': pyautogui.size()[0],
        'screen_height': pyautogui.size()[1]
    } if 'x' in params or 'y' in params else None
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action_type,
        "target": target,
        "params": params,
        "coord": coord,  # 新增坐标信息
        "duration": round(duration, 2),
        "status": status
    }
    
    with open(config.LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

def load_action_history(file_path) -> list:
    """加载历史操作数据"""
    history = []
    try:
        # 使用严格模式打开文件防止编码问题
        with open(file_path, 'r', encoding='utf-8', errors='strict') as f:
            lines = [line.strip() for line in f.readlines()]
            
            try:
                for action_line in lines:
                    # 使用正则表达式提取JSON部分
                    action = robust_json_extract(action_line)
                    if action:
                        validate(action, JSON_SCHEMA)
                        history.append(action)
                        
            except Exception as e:
                    logging.error(f"未知错误解析历史记录: {str(e)}")

    except FileNotFoundError:
        logging.warning(f"历史操作文件不存在: {file_path}")
    except UnicodeDecodeError:
        logging.error("文件编码不符合UTF-8规范")
    except Exception as e:
        logging.error(f"未知错误加载历史记录: {str(e)}")
        
    print(f"历史操作记录记录: {history}")
    return history

def load_instruction_history(file_path) -> list:
    """加载历史指令数据"""
    history = []
    # 读取文件夹中所有的.jsonl
    try:
        for filename in os.listdir(file_path): 
            if filename.endswith('.jsonl'):
                history.append(filename)

        
        # 按照时间戳排序
        history.sort(key=lambda x: os.path.getmtime(os.path.join(file_path, x)), reverse=True)
        # 仅保留最近100条记录防止内存溢出
        history = history[:100]

        return history
    except FileNotFoundError:
        logging.warning(f"历史指令文件夹不存在: {file_path}")
    except Exception as e:
        logging.error(f"未知错误加载历史记录: {str(e)}")
    
    return history

def update_status(input_box, message: str):
    """更新状态提示"""
    input_box.setPlaceholderText(message)
    QApplication.processEvents()

def take_screenshot(controller, image_path = config.SCREENSHOT_PATH):
    """截图操作"""
    start_time = time.time()
    img = controller.screen_shot()
    img.save(image_path)
    duration = time.time() - start_time
    return duration

def process_image():
    """图像处理"""
    from core.api.client import APIClient
    client = APIClient()
    start_time = time.time()
    result = client.process_image(
        image_path=config.SCREENSHOT_PATH,
        box_threshold=config.BOX_THRESHOLD,
        iou_threshold=config.IOU_THRESHOLD,
        use_paddleocr=config.USE_PADDLEOCR,
        imgsz=config.IMGSZ
    )
    duration = time.time() - start_time
    return result, duration

def parse_data(result):
    """解析数据"""
    start_time = time.time()
    objs = []
    lines = result.strip().split('\n')
    for line in lines:
        try:
            # 提取花括号中的内容
            dict_str = line[line.index('{'):line.rindex('}') + 1]
            # 解析字符串为字典
            icon_data = ast.literal_eval(dict_str)
            objs.append(icon_data)
        except Exception as e:
            print(f"解析错误: {e}")
            continue

    ret = []
    count = 0
    for obj in objs:
        if obj["content"] != "No object detected.":
            ret.append({
                "id": count,
                "type": obj["type"],
                "content": obj["content"],
                "bbox": obj["bbox"],
            })
            count += 1

    duration = time.time() - start_time
    return ret, duration

def parse_instruction(instruction, pre_actions, current_icons, type = "text"):
    """指令解析"""
    from core.model_parser import ModelParser
    model_parser = ModelParser()
    start_time = time.time()
    if type == "text":
        action = model_parser.parse_instruction(
            f"{instruction} 先前操作：{pre_actions}",
            current_icons
        )
    else:
        action = model_parser.parse_instruction_omni(
            f"{instruction} 先前操作：{pre_actions}",
            current_icons
        )
    duration = time.time() - start_time

    return action, duration

def robust_json_extract(text: str):
    """健壮的JSON提取"""
    try:
        action_sequence = json.loads(text)
        return action_sequence
    except json.JSONDecodeError:
        if match := JSON_PATTERN.search(text):
            match = match.group(1).strip()
            match = match.replace('```json', '').replace('```', '')

            action_sequence = json.loads(match)
            return action_sequence
    raise ValueError("未找到有效JSON内容")

def execute_action(controller, action_data, objs):
    """执行动作"""
    from core.api import client
    # 确保action_data为字典
    if isinstance(action_data, list):
        action_data = action_data[0]

    target_icon = action_data.get('id')
    if target_icon is None:
        raise ValueError("动作数据中缺少 'id' 字段")

    # 初始化参数
    params = action_data.get('params', {})
    x, y = None, None
    action_type = action_data.get('action', 'unknown')

    # 如果有目标对象，获取坐标并更新参数
    if objs is not None:
        bbox = client.find_coordinates(objs, target_icon)
        if bbox is not None:
            x, y = client.bbox_to_coords(bbox)
            params.update({"x": x, "y": y})
    else:
        x,y = params.get('x'),params.get('y')


    # 执行动作
    start_time = time.time()
    try:
        actions = {
            'click': lambda: controller.click(x, y, params.get('button_type', 'left'), params.get('clicks', 1)),
            'open': lambda: controller.open(x, y),
            'input': lambda: controller.input(params['text_content'], x, y),
            'scroll': lambda: controller.scroll(params['direction']),
            'hot_key': lambda: controller.hot_key(params['key_sequence']),
            'press_enter': lambda: controller.press_enter(),
            'finish': lambda: None
        }
        action_func = actions.get(action_type)
        if action_func is None:
            raise ValueError(f"未知的动作类型: {action_type}")
        action_func()

        if action_type == 'finish':
            return None

        duration = time.time() - start_time
        return action_type, target_icon, params, duration, "success"
    except Exception as e:
        duration = time.time() - start_time
        return action_type, target_icon, params, duration, f"failed: {str(e)}"
   
def compare_image_similarity(image1_path, image2_path):
    """比较图像相似度
    返回包含SSIM、PSNR和MSE的字典，值范围：
    - SSIM: [-1, 1]（1表示完全相同）
    - PSNR: [0, ∞]（值越大越好，通常>30可认为相似）
    - MSE: [0, ∞]（0表示完全相同）
    """
    from PIL import Image
    from skimage.metrics import structural_similarity as ssim
    from skimage.metrics import peak_signal_noise_ratio as psnr
    from skimage.metrics import mean_squared_error
    import numpy as np
    
    try:
        # 加载并转换图像为灰度图
        img1 = Image.open(image1_path).convert('L')
        img2 = Image.open(image2_path).convert('L')
        
        # 统一图像尺寸
        if img1.size != img2.size:
            min_size = (min(img1.width, img2.width), min(img1.height, img2.height))
            img1 = img1.resize(min_size)
            img2 = img2.resize(min_size)
            
        img1_arr = np.array(img1)
        img2_arr = np.array(img2)
        
        # 计算指标
        ssim_score = ssim(img1_arr, img2_arr, full=True)[0]
        mse_score = mean_squared_error(img1_arr, img2_arr)
        psnr_score = psnr(img1_arr, img2_arr)
        

        print(f"SSIM: {ssim_score}")
        print(f"PSNR: {psnr_score}")
        print(f"MSE: {mse_score}")
        return {
            "ssim": round(ssim_score, 4),
            "psnr": round(psnr_score, 2),
            "mse": int(mse_score)
        }
        
    except Exception as e:
        logging.error(f"图像相似度比较失败: {str(e)}")
        return {
            "ssim": 0.0,
            "psnr": 0.0,
            "mse": 999999
        }

def get_all_windows_titles():
    """获取所有窗口标题"""
    import win32gui
    def _enum_windows(hwnd, result):
        result.append(win32gui.GetWindowText(hwnd))
    windows = []
    win32gui.EnumWindows(_enum_windows, windows)
    return windows

def maximize_window(title, controller):
    """最大化指定窗口"""
    try:
        hwnd = controller.find_window_by_title(title)
        controller.set_foreground_window(hwnd)
        controller.maximize_window()
    except Exception as e:
        logging.error(f"最大化窗口失败: {str(e)}")