from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from BattleData import BattleData
import json
import os
import time
import logging
import configparser
import datetime
import numpy as np
from typing import Dict, List, Optional, Any, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("fgo_battle.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("FGOBattle")

# 全局变量
SERVANT_INFO = None
CURRENT_TURN = 0
CURRENT_WAVE = 1
MAX_WAVES = 3  # 默认3波敌人
BATTLE_LOGGER = None


class FGOBattleConfig:
    """FGO战斗配置管理类"""
    def __init__(self, config_file="fgo_config.ini"):
        self.config = configparser.ConfigParser()
        try:
            self.config.read(config_file)
            logger.info(f"配置文件 {config_file} 加载成功")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            # 创建默认配置
            self._create_default_config()
            # 保存默认配置到文件
            with open(config_file, 'w') as f:
                self.config.write(f)
            logger.info(f"已创建默认配置文件: {config_file}")
    
    def _create_default_config(self):
        """创建默认配置"""
        # 位置坐标配置
        self.config['Positions'] = {
            # 从者位置
            'servant1_x': '230', 'servant1_y': '430',
            'servant2_x': '430', 'servant2_y': '430',
            'servant3_x': '630', 'servant3_y': '430',
            # 技能位置
            'skill_y': '500',
            'skill1_offset_x': '50', 'skill2_offset_x': '100', 'skill3_offset_x': '150',
            # 攻击按钮
            'attack_btn_x': '830', 'attack_btn_y': '450',
            # 宝具卡位置
            'np_y': '200',
            'np1_x': '250', 'np2_x': '450', 'np3_x': '650',
            # 普通指令卡位置
            'card_y': '350',
            'card1_x': '170', 'card2_x': '320', 'card3_x': '470', 
            'card4_x': '620', 'card5_x': '770',
            # 敌人位置
            'enemy_y': '100',
            'enemy1_x': '230', 'enemy2_x': '430', 'enemy3_x': '630',
            # 御主技能
            'master_btn_x': '880', 'master_btn_y': '300',
            'master_skill1_x': '780', 'master_skill2_x': '830', 'master_skill3_x': '880',
            # 技能目标位置
            'skill_target_y': '350',
            'skill_target1_x': '230', 'skill_target2_x': '430', 'skill_target3_x': '630'
        }
        
        # 时间配置
        self.config['Timing'] = {
            'skill_animation_wait': '1.5',
            'card_selection_wait': '0.3',
            'np_animation_wait': '10.0',
            'wave_transition_wait': '3.0',
            'battle_result_wait': '5.0',
            'dialog_wait': '1.0'
        }
        
        # 战斗配置
        self.config['Battle'] = {
            'auto_apple': 'False',
            'apple_type': 'gold',
            'max_battles': '0',  # 0表示无限战斗
            'auto_repeat': 'True',
            'apple_limit': '0'   # 0表示无限苹果
        }
        
        # 助战配置
        self.config['Support'] = {
            'enable_support_selection': 'True',
            'servant': '',  # 留空表示不指定
            'craft_essence': '',  # 留空表示不指定
            'auto_refresh': 'True',
            'max_refresh': '5'
        }
    
    def get(self, section, option, fallback=None):
        """获取配置值"""
        return self.config.get(section, option, fallback=fallback)
    
    def getint(self, section, option, fallback=0):
        """获取整数配置值"""
        return self.config.getint(section, option, fallback=fallback)
    
    def getfloat(self, section, option, fallback=0.0):
        """获取浮点数配置值"""
        return self.config.getfloat(section, option, fallback=fallback)
    
    def getboolean(self, section, option, fallback=False):
        """获取布尔配置值"""
        return self.config.getboolean(section, option, fallback=fallback)


class BattleLogger:
    """战斗记录和统计"""
    
    def __init__(self, log_file=None):
        self.start_time = datetime.datetime.now()
        self.battle_count = 0
        self.apple_used = 0
        self.drops = {}
        
        if log_file:
            self.log_file = log_file
        else:
            timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
            self.log_file = f"battle_log_{timestamp}.txt"
        
        with open(self.log_file, 'w') as f:
            f.write(f"=== FGO战斗日志 - 开始于 {self.start_time} ===\n")
    
    def log_battle_start(self, quest_name):
        """记录战斗开始"""
        self.battle_count += 1
        message = f"[{datetime.datetime.now()}] 开始第 {self.battle_count} 次战斗 - {quest_name}"
        logger.info(message)
        
        with open(self.log_file, 'a') as f:
            f.write(message + "\n")
    
    def log_apple_use(self, apple_type):
        """记录苹果使用"""
        self.apple_used += 1
        message = f"[{datetime.datetime.now()}] 使用了 {apple_type} 苹果 (总计: {self.apple_used})"
        logger.info(message)
        
        with open(self.log_file, 'a') as f:
            f.write(message + "\n")
    
    def log_battle_end(self, turns, drops=None):
        """记录战斗结束"""
        battle_time = datetime.datetime.now()
        duration = battle_time - self.start_time
        
        message = f"[{battle_time}] 完成第 {self.battle_count} 次战斗 - 用时: {duration.total_seconds():.1f}秒, 回合数: {turns}"
        logger.info(message)
        
        with open(self.log_file, 'a') as f:
            f.write(message + "\n")
            
            if drops:
                f.write("掉落物品:\n")
                for item, count in drops.items():
                    f.write(f"  - {item}: {count}\n")
                    # 更新总掉落统计
                    self.drops[item] = self.drops.get(item, 0) + count
    
    def generate_report(self):
        """生成战斗统计报告"""
        total_time = datetime.datetime.now() - self.start_time
        hours = total_time.total_seconds() / 3600
        
        report = "\n=== 战斗统计报告 ===\n"
        report += f"总战斗次数: {self.battle_count}\n"
        report += f"总用时: {hours:.2f}小时\n"
        report += f"平均每场用时: {(total_time.total_seconds() / max(1, self.battle_count)) / 60:.2f}分钟\n"
        report += f"使用苹果: {self.apple_used}\n"
        
        if self.drops:
            report += "总掉落物品:\n"
            for item, count in self.drops.items():
                report += f"  - {item}: {count} (平均每场: {count/self.battle_count:.2f})\n"
        
        logger.info(report)
        
        with open(self.log_file, 'a') as f:
            f.write(report)
        
        return report


class ImageRecognition:
    """基于图像识别的游戏状态检测"""
    
    @staticmethod
    def capture_screen(context):
        """获取当前屏幕截图"""
        # 假设context提供了截图接口
        # 实际实现可能需要根据MAA框架的API调整
        try:
            return context.controller.capture_screenshot()
        except Exception as e:
            logger.error(f"截图失败: {e}")
            # 返回空图像
            return np.zeros((720, 1280, 3), dtype=np.uint8)
    
    @staticmethod
    def find_template(image, template, threshold=0.8):
        """在图像中查找模板"""
        try:
            result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
            loc = np.where(result >= threshold)
            if len(loc[0]) > 0:
                return (loc[1][0], loc[0][0])  # 返回第一个匹配点的坐标
            return None
        except Exception as e:
            logger.error(f"模板匹配失败: {e}")
            return None
    
    @staticmethod
    def check_battle_end(context):
        """检查战斗是否结束"""
        try:
            screen = ImageRecognition.capture_screen(context)
            # 加载战斗结束画面的模板
            battle_end_template = cv2.imread('templates/battle_end.png', 0)
            if battle_end_template is None:
                logger.error("无法加载战斗结束模板图像")
                return False
                
            return ImageRecognition.find_template(screen, battle_end_template) is not None
        except Exception as e:
            logger.error(f"检测战斗结束状态失败: {e}")
            return False
    
    @staticmethod
    def check_wave_transition(context):
        """检查波次是否转换"""
        try:
            screen = ImageRecognition.capture_screen(context)
            # 加载波次转换画面的模板
            wave_template = cv2.imread('templates/wave_transition.png', 0)
            if wave_template is None:
                logger.error("无法加载波次转换模板图像")
                return False
                
            return ImageRecognition.find_template(screen, wave_template) is not None
        except Exception as e:
            logger.error(f"检测波次转换失败: {e}")
            return False
    
    @staticmethod
    def detect_servant_status(context, svt_index):
        """检测从者状态(血量、NP等)"""
        # 实现从者状态检测逻辑
        pass


def safe_execute(func):
    """安全执行函数的装饰器，处理可能的异常"""
    def wrapper(*args, **kwargs):
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                retry_count += 1
                logger.warning(f"执行 {func.__name__} 失败 ({retry_count}/{max_retries}): {e}")
                time.sleep(1)
        
        logger.error(f"执行 {func.__name__} 最终失败，放弃")
        return False
    
    return wrapper


@AgentServer.custom_action("InitBattleJson")
class InitBattleInfo(CustomAction):
    battle_data = None
    
    def __init__(self):
        super().__init__()
        self.config = FGOBattleConfig()
    
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        json_file_path = "../assets/resource/team/42200.json" # 假设1001.json在与BattleAction.py相同的目录下
        
        # 检查文件是否存在
        if not os.path.exists(json_file_path):
            logger.error(f"Error: JSON file not found at {json_file_path}")
            return False
        
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                json_data_string = f.read()
            
            # 解析JSON字符串并存储到实例变量
            self.battle_data = BattleData.from_json(json_data_string)

            global SERVANT_INFO, BATTLE_LOGGER
            SERVANT_INFO = self.battle_data
            # 初始化战斗日志
            BATTLE_LOGGER = BattleLogger()

            logger.info("JSON data parsed and stored successfully!")
            logger.info(f"ID: {self.battle_data.id}")
            logger.info(f"Username: {self.battle_data.username}")
            logger.info(f"Quest ID: {self.battle_data.questId}")
            
            # 访问更深层的数据，例如第一个在场从者(onFieldSvts)的ID
            if hasattr(self.battle_data, 'data') and hasattr(self.battle_data.data, 'result') and \
               hasattr(self.battle_data.data.result, 'team') and \
               hasattr(self.battle_data.data.result.team, 'onFieldSvts') and \
               len(self.battle_data.data.result.team.onFieldSvts) > 0:
                first_svt_id = self.battle_data.data.result.team.onFieldSvts[0].svtId
                logger.info(f"First On-Field Servant ID: {first_svt_id}")

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON: {e}")
            self.battle_data = None # 解析失败时清空存储
            return False # 解析失败返回False
        except AttributeError as e:
            logger.error(f"Error accessing attributes: {e}")
            return False
        
        # 初始化完成后开始第一回合
        context.run_action("StartTurn")
        return True


@AgentServer.custom_action("StartTurn")
class StartTurn(CustomAction):
    def __init__(self):
        super().__init__()
        self.ctx = None
        self.config = FGOBattleConfig()
        
        # 从配置中加载位置信息
        self._load_positions()
        
        # 加载时间配置
        self.SKILL_ANIMATION_WAIT = self.config.getfloat('Timing', 'skill_animation_wait', 1.5)
        self.CARD_SELECT_DELAY = self.config.getfloat('Timing', 'card_selection_wait', 0.3)
        self.NP_ANIMATION_WAIT = self.config.getfloat('Timing', 'np_animation_wait', 10.0)
        self.WAVE_TRANSITION_WAIT = self.config.getfloat('Timing', 'wave_transition_wait', 3.0)
        self.BATTLE_RESULT_WAIT = self.config.getfloat('Timing', 'battle_result_wait', 5.0)
        self.DIALOG_WAIT = self.config.getfloat('Timing', 'dialog_wait', 1.0)
        
        # 战斗常量
        self.MAX_CARDS_PER_TURN = 3
    
    def _load_positions(self):
        """从配置中加载位置信息"""
        # 从者位置
        self.SERVANT_POSITIONS = []
        for i in range(1, 4):
            x = self.config.getint('Positions', f'servant{i}_x')
            y = self.config.getint('Positions', f'servant{i}_y')
            self.SERVANT_POSITIONS.append({"x": x, "y": y})
        
        # 技能位置
        self.SKILL_POSITIONS = []
        skill_y = self.config.getint('Positions', 'skill_y')
        skill1_offset = self.config.getint('Positions', 'skill1_offset_x')
        skill2_offset = self.config.getint('Positions', 'skill2_offset_x')
        skill3_offset = self.config.getint('Positions', 'skill3_offset_x')
        
        for i in range(3):  # 3个从者
            svt_x = self.SERVANT_POSITIONS[i]["x"]
            skills = [
                {"x": svt_x - skill1_offset, "y": skill_y},
                {"x": svt_x, "y": skill_y},
                {"x": svt_x + skill3_offset, "y": skill_y}
            ]
            self.SKILL_POSITIONS.append(skills)
        
        # 攻击按钮
        self.ATTACK_BUTTON = {
            "x": self.config.getint('Positions', 'attack_btn_x'),
            "y": self.config.getint('Positions', 'attack_btn_y')
        }
        
        # 宝具卡位置
        self.NOBLE_PHANTASM_CARDS = []
        np_y = self.config.getint('Positions', 'np_y')
        for i in range(1, 4):
            x = self.config.getint('Positions', f'np{i}_x')
            self.NOBLE_PHANTASM_CARDS.append({"x": x, "y": np_y})
        
        # 普通指令卡位置
        self.CARDS = []
        card_y = self.config.getint('Positions', 'card_y')
        for i in range(1, 6):
            x = self.config.getint('Positions', f'card{i}_x')
            self.CARDS.append({"x": x, "y": card_y})
        
        # 敌人位置
        self.ENEMY_POSITIONS = []
        enemy_y = self.config.getint('Positions', 'enemy_y')
        for i in range(1, 4):
            x = self.config.getint('Positions', f'enemy{i}_x')
            self.ENEMY_POSITIONS.append({"x": x, "y": enemy_y})
        
        # 御主技能
        self.MASTER_SKILL_BUTTON = {
            "x": self.config.getint('Positions', 'master_btn_x'),
            "y": self.config.getint('Positions', 'master_btn_y')
        }
        
        self.MASTER_SKILLS = []
        for i in range(1, 4):
            x = self.config.getint('Positions', f'master_skill{i}_x')
            y = self.MASTER_SKILL_BUTTON["y"]
            self.MASTER_SKILLS.append({"x": x, "y": y})
        
        # 技能目标位置
        self.SKILL_TARGET_POSITIONS = []
        target_y = self.config.getint('Positions', 'skill_target_y')
        for i in range(1, 4):
            x = self.config.getint('Positions', f'skill_target{i}_x')
            self.SKILL_TARGET_POSITIONS.append({"x": x, "y": target_y})
        
        # 战斗结束确认按钮位置
        self.BATTLE_FINISHED_CHECK = {
            "x": 450,  # 中间位置
            "y": 450   # 大致位置
        }
    
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        self.ctx = context
        global CURRENT_TURN, CURRENT_WAVE, BATTLE_LOGGER
        
        logger.info(f"开始执行第 {CURRENT_WAVE} 波, 第 {CURRENT_TURN} 回合")
        
        # 记录战斗开始(只在第一回合第一波时记录)
        if CURRENT_TURN == 0 and CURRENT_WAVE == 1 and BATTLE_LOGGER:
            quest_name = "Unknown"  # 可以从配置或SERVANT_INFO中获取
            if hasattr(SERVANT_INFO, 'data') and hasattr(SERVANT_INFO.data, 'result') and \
               hasattr(SERVANT_INFO.data.result, 'quest'):
                quest_name = getattr(SERVANT_INFO.data.result.quest, 'name', "Unknown")
            BATTLE_LOGGER.log_battle_start(quest_name)
        
        # 判断是否有特定回合的战斗数据
        if self.handle_battle_turn(CURRENT_TURN):
            CURRENT_TURN += 1
            # 设置定时器检查下一回合的开始
            self.wait_for_next_turn()
            return True
        else:
            logger.info(f"没有找到回合 {CURRENT_TURN} 的战斗数据，切换到自动战斗模式")
            self.auto_battle_mode()
            return True

    @safe_execute
    def handle_battle_turn(self, turn_index):
        """处理特定回合的战斗流程"""
        global SERVANT_INFO
        turn_battle_data = None
        
        # 访问回合数据
        if SERVANT_INFO and hasattr(SERVANT_INFO, 'data') and hasattr(SERVANT_INFO.data, 'result'):
            turns = SERVANT_INFO.data.result.turns
            if 0 <= turn_index < len(turns):
                turn_battle_data = turns[turn_index]
        
        if turn_battle_data:
            logger.info(f"===== 执行第 {CURRENT_WAVE}/{MAX_WAVES} 波, 第 {turn_index+1} 回合 =====")
            # 1. 技能阶段
            self.skill_phase(turn_battle_data)
            
            # 2. 等待技能动画完成
            time.sleep(self.SKILL_ANIMATION_WAIT)
            
            # 3. 攻击阶段
            self.attack_phase(turn_battle_data)
            return True
        else:
            return False

    def wait_for_next_turn(self):
        """等待并检查下一回合或下一波次是否开始"""
        global CURRENT_TURN, CURRENT_WAVE, MAX_WAVES
        
        # 等待战斗动画完成
        time.sleep(self.NP_ANIMATION_WAIT)
        
        # 检查是否进入新的波次
        if ImageRecognition.check_wave_transition(self.ctx):
            logger.info("检测到波次过渡")
            CURRENT_WAVE += 1
            CURRENT_TURN = 0  # 新波次重置回合计数
            time.sleep(self.WAVE_TRANSITION_WAIT)  # 等待波次过渡动画
            
            if CURRENT_WAVE <= MAX_WAVES:
                # 开始新波次的第一回合
                self.ctx.run_action("StartTurn")
            else:
                logger.info("所有波次已完成")
                self.handle_battle_results()
        
        # 检查战斗是否结束
        elif self.check_battle_finished():
            logger.info("战斗已结束!")
            self.handle_battle_results()
        else:
            # 开始下一回合
            self.ctx.run_action("StartTurn")
    
    def check_battle_finished(self):
        """检查战斗是否结束"""
        # 使用图像识别检查战斗结束标志
        return ImageRecognition.check_battle_end(self.ctx)
    
    @safe_execute
    def handle_battle_results(self):
        """处理战斗结果界面"""
        global BATTLE_LOGGER, CURRENT_TURN
        
        # 点击几次屏幕以跳过结算画面
        for _ in range(5):
            self.ctx.controller.post_click(self.BATTLE_FINISHED_CHECK["x"], 
                                          self.BATTLE_FINISHED_CHECK["y"]).wait()
            time.sleep(self.DIALOG_WAIT)
        
        # 检测掉落物品(这里简化处理)
        drops = self.detect_battle_drops()
        
        # 记录战斗结束
        if BATTLE_LOGGER:
            BATTLE_LOGGER.log_battle_end(CURRENT_TURN, drops)
        
        logger.info("战斗结算完成")
        
        # 处理战斗后的选项(继续/退出)
        self.handle_post_battle_options()
    
    def detect_battle_drops(self):
        """检测战斗掉落物品"""
        # 实际应用中可以使用图像识别检测掉落物
        # 这里简化返回空字典
        return {}
    
    @safe_execute
    def handle_post_battle_options(self):
        """处理战斗后的选项"""
        # 检查是否出现了连续出击询问
        if self.check_continue_quest_dialog():
            logger.info("检测到连续出击询问")
            if self.config.getboolean('Battle', 'auto_repeat', fallback=True):
                self.select_continue_quest()
                # 重置回合和波次计数
                global CURRENT_TURN, CURRENT_WAVE
                CURRENT_TURN = 0
                CURRENT_WAVE = 1
                
                # 检查AP是否足够
                if self.check_ap_recovery_dialog():
                    if self.check_and_restore_ap():
                        # AP恢复后继续
                        time.sleep(2)
                        # 选择助战
                        self.select_support_servant()
                        # 开始新的战斗
                        self.ctx.run_action("StartTurn")
                    else:
                        # 不恢复AP则退出
                        self.select_quit_quest()
                else:
                    # 选择助战
                    self.select_support_servant()
                    # 开始新的战斗
                    self.ctx.run_action("StartTurn")
            else:
                self.select_quit_quest()
    
    def check_continue_quest_dialog(self):
        """检查是否出现了连续出击询问"""
        # 实际应用中使用图像识别检测
        # 这里简化返回True
        return True
    
    def select_continue_quest(self):
        """选择继续出击"""
        # 点击"是"按钮
        self.ctx.controller.post_click(350, 450).wait()
        time.sleep(self.DIALOG_WAIT)
    
    def select_quit_quest(self):
        """选择退出战斗"""
        # 点击"否"按钮
        self.ctx.controller.post_click(550, 450).wait()
        time.sleep(self.DIALOG_WAIT)
    
    def check_ap_recovery_dialog(self):
        """检查是否出现了AP不足提示"""
        # 实际应用中使用图像识别检测
        # 这里简化返回False
        return False
    
    @safe_execute
    def check_and_restore_ap(self):
        """检查并恢复AP(体力)"""
        if not self.config.getboolean('Battle', 'auto_apple', fallback=False):
            logger.info("自动吃苹果功能未开启，如果体力不足将退出")
            return False
        
        # 检查是否达到苹果使用上限
        apple_limit = self.config.getint('Battle', 'apple_limit', fallback=0)
        if apple_limit > 0 and BATTLE_LOGGER and BATTLE_LOGGER.apple_used >= apple_limit:
            logger.info(f"已达到苹果使用上限: {apple_limit}")
            return False
        
        apple_type = self.config.get('Battle', 'apple_type', fallback='gold')
        apple_positions = {
            'gold': {'x': 375, 'y': 300},
            'silver': {'x': 375, 'y': 400},
            'bronze': {'x': 375, 'y': 500},
            'quartz': {'x': 375, 'y': 600}
        }
        
        if apple_type in apple_positions:
            # 点击对应的苹果
            pos = apple_positions[apple_type]
            logger.info(f"使用{apple_type}苹果回复体力")
            self.ctx.controller.post_click(pos['x'], pos['y']).wait()
            time.sleep(self.DIALOG_WAIT)
            
            # 点击确认按钮
            self.ctx.controller.post_click(550, 350).wait()
            time.sleep(2 * self.DIALOG_WAIT)
            
            # 记录苹果使用
            if BATTLE_LOGGER:
                BATTLE_LOGGER.log_apple_use(apple_type)
            
            return True
        else:
            logger.error(f"未知的苹果类型: {apple_type}")
            return False
    
    @safe_execute
    def select_support_servant(self):
        """选择助战从者"""
        if not self.config.getboolean('Support', 'enable_support_selection', fallback=True):
            # 如果没有启用助战选择，直接选第一个
            logger.info("助战选择功能未启用，选择默认助战")
            self.ctx.controller.post_click(450, 300).wait()
            time.sleep(self.DIALOG_WAIT * 2)  # 等待助战加载
            return True
        
        # 配置中指定的助战从者和礼装
        target_servant = self.config.get('Support', 'servant', fallback=None)
        target_craft_essence = self.config.get('Support', 'craft_essence', fallback=None)
        
        # 滑动查找次数
        max_scroll = self.config.getint('Support', 'max_refresh', fallback=5)
        auto_refresh = self.config.getboolean('Support', 'auto_refresh', fallback=True)
        scroll_count = 0
        
        while scroll_count < max_scroll:
            # 使用图像识别查找目标从者/礼装
            if target_servant and self._find_support_servant(target_servant):
                logger.info(f"找到目标从者: {target_servant}")
                time.sleep(self.DIALOG_WAIT)
                return True
            elif target_craft_essence and self._find_support_craft_essence(target_craft_essence):
                logger.info(f"找到目标礼装: {target_craft_essence}")
                time.sleep(self.DIALOG_WAIT)
                return True
            
            # 向下滑动查找更多助战
            if scroll_count < max_scroll - 1:
                self._scroll_support_list()
                scroll_count += 1
                time.sleep(self.DIALOG_WAIT)
            else:
                # 如果达到最大滑动次数且启用了自动刷新
                if auto_refresh:
                    logger.info("刷新助战列表")
                    self._refresh_support_list()
                    time.sleep(3 * self.DIALOG_WAIT)  # 等待刷新完成
                    scroll_count = 0  # 重置计数
                else:
                    break
        
        # 如果找不到指定助战，选择第一个
        logger.info("未找到指定助战，选择第一个")
        self.ctx.controller.post_click(450, 300).wait()
        time.sleep(2 * self.DIALOG_WAIT)
        return True
    
    def _find_support_servant(self, servant_name):
        """查找指定助战从者"""
        # 实际应用中使用OCR或图像识别匹配从者名称
        # 这里简化返回False，表示未找到
        return False
    
    def _find_support_craft_essence(self, ce_name):
        """查找指定助战礼装"""
        # 实际应用中使用OCR或图像识别匹配礼装名称
        # 这里简化返回False，表示未找到
        return False
    
    def _scroll_support_list(self):
        """滑动助战列表"""
        # 模拟从下向上滑动操作
        self.ctx.controller.post_swipe(640, 600, 640, 200, 500).wait()  # 起点x,y，终点x,y，持续时间(ms)
    
    def _refresh_support_list(self):
        """刷新助战列表"""
        # 点击刷新按钮
        self.ctx.controller.post_click(750, 200).wait()
        time.sleep(self.DIALOG_WAIT)
        
        # 点击确认按钮
        self.ctx.controller.post_click(550, 450).wait()
    
    @safe_execute
    def skill_phase(self, turn_data):
        """技能阶段处理"""
        if not hasattr(turn_data, 'skills') or not turn_data.skills:
            logger.info("回合没有技能操作或数据格式不正确")
            return
            
        logger.info(f"开始执行技能阶段，共 {len(turn_data.skills)} 个技能")
        for index, skill in enumerate(turn_data.skills):
            if not hasattr(skill, 'svt') or not hasattr(skill, 'skill') or not hasattr(skill, 'options'):
                logger.warning(f"技能 #{index+1} 数据格式不正确")
                continue
            
            # 获取技能参数    
            skill_owner = skill.svt  # None表示御主技能
            skill_index = skill.skill
            player_target = getattr(skill.options, 'playerTarget', -1)
            enemy_target = getattr(skill.options, 'enemyTarget', -1)
            
            if skill_owner is not None:
                # 从者技能
                logger.info(f"使用从者 {skill_owner+1} 的第 {skill_index+1} 个技能")
                self.use_svt_skill(skill_owner, skill_index, player_target, enemy_target)
            else:
                # 御主技能
                logger.info(f"使用御主的第 {skill_index+1} 个技能")
                self.use_master_skill(skill_index, player_target, enemy_target)
            
            # 等待技能动画
            time.sleep(self.SKILL_ANIMATION_WAIT)
    
    @safe_execute
    def use_svt_skill(self, svt_index, skill_index, player_target, enemy_target):
        """使用从者技能"""
        # 先选择敌人目标(如果有)
        if enemy_target != -1:
            self.select_enemy(enemy_target)
            time.sleep(0.3)
        
        # 获取技能按钮位置
        if 0 <= svt_index < len(self.SKILL_POSITIONS) and 0 <= skill_index < len(self.SKILL_POSITIONS[svt_index]):
            skill_pos = self.SKILL_POSITIONS[svt_index][skill_index]
            self.ctx.controller.post_click(skill_pos["x"], skill_pos["y"]).wait()
            time.sleep(0.5)  # 等待技能按钮动画
            
            # 如果需要选择从者目标
            if player_target != -1 and 0 <= player_target < len(self.SKILL_TARGET_POSITIONS):
                target_pos = self.SKILL_TARGET_POSITIONS[player_target]
                time.sleep(0.3)
                self.ctx.controller.post_click(target_pos["x"], target_pos["y"]).wait()
                time.sleep(0.3)
        else:
            logger.error(f"错误: 从者索引 {svt_index+1} 或技能索引 {skill_index+1} 超出范围")
    
    @safe_execute
    def use_master_skill(self, skill_index, player_target, enemy_target):
        """使用御主技能"""
        # 先点击御主技能按钮打开菜单
        self.ctx.controller.post_click(self.MASTER_SKILL_BUTTON["x"], 
                                      self.MASTER_SKILL_BUTTON["y"]).wait()
        time.sleep(0.5)
        
        # 选择敌人目标(如果有)
        if enemy_target != -1:
            self.select_enemy(enemy_target)
            time.sleep(0.3)
        
        # 选择具体的御主技能
        if 0 <= skill_index < len(self.MASTER_SKILLS):
            skill_pos = self.MASTER_SKILLS[skill_index]
            self.ctx.controller.post_click(skill_pos["x"], skill_pos["y"]).wait()
            time.sleep(0.5)
            
            # 特殊处理：换人礼装(第3个技能)
            if skill_index == 2 and player_target != -1 and hasattr(player_target, 'swap'):
                # 假设player_target是一个包含swap属性的对象，指定要交换的从者
                self.perform_servant_swap(player_target.swap[0], player_target.swap[1])
            # 普通技能目标选择
            elif player_target != -1 and 0 <= player_target < len(self.SKILL_TARGET_POSITIONS):
                target_pos = self.SKILL_TARGET_POSITIONS[player_target]
                time.sleep(0.3)
                self.ctx.controller.post_click(target_pos["x"], target_pos["y"]).wait()
                time.sleep(0.3)
        else:
            logger.error(f"错误: 御主技能索引 {skill_index+1} 超出范围")
    
    @safe_execute
    def perform_servant_swap(self, servant_out_index, servant_in_index):
        """执行换人礼装功能"""
        logger.info(f"执行换人礼装: 将前排从者{servant_out_index+1}换成后排从者{servant_in_index+1}")
        
        # 前排从者位置(0-2)
        front_positions = [
            {"x": 250, "y": 350},
            {"x": 450, "y": 350},
            {"x": 650, "y": 350}
        ]
        
        # 后排从者位置(3-5)
        back_positions = [
            {"x": 250, "y": 500},
            {"x": 450, "y": 500},
            {"x": 650, "y": 500}
        ]
        
        # 确认按钮位置
        confirm_button = {"x": 450, "y": 600}
        
        # 1. 点击前排要换出的从者
        if 0 <= servant_out_index < len(front_positions):
            pos = front_positions[servant_out_index]
            self.ctx.controller.post_click(pos["x"], pos["y"]).wait()
            time.sleep(0.5)
        else:
            logger.error("错误: 无效的前排从者索引")
            return False
        
        # 2. 点击后排要换入的从者
        servant_in_adjusted = servant_in_index - 3  # 调整为后排索引(0-2)
        if 0 <= servant_in_adjusted < len(back_positions):
            pos = back_positions[servant_in_adjusted]
            self.ctx.controller.post_click(pos["x"], pos["y"]).wait()
            time.sleep(0.5)
        else:
            logger.error("错误: 无效的后排从者索引")
            return False
        
        # 3. 点击确认按钮
        self.ctx.controller.post_click(confirm_button["x"], confirm_button["y"]).wait()
        time.sleep(3)  # 等待换人动画
        
        return True
    
    @safe_execute
    def attack_phase(self, turn_data):
        """攻击阶段处理"""
        if not hasattr(turn_data, 'attacks') or not hasattr(turn_data.attacks, 'attacks'):
            logger.warning("回合没有攻击操作或数据格式不正确")
            return
            
        attack_list = turn_data.attacks
        
        # 点击攻击按钮，进入选卡界面
        logger.info("点击攻击按钮，进入选卡阶段")
        self.ctx.controller.post_click(self.ATTACK_BUTTON["x"], self.ATTACK_BUTTON["y"]).wait()
        time.sleep(1.5)  # 等待进入选卡界面
        
        # 如果有指定敌人目标，先选择
        if hasattr(attack_list, 'enemy_target') and attack_list.enemy_target != -1:
            self.select_enemy(attack_list.enemy_target)
            time.sleep(0.3)
        
        # 根据配置选择指令卡
        card_count = 0
        logger.info(f"开始选择指令卡，共 {len(attack_list.attacks)} 张配置卡")
        
        for index, attack in enumerate(attack_list.attacks):
            if card_count >= self.MAX_CARDS_PER_TURN:
                logger.info(f"已选择 {self.MAX_CARDS_PER_TURN} 张卡，忽略剩余配置")
                break
                
            if not hasattr(attack, 'isTD') or not hasattr(attack, 'svt') or not hasattr(attack, 'card'):
                logger.warning(f"攻击 #{index+1} 数据格式不正确")
                continue
                
            if attack.isTD:
                # 选择宝具卡
                if 0 <= attack.svt < len(self.NOBLE_PHANTASM_CARDS):
                    logger.info(f"选择从者 {attack.svt+1} 的宝具卡")
                    np_card = self.NOBLE_PHANTASM_CARDS[attack.svt]
                    self.ctx.controller.post_click(np_card["x"], np_card["y"]).wait()
                else:
                    logger.error(f"错误: 宝具卡从者索引 {attack.svt+1} 超出范围")
            else:
                # 选择普通指令卡
                if 0 <= attack.card < len(self.CARDS):
                    logger.info(f"选择第 {attack.card+1} 张普通指令卡")
                    card = self.CARDS[attack.card]
                    self.ctx.controller.post_click(card["x"], card["y"]).wait()
                else:
                    logger.error(f"错误: 指令卡索引 {attack.card+1} 超出范围")
            
            card_count += 1
            time.sleep(self.CARD_SELECT_DELAY)
        
        # 如果选择的卡牌不足3张，随机选择剩余卡牌
        remaining_cards = self.MAX_CARDS_PER_TURN - card_count
        if remaining_cards > 0:
            logger.info(f"已配置卡牌不足3张，随机选择剩余 {remaining_cards} 张卡")
            
            # 为了避免重复选择，从第一张卡开始尝试
            for card_idx in range(len(self.CARDS)):
                if card_count >= self.MAX_CARDS_PER_TURN:
                    break
                    
                # 实际应用中应检测卡片是否可点击，这里简化处理
                card = self.CARDS[card_idx]
                logger.info(f"随机选择第 {card_idx+1} 张指令卡")
                self.ctx.controller.post_click(card["x"], card["y"]).wait()
                card_count += 1
                time.sleep(self.CARD_SELECT_DELAY)
        
        logger.info("指令卡选择完毕，等待战斗动画")
    
    @safe_execute
    def select_enemy(self, enemy_index=-1):
        """选择敌人目标"""
        # 如果指定了敌人索引且在有效范围内
        if enemy_index != -1 and 0 <= enemy_index < len(self.ENEMY_POSITIONS):
            enemy_pos = self.ENEMY_POSITIONS[enemy_index]
            logger.info(f"选择第 {enemy_index+1} 个敌人")
            self.ctx.controller.post_click(enemy_pos["x"], enemy_pos["y"]).wait()
    
    @safe_execute
    def auto_battle_mode(self):
        """智能自动战斗模式"""
        logger.info("进入智能自动战斗模式")
        
        # 检查是否有宝具可用
        available_np = self.check_available_noble_phantasms()
        
        # 第一步：使用有效的技能
        self.use_effective_skills()
        
        # 第二步：进入攻击阶段
        self.ctx.controller.post_click(self.ATTACK_BUTTON["x"], self.ATTACK_BUTTON["y"]).wait()
        time.sleep(1.5)
        
        # 第三步：选择指令卡
        # 优先使用宝具，然后是克制卡，最后是普通卡
        cards_selected = 0
        
        # 选择可用的宝具
        for svt_idx, is_available in enumerate(available_np):
            if is_available and cards_selected < self.MAX_CARDS_PER_TURN:
                np_card = self.NOBLE_PHANTASM_CARDS[svt_idx]
                self.ctx.controller.post_click(np_card["x"], np_card["y"]).wait()
                cards_selected += 1
                time.sleep(0.3)
        
        # 识别并选择克制卡和高星卡
        advantage_cards = self.identify_advantage_cards()
        for card_idx in advantage_cards:
            if cards_selected < self.MAX_CARDS_PER_TURN:
                card = self.CARDS[card_idx]
                self.ctx.controller.post_click(card["x"], card["y"]).wait()
                cards_selected += 1
                time.sleep(0.3)
        
        # 如果还需要卡，随机选择剩余卡牌
        for card_idx in range(len(self.CARDS)):
            if cards_selected < self.MAX_CARDS_PER_TURN:
                card = self.CARDS[card_idx]
                self.ctx.controller.post_click(card["x"], card["y"]).wait()
                cards_selected += 1
                time.sleep(0.3)
        
        # 等待战斗动画完成后，检查战斗状态
        time.sleep(self.NP_ANIMATION_WAIT)
        self.wait_for_next_turn()
    
    def check_available_noble_phantasms(self):
        """检查哪些从者的宝具可用"""
        # 实际应用中使用图像识别检测宝具卡是否可用
        # 这里简化返回所有从者都可用宝具
        return [True, True, True]
    
    def use_effective_skills(self):
        """智能使用有效的技能"""
        # 简化的自动技能使用逻辑
        # 实际应用中应根据当前从者状态和敌人情况决定使用哪些技能
        pass
    
    def identify_advantage_cards(self):
        """识别克制卡和高星卡"""
        # 实际应用中使用图像识别识别卡牌类型和克制关系
        # 这里简化返回前几张卡是克制卡
        return [0, 1, 2]
    
    def main_loop(self):
        """主循环控制逻辑"""
        global BATTLE_LOGGER
        if not BATTLE_LOGGER:
            BATTLE_LOGGER = BattleLogger()
        
        try:
            while True:
                # 1. 选择关卡
                quest_name = self.select_quest()
                if not quest_name:
                    logger.info("无法选择关卡，退出")
                    break
                    
                # 2. 选择助战
                if not self.select_support_servant():
                    logger.info("无法选择助战，退出")
                    break
                
                # 3. 开始战斗并记录
                BATTLE_LOGGER.log_battle_start(quest_name)
                
                # 4. 执行战斗流程
                battle_success = self.execute_battle()
                
                # 5. 处理战斗结果
                if battle_success:
                    drops = self.detect_battle_drops()
                    BATTLE_LOGGER.log_battle_end(CURRENT_TURN, drops)
                    
                    # 检查是否继续下一场战斗
                    if not self.handle_post_battle_options():
                        logger.info("战斗循环中断")
                        break
                else:
                    logger.warning("战斗异常，退出循环")
                    break
                    
                # 6. 检查是否达到最大战斗次数
                max_battles = self.config.getint('Battle', 'max_battles', fallback=0)
                if max_battles > 0 and BATTLE_LOGGER.battle_count >= max_battles:
                    logger.info(f"已达到设定的最大战斗次数: {max_battles}")
                    break
        except KeyboardInterrupt:
            logger.info("用户中断，停止脚本")
        except Exception as e:
            logger.error(f"发生错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 生成战斗报告
            if BATTLE_LOGGER:
                report = BATTLE_LOGGER.generate_report()
                logger.info(f"战斗报告已保存至: {BATTLE_LOGGER.log_file}")
    
    def select_quest(self):
        """选择关卡"""
        # 实际应用中应实现选择关卡的逻辑
        # 这里简化返回一个默认关卡名
        return "默认关卡"
    
    def execute_battle(self):
        """执行战斗流程"""
        # 这个方法在主循环中被调用，实际战斗逻辑已经在run方法中实现
        # 这里简化返回True表示战斗成功
        return True


# 添加脚本入口点
if __name__ == "__main__":
    # 直接启动时的初始化逻辑
    config = FGOBattleConfig()
    battle = StartTurn()
    battle.main_loop()
class SupportServantSelector:
    """助战从者选择类"""
    
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config
        self.logger = logging.getLogger("SupportServantSelector")
        
        # 加载等待时间
        self.DIALOG_WAIT = self.config.getfloat('Timing', 'dialog_wait', fallback=1.0)
    
    @safe_execute
    def select_support(self):
        """选择助战从者"""
        if not self.config.getboolean('Support', 'enable_support_selection', fallback=True):
            # 如果没有启用助战选择，直接选第一个
            self.logger.info("助战选择功能未启用，选择默认助战")
            self.ctx.controller.post_click(450, 300).wait()
            time.sleep(self.DIALOG_WAIT * 2)  # 等待助战加载
            return True
        
        # 配置中指定的助战从者和礼装
        target_servant = self.config.get('Support', 'servant', fallback=None)
        target_craft_essence = self.config.get('Support', 'craft_essence', fallback=None)
        target_skill = self.config.get('Support', 'skill', fallback=None)
        
        # 优先级：从者 > 礼装 > 技能
        if not target_servant and not target_craft_essence and not target_skill:
            # 没有指定任何筛选条件，选择第一个
            self.logger.info("未指定助战筛选条件，选择第一个")
            self.ctx.controller.post_click(450, 300).wait()
            time.sleep(self.DIALOG_WAIT * 2)
            return True
        
        # 滑动查找次数
        max_scroll = self.config.getint('Support', 'max_refresh', fallback=5)
        auto_refresh = self.config.getboolean('Support', 'auto_refresh', fallback=True)
        scroll_count = 0
        
        # 先使用职阶筛选(如果配置了)
        class_filter = self.config.get('Support', 'class_filter', fallback=None)
        if class_filter:
            self._apply_class_filter(class_filter)
        
        while scroll_count < max_scroll:
            found = False
            
            # 按优先级查找
            if target_servant:
                found = self._find_target_servant(target_servant)
                if found:
                    self.logger.info(f"找到目标从者: {target_servant}")
                    return True
            
            if not found and target_craft_essence:
                found = self._find_target_ce(target_craft_essence)
                if found:
                    self.logger.info(f"找到目标礼装: {target_craft_essence}")
                    return True
            
            if not found and target_skill:
                found = self._find_target_skill(target_skill)
                if found:
                    self.logger.info(f"找到目标技能: {target_skill}")
                    return True
            
            # 没找到，滚动或刷新
            if scroll_count < max_scroll - 1:
                self._scroll_support_list()
                scroll_count += 1
                time.sleep(self.DIALOG_WAIT)
            else:
                # 达到最大滚动次数，考虑刷新
                if auto_refresh:
                    self.logger.info("刷新助战列表")
                    self._refresh_support_list()
                    time.sleep(3 * self.DIALOG_WAIT)
                    scroll_count = 0  # 重置计数
                else:
                    break
        
        # 如果经过所有尝试仍未找到，选择第一个
        self.logger.info("未找到指定助战，选择第一个")
        self.ctx.controller.post_click(450, 300).wait()
        time.sleep(2 * self.DIALOG_WAIT)
        return True
    
    def _apply_class_filter(self, class_name):
        """应用职阶筛选"""
        class_positions = {
            "all": {"x": 150, "y": 200},      # 全部
            "saber": {"x": 250, "y": 200},    # 剑阶
            "archer": {"x": 350, "y": 200},   # 弓阶
            "lancer": {"x": 450, "y": 200},   # 枪阶
            "rider": {"x": 550, "y": 200},    # 骑阶
            "caster": {"x": 650, "y": 200},   # 术阶
            "assassin": {"x": 750, "y": 200}, # 杀阶
            "berserker": {"x": 850, "y": 200},# 狂阶
            "extra": {"x": 950, "y": 200}     # 特殊职阶
        }
        
        if class_name in class_positions:
            pos = class_positions[class_name]
            self.logger.info(f"应用{class_name}职阶筛选")
            self.ctx.controller.post_click(pos["x"], pos["y"]).wait()
            time.sleep(self.DIALOG_WAIT)
            return True
        else:
            self.logger.warning(f"未知的职阶名称: {class_name}")
            return False
    
    def _find_target_servant(self, servant_name):
        """查找特定从者"""
        # 实际实现中使用OCR或图像识别识别从者名称
        # 这里仅作示例，返回False表示未找到
        return False
    
    def _find_target_ce(self, ce_name):
        """查找特定礼装"""
        # 实际实现中使用OCR或图像识别识别礼装名称
        # 这里仅作示例，返回False表示未找到
        return False
    
    def _find_target_skill(self, skill_name):
        """查找特定技能"""
        # 实际实现中使用OCR或图像识别识别技能图标
        # 这里仅作示例，返回False表示未找到
        return False
    
    def _scroll_support_list(self):
        """滚动助战列表"""
        # 从下向上滑动
        self.ctx.controller.post_swipe(640, 600, 640, 200, 500).wait()
    
    def _refresh_support_list(self):
        """刷新助战列表"""
        # 点击刷新按钮
        self.ctx.controller.post_click(750, 200).wait()
        time.sleep(self.DIALOG_WAIT)
        
        # 点击确认按钮
        self.ctx.controller.post_click(550, 450).wait()


# 使用示例
@AgentServer.custom_action("StartLostbeltQuest")
class StartLostbeltQuest(CustomAction):
    """启动白纸化地球关卡出击的自定义操作"""
    
    def __init__(self):
        super().__init__()
        self.config = FGOBattleConfig()
    
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        # 获取参数
        try:
            # 解析参数
            chapter = argv.get("chapter", "lb1")
            node = int(argv.get("node", 0))
            difficulty = int(argv.get("difficulty", 0))
            ap_recovery = argv.get("ap_recovery", "false").lower() == "true"
            
            # 创建关卡选择器
            quest_selector = FGOLostbeltQuest(context, self.config)
            
            # 执行关卡选择流程
            success = quest_selector.complete_quest_selection(
                chapter, node, difficulty, ap_recovery
            )
            
            if success:
                # 选择成功后开始战斗
                context.run_action("StartTurn")
                return True
            else:
                return False
            
        except Exception as e:
            logger.error(f"启动白纸化地球关卡出击时出错: {e}")
            import traceback
            traceback.print_exc()
            return False