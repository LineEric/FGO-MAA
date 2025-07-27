from datetime import date
import json
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Union
from dataclasses_json import dataclass_json, config # 导入 config 用于联合类型配置

# ================================
# 单个动作的结构定义 (保持不变，因为它们仍然表示单独的技能或攻击指令)
# ================================

@dataclass_json
@dataclass
class Attack:
    svt: int
    card: int
    isTD: bool
    critical: bool
    cardType: str

@dataclass_json
@dataclass
class ActionOptions:
    playerTarget: int
    enemyTarget: int
    random: int
    threshold: int

@dataclass_json
@dataclass
class BaseAction:
    type: str
    options: Optional[ActionOptions] = None

@dataclass_json
@dataclass
class AttackAction(BaseAction):
    attacks: List[Attack]

@dataclass_json
@dataclass
class SkillAction(BaseAction):
    svt: Optional[int] = None
    skill: int

# ================================
# 引入 Turn 数据类：表示一个游戏回合
# ================================
@dataclass_json
@dataclass
class Turn:
    turn_number: int # 方便追踪回合数
    skills: List[SkillAction] = field(default_factory=list) # 本回合的所有技能
    attacks: List[AttackAction] = field(default_factory=list) # 本回合的所有攻击

# ================================
# 其他数据结构 (大部分保持不变)
# ================================

@dataclass_json
@dataclass
class Votes:
    up: Optional[Any] = None
    down: Optional[Any] = None
    mine: Optional[Any] = None

@dataclass_json
@dataclass
class QuestInner:
    id: int
    phase: int
    enemyHash: str

@dataclass_json
@dataclass
class OptionsInner:
    mightyChain: bool
    disableEvent: bool
    pointBuffs: Optional[Any] = None
    simulateAi: bool
    enemyRateUp: Optional[Any] = None

@dataclass_json
@dataclass
class MysticCode:
    mysticCodeId: int
    level: int

@dataclass_json
@dataclass
class OnFieldSvt:
    svtId: int
    limitCount: int
    skillIds: List[int]
    skillLvs: List[int]
    tdId: int
    tdLv: int
    lv: int
    atkFou: int
    hpFou: int
    ceId: Optional[int] = None
    ceLimitBreak: Optional[bool] = None
    ceLv: Optional[int] = None
    supportType: str

@dataclass_json
@dataclass
class Team:
    name: Optional[str] = None
    mysticCode: MysticCode
    onFieldSvts: List[OnFieldSvt]
    backupSvts: List[Optional[Any]]

@dataclass_json
@dataclass
class Result:
    minBuild: int
    appBuild: int
    quest: QuestInner
    options: OptionsInner
    team: Team
    delegate: Dict[str, Any]
    turns: List[Turn] # **关键改变：现在存储的是回合列表**
    isCritTeam: bool

@dataclass_json
@dataclass
class DataWrapper:
    result: Result

