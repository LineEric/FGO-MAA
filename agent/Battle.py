from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from BattleData import *
import json

BattleData = None #  BattleJson

@AgentServer.custom_action("InitBattleJson")
class InitBattleInfo(CustomAction):
    battle_data = None
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:

        json_file_path = "1001.json" # 假设1001.json在与BattleAction.py相同的目录下

        # 检查文件是否存在
        if not os.path.exists(json_file_path):
            print(f"Error: JSON file not found at {json_file_path}")
            return False
        
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                json_data_string = f.read()
            
            # 解析JSON字符串并存储到实例变量
            self.battle_data = BattleData.from_json(json_data_string)

            global Sevant_Info
            Sevant_Info = self.battle_data

            print(f"JSON data parsed and stored successfully!")
            print(f"ID: {self.battle_data.get('id')}")
            print(f"Username: {self.battle_data.get('username')}")
            print(f"Quest ID: {self.battle_data.get('questId')}")
            
            # 访问更深层的数据，例如第一个在场从者(onFieldSvts)的ID
            if 'data' in self.battle_data and 'result' in self.battle_data['data'] and \
               'team' in self.battle_data['data']['result'] and \
               'onFieldSvts' in self.battle_data['data']['result']['team'] and \
               len(self.battle_data['data']['result']['team']['onFieldSvts']) > 0:
                first_svt_id = self.battle_data['data']['result']['team']['onFieldSvts'][0].get('svtId')
                print(f"First On-Field Servant ID: {first_svt_id}")

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            self.battle_data = None # 解析失败时清空存储
            return False # 解析失败返回False
        
        context.run_action("回合开始")
        return True
    
@AgentServer.custom_action("StartTurn")
class StartTurn(CustomAction):
    ctx = None
    
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        ctx = context
        # 先默认第一回合，再寻找方法来读取index
        self.StartTurnBattle(1)
        return True


    def StartTurnBattle(self, turn_index):
        turn_battle_data = BattleData.get_turn_data(turn_index)
        if turn_battle_data:
            self.SkillPhase(turn_battle_data)  
            self.ClothSkillPhase()
            self.AttackPhase()
        else:
            self.start_auto_battle()
        return
    
    ## 默认关闭技能确认
    def SkillPhase(self, turn_data: Turn):
        for skill in turn_data.skills:
             self.UseSvtSkill(skill.svt, skill.skill, skill.options.playerTarget, skill.options.enemyTarget)
        return

    def UseSvtSkill(self, svt, skill, playerTarget, enemyTarget):
        self.SelectEnemy(enemyTarget)
        svt_pos_spacing_x = 100 #从者间隔
        skill_icon_spacing_x = 100 #技能间隔
        skill_pos_x = svt * svt_pos_spacing_x + skill * skill_icon_spacing_x
        skill_pos_y = 100 # 先填一个默认值
        self.ctx.controller.post_click(skill_pos_x, skill_pos_y).wait()
        
        
        # 要看一下，这个怎么选的
        if playerTarget != -1:
            svt_skill_select_svt_target_spacing_x = 100 #技能对象选择间隔
            svt_skill_target_pos_y = 100 #垂直方向
            svt_skill_target_pos_x = playerTarget * svt_skill_select_svt_target_spacing_x
            self.ctx.controller.post_click(svt_skill_target_pos_x, svt_skill_target_pos_y).wait()

        
    def ClothSkillPhase():
        #先不做，懒了
        return

    def AttackPhase(self, turn_data: Turn):
        self.SelectCard(turn_data)
        return

    def SelectCard(self, svt, noble_phantasm):
        return

    def SelectEnemy():
        #now default
        return

    def start_auto_battle():
        return

