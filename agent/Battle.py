from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
from BattleData import *
import json

BattleData = None #  BattleJson

@AgentServer.custom_action("InitBattleJson")
class InitBattleInfo(CustomAction):
    self.battle_data = None
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
    def run(
        self,
        context: Context,
        argv: CustomAction.RunArg,
    ) -> bool:
        StartTurnBattle()
        return True

def StartTurnBattle(turn_index):
    turn_battle_data = BattleData.get_turn_data(turn_index)
    if(turn_battle_data):
        UseSkill()  
        UseClothSkill()
        Attack()
    else:
        start_auto_battle()
    return
    
## 默认关闭技能确认
def UseSkill(turn_data: Turn):
    return

def UseClothSkill():
    return

def Attack():
    return

def SeleteEnemy():
    return

def SelectCard():
    return

def start_auto_battle():
    return

