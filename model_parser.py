# model_parser.py
import base64
import config
from openai import OpenAI
from config import BASE_URLS, MODELS, API_KEYS

client_ds = OpenAI(api_key=API_KEYS["local"], base_url=BASE_URLS["local"])
client_qwen = OpenAI(api_key=API_KEYS["aliyun"], base_url=BASE_URLS["aliyun"])

#  base 64 编码格式
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

prompt = f"""
    核心任务：
    基于用户指令和当前屏幕状态，严格按以下逻辑生成操作序列：
    1. 当检测到指令目标已达成 → 返回终止标记
    2. 当存在未完成步骤 → 生成可执行动作
    3. 确保每个动作均可被自动化工具精准执行
    4. 如果是打开一个软件，通常是双击图标
    5. 如果看到一个输入框，直接输入文本内容而不需要点击
    6. 如果你认为任务已经完成，可以直接返回终止标记

    输入输出规范：
    1.用户指令：自然语言描述的任务目标
    2.屏幕截图：通过 CV 解析的界面元素信息 
    3.历史操作：已执行步骤的轨迹记录

     JSON 结构规范（严格模式）
    {{
      "action": "[click|double_click|scroll|input|hotkey|press_enter|finish]",  // 必须枚举值
      "id": 图标被标记的序号,  // 必填,用于选择存在的页面元素被标记的序号,int类型
      "target": "存在的界面元素描述（需与屏幕元素匹配）",  // 必填
      "params": {{
        // 动态参数（当且仅当需要时存在）
        "clicks": 2,                         // 点击次数，当 action 为 click 时必填
        "button_type": "left|right|middle",    // 默认 left
        "text_content": "str",                // 输入动作必填
        "key_sequence": ["ctrl","c"]          // 组合键必填
      }}
    }}

    验证标准示例
    合法输出：
    {{
          "id" : 12
          "action": "double_click",
          "target": "Chrome 快捷方式",
          "params": {{}}
    }}

    非法输出：
    {{
      "action": "打开软件",  // 非枚举值
      "target": "不存在的图标"  // 无法定位
    }}

    特殊约束
    1. 原子操作：每次仅生成一个待执行动作
    2. 路径回溯：当操作失败时生成替代方案
    3. 状态感知：通过历史操作避免循环
    4. input操作包含了输入文本内容然后按下回车键
    5. 点击操作包含了点击次数和点击类型
    6. 滚动操作包含了滚动方向和滚动次数
    7. 组合键操作包含了组合键序列
    8. 严格区分单独点击和双击
    9. 遵循jsonschema规范

    最后校验
    请严格检查以下事项：
    [ ] 1. id必须是图片中被标记的
    [ ] 2. 动作类型符合枚举值
    [ ] 3. 必需参数完整
    [ ] 4. 坐标值在屏幕分辨率范围内
    """
# 多模态解析
def parse_instruction_omni(instruction, data):
    completion = client_qwen.chat.completions.create(
        model="qwen-vl-max",
        messages=[
            {
                "role": "system",
                "content": [{"type": "text", "text": "解析图片内容，结合当前界面元素信息以及用户指令，判断在该界面应该执行的操作,请注意是单步操作，尽可能给出应当操作的图标的编号，或者描述内容，如果不需要操作图标则不用编号。"}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encode_image(config.LABELED_IMAGE_PATH)}"
                        },
                    },
                    {"type": "text", "text": f"界面元素信息如下: {data}, 用户指令: {instruction}。请只给出基于当前界面单步操作！"},
                ],
            },
        ],
        # 设置输出数据的模态，当前支持["text"]
        modalities=["text"],
        # stream 必须设置为 True，否则会报错
        stream=True,
        stream_options={
            "include_usage": True
        }
    )

    result = ""
    for chunk in completion:
        if chunk.choices and chunk.choices[0].delta.content:
            result += chunk.choices[0].delta.content
        else:
            print(chunk.usage)

    print(result)
    return result
def parse_instruction(instruction, data):
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"当前界面元素信息如下: {data}, 用户指令: {instruction}，请生成操作序列。"}
    ]

    print(data)

    response = client_qwen.chat.completions.create(
        model="qwen-max",
        messages=messages,
        max_tokens=8192,
        temperature=0,
        presence_penalty=1.1,
        top_p=0.95,
        response_format={"type": "json_object"}
    )

    result = response.choices[0].message.content
    return result

