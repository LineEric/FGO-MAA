from datetime import date
import json
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict, Union
from dataclasses_json import dataclass_json, config

# ================================
# 1. 基础动作定义 (修正了继承问题)
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

@dataclass_json
@dataclass
class AttackAction(BaseAction):
    attacks: List[Attack]
    options: Optional[ActionOptions] = None

@dataclass_json
@dataclass
class SkillAction(BaseAction):
    skill: int
    svt: Optional[int] = None
    options: Optional[ActionOptions] = None

# ================================
# 2. Turn 定义 (保持不变)
# ================================
@dataclass_json
@dataclass
class Turn:
    turn_number: int
    skills: List[SkillAction] = field(default_factory=list)
    attacks: List[AttackAction] = field(default_factory=list)

# ================================
# 3. 其他数据结构 (修正了 OnFieldSvt)
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
    simulateAi: bool
    pointBuffs: Optional[Any] = None
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
    supportType: str
    ceId: Optional[int] = None
    ceLimitBreak: Optional[bool] = None
    ceLv: Optional[int] = None
    # 新增：添加 appendLvs 字段来匹配 JSON
    appendLvs: Optional[List[int]] = None

@dataclass_json
@dataclass
class Team:
    mysticCode: MysticCode
    onFieldSvts: List[OnFieldSvt]
    backupSvts: List[Optional[Any]]
    name: Optional[str] = None

# ================================
# 4. Result 定义 (使用 __post_init__ 进行转换)
# ================================
@dataclass_json
@dataclass
class Result:
    minBuild: int
    appBuild: int
    quest: QuestInner
    options: OptionsInner
    team: Team
    delegate: Dict[str, Any]
    isCritTeam: bool
    
    # 接受原始的 "actions" 列表
    actions: List[Dict[str, Any]] = field(default_factory=list)
    
    # "turns" 列表将在初始化后被创建
    turns: List[Turn] = field(init=False, default_factory=list)

    def __post_init__(self):
        """
        在对象创建后自动运行，将扁平的 actions 列表转换为按回合分组的 turns 列表。
        """
        if not self.actions:
            return

        parsed_turns: List[Turn] = []
        current_turn_skills: List[SkillAction] = []
        current_turn_attacks: List[AttackAction] = []
        current_turn_number = 1
        
        for action_raw_dict in self.actions:
            action_type = action_raw_dict.get('type')
            
            if action_type == 'skill':
                if current_turn_attacks:
                    parsed_turns.append(Turn(
                        turn_number=current_turn_number,
                        skills=current_turn_skills,
                        attacks=current_turn_attacks
                    ))
                    current_turn_number += 1
                    current_turn_skills = []
                    current_turn_attacks = []
                
                current_turn_skills.append(SkillAction.from_dict(action_raw_dict))
                
            elif action_type == 'attack':
                current_turn_attacks.append(AttackAction.from_dict(action_raw_dict))

        if current_turn_skills or current_turn_attacks:
            parsed_turns.append(Turn(
                turn_number=current_turn_number,
                skills=current_turn_skills,
                attacks=current_turn_attacks
            ))
            
        self.turns = parsed_turns

@dataclass_json
@dataclass
class DataWrapper:
    result: Result

# ================================
# 5. 顶层 BattleData 定义 (已简化)
# ================================
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

    # 无需自定义 from_json 或 from_dict，dataclasses-json 会自动处理
    
    def get_turn_data(self, turn_index: int) -> Optional[Turn]:
        """获取指定回合的数据"""
        # 注意路径现在是 self.data.result.turns
        if turn_index < len(self.data.result.turns):
            return self.data.result.turns[turn_index]
        return None