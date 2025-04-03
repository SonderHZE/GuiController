# model_parser.py
import base64
import logging
from typing import Dict, List, Optional, Any, Union
from openai import OpenAI
from config import BASE_URLS, API_KEYS, LABELED_IMAGE_PATH
import config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelParser:
    """模型解析器，负责与AI模型交互并解析指令"""
    
    def __init__(self):
        """初始化模型客户端"""
        try:
            self.client_ds = OpenAI(api_key=API_KEYS["local"], base_url=BASE_URLS["local"])
            self.client_qwen = OpenAI(api_key=API_KEYS["aliyun"], base_url=BASE_URLS["aliyun"])
            logger.info("ModelParser初始化成功")
        except Exception as e:
            logger.error(f"ModelParser初始化失败: {e}")
            raise

    def encode_image(self, image_path: str) -> str:
        """将图像编码为base64字符串
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            base64编码的字符串
            
        Raises:
            ValueError: 当图像文件未找到时
        """
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except FileNotFoundError as e:
            error_msg = f"图像文件未找到: {image_path}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"图像编码失败: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e

    @property
    def analyze_prompt(self) -> str:
        """分析提示词模板"""
        return """
        你是一名电脑专家，你首先需要明确当前电脑界面包含了什么内容，明确每一个可见控件的被框选的内容以及id。
        接着，你需要明确用户当前的指令是什么，明确用户的意图，然后判断用户的意图在当前界面是否已经完成，如果已经完成，那么你需要给出一个finish操作，否则你需要给出一个操作来完成用户的指令。
        然后，你需要根据当前界面和用户的指令，给出一个基于当前界面的单步操作，你必须明确指出要操作的具体元素的id，以及对应的操作内容，参考动作封装要求，你每次只能给出一个操作。
        每一次操作，你需要优先考虑使用快捷键操作（如能用hotkey完成不用click）。
        利用hotkey等快捷键进行系统级快捷键（如Win+D、Alt+Tab）或应用级快捷键如Ctrl+S、F12）应优先使用。若无法用快捷键完成，则依次选择open、input、click等操作。 
        可使用的五种操作有：
            hotkey：直接执行（如"hotkey Ctrl+C"）
            open：定位图标→双击（如"open 浏览器(id 25)"）
            input：定位→清空→输入→回车（如"input 搜索框(id 11) 输入'hello'"）
            click：指定ID和点击次数（如"click 发送按钮(id 19) 左键1次"）
            finish：当你认为目标达成时使用
        click/open/input必须使用当前界面存在的有效ID（>0），禁止操作未被框选或超出屏幕的元素，禁止操作含'单步执行''执行''停止'等字样的底部控制台
        当出现以下情况立即尝试使用其他途径：用户指令需要操作不存在于当前界面的控件，要求的操作类型与目标元素不匹配（如对文本框执行open操作），检测到循环操作超过3次未达成目标。
        避免使用任务管理器，如果能够通过快捷键完成，优先使用快捷键，比如命令行指令。
        你必须给出你的推理过程，保证推理过程清晰可见，最后给出操作指令。
        """

    @property
    def execute_prompt(self) -> str:
        """执行提示词模板"""
        return """
        你是一个电脑操作专家，你的任务是根据用户指令和当前界面元素数据，以及分析者给出的建议，生成一个符合要求的json格式的操作指令，例如：{"action":"input","id":23,"target":"搜索框","params":{"text_content":"hello"}}
        JSON Schema定义：
        {
            "action": "open|click|scroll|input|hotkey|finish",
            "id": int（open/click/input操作需有效ID，hotkey/finish设为-1）,
            "target": "元素描述",
            "params": {
                "text_content": "输入文本（input必填）",
                "key_sequence": ["组合键列表（hotkey必填）"],
                "button_type": "left/right"（click可选，默认left）,
                "direction": "up/down"（scroll必填）,
                "clicks": 1（如需双击设为2）
            }
        }

        执行验证标准：
        - 合法示例：分析者建议"input 搜索框 输入'hello'" → 输出如上JSON。
        - 错误示例：input操作设id=-1或hotkey缺少key_sequence字段。

        执行者职责规范：
        1. 参数解析规则：
        - "open Chrome" → action=open, target=Chrome图标, id=12
        - "hotkey Ctrl+S" → action=hotkey, params.key_sequence=["ctrl","s"]
        - "input 搜索框 输入'hello'" → action=input, params.text_content="hello"
        2. 禁止行为：
        - 输出自然语言指令而非JSON
        - 忽略必填字段（如id或target）
        - 生成循环操作（如无限滚动）
        - 添加额外字段或注释

        兼容性说明：
        - open操作自动包含：定位图标→双击打开（默认clicks=2）
        - input操作自动包含：定位输入框→清空→输入→回车
        """

    def parse_instruction_omni(self, instruction: str, data: Dict[str, Any], pre_actions: List[str]) -> str:
        """多模态解析方法
        
        Args:
            instruction: 用户指令
            data: 当前界面元素数据
            pre_actions: 已执行的操作列表
            
        Returns:
            解析结果
            
        Raises:
            Exception: 当API调用失败时
        """
        logger.info(f"开始多模态解析: 指令={instruction}, 已执行操作数={len(pre_actions)}")
        try:
            messages = self._build_omni_messages(instruction, data, pre_actions)
            
            completion = self.client_qwen.chat.completions.create(
                model="qwen2.5-vl-72b-instruct",
                messages=messages,
                stream=True,
                stream_options={"include_usage": True}
            )
            result = self._handle_streaming_response(completion)
            logger.info("多模态解析完成")
            return result
        except Exception as e:
            error_msg = f"多模态解析失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    def parse_instruction(self, instruction: str, data: Dict[str, Any], pre_actions: List[str], analysis: str) -> str:
        """文本解析方法
        
        Args:
            instruction: 用户指令
            data: 当前界面元素数据
            pre_actions: 已执行的操作列表
            analysis: 分析结果
            
        Returns:
            解析结果JSON字符串
            
        Raises:
            ValueError: 当响应内容为空时
            Exception: 当API调用失败时
        """
        logger.info(f"开始文本解析: 指令={instruction}, 已执行操作数={len(pre_actions)}")
        try:
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
                error_msg = "响应内容为空"
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.info("文本解析完成")
            return content
        except Exception as e:
            error_msg = f"文本解析失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg) from e

    def _build_omni_messages(self, instruction: str, data: Dict[str, Any], pre_actions: List[str]) -> List[Dict[str, Any]]:
        """构建多模态消息结构
        
        Args:
            instruction: 用户指令
            data: 当前界面元素数据
            pre_actions: 已执行的操作列表
            
        Returns:
            消息列表
        """
        user_prompt = f"已经执行过的指令有:{pre_actions},用户指令: {instruction}。请只给出基于当前界面单步操作。"
        print(user_prompt)

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
                    {"type": "text", "text": user_prompt}
                ]
            }
        ]

    def _build_image_content(self) -> Dict[str, Any]:
        """构建图像内容结构
        
        Returns:
            图像内容字典
        """
        try:
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{self.encode_image(LABELED_IMAGE_PATH)}"
                }
            }
        except Exception as e:
            logger.error(f"构建图像内容失败: {e}")
            raise

    def _handle_streaming_response(self, completion) -> str:
        """处理流式响应
        
        Args:
            completion: 流式响应对象
            
        Returns:
            完整响应内容
        """
        result = []
        try:
            for chunk in completion:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    result.append(content)
                    print(content, end='', flush=True)
                elif hasattr(chunk, 'usage') and chunk.usage:
                    self._log_usage(chunk.usage)
            
            print(result)
            return ''.join(result)
        except Exception as e:
            logger.error(f"处理流式响应失败: {e}")
            raise

    def _build_user_prompt(self, instruction: str, data: Dict[str, Any], pre_actions: List[str], analysis: str) -> str:
        """构建用户提示模板
        
        Args:
            instruction: 用户指令
            data: 当前界面元素数据
            pre_actions: 已执行的操作列表
            analysis: 分析结果
            
        Returns:
            用户提示字符串
        """
        return f"当前界面元素内容如:{data},已经执行过的指令有:{pre_actions},用户指令: {instruction},分析者给出的建议为:{analysis}。请只给出基于当前界面单步操作。"

    def _log_usage(self, usage: Optional[Dict[str, Any]]) -> None:
        """记录API使用情况
        
        Args:
            usage: API使用情况
        """
        if usage:
            usage_info = f"API Usage: {usage}"
            logger.info(usage_info)
            print(f"\n{usage_info}")


