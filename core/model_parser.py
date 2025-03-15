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
智能界面操作推理系统规范 v1.1

▌认知架构设计
采用三阶决策模型实现类人推理：
1. 语义解析层：理解指令本质需求
2. 环境感知层：分析屏幕元素状态
3. 路径规划层：生成最优操作序列
4. 务必使用JSON格式输出

▌动态决策流程图
START
├─ 是否已达成目标？ → YES → 返回finish
├─ NO → 是否存在直接快捷键？ → YES → 生成hotkey
├─ NO → 目标元素是否可见？
│    ├─ YES → 是否需要输入？ → input
│    ├─ NO → 是否需要启动应用？ → open
├─ NO → 执行路径回溯（基于历史操作）
└─ 生成操作前校验：
   ├─ 元素坐标是否有效？
   ├─ 参数是否符合schema？
   └─ 是否产生状态循环？

▌增强型JSON Schema（带语义校验）
{{
    "action": "open|click|scroll|input|hotkey|press_enter|finish",  // 必须为枚举值
    "id": 图标标记序号,  // 必填，int 类型，用于选择页面元素
    "target": "存在的界面元素描述（需与屏幕元素匹配）",  // 必填
    "params": {{
        // 动态参数（按需存在）
        "clicks": 1,  // 点击次数，action 为 click 时必填， 默认为11
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
    "action": "open",
    "target": "Chrome 快捷方式",
    "params": {{}}
}}

非法输出：
{{
    "action": "打开软件",  // 非枚举值
    "target": "不存在的图标"  // 无法定位
}}

▌思维链示例（CoT模板）
用户指令：将文档保存为PDF格式
当前屏幕元素：[id:15] 文件菜单 [id:16] 导出按钮 [id:20] 保存类型下拉框

推理过程：
1. 目标解析：需要完成格式转换操作
2. 环境检测：检测到导出功能相关元素
3. 快捷键检查：常见快捷键Ctrl+Shift+S可能适用
4. 路径选择：
   - PlanA：使用hotkey直接保存（最优路径）
   - PlanB：文件菜单→导出→选择PDF格式（备用路径）
5. 生成决策：优先尝试hotkey方案
6. 单击一个图标无法启动任何应用，当你需要启动应用时，使用open或者hotkey，最后考虑使用click，并且多数为2次
7. input操作包括移动到目标位置、点击、删除原有内容、输入、回车，这些动作被封装为一个input
8. open操作包括移动到目标位置、点击、回车，这些动作被封装为一个open

▌异常处理协议
当操作失败时，启动三级恢复机制：
1. 重试策略：相同操作最多尝试2次
2. 替代路径：使用备用方案（如用click代替hotkey）
3. 环境重置：执行应用重启流程（open→操作...）
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
                    "text": f"基于当前界面以及用户指令，你需要给出一个建议，该建议为单步操作，可选操作包括：打开一个软件、点击某个图标或坐标、输入、滚动、热键、回车。单击一个图标无法启动任何应用，当你需要启动应用时，使用open或者hotkey，最后考虑使用click，并且多数为2次input操作包括移动到目标位置、点击、删除原有内容、输入、回车，这些动作被封装为一个inputopen操作包括移动到目标位置、点击、回车，这些动作被封装为一个open"
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