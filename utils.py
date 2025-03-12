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

from requests import utils
import config

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},
        "id": {"type": "integer"},
        "target": {"type": "string"},
        "params": {
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
    """记录操作日志"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action_type,
        "target": target,
        "params": params,
        "duration": round(duration, 2),
        "status": status
    }
    logging.info(json.dumps(log_entry, indent=2, ensure_ascii=False))

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

def take_screenshot(controller):
    """截图操作"""
    start_time = time.time()
    img = controller.screen_shot()
    img.save(config.SCREENSHOT_PATH)
    duration = time.time() - start_time
    return duration

def process_image():
    """图像处理"""
    import client
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
    print(f"解析结果: {ret}")
    return ret, duration

def parse_instruction(instruction, pre_actions, current_icons, type = "text"):
    """指令解析"""
    import model_parser
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

    print(f"解析结果: {action}")
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
    import client

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
            'click': lambda: controller.click(x, y, params.get('button_type', 'left')),
            'double_click': lambda: controller.double_click(x, y),
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
   