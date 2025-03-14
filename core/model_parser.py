# model_parser.py
import base64
from openai import OpenAI
from config import BASE_URLS, API_KEYS, LABELED_IMAGE_PATH

class ModelParser:
    def __init__(self):
        self.client_ds = OpenAI(api_key=API_KEYS["local"], base_url=BASE_URLS["local"])
        self.client_qwen = OpenAI(api_key=API_KEYS["aliyun"], base_url=BASE_URLS["aliyun"])

    #  base 64 编码格式
    def encode_image(self, image_path: str) -> str:
        """将图像编码为base64字符串"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except FileNotFoundError as e:
            raise ValueError(f"图像文件未找到: {image_path}") from e

    @property
    def prompt(self):
        return f"""
核心任务：
基于用户指令和当前屏幕状态，按以下逻辑生成操作序列：
1. 指令目标达成 → 返回终止标记
2. 存在未完成步骤 → 生成可执行动作
3. 确保动作可被自动化工具精准执行
4. 打开软件使用 "open" 操作
5. 遇到输入框，直接输入文本无需点击
6. 任务完成，直接返回终止标记
7. 打开操作通过双击图标实现

输入输出规范：
- 用户指令：自然语言描述的任务目标
- 屏幕截图：CV 解析的界面元素信息
- 历史操作：已执行步骤的轨迹记录

JSON 结构规范（严格模式）：
{{
    "action": "click|open|scroll|input|hotkey|press_enter|finish",  // 必须为枚举值
    "id": 图标标记序号,  // 必填，int 类型，用于选择页面元素
    "target": "存在的界面元素描述（需与屏幕元素匹配）",  // 必填
    "params": {{
        // 动态参数（按需存在）
        "clicks": 2,  // 点击次数，action 为 click 时必填
        "button_type": "left|right|middle",  // 默认 left
        "text_content": "str",  // 输入动作必填
        "direction": "up|down|left|right",  // 滚动方向，action 为 scroll 时必填
        "key_sequence": ["ctrl", "c"]  // 组合键必填
    }}
}}

验证标准示例：
合法输出：
{{
    "id": 12,
    "action": "double_click",
    "target": "Chrome 快捷方式",
    "params": {{}}
}}

非法输出：
{{
    "action": "打开软件",  // 非枚举值
    "target": "不存在的图标"  // 无法定位
}}

特殊约束：
1. 原子操作：每次仅生成一个待执行动作
2. 路径回溯：操作失败时生成替代方案
3. 状态感知：通过历史操作避免循环
4. "input" 操作包含输入文本并按下回车键
5. 点击操作包含点击次数和类型
6. 滚动操作包含滚动方向和次数
7. 组合键操作包含组合键序列
8. 一定要思考是open还是click
9. 遵循 jsonschema 规范

最后校验：
1. "id" 必须是图片中被标记的
2. 动作类型符合枚举值
3. 必需参数完整
4. 坐标值在屏幕分辨率范围内
"""

    def parse_instruction_omni(self, instruction: str, data: dict) -> str:
        """多模态解析方法优化"""
        messages = self._build_omni_messages(instruction, data)
        
        completion = self.client_qwen.chat.completions.create(
            model="qwen-vl-max",
            messages=messages,
            stream=True,
            stream_options={"include_usage": True}
        )
        return self._handle_streaming_response(completion)

    def parse_instruction(self, instruction: str, data: dict) -> str:
        """文本解析方法优化"""
        messages = [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": self._build_user_prompt(instruction, data)}
        ]
        
        response = self.client_qwen.chat.completions.create(
            model="qwen-max",
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=8192,
            temperature=0,
            presence_penalty=1.1,
            top_p=0.95
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("The response content is None.")
        return content

    def _build_omni_messages(self, instruction: str, data: dict) -> list:
        """构建多模态消息结构"""
        return [
            {
                "role": "system",
                "content": [{
                    "type": "text",
                    "text": f"基于当前界面以及用户指令，你需要给出一个建议，该建议为单步操作，可选操作包括：点击、打开、输入、滚动、热键、回车。"
                }]
            },
            {
                "role": "user",
                "content": [
                    self._build_image_content(),
                    {"type": "text", "text": f"界面元素信息如下: {data}, 用户指令: {instruction}。请只给出基于当前界面单步操作"}
                ]
            }
        ]

    def _build_image_content(self) -> dict:
        """构建图像内容结构"""
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{self.encode_image(LABELED_IMAGE_PATH)}"
            }
        }

    def _handle_streaming_response(self, completion) -> str:
        """统一处理流式响应"""
        result = []
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content:
                result.append(chunk.choices[0].delta.content)
            else:
                self._log_usage(chunk.usage)
        return ''.join(result)

    def _build_user_prompt(self, instruction: str, data: dict) -> str:
        """构建用户提示模板"""
        return f"当前界面元素信息如下: {data}, 用户指令: {instruction}，请生成操作序列。"

    def _log_usage(self, usage):
        """统一记录API使用情况"""
        if usage:
            print(f"API Usage: {usage}")