# MaaFgo 原生回合战斗 Planner：具体技术方案

> **版本**：v1.0  
> **日期**：2026-07-30  
> **目标**：在 MaaFgo 内部实现可测试、可回放、可逐回合验证的原生战斗 Planner；BBC 保留为兼容性外部后端，但不作为 Planner 的测试基础或必要依赖。  
> **适用代码基线**：[MaaFgo](https://github.com/xlxyvergil/MaaFgo) `main`、MaaFramework Python Agent。  

---

## 0. 决策摘要

### 0.1 核心决策

1. **原生 Planner 不调用 BBC，也不依赖 BBC 的 TCP、回调、弹窗或进程生命周期。**
2. **MaaFramework Controller 是唯一的实时输入/输出通道**：获取截图、执行点击、等待画面稳定。
3. **战斗核心拆为纯逻辑与运行时适配两部分**：
   - 纯逻辑：状态模型、候选生成、规则、模拟、校验、回放——可在 CI 中无设备运行；
   - 运行时：截图识别与 Maa Controller 点击——仅在集成测试/人工验收中运行。
4. **BBC 仅保留为 `ExternalBbcBackend`**，用于旧配置与稳定周回；不得作为 Planner 单元测试、决策测试、回放测试的依赖。
5. **首个可执行版本只处理“固定计划 + 动态选卡”**；技能、NP、换人和复杂伤害模拟逐步扩展。
6. **LLM 不进入 MVP 实时路径**；先完成确定性规则与模拟测试，再加“候选选择器”。

### 0.2 目标形态

```text
                ┌────────────────────────────────────┐
                │ MaaFgo Pipeline / Custom Action     │
                │ 进入战斗、调用 Planner、结算处理      │
                └────────────────┬───────────────────┘
                                 ▼
                ┌────────────────────────────────────┐
                │ PlannerRuntime（可替换适配层）       │
                │ observation -> plan -> execute      │
                └───────┬──────────────────┬─────────┘
                        │                  │
                        ▼                  ▼
       ┌────────────────────────┐ ┌────────────────────────┐
       │ LiveMaaBattlePort       │ │ FakeBattlePort          │
       │ Maa Controller + CV     │ │ Fixture / Replay / Fake │
       └────────────┬───────────┘ └────────────┬───────────┘
                    ▼                            ▼
              真机/模拟器                   pytest / CI

                    ┌─────────────────────────────────┐
                    │ Pure Battle Core                 │
                    │ models / rules / sim / validator │
                    └─────────────────────────────────┘
```

---

# 1. 为什么 BBC 不应成为 Planner 测试基础

BBC 在 MaaFgo 当前架构中是一个通过本机 TCP、独立进程与回调端口调用的外部战斗后端。它适合作为成熟周回功能的实现，但不适合作为新 Planner 的测试桩，原因如下。

| 问题 | 对测试的影响 |
|---|---|
| 进程外依赖 | 单元测试需要安装/启动 BBC，环境不稳定 |
| 固定端口与回调 | 并发测试、CI、开发机多实例会互相干扰 |
| 结果粒度有限 | 弹窗/完成回调不足以提供每回合状态与决策证据 |
| 运行不可控 | 难以注入“某回合卡牌为 X、HP 为 Y、识别失败”的边界条件 |
| 真实设备依赖 | 无法快速覆盖几十/几百个策略分支 |
| 外部黑盒 | 失败原因难以定位到视觉、规则、执行还是外部进程 |

因此应把测试层次分开：

```text
纯单元测试          不启动 MaaFramework、不启动 BBC、不连接设备
回放测试            不启动 BBC；使用截图/状态 fixture
组件测试            使用 FakeBattlePort；验证 Runtime 状态机
视觉测试            使用静态截图；验证 Perception
设备集成测试        仅在受控模拟器上运行 MaaFramework Controller
BBC 回归测试        仅验证旧 BBC 后端仍可用，与 Planner 无关
```

---

# 2. 范围与非目标

## 2.1 MVP 范围

MVP 的实时战斗能力限定为：

- 识别是否处于指令选择界面；
- 识别五张指令卡的槽位、卡色与所属前排位置（可先限制固定队伍/视觉样式）；
- 识别当前可用 NP（初期只做是否可用）；
- 可选择敌方目标；
- 根据固定 `TurnPlan` 和 `CardPolicy` 选择三张卡；
- 在严格后置确认下选择卡并点击攻击；
- 识别胜利、下一回合、异常页面并安全停止；
- 保存回放证据。

## 2.2 后续范围

- 主动施放从者技能与目标选择；
- 御主技能、换人；
- NP 顺序和 Overcharge；
- 伤害、NP 回收、暴击星高保真模拟；
- Buff/Debuff 图标与敌方特殊机制；
- LLM 候选选择、策略解释、离线复盘；
- 多服、多 UI 版本和多分辨率广泛覆盖。

## 2.3 非目标

- 不尝试在第一版覆盖所有从者特殊技能；
- 不承诺未知高难关卡通用自动通关；
- 不让 LLM 直接获取 Controller 或执行坐标；
- 不使用 BBC 来伪装 Planner 测试通过；
- 不涉及规避检测、对抗机制或绕过服务限制。

---

# 3. 架构与依赖倒置

## 3.1 分层原则

```text
层 1：领域核心（100% 可离线测试）
  - 数据模型
  - 合法动作生成
  - 规则评分
  - 模拟/估值
  - 验证器
  - 回放状态机

层 2：应用编排（Fake 可测）
  - PlannerRuntime
  - 回合循环
  - 超时、重试、停止
  - 事件日志

层 3：适配器（集成测试）
  - MaaBattlePort：截图/点击/稳定等待
  - Perception：图片 -> 观察结果
  - UI 坐标与视觉锚点

层 4：外部后端（兼容）
  - BBC adapter，仅维持原有能力
```

任何 `battle/core/*` 文件不得导入：

```text
maa.*
cv2
PIL
socket
subprocess
threading
agent.custom.bbc_*
```

这样才能确保核心测试不依赖设备、图像库或 BBC。

## 3.2 端口（Port）接口

使用 Python `Protocol`，让运行时依赖接口而非 MaaFramework/BBC 实现。

```python
# agent/battle/runtime/ports.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

from battle.core.models import BattleState, PrimitiveAction, UiObservation


class BattlePort(Protocol):
    """Planner 唯一可见的运行时端口。"""

    def observe(self) -> UiObservation:
        """获取稳定画面并产生一次 UI 观察；不得做策略决策。"""

    def execute(self, action: PrimitiveAction) -> None:
        """执行受限原子动作；不得接受任意坐标/脚本文本。"""

    def wait_for(self, expected: "ExpectedUiState", timeout_ms: int) -> UiObservation:
        """等待预期 UI 后置状态；超时返回最后观测。"""

    def now_ms(self) -> int:
        """供 runtime 记录时间与超时逻辑。"""
```

实现：

```text
LiveMaaBattlePort  -> MaaFramework Controller + Perception + 确认器
ReplayBattlePort   -> 从回放帧序列读取 observation，验证 action 序列
FakeBattlePort     -> 测试中按预设状态迁移，不使用图像
```

**关键点**：PlannerRuntime 只依赖 `BattlePort`，所以它对 BBC、Maa Controller、真实设备一无所知。

---

# 4. 目录与模块设计

建议新增如下目录；原 `agent/custom/bbc_*` 不作为新实现依赖。

```text
agent/
├── battle/
│   ├── core/                         # 纯逻辑，禁止依赖 Maa/CV/BBC
│   │   ├── __init__.py
│   │   ├── enums.py
│   │   ├── models.py
│   │   ├── errors.py
│   │   ├── policy.py
│   │   ├── legal_actions.py
│   │   ├── card_rules.py
│   │   ├── evaluator.py
│   │   ├── simulator.py
│   │   ├── validator.py
│   │   └── turn_planner.py
│   │
│   ├── runtime/                      # 编排，可依赖 core 与 ports
│   │   ├── ports.py
│   │   ├── planner_runtime.py
│   │   ├── state_machine.py
│   │   ├── retry.py
│   │   └── events.py
│   │
│   ├── perception/                   # 图像 -> 观察，集成层
│   │   ├── scene_detector.py
│   │   ├── command_cards.py
│   │   ├── np_detector.py
│   │   ├── enemy_detector.py
│   │   ├── skill_detector.py
│   │   ├── stability.py
│   │   └── mapper.py
│   │
│   ├── execution/                    # PrimitiveAction -> Maa 控制器输入
│   │   ├── actions.py
│   │   ├── anchors.py
│   │   ├── maa_port.py
│   │   ├── confirmation.py
│   │   └── safety.py
│   │
│   ├── data/
│   │   ├── repository.py
│   │   ├── schemas.py
│   │   ├── manifest.json
│   │   └── profiles/
│   │
│   ├── telemetry/
│   │   ├── recorder.py
│   │   ├── replay_port.py
│   │   ├── fixture_io.py
│   │   └── metrics.py
│   │
│   └── llm/                          # 后置、可选
│       ├── provider.py
│       ├── candidate_selector.py
│       └── schemas.py
│
├── backends/
│   ├── base.py
│   ├── bbc_backend.py                # 对旧 BBC action 的薄适配
│   ├── planner_backend.py
│   ├── shadow_backend.py
│   └── router.py
│
├── custom/
│   ├── planner_action.py             # Maa Agent 注册入口
│   └── bbc_action.py                 # 保持兼容，不与 planner 相互 import
│
└── chaldea/
    └── ...                           # 提供 TeamSnapshot，不参与实时点击

tests/
├── unit/battle/core/
├── component/battle/runtime/
├── visual/battle/perception/
├── replay/battle/
├── integration/maa/
└── fixtures/battle/
```

---

# 5. 核心数据模型

以下示例使用标准库 `dataclasses`。如项目已引入 Pydantic，可将外部 JSON 边界改为 Pydantic，内部仍推荐不可变 dataclass。

## 5.1 枚举

```python
# agent/battle/core/enums.py
from enum import Enum


class Scene(str, Enum):
    COMMAND_SELECTION = "command_selection"
    TARGET_SELECTION = "target_selection"
    NP_SELECTION = "np_selection"
    BATTLE_ANIMATION = "battle_animation"
    WAVE_TRANSITION = "wave_transition"
    VICTORY = "victory"
    DEFEAT = "defeat"
    DIALOG = "dialog"
    UNKNOWN = "unknown"


class CardColor(str, Enum):
    BUSTER = "B"
    ARTS = "A"
    QUICK = "Q"


class Goal(str, Enum):
    FINISH_WAVE = "finish_wave"
    BUILD_NP = "build_np"
    BUILD_STARS = "build_stars"
    SURVIVE = "survive"


class PrimitiveKind(str, Enum):
    SELECT_ENEMY = "select_enemy"
    SERVANT_SKILL = "servant_skill"
    MASTER_SKILL = "master_skill"
    ORDER_CHANGE = "order_change"
    SELECT_NP = "select_np"
    SELECT_CARD = "select_card"
    ATTACK = "attack"
    STOP = "stop"
```

## 5.2 观测和 BattleState

```python
# agent/battle/core/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .enums import CardColor, Scene, PrimitiveKind


@dataclass(frozen=True)
class Confidence:
    value: float
    source: str = ""

    def passes(self, threshold: float) -> bool:
        return self.value >= threshold


@dataclass(frozen=True)
class CommandCard:
    ui_slot: int                 # 1..5，UI 槽位，不是坐标
    color: CardColor
    owner_slot: Optional[int]    # 1..3；未知为 None
    critical_rate: Optional[float]
    confidence: Confidence


@dataclass(frozen=True)
class SkillState:
    index: int
    available: bool
    confidence: Confidence


@dataclass(frozen=True)
class AllyState:
    slot: int                    # 1..3
    servant_id: Optional[int]
    np: Optional[int]
    np_ready: bool
    skills: Tuple[SkillState, ...] = ()


@dataclass(frozen=True)
class EnemyState:
    slot: int
    alive: bool
    hp: Optional[int]
    class_name: Optional[str]
    targeted: bool
    confidence: Confidence


@dataclass(frozen=True)
class BattleState:
    schema_version: int
    scene: Scene
    scene_confidence: Confidence
    wave: Optional[int]
    turn: Optional[int]
    enemies: Tuple[EnemyState, ...]
    allies: Tuple[AllyState, ...]
    cards: Tuple[CommandCard, ...]
    screenshot_id: str
    unknown_fields: Tuple[str, ...] = ()

    def command_ready(self) -> bool:
        return self.scene is Scene.COMMAND_SELECTION and self.scene_confidence.passes(0.95)

    def cards_ready(self) -> bool:
        return len(self.cards) == 5 and all(c.confidence.passes(0.90) for c in self.cards)
```

## 5.3 抽象动作与原子动作

```python
@dataclass(frozen=True)
class SkillUse:
    servant_slot: int
    skill_index: int
    target_ally: Optional[int] = None


@dataclass(frozen=True)
class BattleAction:
    target_enemy: Optional[int]
    servant_skills: Tuple[SkillUse, ...]
    np_order: Tuple[int, ...]
    card_order: Tuple[int, ...]  # 三个 ui_slot
    rationale_tag: str


@dataclass(frozen=True)
class PrimitiveAction:
    kind: PrimitiveKind
    slot: Optional[int] = None
    skill_index: Optional[int] = None
    target: Optional[int] = None
```

`PrimitiveAction` 不包含 `x/y`。坐标仅存在于 `execution/anchors.py` 和 `LiveMaaBattlePort` 内部。

## 5.4 策略与回合计划

```python
# agent/battle/core/policy.py
from dataclasses import dataclass
from typing import Tuple
from .enums import CardColor, Goal


@dataclass(frozen=True)
class CardPolicy:
    goal: Goal
    color_priority: Tuple[CardColor, ...]
    servant_priority: Tuple[int, ...]
    prefer_brave_chain: bool = True
    rearrange_cards: bool = True
    allow_mighty_chain: bool = True


@dataclass(frozen=True)
class TurnPlan:
    wave: int
    skills: Tuple[SkillUse, ...] = ()
    np_order: Tuple[int, ...] = ()
    card_policy: CardPolicy | None = None


@dataclass(frozen=True)
class StrategyProfile:
    id: str
    min_confidence: float = 0.90
    max_turns: int = 20
    allow_command_spell: bool = False
    allow_sq_revive: bool = False
    allow_ap_refill: bool = False
    fallback: str = "stop"            # stop | bbc（仅外层明确允许时）
```

---

# 6. Planner 核心算法

## 6.1 MVP：固定计划 + 卡牌规则

第一版不搜索所有技能组合。它读取当前 Wave 的固定计划：

```text
TurnPlan
  - 固定技能序列（可为空）
  - 固定 NP 顺序（可为空）
  - CardPolicy
```

实际卡牌随机，因此 Planner 动态生成三卡顺序。

### 卡链评分规则

候选空间只有：从 5 张选 3 张并排列，最多：

\[
P(5,3)=5\times4\times3=60
\]

60 个候选可以完整枚举，不需要大模型或复杂搜索。

评分初版：

```text
总分 =
  卡色优先级分
+ 从者优先级分
+ Brave Chain 奖励
+ 同色 Chain 奖励
+ 首卡目标奖励
+ 第三卡收益奖励
+ 目标模式权重（清场/NP/星）
```

伪代码：

```python
# agent/battle/core/card_rules.py
from itertools import permutations
from .enums import CardColor, Goal


def choose_cards(state: BattleState, policy: CardPolicy) -> tuple[int, int, int]:
    candidates = permutations(state.cards, 3)
    scored = [(score_chain(chain, policy), chain) for chain in candidates]
    _, best = max(scored, key=lambda item: item[0])
    return tuple(card.ui_slot for card in best)


def score_chain(chain, policy: CardPolicy) -> float:
    first, second, third = chain
    score = 0.0

    # 颜色优先级
    weights = {color: len(policy.color_priority) - i for i, color in enumerate(policy.color_priority)}
    score += sum(weights.get(card.color, 0) * 10 for card in chain)

    # 从者优先级
    servant_weights = {slot: len(policy.servant_priority) - i for i, slot in enumerate(policy.servant_priority)}
    score += sum(servant_weights.get(card.owner_slot, 0) * 3 for card in chain)

    # Brave Chain
    owners = [c.owner_slot for c in chain]
    if policy.prefer_brave_chain and None not in owners and len(set(owners)) == 1:
        score += 50

    # 同色 Chain
    colors = [c.color for c in chain]
    if len(set(colors)) == 1:
        score += 15

    # 目标导向：首卡和末卡
    if policy.goal is Goal.FINISH_WAVE:
        if first.color is CardColor.BUSTER:
            score += 15
        if third.color is CardColor.BUSTER:
            score += 8
    elif policy.goal is Goal.BUILD_NP:
        if first.color is CardColor.ARTS:
            score += 15
        if third.color is CardColor.ARTS:
            score += 8
    elif policy.goal is Goal.BUILD_STARS:
        if first.color is CardColor.QUICK:
            score += 15
        if third.color is CardColor.QUICK:
            score += 8

    return score
```

此算法的意义不是高保真伤害模拟，而是先完成：**确定性、可解释、可单测、可执行的动态选卡。**

## 6.2 合法动作生成

```python
# agent/battle/core/legal_actions.py
from .models import BattleAction, BattleState, TurnPlan
from .card_rules import choose_cards


def generate_action(state: BattleState, plan: TurnPlan) -> BattleAction:
    if not state.command_ready():
        raise ValueError("not in a confident command-selection state")
    if not state.cards_ready():
        raise ValueError("command cards are not sufficiently recognized")

    target = next((e.slot for e in state.enemies if e.alive and e.targeted), None)
    if target is None:
        target = next((e.slot for e in state.enemies if e.alive), None)

    cards = choose_cards(state, plan.card_policy)
    return BattleAction(
        target_enemy=target,
        servant_skills=plan.skills,
        np_order=plan.np_order,
        card_order=cards,
        rationale_tag=f"policy:{plan.card_policy.goal.value}",
    )
```

## 6.3 独立 Validator

Validator 必须独立于 Planner。即使未来 LLM、用户 DSL 或 Chaldea 导入产生 Action，也必须经过它。

```python
# agent/battle/core/validator.py
from dataclasses import dataclass
from .models import BattleAction, BattleState, StrategyProfile


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""


def validate(action: BattleAction, state: BattleState, profile: StrategyProfile) -> Verdict:
    if not state.command_ready():
        return Verdict(False, "scene_not_command_selection")
    if not state.cards_ready():
        return Verdict(False, "cards_not_confident")

    if len(action.card_order) != 3 or len(set(action.card_order)) != 3:
        return Verdict(False, "invalid_card_count_or_duplicates")

    present = {c.ui_slot for c in state.cards}
    if not set(action.card_order).issubset(present):
        return Verdict(False, "card_not_present")

    alive = {e.slot for e in state.enemies if e.alive}
    if action.target_enemy is not None and action.target_enemy not in alive:
        return Verdict(False, "invalid_enemy_target")

    for skill in action.servant_skills:
        ally = next((a for a in state.allies if a.slot == skill.servant_slot), None)
        if ally is None:
            return Verdict(False, "invalid_servant_slot")
        s = next((x for x in ally.skills if x.index == skill.skill_index), None)
        if s is None or not s.available:
            return Verdict(False, "skill_unavailable")

    ready_np = {a.slot for a in state.allies if a.np_ready}
    if not set(action.np_order).issubset(ready_np):
        return Verdict(False, "np_unavailable")

    return Verdict(True)
```

---

# 7. Runtime 状态机

## 7.1 状态

```text
INIT
  -> OBSERVE
  -> COMMAND_READY
  -> PLAN
  -> VALIDATE
  -> EXECUTE_TARGET
  -> EXECUTE_SKILLS
  -> EXECUTE_NP
  -> EXECUTE_CARDS
  -> EXECUTE_ATTACK
  -> WAIT_RESULT
  -> OBSERVE

任意状态 -> STOPPED（安全停止）
任意状态 -> SUCCESS（胜利）
任意状态 -> FAILURE（失败/超时/不可恢复）
```

## 7.2 Runtime 伪代码

```python
# agent/battle/runtime/planner_runtime.py
class PlannerRuntime:
    def __init__(self, port, planner, validator, recorder, profile):
        self.port = port
        self.planner = planner
        self.validator = validator
        self.recorder = recorder
        self.profile = profile

    def run(self, battle_plan) -> "BattleResult":
        turns = 0

        while turns < self.profile.max_turns:
            observation = self.port.observe()
            state = observation.state
            self.recorder.observe(observation)

            if state.scene.name == "VICTORY":
                return BattleResult.success(turns)
            if state.scene.name in {"DEFEAT", "DIALOG", "UNKNOWN"}:
                return BattleResult.fail(f"unsafe_scene:{state.scene.value}")
            if state.scene.name != "COMMAND_SELECTION":
                continue

            plan = battle_plan.for_wave(state.wave)
            action = self.planner.plan(state, plan)
            verdict = self.validator.validate(action, state, self.profile)
            self.recorder.decision(state, action, verdict)
            if not verdict.ok:
                return BattleResult.fail(f"action_rejected:{verdict.reason}")

            result = self._execute_turn(action)
            if not result.ok:
                return BattleResult.fail(result.reason)
            turns += 1

        return BattleResult.fail("max_turns_exceeded")

    def _execute_turn(self, action):
        # 每一个 primitive action 后等待预期 UI 后置状态
        if action.target_enemy is not None:
            self.port.execute(PrimitiveAction(PrimitiveKind.SELECT_ENEMY, slot=action.target_enemy))
            if not self._confirm(ExpectedUiState.COMMAND_SELECTION):
                return StepResult.fail("enemy_target_not_confirmed")

        for skill in action.servant_skills:
            self.port.execute(PrimitiveAction(
                PrimitiveKind.SERVANT_SKILL,
                slot=skill.servant_slot,
                skill_index=skill.skill_index,
                target=skill.target_ally,
            ))
            if not self._confirm(ExpectedUiState.COMMAND_SELECTION):
                return StepResult.fail("skill_not_confirmed")

        for servant_slot in action.np_order:
            self.port.execute(PrimitiveAction(PrimitiveKind.SELECT_NP, slot=servant_slot))
            if not self._confirm(ExpectedUiState.COMMAND_SELECTION):
                return StepResult.fail("np_not_confirmed")

        for card_slot in action.card_order:
            self.port.execute(PrimitiveAction(PrimitiveKind.SELECT_CARD, slot=card_slot))
            if not self._confirm(ExpectedUiState.COMMAND_SELECTION):
                return StepResult.fail("card_not_confirmed")

        self.port.execute(PrimitiveAction(PrimitiveKind.ATTACK))
        if not self._confirm(ExpectedUiState.BATTLE_PROGRESS):
            return StepResult.fail("attack_not_confirmed")
        return StepResult.success()
```

实际实现中，`ExpectedUiState.COMMAND_SELECTION` 对“选卡后仍处于同一界面但选中计数变化”的确认需要带状态参数，例如：

```python
ExpectedUiState(scene=Scene.COMMAND_SELECTION, selected_cards=2)
```

---

# 8. MaaFramework 集成

## 8.1 新增 Custom Action

新增文件：`agent/custom/planner_action.py`

```python
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context

from backends.planner_backend import PlannerBackend


@AgentServer.custom_action("run_planner_battle")
class RunPlannerBattle(CustomAction):
    def run(self, context: Context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
        # 1. 从节点 attach 读取 backend/profile/plan/evidence 参数
        # 2. 创建 MaaControllerAdapter（LiveMaaBattlePort）
        # 3. 创建 PlannerBackend
        # 4. backend.run(request, context)
        # 5. 写入 focus / telemetry
        result = PlannerBackend().run_from_context(context)
        return CustomAction.RunResult(success=result.success)
```

## 8.2 Pipeline 节点

在 `assets/resource/base/pipeline/` 新增例如 `planner战斗.json`：

```jsonc
{
  "原生Planner战斗": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "run_planner_battle",
    "attach": {
      "backend": "planner",
      "battle_plan": "plans/demo_card_only.json",
      "strategy_profile": "farm-safe-v1",
      "max_turns": 20,
      "save_evidence": true,
      "fallback": "stop"
    },
    "next": ["战斗完成信息"],
    "on_error": ["保存Planner战斗证据并停止"]
  }
}
```

## 8.3 与原有调度接入

不要直接替换 `执行bbc战斗`。在 `通用战斗调度` 前增加后端分支，或在 UI task override 中设置：

```text
默认：执行bbc战斗 -> bbc战斗
实验：执行原生Planner战斗 -> 原生Planner战斗
影子：执行bbc战斗 + Planner 观测记录（不控制）
```

第一阶段可仅暴露开发者开关，避免普通用户误用实验功能。

---

# 9. LiveMaaBattlePort 实现细节

## 9.1 不让核心接触坐标

`LiveMaaBattlePort` 负责：

```text
PrimitiveAction.SELECT_CARD(slot=3)
  -> 根据锚点、内容区和当前分辨率得到第 3 张卡点击区域
  -> Controller.post_click(x, y).wait()
  -> 记录点击和截图证据
```

坐标来源顺序：

1. 基于稳定 UI 锚点识别内容区；
2. 将标准 16:9 战斗布局的归一化坐标映射到实际内容区；
3. 通过局部模板确认按钮/卡槽；
4. 不通过则拒绝点击。

禁止仅依赖绝对屏幕坐标。

## 9.2 标准化坐标

建立逻辑坐标系统：

```text
设计分辨率：1920 x 1080（横屏 16:9）
实际内容区：content_left, content_top, content_width, content_height
映射：x = left + nx * width, y = top + ny * height
```

例如：

```python
CARD_CENTER_NORM = {
    1: (0.142, 0.794),
    2: (0.322, 0.794),
    3: (0.500, 0.794),
    4: (0.678, 0.794),
    5: (0.858, 0.794),
}
```

这些数值必须经过截图集校准，不应直接写进 core。

## 9.3 观察稳定性

在关键动作前：

```text
连续截取 2~3 帧
  -> 比较关键 ROI（攻击区、指令卡区、弹窗区）
  -> 变化低于阈值并持续 N ms 才认定稳定
  -> 否则等待到 timeout
```

MaaFramework 的 `pre_wait_freezes` / `post_wait_freezes` 可用于 Pipeline 外层；Planner 内部还需对关键 ROI 做显式检查，便于记录和测试。

## 9.4 后置确认

| 原子动作 | 最小确认 |
|---|---|
| 选敌 | 敌方目标框/目标标识变化，或状态未变化时不重复点 |
| 放技能 | 目标选择面板出现/消失，技能 CD/视觉状态改变 |
| 选 NP | NP 被选择状态、攻击序列计数变化 |
| 选卡 | 对应卡高亮/被选遮罩、已选卡计数变化 |
| 攻击 | 选卡区离开、战斗动画/转场/下一场景出现 |

确认失败的处理必须是：**重新观测 -> 记录 -> 停止**，不是无限重击。

---

# 10. 感知（Perception）实施方案

## 10.1 先做固定 ROI

MVP 不训练全屏大模型。针对标准横屏 UI，定义：

| 观察项 | ROI | 初始算法 |
|---|---|---|
| 场景：选卡 | 攻击按钮/卡区 | 模板匹配 + 颜色特征 |
| 胜利/结算 | 结算关键模板 | 模板匹配 |
| 未知弹窗 | 中央对话框区域 | 模板集合 + OCR |
| 五张卡位置 | 固定五个卡 ROI | 固定区域 |
| 卡色 | 每卡颜色带/背景 ROI | HSV 分类 + 置信度 |
| 卡所属从者 | 每卡头像/边缘 ROI | 模板/轻量分类器；初期可由已知队伍限制 |
| NP 可用 | 三个 NP 区 | 模板/颜色状态 |
| 敌人目标 | 上方敌方槽位 | 固定槽位模板/颜色 |
| Wave/Turn | 顶部文字 ROI | OCR，后置阶段接入 |

## 10.2 识别结果必须保留证据

```python
@dataclass(frozen=True)
class DetectionEvidence:
    screenshot_id: str
    roi: tuple[int, int, int, int]
    method: str                  # template|ocr|hsv|model
    score: float
    debug_image_path: str | None
```

`BattleState` 的每个关键字段应可追到证据。便于处理“卡色错了”还是“Planner 选错了”。

## 10.3 卡归属的 MVP 降级策略

卡归属比卡色难。按以下顺序推进：

1. **MVP-0**：仅按卡色，`owner_slot=None`，禁用 Brave Chain 与从者优先级；
2. **MVP-1**：仅支持固定前排，通过预先采集的卡头像/边框模板识别；
3. **MVP-2**：轻量分类器识别归属；
4. **MVP-3**：结合战斗状态追踪、换人和动态卡池记忆。

这样不会因卡归属识别尚未完成而阻塞“动态选卡”最小闭环。

---

# 11. 测试方案（无 BBC 依赖）

## 11.1 单元测试：纯核心

执行环境：普通 Python、pytest；不导入 Maa、OpenCV、BBC。

覆盖：

- `CardPolicy` 下 60 种排列中选择预期卡序；
- Brave Chain、同色 Chain、首卡/末卡权重；
- 合法动作生成；
- Validator 对重复卡、不可用 NP、技能 CD、无效敌方目标的拒绝；
- 低置信度状态必须拒绝执行；
- Profile 禁止项不会被绕过。

示例：

```python
def test_finish_wave_prefers_buster_first_and_last():
    state = make_state(cards=[
        card(1, "A", 1), card(2, "B", 1), card(3, "Q", 2),
        card(4, "B", 2), card(5, "A", 3),
    ])
    policy = CardPolicy(
        goal=Goal.FINISH_WAVE,
        color_priority=(CardColor.BUSTER, CardColor.ARTS, CardColor.QUICK),
        servant_priority=(1, 2, 3),
    )
    selected = choose_cards(state, policy)
    assert selected[0] in (2, 4)
    assert selected[-1] in (2, 4)
```

## 11.2 组件测试：PlannerRuntime + FakeBattlePort

`FakeBattlePort` 是有限状态机：

```text
初始 COMMAND_SELECTION
SELECT_CARD(1) -> COMMAND_SELECTION(selected_cards=1)
SELECT_CARD(3) -> COMMAND_SELECTION(selected_cards=2)
SELECT_CARD(5) -> COMMAND_SELECTION(selected_cards=3)
ATTACK -> BATTLE_ANIMATION -> VICTORY
```

可验证：

- Runtime 是否按正确顺序执行；
- 每步是否调用确认；
- 发生不符合预期的状态迁移时是否停止；
- 最大回合数、超时与重试是否正确；
- 不会发出未定义原子动作。

## 11.3 视觉回归测试：静态截图

输入为版本化截图 fixture，输出为 `BattleState` 或局部检测结果。

```text
tests/fixtures/battle/screenshots/
  cn_bilibili_1920x1080/
    command_cards_001.png
    command_cards_002.png
    victory_001.png
    unknown_dialog_001.png
  jp_1920x1080/
    ...
```

对应标注：

```json
{
  "screenshot": "command_cards_001.png",
  "scene": "command_selection",
  "cards": [
    {"slot": 1, "color": "B", "owner": 1},
    {"slot": 2, "color": "A", "owner": 2}
  ]
}
```

CI 不要求连接模拟器；仅测试识别器输出是否仍满足标注与阈值。

## 11.4 回放测试：ReplayBattlePort

回放格式示例：

```json
{
  "metadata": {"server": "CN_BILIBILI", "ui_version": "..."},
  "frames": [
    {"id": "f001", "state": {"scene": "command_selection"}},
    {"id": "f002", "after": {"kind": "select_card", "slot": 2}, "state": {"selected_cards": 1}},
    {"id": "f003", "after": {"kind": "attack"}, "state": {"scene": "battle_animation"}},
    {"id": "f004", "state": {"scene": "victory"}}
  ]
}
```

测试目标：给定相同 `BattlePlan` 和回放输入，Planner 输出相同动作，并产生相同最终结果。

## 11.5 Maa 集成测试：少量、受控

仅在 Windows + 指定模拟器 + 指定 FGO 客户端版本运行：

- 验证 `LiveMaaBattlePort` 的内容区锚点；
- 验证点击映射和选卡确认；
- 验证 Pipeline Custom Action 入口；
- 不把此类测试作为日常 CI 的唯一通过条件。

## 11.6 BBC 回归测试：独立维护

BBC 后端可继续有自己的测试，但测试矩阵独立：

```text
pytest -m core           # 无 Maa、无 BBC
pytest -m replay         # 无 BBC
pytest -m vision         # 无 BBC、无设备
pytest -m maa_integration
pytest -m bbc_integration
```

---

# 12. 数据与模拟器的具体接入策略

## 12.1 不直接把 Chaldea 作为实时依赖

原生 Planner 运行中不能因为网络失败而无法决策。建议：

```text
上游数据 / Chaldea 导入
  -> update_battle_data.py
  -> 校验、转换、写入 MaaFgo 本地数据包
  -> runtime 只读本地 manifest + JSON/SQLite
```

## 12.2 TeamSnapshot

新增稳定的中间模型，隔离 Chaldea、BBC 配置和手动配置：

```python
@dataclass(frozen=True)
class TeamSnapshot:
    frontline_servants: tuple[int | None, int | None, int | None]
    backline_servants: tuple[int | None, int | None, int | None]
    craft_essences: tuple[int | None, ...]
    mystic_code_id: int | None
    skill_levels: dict[int, tuple[int, int, int]]
    np_levels: dict[int, int]
    source: str                    # manual|chaldea|bbc_import
    data_version: str
```

## 12.3 模拟器的渐进接口

```python
class BattleEstimator(Protocol):
    def estimate(self, state: BattleState, action: BattleAction, team: TeamSnapshot) -> "Estimate": ...
```

初始实现：`HeuristicEstimator`。  
后续实现：`FormulaEstimator`（参考 Laplace 的领域模型，但独立重实现/确认许可证）。

```python
@dataclass(frozen=True)
class Estimate:
    clear_probability: float | None
    expected_damage: float | None
    expected_np_gain: float | None
    certainty: float
    notes: tuple[str, ...]
```

估值不确定时返回 `None` 与低 certainty；Planner 应降低评分或停用依赖该估值的激进行动。

---

# 13. LLM 接入具体方案（后置）

## 13.1 接入位置

只允许在以下链路中出现：

```text
RuleEngine / Estimator
  -> 生成 3~10 个已通过 Validator 的候选
  -> LLM CandidateSelector（可选）
  -> 再次 Validator
  -> Executor
```

## 13.2 输入输出 Schema

输入：

```json
{
  "task": "select_best_candidate",
  "strategy": {
    "goal": "finish_wave",
    "min_clear_probability": 0.95,
    "forbidden": ["command_spell", "sq_revive"]
  },
  "state_summary": {
    "wave": 3,
    "enemy_count": 1,
    "enemy_hp_known": true,
    "np_ready_slots": [1, 3]
  },
  "candidates": [
    {"id": "c1", "clear_probability": 0.98, "cost": 0},
    {"id": "c2", "clear_probability": 0.96, "cost": 0}
  ]
}
```

输出：

```json
{"candidate_id":"c1","reason":"清场概率更高且无额外资源消耗。"}
```

必须校验：

- JSON 可解析；
- 候选 ID 在输入集合中；
- 不允许出现任何额外执行字段；
- 超时或失败使用规则第一名；
- 默认关闭、记录 provider/model/latency，不记录敏感截图。

---

# 14. 详细实施计划与交付物

## Sprint 1：骨架与测试基座（约 1–2 周）

**交付物**：

- `battle/core` 的模型、枚举、Policy、Validator；
- `BattlePort`、`FakeBattlePort`、`PlannerRuntime` 最小状态机；
- pytest marker 与目录；
- 20+ 纯核心单元测试；
- 不改动现有 BBC 默认路径。

**验收**：

```bash
pytest -m core
```

在没有 MaaFramework、模拟器、BBC 的环境中通过。

## Sprint 2：卡牌决策与回放（约 1–2 周）

**交付物**：

- `CardPolicy`、60 种排列枚举评分；
- `ReplayBattlePort`；
- 10+ 回放 fixture；
- Runtime 组件测试；
- NDJSON 事件记录器。

**验收**：

```bash
pytest -m replay
```

每个 fixture 中动作序列与最终状态符合预期。

## Sprint 3：视觉 MVP（约 2–3 周）

**交付物**：

- 场景、卡色、卡槽、胜利/未知弹窗识别；
- 静态截图黄金集与标注格式；
- 卡归属先支持 `None`，不阻塞卡色策略；
- `LiveMaaBattlePort.observe()` 原型。

**验收**：

```bash
pytest -m vision
```

在固定服/分辨率截图集上达到目标阈值。

## Sprint 4：Maa 集成与卡牌层实时执行（约 2–3 周）

**交付物**：

- `LiveMaaBattlePort.execute()`；
- 内容区锚点与归一化坐标；
- 选卡后置确认；
- `run_planner_battle` Custom Action；
- `planner战斗.json`；
- 固定测试关卡/队伍白名单。

**验收**：

- 不依赖 BBC；
- 在受控模拟器中完成“选三卡 -> 攻击 -> 识别胜利/下一回合”；
- 任一确认失败均停止并保存证据。

## Sprint 5：NP/技能与 TeamSnapshot（约 3–5 周）

**交付物**：

- NP 可用性识别与选择确认；
- 简单技能和目标选择；
- TeamSnapshot 与 Chaldea 导入适配；
- HeuristicEstimator；
- 白名单从者/关卡配置。

**验收**：

- 固定计划 + 动态选卡 + NP 的战斗闭环；
- 所有特殊动作有回放 fixture。

## Sprint 6：模拟器与 LLM 顾问（按需求）

**交付物**：

- 公式估值逐步实现；
- CandidateSelector；
- 模型安全 schema、超时和回退；
- 离线失败复盘工具。

---

# 15. 关键验收标准

在将 Planner 标记为可用前，至少满足：

- [ ] `battle/core` 不依赖 MaaFramework、BBC、OpenCV、设备；
- [ ] `pytest -m core` 与 `pytest -m replay` 可在无设备环境通过；
- [ ] Planner 的实时路径不导入或调用 `bbc_action` / `bbc_connection_manager`；
- [ ] Planner 运行时不能产生含原始坐标的策略动作；
- [ ] Validator 对非法卡槽、重复卡、不可用 NP、不可用技能和低置信度状态全部拒绝；
- [ ] 高风险动作不存在于 Planner 的 `PrimitiveKind`；
- [ ] 每一步原子点击有后置确认；
- [ ] 确认失败保存证据并停止；
- [ ] 已有 BBC 默认功能无回归；
- [ ] 视觉黄金集与回放集已版本化并进入 CI；
- [ ] 实验功能默认关闭，且 UI 标明适用服务器/分辨率/白名单范围。

---

# 16. 需要立即创建的 Issue

1. **`feat(battle): introduce pure battle core and domain models`**  
   建立 `BattleState`、`BattleAction`、`CardPolicy`、`StrategyProfile`、Validator。

2. **`test(battle): add FakeBattlePort and PlannerRuntime component tests`**  
   确保不依赖 BBC 的核心回合状态机可测。

3. **`feat(battle): add card-only deterministic planner`**  
   实现 60 卡序枚举、规则评分与单元测试。

4. **`feat(battle): add replay format and ReplayBattlePort`**  
   建立离线回放与事件证据标准。

5. **`feat(perception): command-selection and card-color detector MVP`**  
   固定分辨率/单服截图的场景与卡色检测。

6. **`feat(execution): MaaBattlePort with normalized anchors and confirmations`**  
   原子点击、后置确认和 fail-closed。

7. **`feat(pipeline): register run_planner_battle custom action`**  
   保持与 BBC 路径独立。

8. **`chore(data): define TeamSnapshot and local battle-data manifest`**  
   为 Chaldea/Atlas 数据输入建立本地数据边界。

---

# 参考资料

1. [MaaFgo](https://github.com/xlxyvergil/MaaFgo) —— 本方案的现有项目基线。  
2. [MaaFgo `bbc_action.py`](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/agent/custom/bbc_action.py) —— 现有外部 BBC 战斗后端，本文明确将其与原生 Planner 测试路径隔离。  
3. [MaaFgo `bbc_connection_manager.py`](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/agent/custom/bbc_connection_manager.py) —— BBC TCP/回调和进程相关实现。  
4. [MaaFramework Pipeline Protocol](https://maafw.com/en/docs/3.1-PipelineProtocol/) —— Pipeline、错误处理、等待与 Custom 扩展机制。  
5. [MaaFramework 快速开始（中文）](https://raw.githubusercontent.com/MaaXYZ/MaaFramework/refs/heads/main/docs/zh_cn/1.1-%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.md) —— Custom Action/Recognition 集成方法。  
6. [Chaldea / Laplace](https://github.com/chaldea-center/chaldea) —— 数据与战斗模拟设计参考；仓库许可证为 AGPL-3.0。  
7. [FGA](https://github.com/Fate-Grand-Automata/FGA) —— 战斗配置、卡牌优先级、动作 DSL 和用户体验参考；仓库许可证为 MIT。  
8. [FGA Battle Wiki](https://github.com/Fate-Grand-Automata/FGA/wiki/Battle) —— 技能、宝具、目标、换人、Wave 和卡牌优先级等动作维度。  
9. [FGO Combat Mechanics — GamePress](https://fgo.gamepress.gg/combat-mechanics) —— 指令卡、首卡、同色链、Brave/Mighty Chain、NP 等战斗机制参考。  