class WorkFlowGenerator:
    """工作流生成器，负责生成完整的操作流程"""
    
    def __init__(self):
        """初始化工作流生成器"""
        try:
            self.client = OpenAI(api_key=API_KEYS["aliyun"], base_url=BASE_URLS["aliyun"])
            logger.info("WorkFlowGenerator初始化成功")
        except Exception as e:
            logger.error(f"WorkFlowGenerator初始化失败: {e}")
            raise

    def generate_workflow(self, instruction: str) -> str:
        """生成工作流
        
        Args:
            instruction: 用户指令
            
        Returns:
            工作流JSON字符串
        """
        logger.info(f"开始生成工作流: 指令={instruction}")
        print(f"可用icons: {config.ICONS}")
        
        # 系统提示词
        SYSTEM = """
        你是一个熟悉电脑操作的大师，能够根据用户指令和当前界面，将任务分解为多个子任务，并生成包含JSON对象的步骤列表。
        你必须根据用户指令的复杂性，将其拆分为可执行的子任务。例如，"查看华南理工大学培养计划"需分解为"打开浏览器→搜索关键词→选择目标链接"等步骤。若子任务涉及多阶段操作（如文件保存），需递归分解为更细的操作序列。  
        系统级快捷键（如Win+D、Alt+Tab）或应用级快捷键如Ctrl+S、F12）应优先使用。若无法用快捷键完成，则依次选择click、input、open等操作。若目标元素无法定位（如模糊描述"打开微信联系人"），用自然语言补充描述，例如"target": "通过微信搜索框找到联系人"姐姐""。  
        JSON操作规范  
        每个JSON对象需严格符合以下格式：  
        {  
        "action": "open|click|scroll|input|hotkey|finish", // 必填，操作类型  
        "id": -1, // 唯一标识符（若无法确定设为-1）  
        "target": "元素描述", // 当action为click/input/open时必填，其他情况设为"None"  
        "params": {  
            "text_content": "输入文本", // action为input时必填  
            "key_sequence": ["组合键列表"], // action为hotkey时必填（如["win", "r"]）  
            "button_type": "left/right", // action为click时可选，默认"left"  
            "direction": "up/down", // action为scroll时必填  
            "clicks": 1 // action为click时可选，默认1次  
        }  
        }   
        Action描述及参数要求：  
        - hotkey：执行系统或应用级快捷键。参数：key_sequence必填，target设为"None"。  
        - open：双击打开软件/文件。参数：target需描述图标名称（如"Microsoft Edge图标"）。  
        - input：输入文本并回车。参数：text_content必填，target描述输入框位置（如"搜索框"）。  
        - click：鼠标点击。参数：target描述元素（如"确定按钮"），clicks可设为2/3次（如打开文件需双击）。  
        - finish：标记任务完成。无需参数，target设为"None"。  
        示例与规则  
        示例1：查看Python版本**
        [  
        {"action": "hotkey", "id": -1, "target": "None", "params": {"key_sequence": ["win", "r"]}},  
        {"action": "input", "id": -1, "target": "运行对话框", "params": {"text_content": "python --version"}},  
        {"action": "click", "id": -1, "target": "确定", "params": {"button_type": "left", "clicks": 1}},  
        {"action": "finish", "id": -1, "target": "None", "params": {}}  
        ]  
        示例2：搜索华南理工大学培养计划**  
        [  
        {"action": "open", "id": -1, "target": "Microsoft Edge图标", "params": {}},  
        {"action": "input", "id": -1, "target": "地址栏", "params": {"text_content": "华南理工大学计算机学院 计科培养计划"}},  
        {"action": "click", "id": -1, "target": "点击界面中第一条网页链接，当完成该目标时可停止", "params": {"clicks": 1}},  
        {"action": "finish", "id": -1, "target": "None", "params": {}}  
        ]  
        注意事项：
        1. 优先使用快捷键完成任务（如Win+R打开运行窗口）。  
        2. 若需点击，确保clicks次数足够（如双击文件需设为2次）。  
        3. 模糊操作需用自然语言描述目标（如"通过搜索栏找到联系人"）,你需要在target中如同用户指令一样进行描述，你需要将target当做对另一个ai的指令。
        4. 对于使用自然语言进行描述的任务，必须指明当完成什么条件时结束。

        通过以上规范，确保生成的JSON步骤清晰、可执行，并符合用户意图分解的逻辑。
        """

        # 增强系统提示词
        enhanced_system = SYSTEM + f"""
        目前target你只能从以下内容中选择：{config.ICONS}，你必须使用原有的名称，不得将其重命名。
        若目标元素无法定位（如模糊描述"打开微信联系人"），用自然语言补充描述。
        当前页面为Windows桌面，背景为一人使用电脑的场景。
        桌面上有多种应用图标（如QQ、微信、PyCharm、VS Code等）和文件夹（如homework、考研、学习等），表明用户主要从事编程、学习及办公相关活动。
        
        请确保每个JSON对象都包含完整的必要字段，特别是params字段，即使它是空对象也必须包含。
        """

        reasoning_content = ""  # 定义完整思考过程
        answer_content = ""  # 定义完整回复
        is_answering = False  # 判断是否结束思考过程并开始回复

        try:
            print(instruction)
            response = self.client.chat.completions.create(
                model="qwq-plus",
                messages=[
                    {"role": "system", "content": enhanced_system},
                    {"role": "user", "content": "用户指令为：" + instruction}
                ],
                stream=True
            )
            
            for chunk in response:
                # 如果chunk.choices为空
                if not chunk.choices:
                    if hasattr(chunk, 'usage') and chunk.usage:
                        usage_info = f"\nUsage: {chunk.usage}"
                        logger.info(usage_info)
                        print(usage_info)
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
                            print("---------------------------------")
                        # 打印回复过程
                        if delta.content:
                            answer_content += delta.content
                            print(delta.content, end='', flush=True)
            
            logger.info("工作流生成完成")
            return answer_content
        except Exception as e:
            error_msg = f"生成工作流失败: {e}"
            logger.error(error_msg)
            raise Exception(error_msg) from e