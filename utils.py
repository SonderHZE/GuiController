# utils.py
# 工具函数模块，包含日志记录、状态更新等常用函数
import ast
import json
import logging
import re
import time
from datetime import datetime
from typing import final
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
                "key_sequence": {"type": "array"},
                "direction": {"type": "string"},
                "clicks": {"type": "integer"}
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

def parse_instruction(instruction, pre_actions, current_icons, analysis = "", type = "text"):
    """指令解析"""
    from core.model_parser import ModelParser
    model_parser = ModelParser()
    start_time = time.time()
    if type == "text":
        action = model_parser.parse_instruction(
            f"{instruction}",
            current_icons,
            pre_actions,
            analysis=analysis
        )
    else:
        action = model_parser.parse_instruction_omni(
            instruction,
            current_icons,
            pre_actions
        )
    duration = time.time() - start_time

    return action, duration

def robust_json_extract(text: str):
    """健壮的JSON提取"""
    try:
        # 尝试直接将文本解析为JSON
        if isinstance(text, list):
            text = json.dumps(text)
        action_sequence = json.loads(text)
        return action_sequence
    except json.JSONDecodeError:
        if match := JSON_PATTERN.search(text):
            match = match.group(1).strip()
            match = match.replace('```json', '').replace('```', '')
            # 若匹配内容是列表，转换为字符串
            if isinstance(match, list):
                match = json.dumps(match)
            action_sequence = json.loads(match)
            return action_sequence
    raise ValueError("未找到有效JSON内容")

def execute_action(controller, action_data, objs, ifWorkFlw=False):
    """执行动作
    Args:
        controller: 屏幕控制器实例
        action_data: 动作数据(dict/list)
        objs: 界面对象列表
        ifWorkFlw: 是否工作流模式
    """
    from core.api import client
    from core.screen_controller import PyAutoGUIWrapper
    
    # 统一转换为字典格式
    final_action = action_data[0] if isinstance(action_data, list) else action_data.copy()
    action_type = final_action.get('action', 'unknown')
    params = final_action.get('params', {})
    target_key = 'target' if ifWorkFlw else 'id'
    target_icon = final_action.get(target_key)

    # 初始化执行器
    executor = PyAutoGUIWrapper() if ifWorkFlw else controller
    log_prefix = "[Workflow]" if ifWorkFlw else "[SingleStep]"
    
    try:
        # 获取坐标参数
        if params.get('x') and params.get('y'):
            x, y = params['x'], params['y']
        else:
            x, y = _get_action_coordinates(
                action_type=action_type,
                target_icon=target_icon,
                params=params,
                objs=objs,
                executor=executor,
                ifWorkFlw=ifWorkFlw
            )
        
        # 更新最终参数
        if x and y:
            params.update({"x": x, "y": y})
            final_action['params'] = params
        
        print(x,y)

        # 执行核心操作
        return _execute_core_action(
            executor=executor,
            action_type=action_type,
            params=params,
            final_action=final_action,
            log_prefix=log_prefix
        )
        
    except Exception as e:
        logging.error(f"{log_prefix} 执行失败: {str(e)}")
        raise e

def _get_action_coordinates(action_type, target_icon, params, objs, executor, ifWorkFlw):
    """获取动作坐标"""
    from core.api import client
    # 已有坐标直接返回
    if params.get('x') and params.get('y'):
        return params['x'], params['y']
        
    # 需要坐标的操作类型
    if action_type in ['click', 'open', 'input']:
        if not target_icon:
            raise ValueError(f"缺少必要参数: {target_icon}")
            
        # 工作流模式使用图标查找
        if ifWorkFlw:
            return executor.find_icons(f"icons/{target_icon}.png")
            
        # 普通模式使用坐标解析
        if objs and target_icon != -1:
            bbox = client.find_coordinates(objs, target_icon)
            return client.bbox_to_coords(bbox)
            
    return None, None

def _execute_core_action(executor, action_type, params, final_action, log_prefix):
    """执行核心操作逻辑"""
    from core.api import client
    
    action_handlers = {
        'click': lambda: executor.click(
            params.get('x'), params.get('y'),
            params.get('button_type', 'left'),
            params.get('clicks', 1)
        ),
        'open': lambda: executor.open(params.get('x'), params.get('y')),
        'input': lambda: executor.input(
            params['text_content'],
            params.get('x'), params.get('y')
        ),
        'scroll': lambda: executor.scroll(params['direction']),
        'hotkey': lambda: executor.hot_key(*params['key_sequence']),
        'press_enter': lambda: executor.press_enter(),
        'finish': lambda: None
    }

    if action_type not in action_handlers:
        raise ValueError(f"未知动作类型: {action_type}")

    start_time = time.time()
    try:
        logging.info(f"{log_prefix} 开始执行 {action_type}")
        action_handlers[action_type]()
        
        if action_type == 'finish':
            return None

        duration = time.time() - start_time
        logging.info(f"{log_prefix} {action_type} 执行成功，耗时: {duration:.2f}s")
        return action_type, final_action.get('target'), params, duration, "success", final_action
        
    except Exception as e:
        logging.error(f"{log_prefix} 操作执行失败: {str(e)}")
        raise 

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

def generate_workflow(instruction):
    """生成工作流"""
    from core.model_parser import WorkFlowGenerator
    model_parser = WorkFlowGenerator()
    start_time = time.time()
    workflow = model_parser.generate_workflow(instruction)
    workflow = robust_json_extract(workflow)
    duration = time.time() - start_time
    return workflow, duration

def maximize_window(title, controller):
    """最大化指定窗口"""
    try:
        hwnd = controller.find_window_by_title(title)
        controller.set_foreground_window(hwnd)
        controller.maximize_window()
    except Exception as e:
        logging.error(f"最大化窗口失败: {str(e)}")

def _execute_core_action(executor, action_type, params, final_action, log_prefix):
    """执行核心操作逻辑"""
    from core.api import client
    
    action_handlers = {
        'click': lambda: executor.click(
            params.get('x'), params.get('y'),
            params.get('button_type', 'left'),
            params.get('clicks', 1)
        ),
        'open': lambda: executor.open(params.get('x'), params.get('y')),
        'input': lambda: executor.input(
            params['text_content'],
            params.get('x'), params.get('y')
        ),
        'scroll': lambda: executor.scroll(params['direction']),
        'hotkey': lambda: executor.hot_key(*params['key_sequence']),
        'press_enter': lambda: executor.press_enter(),
        'finish': lambda: None,
        'delay': lambda: time.sleep(params.get('seconds', 1)),  # 添加延迟操作
        'move': lambda: executor.move_to(params.get('x'), params.get('y'))  # 添加鼠标移动操作
    }

    if action_type not in action_handlers:
        raise ValueError(f"未知动作类型: {action_type}")

    start_time = time.time()
    try:
        logging.info(f"{log_prefix} 开始执行 {action_type}")
        action_handlers[action_type]()

        if action_type == 'finish':
            return None

        duration = time.time() - start_time
        logging.info(f"{log_prefix} {action_type} 执行成功，耗时: {duration:.2f}s")
        return action_type, final_action.get('target'), params, duration, "success", final_action

    except Exception as e:
        logging.error(f"{log_prefix} 操作执行失败: {str(e)}")
        raise 
