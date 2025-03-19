# model_parser.py
import base64
from openai import OpenAI
from config import BASE_URLS, API_KEYS, LABELED_IMAGE_PATH
import config

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
    def analyze_prompt(self):
        return f"""
       1. 环境感知与历史回顾  
        - 当前界面描述：  
        "当前界面显示[具体界面元素，如：桌面/XX软件窗口]，包含[可见控件，如：[图标名称]、[输入框]、[按钮]]，指出可能需要的图标的ID。"
        - 历史操作引用：  
        "用户此前执行过[操作1]、[操作2]， 判断当前界面是否实现了上一步的操作。"
        - 特别提醒：
        "打开一个软件需要使用open操作,不能使用click操作。"

        2. 目标分析与路径规划  
        - 目标拆解层级：
          ① 主任务: "[目标]"
          ② 当前进展: 已完成 [pre_actions]
          ③ 待完成子任务: [根据界面元素推断]
          
        - 快捷键决策矩阵（优先级排序）：
          1) 系统级快捷键（立即生效）：
            窗口管理: Win+D(显示桌面)/Alt+Tab(切换窗口)
          2) 应用级快捷键（需焦点在目标应用）：
            Office: Ctrl+S(保存)/F12(另存为)
            浏览器: Ctrl+T(新标签)/Ctrl+W(关闭标签)
            
        - 路径生成规则：
          1. 当检测到「精确匹配」的快捷键方案时 → 直接采用
          2. 当界面存在「高置信度元素」(相似度>85%) → 优先open/click
          3. 混合路径示例：
            "使用Win+R打开运行 → input输入'cmd' → press_enter执行"
        - 有效性校验条件：
          快捷键是否在当前系统环境可用
          界面元素是否处于可交互状态

        3. 动作封装与输出  
        - 单步操作指令： 
        - 每一次执行的图标id都可能不同，你需要根据最新给出的图标id来执行操作，对于不需要id的操作，你应当将其id设置为-1
        - 每一个指明的图标ID必须是真实的，符合图片以及给出的数据要求的，请先指出ID，再执行操作
        - open操作包括：定位图标→双击打开软件（打开软件最佳选择）
        - input操作包括：定位图标→点击图标并清空内容→输入内容→回车（因此如果需要在一个输入框进行输入操作，不需要提前click操作，也不需要enter操作）
        - hotkey操作包括：直接执行热键操作
        - click操作包括：定位图标→【选择的鼠标按键】点击【点击次数】次。
        "最终建议：[操作类型] [参数]。例如：  
        - `open 浏览器(id 25)；  
        - `input 搜索框(id 11) 输入'hello'`；  
        - `hotkey Ctrl+C`。"  
        - `click 发送按键（id 19） 左键 1次；
        - `finish 当你当前状态已经满足用户指令时。"

        4. 输出格式规范  
        - 最终指令：用`最终建议：`明确标出单步操作，格式严格遵循`[操作类型] [参数],同时给出理由与目的。`
        """

    @property
    def execute_prompt(self):
        return f"""
        认知架构设计（与分析者协同）
        1. 语义解析层：解析分析者提供的「最终建议」指令
        2. 根据分析者给出的建议，判断是否能够完成其目标，例如意图打算打开一个应用程序时，分析者可能给出click一次图标的操作，但实际上应用程序可能需要双击才能打开，因此需要判断是否需要执行open操作。
        3. 强制JSON格式输出，严格遵循Schema
        4. 分析者给出的id可能是错误的，需要你重新判断是否正确，例如分析者给出的id是19，但实际上应用程序中并没有这个id或者这个id是错误的，因此需要你重新判断是否正确。
        5. 分析者试图打开一个应用程序时，你需要判断是否需要执行open操作，如果需要执行open操作，你需要给出open操作的指令
        6. 对于不需要id的操作，你应当将其id设置为-1

        动态决策流程图:接收分析者指令 → 解析指令结构 → 元素匹配验证 → 生成JSON → 输出结果。

        JSON Schema
        {{
            "action": "open|click|scroll|input|hotkey|press_enter|finish",  // 必须为枚举值
            "id": int,  // 必填，界面元素唯一标识符
            "target": "元素描述",  // 必填，如"搜索框"
            "params": {{
                "text_content": "输入文本（input必填）",
                "key_sequence": ["组合键列表（hotkey必填）"],
                "button_type": "鼠标按键类型（click选填）",
                "direction": "滚动方向（scroll必填）",
                "clicks": 1  // 点击次数（默认1）
            }},
        }}

        执行验证标准
        合法示例（来自分析者建议"input 搜索框 输入'hello'并回车"）：
        {{
            "id": 23,
            "action": "input",
            "target": "搜索框",
            "params": {{
                "text_content": "hello"
            }},
        }}

        执行者职责规范
        1. 参数解析规则：
            - "open Chrome" → action=open, target="Chrome图标", id=12
            - "hotkey Ctrl+S" → action=hotkey, params.key_sequence=["ctrl","s"]
            - "input 搜索框 输入'hello'" → action=input, params.text_content="hello"
        2. 禁止行为：
            - 直接生成未解析的自然语言指令
            - 忽略Schema的必填字段
            - 生成包含循环状态的操作序列
            - json中包含不必要的信息（如多余的字段、注释）

        兼容性说明
        1. 动作封装规则：
            - "open"自动包含[移动→点击→回车]
            - "input"自动包含[定位→清空→输入→回车]

        思维链示例
        用户指令：将文档保存为PDF格式
        分析者建议："open 导出对话框 → input PDF格式"
        """

    def parse_instruction_omni(self, instruction: str, data: dict, pre_actions : list) -> str:
        """多模态解析方法优化"""
        messages = self._build_omni_messages(instruction, data, pre_actions)
        
        completion = self.client_qwen.chat.completions.create(
            model="qwen2.5-vl-72b-instruct",
            messages=messages,
            stream=True,
            stream_options={"include_usage": True}
        )
        return self._handle_streaming_response(completion)

    def parse_instruction(self, instruction: str, data: dict, pre_actions: list, analysis: str) -> str:
        """文本解析方法优化"""
        messages = [
            {"role": "system", "content": self.execute_prompt},
            {"role": "user", "content": self._build_user_prompt(instruction, data, pre_actions, analysis)}
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

    def _build_omni_messages(self, instruction: str, data: dict, pre_actions : list) -> list:
        """构建多模态消息结构"""
        return [
            {
                "role": "system",
                "content": [{
                    "type": "text",
                    "text": self.analyze_prompt
                }]
            },
            {
                "role": "user",
                "content": [
                    self._build_image_content(),
                    {"type": "text", "text": f"当前界面元素内容如:{data},已经执行过的指令有:{pre_actions},用户指令: {instruction}。请只给出基于当前界面单步操作"}
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
                print(chunk.choices[0].delta.content, end='', flush=True)
            else:
                self._log_usage(chunk.usage)
        return ''.join(result)

    def _build_user_prompt(self, instruction: str, data: dict, pre_actions : list, analysis : str) -> str:
        """构建用户提示模板"""
        return f"当前界面元素内容如:{data},已经执行过的指令有:{pre_actions},用户指令: {instruction}。请只给出基于当前界面单步操作。\n分析结果:{analysis}"

    def _log_usage(self, usage):
        """统一记录API使用情况"""
        if usage:
            print(f"API Usage: {usage}")

class WorkFlowGenerator:
    def __init__(self):
        self.client = OpenAI(api_key=API_KEYS["aliyun"], base_url=BASE_URLS["aliyun"])

    # def describe_current_desktop(self) -> str:
    #     """描述当前桌面方法"""
    #     SYSTEM = """
    #     你需要根据当前的界面，言简意赅地描述当前的界面。
    #     """
    #     messages = [
    #         {"role": "system", "content": SYSTEM},
    #         {"role": "user", "content": "请描述当前的界面，只需要描述界面元素的名称，不需要描述界面元素的内容。"}
    #     ]
    #     response = self.client.chat.completions.create(
    #         model="qwen-v",
    #         messages=messages,
    #         stream=True
    #     )

    def generate_workflow(self, instruction: str) -> str:
        """生成工作流方法"""
        print(f"可用icons: {config.ICONS}")
        SYSTEM = """
        你是一个熟悉如何操作电脑的大师，并且能够根据当前界面以及用户指令规划出一个包含多个json对象的列表。
        你需要将用户指令分解为多个子任务，每个子任务都需要一个json对象来描述。你可以通过hotkey、click、input、open、scroll、finish、finish等操作来完成子任务。
        对于快捷键，你需要使用系统级快捷键（立即生效，例如窗口管理: Win+D(显示桌面)/Alt+Tab(切换窗口)）或者应用级快捷键（需焦点在目标应用，例如Office: Ctrl+S(保存)/F12(另存为)；浏览器: Ctrl+T(新标签)/Ctrl+W(关闭标签)）。
        - 路径生成规则：
          1. 当你确定能够使用快捷键完成任务时，你需要使用快捷键。
          2. 如果你无法使用快捷键完成任务，你需要使用click、input、open、scroll等操作来完成任务。
         请你按照json的格式输出, e.g. 查看本系统python当前版本", 用于完成任务的步骤可能如下:
            ‘‘‘json
            [
                {"action": "hotkey", "id": -1, "target": "系统级快捷键", "params": {"key_sequence": ["win", "r"]}}
                {"action": "click", "id": 4, "target": "确定", "params": {"button_type": "left", "clicks": 1}}
                {"action": "input", "id": 2, "target": "输入框", "params": {"text_content": "python --version"}
            ]
            ‘‘‘
            另一个示例, 用户指令为“查看华南理工大学计算机学院的计科培养计划”，可能的操作步骤如下:
            ‘‘‘json
            [
                {"action": "open", "id": 21, "target": "Microsoft Edge图标", "params": {}
                {"action": "input", "id": 1, "target": "搜索框", "params": {"text_content": "华南理工大学计算机学院 计科培养计划"}
                {"action": "click", "id": 8, "target": "硕士培养方案-华南理工大学", "params": {"button_type": "left", "clicks": 1, "x": 393.0000042915344, "y": 412.0000022649765}}
                {"action": "click", "id": 6, "target": "计算机科学与技术[学术型硕士]--培养方案基本信息", "params": {"button_type": "left", "clicks": 1, "x": 922.0000076293945, "y": 700.0000011920929}}
            ]
            ‘‘‘
        - open操作包括：定位图标→双击打开软件（打开软件最佳选择）
        - input操作包括：定位图标→点击图标并清空内容→输入内容→回车（因此如果需要在一个输入框进行输入操作，不需要提前click操作，也不需要再进行enter操作）
        - hotkey操作包括：直接执行热键操作
        - click操作包括：定位图标→【选择的鼠标按键】点击【点击次数】次。
        请注意，click1次无法完成任务时，你需要使用click2次或者3次来完成任务，例如打开一个文件。
        每个json对象的结构如下：
                {
                "action": "open|click|scroll|input|hotkey|finish", // 必须为枚举值，可选值包括：open（打开）、click（点击）、scroll（滚动）、input（输入）、hotkey（快捷键）、finish（完成）
                "id": -1, // 当前元素的唯一标识符，若无法确定可设置为-1
                "target": "元素描述", // 当action为click、input和open时必填，如"搜索框"，表示操作的目标元素，若不需要操作元素，输入“None”
                "params": {
                "text_content": "输入文本（input必填）", // 当action为input时，必填，表示要输入的文本内容
                "key_sequence": ["组合键列表（hotkey必填）"], // 当action为hotkey时，必填，表示要按下的组合键列表
                "button_type": "鼠标按键类型（click选填）", // 当action为click时，可选填，表示鼠标按键类型，默认为左键
                "direction": "滚动方向（scroll必填）", // 当action为scroll时，必填，表示滚动的方向
                "clicks": 1 // 点击次数，默认为1次，可根据需要调整
                }
                }
        你需要确保分解后的动作能够准确无误地完成用户的任务，如果一定需要target但是没有可选的内容，用“NoFit”替代。
        hotkey、press_enter、finish都不需要target，可以直接使用。
        """

        reasoning_content = ""  # 定义完整思考过程
        answer_content = ""  # 定义完整回复
        is_answering = False  # 判断是否结束思考过程并开始回复


        print(instruction)
        response = self.client.chat.completions.create(
            model="qwq-plus",
            messages=[
                {"role": "system", "content": SYSTEM + f"目前target你只能从以下内容中选择：{config.ICONS}，你必须使用原有的名称，不得将其重命名。当前页面为Windows桌面，背景为一人使用电脑的场景。桌面上有多种应用图标（如QQ、微信、PyCharm、VS Code等）和文件夹（如homework、考研、学习等），表明用户主要从事编程、学习及办公相关活动。"},
                {"role": "user", "content": "用户指令为：" + instruction}
            ],
            stream=True
        )
        for chunk in response:
            # 如果chunk.choices为空
            if not chunk.choices:
                print("\nUsage:")
                print(chunk.usage)
            else:
                delta = chunk.choices[0].delta
                # 打印思考过程
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                    reasoning_content += delta.reasoning_content
                    print(delta.reasoning_content, end='', flush=True)
                else:
                    # 开始回复
                    if delta.content != "" and not is_answering:
                        is_answering = True
                    # 打印回复过程
                    answer_content += delta.content
                    print(delta.content, end='', flush=True)

        return answer_content