@dataclass_json
@dataclass
class BattleData:
    id: int
    ver: int
    appVer: str
    userId: int
    questId: int
    phase: int
    enemyHash: str
    createdAt: int
    content: str
    username: str
    votes: Votes
    data: DataWrapper

    @classmethod
    def get_turn_data(turn_index):
        if self.data.turns.length > turn_index:
            return self.data.turns[turn_index]
        return None
    
    @classmethod
    def from_dict(cls, data_dict: Dict[str, Any]) -> 'BattleData':
        """
        从字典数据构建 BattleData 实例。
        此方法现在会处理将扁平的原始 actions 列表分组为 Turn 对象列表的逻辑。
        """
        # 利用 dataclasses_json 的 from_dict 自动解析大部分结构
        votes_obj = Votes.from_dict(data_dict['votes'])
        
        # 处理嵌套的 data -> result 部分
        result_dict = data_dict['data']['result']
        
        quest_inner_obj = QuestInner.from_dict(result_dict['quest'])
        options_inner_obj = OptionsInner.from_dict(result_dict['options'])
        team_obj = Team.from_dict(result_dict['team']) # team内部结构由dataclasses_json处理
        
        # ====================================================================
        # 自定义解析逻辑：将扁平的 actions 列表分组为回合 (turns)
        # ====================================================================
        original_actions_list = result_dict.get('actions', [])
        
        parsed_turns: List[Turn] = []
        current_turn_skills: List[SkillAction] = []
        current_turn_attacks: List[AttackAction] = []
        current_turn_number = 1
        
        # 由于 original_actions_list 中的每个字典都包含 'type' 字段
        # 我们可以用它来动态创建 SkillAction 或 AttackAction
        # 这里需要手动模拟 dataclasses_json 的判别器逻辑，因为我们是在 from_dict 内部手动处理
        # 更好的方法是在顶层使用 dataclasses_json.from_dict，并让它处理多态性
        # 但既然要手动分组，就手动构建 Action 对象
        
        for action_raw_dict in original_actions_list:
            action_type = action_raw_dict.get('type')
            
            if action_type == 'skill':
                # 如果当前有攻击动作，说明一个回合结束，开始新的回合
                if current_turn_attacks:
                    parsed_turns.append(Turn(
                        turn_number=current_turn_number,
                        skills=current_turn_skills,
                        attacks=current_turn_attacks
                    ))
                    current_turn_number += 1
                    current_turn_skills = []
                    current_turn_attacks = []
                
                # 解析并添加技能动作
                # 这里我们假设 ActionOptions 总是存在的
                options_dict = action_raw_dict.get('options')
                action_options = ActionOptions.from_dict(options_dict) if options_dict else None
                
                skill_action = SkillAction(
                    type=action_type,
                    svt=action_raw_dict.get('svt'),
                    skill=action_raw_dict.get('skill'),
                    options=action_options
                )
                current_turn_skills.append(skill_action)
                
            elif action_type == 'attack':
                # 解析并添加攻击动作
                attacks_list = []
                for attack_raw_dict in action_raw_dict.get('attacks', []):
                    attacks_list.append(Attack.from_dict(attack_raw_dict))

                options_dict = action_raw_dict.get('options')
                action_options = ActionOptions.from_dict(options_dict) if options_dict else None

                attack_action = AttackAction(
                    type=action_type,
                    attacks=attacks_list,
                    options=action_options
                )
                current_turn_attacks.append(attack_action)
            else:
                print(f"Warning: Unknown action type encountered: {action_type}")

        # 将最后一个回合添加到列表中（如果还有未处理的动作）
        if current_turn_skills or current_turn_attacks:
            parsed_turns.append(Turn(
                turn_number=current_turn_number,
                skills=current_turn_skills,
                attacks=current_turn_attacks
            ))
        
        # ====================================================================
        # 构建 Result 对象，传入我们解析和分组好的 turns 列表
        # ====================================================================
        result_obj = Result(
            minBuild=result_dict['minBuild'],
            appBuild=result_dict['appBuild'],
            quest=quest_inner_obj,
            options=options_inner_obj,
            team=team_obj,
            delegate=result_dict.get('delegate', {}), # delegate 可能是空的字典
            turns=parsed_turns, # 使用我们分组好的 turns 列表
            isCritTeam=result_dict['isCritTeam']
        )
        data_wrapper_obj = DataWrapper(result=result_obj)

        return cls(
            id=data_dict['id'],
            ver=data_dict['ver'],
            appVer=data_dict['appVer'],
            userId=data_dict['userId'],
            questId=data_dict['questId'],
            phase=data_dict['phase'],
            enemyHash=data_dict['enemyHash'],
            createdAt=data_dict['createdAt'],
            content=data_dict['content'],
            username=data_dict['username'],
            votes=votes_obj,
            data=data_wrapper_obj
        )

    @classmethod
    def from_json(cls, json_string: str) -> 'BattleData':
        """
        从JSON字符串构建 BattleData 实例。
        """
        data_dict = json.loads(json_string)
        return cls.from_dict(data_dict)