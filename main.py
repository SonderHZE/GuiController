from core.api.client import APIClient
from core.screen_controller import PyAutoGUIWrapper
from ui import main_window

def main():
    client = APIClient()
    
    # 初始化屏幕控制器
    screen_ctrl = PyAutoGUIWrapper(pause=1.0)
    main_window.FloatingWindow(screen_ctrl).show()

    # 执行截图和处理
    try:
        screenshot = screen_ctrl.screen_shot()
        screenshot.save("screenshot.png")
        
        result = client.process_image("screenshot.png")
        
        if result.status == 'success':
            print("处理成功！")
            if result.labeled_image is not None:
                result.labeled_image.show()
            else:
                print("未获取到标记图像")
        else:
            print(f"处理失败: {result.message}")
            
    except KeyboardInterrupt:
        print("\n用户中断操作")

if __name__ == "__main__":
    main()