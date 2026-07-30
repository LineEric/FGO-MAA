# MaaFgo 智能战斗可行性分析与整体项目框架设计

> **版本**：v1.0（调研设计稿）  
> **日期**：2026-07-30  
> **目标项目**：[MaaFgo](https://github.com/xlxyvergil/MaaFgo)  
> **调研对象**：[MaaFramework](https://github.com/MaaXYZ/MaaFramework)、[Chaldea / Laplace](https://github.com/chaldea-center/chaldea)、[Fate/Grand Automata（FGA）](https://github.com/Fate-Grand-Automata/FGA)、MaaFgo 当前实现  
> **定位**：为 MaaFgo 增加“回合级智能战斗”能力的可行性分析、架构蓝图与实施路线。  

---

## 执行摘要

### 结论

**在 MaaFgo 上实现回合级智能战斗具有较高可行性，但推荐采用“现有 BBC 稳定执行路径 + 新增受约束 Planner 后端”的渐进方案。**

MaaFgo 当前已经具备：

- MaaFramework Pipeline 驱动的登录、导航、选关、组队、结算等流程；
- Python Agent 的 Custom Action 扩展机制；
- BBchannel（BBC）战斗后端及 TCP/回调、弹窗、有限重试封装；
- Chaldea 队伍导入、从者/礼装名称与数据回退机制；
- 主线、活动、日常、冠位战等多类任务入口。

这意味着项目缺少的不是“自动点击能力”，而是战斗中间层：

```text
当前：关卡导航 -> BBC 执行完整战斗 -> 结果
目标：关卡导航 -> Battle Backend
                    ├─ BBC：固定、成熟、默认路径
                    └─ Planner：逐回合观测 -> 决策 -> 校验 -> 执行 -> 确认
```

### 关键建议

1. **不以 LLM 替换 BBC。** BBC 保持默认和稳定周回路径；Planner 面向白名单队伍/关卡、卡牌补偿、实验性高阶策略。
2. **不做“截图直接交给大模型，然后输出坐标”。** 先将画面解析为 `BattleState`，模型只可在本地生成的合法候选中选择。
3. **以 Chaldea/Laplace 为“数据与模拟”参考，以 FGA 为“战斗 DSL、优先级、助战选择与容错 UX”参考。**
4. **先 Shadow Mode，再离线回放，再受控实时执行。** 先证明观测和执行足够可靠，最后才启用 LLM。
5. **执行器必须 Fail-Closed。** 关键识别不确定、未知弹窗、高风险资源路径均默认停止。

---

# 1. 项目背景与目标

## 1.1 当前 MaaFgo 的能力边界

根据 MaaFgo README 与当前 `main` 分支代码，项目采用 MaaFramework，包含：

- 自动登录与游戏启动；
- 主线自由本、Ordeal Call、活动、迦勒底之门、冠位戴冠战等导航与刷取入口；
- 队伍配置、助战处理、苹果策略；
- Chaldea 队伍链接/数据导入；
- MWU/MXU 前端；
- 通过 BBC 处理战斗核心。

当前典型路径：

```text
MaaFramework Pipeline
  -> 回主界面 / 选队 / 章节导航
  -> bbc战斗 Pipeline 节点
  -> Python Custom Action: execute_bbc_task
  -> BBC TCP 命令 + 回调弹窗
  -> 战斗结束 / 重试 / 回到 MaaFgo 流程
```

`execute_bbc_task` 已负责读取队伍、次数、苹果、战斗类型等 `attach` 参数，连接 BBC、验证模拟器、接收回调、回写 GUI 信息并处理失败重启。这是一条可复用的稳定路径。

## 1.2 智能战斗的定义

本文的“智能战斗”不是泛指自动刷本，而是指：

> 在进入 FGO 战斗后，于每个可操作回合读取可观测游戏状态，并在用户策略约束下，选择和执行技能、目标、宝具、指令卡与顺序，同时对执行结果进行确认。

最低闭环：

```text
COMMAND_SELECTION
  -> 截图/识别
  -> BattleState
  -> 生成合法 BattleAction 候选
  -> 规则评分（LLM 可选）
  -> Validator
  -> 原子点击与确认
  -> 下一回合 / 结算 / 异常停止
```

## 1.3 分层目标

| 等级 | 能力 | 推荐优先级 |
|---|---|---:|
| L0 | 预设操作序列、BBC 既有周回 | 已有 / 默认 |
| L1 | 固定技能/宝具计划下的动态选卡、选目标 | 高 |
| L2 | 识别 NP、技能、敌方 HP，做规则化回合决策 | 高 |
| L3 | 伤害/NP/星估值，技能与 NP 组合搜索 | 中 |
| L4 | LLM 在有限候选中进行策略选择、解释、离线复盘 | 低 / 后置 |
| L5 | 全自动高难通关、自适应未知机制 | 远期，不作为 MVP 承诺 |

---

# 2. 外部项目调研与能力映射

## 2.1 MaaFramework：流程控制与设备交互底座

MaaFramework 提供 JSON Pipeline、图像识别、OCR、模板/特征匹配、控制器操作，以及 Custom Recognition/Custom Action 扩展。Pipeline 可使用 `next`、`on_error`、`timeout`、稳定帧等待和锚点等机制表达页面状态机。

对 MaaFgo 智能战斗的定位：

| MaaFramework 能力 | 在新架构中的职责 |
|---|---|
| Controller | 截图、点击、滑动及设备连接 |
| Pipeline | 战前导航、战斗入口、结算、异常页面和总调度 |
| OCR/模板/特征 | 场景、按钮、文本、固定 UI 的基础识别 |
| Custom Action | 回合循环、Planner、动作执行、事件记录 |
| Custom Recognition | 战斗页面/结果页/异常弹窗等高层状态识别 |
| `on_error` / timeout / freeze wait | 加载延迟、动画、识别失败与安全收敛 |

**结论**：MaaFramework 足以作为“战斗外粗粒度状态机 + 战斗内自定义逻辑”的运行环境，不需要为 Planner 另起一套设备自动化框架。

## 2.2 Chaldea / Laplace：战斗数据与模拟器参考

[Chaldea](https://github.com/chaldea-center/chaldea) 是跨平台 FGO 工具，包含 Chaldeas 规划器与 Laplace 战斗模拟器。其 README 声明 Laplace 支持任意关卡的友方战斗模拟、较新的关卡数据、可控随机数下的伤害/NP 计算，以及一定程度的自定义技能/敌方/场地 AI 效果。

### 可参考的功能方向

| Chaldea / Laplace 能力 | MaaFgo 可借鉴点 |
|---|---|
| 从者/礼装/魔术礼装/关卡数据 | 建立本地版本化战斗知识库 |
| 队伍与关卡配置 | 定义 `BattlePlan`、`StrategyProfile` 和数据版本绑定 |
| 伤害、NP、星模拟 | Planner 的估值器与清场概率估算 |
| 3T 组队与操作计划 | 预设策略生成、导入/导出与离线验证 |
| 自定义效果模拟 | 作为复杂关卡机制的长期扩展方向 |

### 许可证注意事项

Chaldea 仓库公开许可证为 **AGPL-3.0**。因此：

- **可以学习其公开接口、数据组织和算法思路**；
- 若复制、改编或链接其受 AGPL 覆盖的源代码并进行分发/网络交互，应由项目维护者评估 AGPL 义务；
- 更稳妥的工程路径是：使用可合法获取的公开数据源，按 MaaFgo 自己的 schema 重实现所需估值模块，或在明确授权下集成。

### 对 MaaFgo 当前代码的直接启发

MaaFgo 已有 `agent/chaldea/`：

- `chaldea_client.py`：按关卡/队伍获取与解析 Chaldea 数据；
- `chaldea_converter.py`：将外部队伍转换为项目可用配置；
- `game_data.py`：本地 JSON 缓存优先、Atlas Academy 网络回退。

因此可以将 Chaldea 导入从“配置 BBC 队伍”的能力扩展为：

```text
Chaldea Team / Quest
  -> MaaFgo TeamSnapshot
  -> 本地战斗数据查询
  -> BattlePlan / StrategyProfile
  -> Planner 的先验信息
```

但运行时的实际 NP、技能 CD、卡牌、敌人状态仍必须由屏幕观测决定。

## 2.3 FGA：战斗配置、动作语义与容错 UX 参考

[FGA](https://github.com/Fate-Grand-Automata/FGA) 是 Kotlin Android 自动战斗项目。其 README 指出使用 OpenCV 图像识别、Media Projection 截图和 Accessibility Service 交互。项目关注点是刷本自动化，而非剧情自动通关。

### 值得借鉴的功能

| FGA 功能 | MaaFgo 可借鉴的抽象 |
|---|---|
| Battle Config | 可持久化、可编辑、可分享的 `BattlePlan` |
| 技能命令解析 | 战斗 DSL 与语法校验 |
| 从者站位/技能/目标 | 结构化动作模型，而非原始坐标 |
| NP 顺序与卡前 NP | `BattleAction` 的可组合行动序列 |
| Wave/Turn 指示 | 分阶段计划和状态机同步 |
| 每 Wave 卡牌优先级 | `CardPolicy` 与快速规则决策 |
| 从者优先级、Brave Chain、卡序重排 | 启发式候选排序 |
| 助战职阶/偏好/回退 | 可靠的前置条件管理 |
| 特殊从者/变身技能选项 | 特例注册表，而不是通用逻辑污染 |

例如，FGA 的 UI 对技能命令调用 `AutoSkillCommand.parse()` 进行解析校验；其卡牌设置按 Wave 保存卡优先级、从者优先级、重排卡序和 Brave Chain 偏好。这说明成熟的自动战斗产品应把“策略表达”和“执行坐标”分开。

### 许可证注意事项

FGA 仓库标为 **MIT License**。可参考或在许可证要求下复用相应代码；但仍建议避免直接复制 Android 平台相关实现，因为 MaaFgo 的平台、语言和 MaaFramework 集成边界不同。优先复用其**功能模型和配置语义**。

## 2.4 BBC：保留为当前稳定后端

MaaFgo README 将 BBchannel 标记为战斗核心。已有 `BbcConnectionManager` 管理：

- TCP 命令端口 `25001`；
- 回调端口 `25002`；
- 消息队列、弹窗回调、就绪信号；
- 进程与连接生命周期。

**设计结论**：BBC 不是新 Planner 的竞争对象，而是 `BattleBackend` 的一个实现。新功能应做到可按任务/策略选择后端：

```text
backend = bbc       # 既有稳定路径
backend = planner   # 新的逐回合原生决策路径
backend = shadow    # BBC 执行，Planner 仅观测和记录
```

---

# 3. 可行性分析

## 3.1 技术可行性

| 子问题 | 可行性 | 依据与限制 |
|---|---:|---|
| 战前导航和战斗启动 | 高 | MaaFgo 已实现 Pipeline 与 Custom Action 链路 |
| 截图和点击 | 高 | MaaFramework Controller 已提供基础能力 |
| 战斗场景识别 | 高 | 攻击/结算等固定 UI 适合模板/特征识别 |
| 卡色识别 | 高 | 卡色明显，可从固定 ROI 与轻量分类开始 |
| NP/技能可用性识别 | 中高 | 固定 UI 可实现；需应对版本、特效和不同服差异 |
| 卡归属从者识别 | 中 | 需识别卡面边框/头像或利用状态追踪；是 MVP 难点 |
| 敌方 HP OCR | 中 | 数字识别可做，但动画/遮挡/格式差异需置信度和时序校验 |
| 规则化选卡与卡链优化 | 高 | 动作空间有限、规则明确 |
| 伤害/NP 高保真模拟 | 中 | 需要完整、持续更新的数据和复杂机制覆盖 |
| 实时 LLM 参与决策 | 中 | 技术可接入，但延迟、成本、稳定性与幻觉使其不适合作为基础依赖 |
| 高难本通用智能通关 | 低到中 | 机制差异、不可观测状态和数据维护成本高，应采用白名单推进 |

## 3.2 工程可行性

项目已使用 Python Agent，适合快速实现：

- `dataclass`/Pydantic 领域模型；
- 本地 JSON/SQLite 数据缓存；
- OpenCV/Numpy/Pillow 视觉辅助；
- 规则引擎、搜索与回放测试；
- 可选 HTTP LLM provider。

主要工程挑战不在语言，而在：

1. 多服/多 UI 版本的视觉资源维护；
2. 将动态战斗状态可靠地转化为结构化数据；
3. 建立高质量截图/回放集；
4. 在执行层严格确认并停止错误扩散；
5. 处理从者、关卡、敌方机制的持续更新。

## 3.3 产品可行性

最能体现价值的顺序：

1. **BBC 周回脚本的动态补刀和异常收敛**；
2. **固定队伍/固定关卡下的卡牌优化和回合状态可视化**；
3. **Chaldea 导入后的计划验证、战斗预估、策略生成**；
4. **白名单高难/特殊关卡的半自动回合辅助**；
5. LLM 的自然语言策略、解释和离线复盘。

不应将“全自动打任何高难”作为早期宣传点。

## 3.4 风险可控性

风险可通过架构控制：

- 使用 BBC 默认路径与 `shadow` 模式降低引入风险；
- 执行器硬禁区避免高价值资源误触；
- 低置信度不执行；
- 每步确认与回放证据使问题可定位；
- LLM 不拥有坐标/脚本/系统命令权限。

总体结论：**可控，但前提是坚持受约束架构和分阶段发布。**

---

# 4. 总体项目框架

## 4.1 架构总览

```text
┌────────────────────────────────────────────────────────────┐
│                         MaaFgo UI                            │
│  任务、关卡、队伍、助战、后端、策略、风险权限、调试与回放设置   │
└────────────────────────────┬───────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────┐
│                  MaaFramework Orchestrator                   │
│ Pipeline：登录、导航、选队、启动、结算、通用错误恢复           │
└────────────────────────────┬───────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────┐
│                    Battle Backend Router                     │
│  backend=bbc | planner | shadow                              │
└────────────────┬─────────────────────────────┬─────────────┘
                 │                             │
                 ▼                             ▼
┌────────────────────────┐          ┌────────────────────────┐
│ BbcBackend             │          │ PlannerBackend         │
│ 现有 BBC TCP/回调适配  │          │ 回合循环               │
└────────────────────────┘          └────────────┬───────────┘
                                                  ▼
                              ┌─────────────────────────────────┐
                              │ Perception                       │
                              │ screenshot -> BattleState        │
                              └────────────┬────────────────────┘
                                           ▼
                              ┌─────────────────────────────────┐
                              │ Planner / Decision               │
                              │ policy + legal candidates + eval │
                              │ rules/search + LLM optional      │
                              └────────────┬────────────────────┘
                                           ▼
                              ┌─────────────────────────────────┐
                              │ Validator / Safety Gate          │
                              │ schema + state + policy + risk   │
                              └────────────┬────────────────────┘
                                           ▼
                              ┌─────────────────────────────────┐
                              │ BattleExecutor                   │
                              │ atomic input + postcondition ack │
                              └────────────┬────────────────────┘
                                           ▼
                              ┌─────────────────────────────────┐
                              │ Telemetry / Replay               │
                              │ screenshot refs + states + events│
                              └─────────────────────────────────┘
```

## 4.2 模块边界

### A. Orchestrator（已有 MaaFramework Pipeline 为主体）

职责：

- 启动游戏、处理登录和公告；
- 进入目标关卡、选队、选助战；
- 把控制权交给对应战斗后端；
- 检测战斗完成、AP 弹窗、未知错误；
- 处理循环次数、结束和回主界面。

不负责：逐卡选择、伤害计算、LLM 调用。

### B. BattleBackend Router（新增）

职责：选择并统一调用战斗后端。

```python
class BattleBackend(Protocol):
    def run(self, request: "BattleRequest", context) -> "BattleResult": ...
```

实现：

```text
BbcBackend       适配当前 execute_bbc_task / ConnectionManager
PlannerBackend   逐回合原生决策与执行
ShadowBackend    BBC 实际执行，Planner 仅记录/推演
```

### C. Perception（新增）

职责：将截图变为结构化战斗状态和置信度。

输入：`ImageBuffer / Screenshot`  
输出：`BattleState` + `ObservationEvidence`

### D. Planner（新增）

职责：基于状态、静态知识、策略与候选，选出 `BattleAction`。

子模块：

```text
legal_actions   生成全部合法候选
rule_engine     快速确定性规则
simulator       伤害/NP/星估值（渐进实现）
search          剪枝与组合搜索
llm_selector    可选候选选择器
validator       独立合法性与策略校验
```

### E. Executor（新增）

职责：将抽象行动转换为受限原子操作，每一步确认后再进入下一步。

### F. Data & Knowledge（新增/扩展）

职责：版本化从者、礼装、魔术礼装、关卡和策略数据；与 Chaldea/Atlas 数据输入解耦。

### G. Telemetry & Replay（新增）

职责：记录每次观测、候选、决策、点击和确认结果，构建离线回放与回归测试能力。

---

# 5. 关键领域模型

## 5.1 BattleRequest

用于把 UI/Pipeline 参数统一传入后端：

```json
{
  "quest_id": 0,
  "server": "CN_BILIBILI",
  "team_source": "chaldea|manual|bbc",
  "team_snapshot_id": "...",
  "run_count": 3,
  "backend": "planner",
  "strategy_profile": "farm-safe-v1",
  "fallback_backend": "stop",
  "debug": {
    "shadow": false,
    "save_evidence": true
  }
}
```

## 5.2 BattleState

```json
{
  "schema_version": 1,
  "screen": "COMMAND_SELECTION",
  "wave": 2,
  "turn": 3,
  "confidence": 0.97,
  "enemies": [
    {"slot": 1, "class": "LANCER", "hp": 18432, "alive": true, "targeted": true}
  ],
  "frontline": [
    {
      "slot": 1,
      "servant_id": 0,
      "np": 100,
      "np_ready": true,
      "skills": [
        {"index": 1, "available": true, "target_type": "SELF"},
        {"index": 2, "available": false, "cooldown": 4}
      ]
    }
  ],
  "command_cards": [
    {"ui_slot": 1, "owner_slot": 1, "color": "B", "critical": 0.0}
  ],
  "uncertainties": []
}
```

必须支持：

- 字段级置信度或未知原因；
- 截图与 ROI 证据引用；
- 版本字段；
- 不可观测状态的显式表达。

## 5.3 BattleAction

```json
{
  "target_enemy": 1,
  "servant_skills": [
    {"servant_slot": 1, "skill_index": 3, "target_ally": 1}
  ],
  "master_skills": [],
  "order_change": null,
  "np_order": [1],
  "card_order": [1, 3, 5],
  "expected": {
    "clear_probability": 0.96,
    "damage": 210000,
    "np_gain": 15,
    "risk": 0.02
  }
}
```

`BattleAction` 永远不包含：

- 绝对屏幕坐标；
- 任意 Python/Shell/Pipeline 文本；
- 禁止资源的操作命令；
- 未经过候选生成器定义的新动作类型。

## 5.4 StrategyProfile

```json
{
  "id": "farm-safe-v1",
  "mode": "FARM",
  "objective": "CLEAR_FAST",
  "min_clear_probability": 0.95,
  "allow_command_spell": false,
  "allow_sq_revive": false,
  "allow_ap_refill": false,
  "llm_mode": "OFF",
  "fallback": "STOP"
}
```

## 5.5 CardPolicy（吸收 FGA 的可配置经验）

```json
{
  "wave": 3,
  "goal": "FINISH_WAVE",
  "card_color_priority": ["B", "A", "Q"],
  "servant_priority": [1, 3, 2],
  "prefer_brave_chain": true,
  "rearrange_cards": true,
  "allow_mighty_chain": true
}
```

它可作为：

- 用户显式配置；
- L1 规则引擎的默认策略；
- LLM 的不可修改约束输入；
- FGA/BBC 风格固定周回计划的兼容层。

---

# 6. 回合战斗的执行闭环

## 6.1 主循环

```text
进入战斗
  ↓
等待 / 识别当前场景
  ├─ COMMAND_SELECTION -> 回合规划
  ├─ BATTLE_ANIMATION  -> 等待稳定
  ├─ WAVE_TRANSITION   -> 等待下一回合
  ├─ VICTORY           -> 返回 Orchestrator
  ├─ DEFEAT            -> 停止或由外层策略处理
  └─ UNKNOWN           -> 保存证据并停止
```

`COMMAND_SELECTION` 分支：

```text
截图
  -> Perception 生成 BattleState
  -> 关键字段置信度检查
  -> 生成合法候选
  -> 规则评分 / 可选模拟
  -> 可选 LLM 在候选中选择
  -> Validator
  -> Executor 原子执行
  -> 每一步确认 UI 后置条件
  -> 回到场景识别
```

## 6.2 执行器原子操作

```python
class BattleExecutor:
    def select_enemy(self, slot: int) -> bool: ...
    def cast_servant_skill(self, servant_slot: int, skill_index: int, target: int | None) -> bool: ...
    def cast_master_skill(self, skill_index: int, target: int | None) -> bool: ...
    def order_change(self, out_slot: int, in_slot: int) -> bool: ...
    def select_np(self, servant_slot: int) -> bool: ...
    def select_card(self, ui_slot: int) -> bool: ...
    def attack(self) -> bool: ...
```

示例确认逻辑：

```text
施放技能
  -> 识别目标选择面板是否出现
  -> 若需要，选择目标
  -> 识别面板消失、图标状态变化或效果出现
  -> 若失败，有限重试；仍失败则停止

选择指令卡
  -> 识别卡片选中状态/计数变化
  -> 未变化时重新观测，不盲目重复点击

点击攻击
  -> 识别选卡页退出、攻击动画或下一状态
  -> 超时后保存完整证据并停止
```

## 6.3 安全策略：Fail-Closed

以下情形禁止继续执行：

- 当前场景不是预期战斗场景；
- 关键识别字段低于阈值；
- 出现未被白名单识别的弹窗；
- 计划动作与当前状态不一致；
- 操作后未出现预期后置状态；
- 已超过每回合/每战斗最大重试次数；
- 命中禁止资源区域或疑似高风险页面。

高风险功能必须在 Executor 层硬禁：

- 令咒；
- 圣晶石复活；
- 圣晶石或付费货币消费；
- 抽卡；
- 账号登录、授权、绑定；
- 未确认的 AP 补充操作。

已有“苹果策略”可继续由 MaaFgo 外层 Pipeline 显式控制；战斗 Planner 不拥有自主消费资源权限。

---

# 7. 规则引擎、模拟器与 LLM 的职责划分

## 7.1 L1 规则引擎：必须优先实现

输入：`BattleState + TeamSnapshot + QuestProfile + StrategyProfile`  
输出：按得分排序的候选 `BattleAction`。

基本候选生成：

1. 枚举存活敌人目标；
2. 枚举可用技能与可选目标（设置上限与剪枝）；
3. 枚举可用 NP 子集及顺序；
4. 枚举三张指令卡及排列；
5. 过滤不合法、违反资源策略、低置信度依赖的动作；
6. 按清场、伤害、NP、星、资源和风险进行评分。

简化评分：

\[
Score(a)=w_k P(\text{clear}|a)+w_dE(\text{damage})+w_nE(\text{NP gain})+w_sE(\text{stars})-w_rRisk(a)-w_cCost(a)
\]

MVP 可不追求完整伤害模拟，优先采用：

- 已知 NP 可稳定清场的静态判定；
- 卡色、首卡、同色链、Brave Chain 启发式；
- 职阶克制和可用 Buff 的粗粒度估值；
- 不确定时保守选择或停止。

## 7.2 L2 模拟器：参考 Laplace，按需渐进

目标不是立即复刻 Laplace，而是逐项扩展：

| 阶段 | 模拟能力 |
|---|---|
| S1 | 卡色、首卡、卡序、Brave/Mighty Chain 估值 |
| S2 | 职阶克制、基础 ATK、宝具倍率、常规 Buff |
| S3 | NP 回收、掉星、暴击、Overcharge |
| S4 | 敌方特性、场地、特殊机制、随机分布 |

每项公式必须：

- 有数据来源与版本；
- 有单元测试和已知样例；
- 在不支持时明确返回“不确定”，而不是伪造精确数字。

## 7.3 LLM：只做受限顾问

LLM 可做：

- 自然语言策略 -> 待审核 `StrategyProfile`；
- 在候选集合中选择；
- 为决策提供自然语言解释；
- 离线回放失败分析；
- 从关卡描述生成不可直接执行的策略草案。

LLM 不可做：

- 输出点击坐标；
- 直接调用 MaaFramework Controller；
- 自由生成并执行 Python、Shell 或 Pipeline；
- 编造从者/敌人/技能数据；
- 覆盖本地安全策略。

推荐协议：

```json
{
  "state": {"...": "已脱敏的 BattleState 摘要"},
  "constraints": {"forbidden": ["COMMAND_SPELL", "SQ_REVIVE"]},
  "candidates": [
    {"id": "A", "estimated": {"clear_probability": 0.96}},
    {"id": "B", "estimated": {"clear_probability": 0.93}}
  ]
}
```

模型只能返回：

```json
{"candidate_id": "A", "reason": "满足清场概率门槛且资源消耗更低。"}
```

响应必须经过 Schema、候选归属、策略和状态合法性验证。超时/失败即退回规则引擎或停止。

---

# 8. 数据架构

## 8.1 本地知识库优先

建议建立 `agent/battle/data/`，避免 Planner 运行时依赖网络：

```text
agent/battle/data/
├── manifest.json                 # 数据版本、来源、hash、服务器
├── servants.json                 # 职阶、卡组、宝具、技能元数据
├── craft_essences.json
├── mystic_codes.json
├── quests.json                   # 关卡、Wave、敌方基础数据
├── traits.json
├── special_rules.json            # 白名单特殊机制
└── profiles/
    ├── farm-safe-v1.json
    └── quest-*.json
```

## 8.2 数据来源与更新

建议将“来源”与“运行时依赖”分开：

```text
上游公开数据 / 已授权数据
  -> MaaFgo update-data 工具
  -> schema 校验 / 版本化 / hash
  -> 本地资源包
  -> Planner 离线读取
```

这样可避免上游服务临时不可用影响战斗执行。

## 8.3 Chaldea 接口的位置

Chaldea API/导入是可选输入：

```text
Chaldea 分享链接 / team id / quest id
  -> ChaldeaClient
  -> TeamSnapshot
  -> 对应本地数据和策略
```

它不应成为实时战斗判断的唯一来源。

---

# 9. 建议代码结构

```text
agent/
├── main.py
├── custom/
│   ├── bbc_action.py                 # 既有兼容入口，逐步瘦身
│   ├── planner_action.py             # run_planner_battle
│   └── general_navigation_action.py
├── backends/
│   ├── base.py                       # BattleBackend protocol
│   ├── router.py
│   ├── bbc_backend.py
│   ├── planner_backend.py
│   └── shadow_backend.py
├── battle/
│   ├── models.py                     # BattleState/Action/Request/Result
│   ├── profiles.py
│   ├── errors.py
│   ├── perception/
│   │   ├── scene.py
│   │   ├── cards.py
│   │   ├── enemy.py
│   │   ├── skills.py
│   │   ├── np.py
│   │   ├── ocr.py
│   │   └── confidence.py
│   ├── planning/
│   │   ├── legal_actions.py
│   │   ├── card_policy.py
│   │   ├── rule_engine.py
│   │   ├── evaluator.py
│   │   ├── simulator.py
│   │   ├── validator.py
│   │   └── llm_selector.py
│   ├── execution/
│   │   ├── executor.py
│   │   ├── anchors.py
│   │   ├── confirmations.py
│   │   └── safety.py
│   ├── data/
│   │   ├── repository.py
│   │   ├── manifest.json
│   │   └── profiles/
│   └── telemetry/
│       ├── events.py
│       ├── evidence.py
│       ├── replay.py
│       └── metrics.py
├── chaldea/                           # 既有模块，提供 TeamSnapshot 输入
└── utils/

tests/
├── battle/
│   ├── fixtures/
│   │   ├── screenshots/
│   │   ├── observations/
│   │   ├── replays/
│   │   └── expected_actions/
│   ├── test_perception.py
│   ├── test_legal_actions.py
│   ├── test_rule_engine.py
│   ├── test_validator.py
│   ├── test_executor_confirmation.py
│   └── test_replay.py
```

---

# 10. 配置与 UI 设计

## 10.1 后端选择

默认应保持：

```json
{"battle_backend": "bbc"}
```

开发者/实验设置：

```json
{
  "battle_backend": "planner",
  "strategy_profile": "farm-safe-v1",
  "planner_mode": "shadow|observe|execute",
  "llm_mode": "off|candidate_selector",
  "save_evidence": true
}
```

## 10.2 用户可见策略层级

建议避免让普通用户直接配置复杂伤害公式。提供三层：

| 层级 | 示例 | 目标用户 |
|---|---|---|
| 简单模式 | “快速清场 / 稳妥清场 / 回收 NP / 保留宝具” | 普通用户 |
| 高级策略 | 每 Wave NP、技能、卡优先级、助战回退 | 熟练用户 |
| 开发者模式 | 数据版本、置信度阈值、回放、Planner 模式、LLM | 维护者/测试者 |

## 10.3 策略预览

在真正执行前显示可审计计划：

```text
第 1 面：预计使用 1号宝具；若未清场，优先 Buster Chain
第 2 面：保留御主技能；优先 Arts 回收
第 3 面：使用 1号技能3 -> 目标1；双宝具；最低清场置信度 95%
```

这比只显示一串脚本更容易让用户发现配置错误。

---

# 11. 测试、回放与可观测性

## 11.1 事件日志

建议每个 Planner Session 输出本地 NDJSON：

```json
{"type":"state_observed","session_id":"...","screen":"COMMAND_SELECTION","confidence":0.97,"screenshot_id":"..."}
{"type":"candidates_generated","count":12,"state_hash":"..."}
{"type":"action_selected","planner":"rules-v1","action_id":"...","score":0.91}
{"type":"primitive_confirmed","primitive":"select_card","slot":2,"before":"...","after":"..."}
```

截图默认仅本地保留；上传或导出必须由用户主动选择。

## 11.2 回放体系

| 集合 | 内容 | 用途 |
|---|---|---|
| 视觉黄金集 | 截图 + 标注状态 | 验证识别准确率 |
| 决策黄金集 | BattleState + 期望候选/动作 | 规则回归 |
| 交互回放集 | 截图序列 + 操作 + 后置状态 | 执行器和异常恢复 |
| 失败案例库 | 低置信度、弹窗、加载慢、UI 改版 | Fail-Closed 验证 |

## 11.3 建议质量门槛

| 指标 | MVP 执行前门槛 |
|---|---:|
| 关键战斗场景识别准确率 | ≥ 99% |
| 卡色识别准确率 | ≥ 99% |
| 关键动作后置确认成功率 | ≥ 99.5% |
| 非法 Action 通过 Validator 的次数 | 0 |
| 高风险动作误触发 | 0 |
| 关键低置信度状态仍执行的次数 | 0 |
| 同版本回放可复现率 | ≥ 99% |

---

# 12. 分阶段实施路线

## Phase 0：设计与基础设施

- 定义 `BattleBackend`、`BattleRequest`、`BattleResult`；
- 建立错误码、事件 schema、截图证据目录；
- 给现有 BBC 路径增加结构化结果包装；
- 增加 `backend=bbc|shadow|planner` 配置，默认 BBC。

**验收**：现有 BBC 流程无行为回归。

## Phase 1：Shadow Perception

- BBC 正常执行，Planner 只截图和解析；
- 识别战斗场景、Wave/Turn、NP、卡色；
- 初期只针对固定分辨率、单服和少数队伍；
- 建立截图黄金集与标注工具。

**验收**：核心观测字段达到设定准确率，且低置信度正确暴露。

## Phase 2：离线决策

- 实现 `BattleState`、`BattleAction`、`StrategyProfile`；
- 合法动作生成、卡链规则、卡优先级和 Validator；
- 对录制状态做回放、输出建议，不点击；
- 与 BBC 既有脚本进行差异分析。

**验收**：非法动作率为零，规则输出可解释、可复现。

## Phase 3：实时卡牌层执行

- 固定关卡、固定队伍、固定技能/NP 计划；
- Planner 仅处理选敌和三张卡；
- 原子操作 + 后置确认 + 出错停止；
- 禁用一切高风险资源。

**验收**：在受控条件下连续运行通过，并满足误触发为零。

## Phase 4：技能、NP 与估值器

- 接入队伍静态数据；
- 支持技能目标、NP 顺序、基础伤害估值；
- 支持更多白名单从者和简单换人；
- 按需引入 NP 回收、暴击星和特殊机制。

**验收**：明确白名单范围内可以稳定完成预定回合计划。

## Phase 5：LLM 顾问模式

- 仅启用候选选择、策略解释、离线复盘；
- Provider 抽象、超时、速率限制、日志脱敏；
- 模型异常时自动退回 L1 或停止；
- 默认关闭，标记实验性。

**验收**：没有任何模型输出能绕过 Validator 或扩大执行权限。

---

# 13. 风险与缓解措施

| 风险 | 后果 | 缓解措施 |
|---|---|---|
| UI/服务器/版本变化 | 模板、OCR、坐标失效 | 多资源包、版本矩阵、黄金集、白名单 |
| 模拟器显示差异 | 识别偏差、点击偏移 | 锚点校准、内容区归一化、推荐配置 |
| 动画和网络延迟 | 连点、状态错乱 | 稳定帧、后置确认、超时、有限重试 |
| 卡归属/HP 误识别 | 错误战术决策 | 字段置信度、二次观测、保守策略 |
| 复杂敌方机制 | 模拟偏差 | 机制 Profile、白名单、明确不支持状态 |
| LLM 幻觉/超时 | 非法或不一致建议 | 候选选择模式、Schema、Validator、规则回退 |
| 上游数据不可用 | 配置/模拟失败 | 本地缓存优先、更新工具与 manifest |
| 端口/进程竞争 | BBC/Agent 互相影响 | 单实例锁、端口配置化、明确进程所有权 |
| 高价值资源误触 | 用户损失 | Executor 硬禁区、未知弹窗即停 |
| 开源许可证不兼容 | 分发风险 | 记录来源；Chaldea 代码不直接混入，必要时寻求授权 |
| 账号/条款风险 | 用户与项目风险 | 不实现规避/对抗功能；明确风险边界 |

---

# 14. 近期 Milestone 与 Issue 建议

## M1：`battle-backend-abstraction`

- [ ] `BattleBackend` Protocol
- [ ] `BattleRequest` / `BattleResult` / ErrorCode
- [ ] `BbcBackend` 适配现有 `ExecuteBbcTask`
- [ ] Backend Router
- [ ] 不改变现有 UI 默认行为

## M2：`battle-shadow-perception`

- [ ] `BattleState` schema
- [ ] Scene detector：战斗/选卡/结算/未知
- [ ] 卡色、NP、Wave/Turn 基础识别
- [ ] 置信度与证据引用
- [ ] 截图保存、标注和指标脚本

## M3：`battle-offline-planner`

- [ ] `BattleAction` schema
- [ ] `CardPolicy`
- [ ] 合法候选生成器
- [ ] 规则评分器
- [ ] Validator
- [ ] 回放 Runner

## M4：`battle-live-card-executor`

- [ ] 原子 Executor
- [ ] 选卡/攻击后的后置确认
- [ ] Fail-Closed 状态机
- [ ] 固定关卡白名单
- [ ] 长时间稳定性测试

## M5：`battle-simulation-data`

- [ ] 本地数据 manifest
- [ ] TeamSnapshot/Chaldea 导入对接
- [ ] 基础伤害与 NP 估值
- [ ] 数据更新和回归测试

## M6：`battle-llm-advisory`

- [ ] Provider interface
- [ ] 候选选择 schema
- [ ] 超时/限流/缓存/脱敏
- [ ] 审计日志
- [ ] 默认关闭的实验配置

---

# 15. 最终建议

MaaFgo 最合理的演进不是做一个“让 LLM 盲点屏幕”的工具，而是建设一套可验证的战斗系统：

```text
MaaFgo：导航与运行编排
MaaFramework：截图、识别、控制与状态机底座
BBC：当前稳定周回执行后端
Chaldea/Laplace：数据结构、模拟与计划能力参考
FGA：战斗 DSL、优先级、助战和容错产品设计参考
Planner：结构化观测、规则决策、模拟估值、受限 LLM
Executor：唯一能点击、且带硬性安全限制的组件
```

推荐投入顺序：

1. **后端抽象与 Shadow Mode**；
2. **BattleState + 视觉黄金集**；
3. **离线规则决策与回放**；
4. **受控卡牌层实时执行**；
5. **技能/NP/估值器**；
6. **最后才是 LLM 顾问。**

这样可以在不破坏 MaaFgo 现有稳定能力的前提下，逐步获得“进入回合后真正理解局面、做出决策并可靠执行”的能力。

---

# 参考资料

1. [MaaFgo](https://github.com/xlxyvergil/MaaFgo) —— 项目基线、README、Pipeline、Python Agent 与 BBC 集成实现。  
2. [MaaFgo README](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/README.md) —— 功能范围、技术栈、BBC/MWU/MXU 集成说明。  
3. [MaaFgo `bbc_action.py`](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/agent/custom/bbc_action.py) —— 现有 BBC 战斗任务、重试、GUI 回写实现。  
4. [MaaFgo `bbc_connection_manager.py`](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/agent/custom/bbc_connection_manager.py) —— BBC TCP/回调、端口与消息管理。  
5. [MaaFramework Pipeline Protocol](https://maafw.com/en/docs/3.1-PipelineProtocol/) —— Pipeline 的识别、动作、超时、错误处理与扩展机制。  
6. [MaaFramework 快速开始（中文）](https://raw.githubusercontent.com/MaaXYZ/MaaFramework/refs/heads/main/docs/zh_cn/1.1-%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.md) —— JSON 与 Custom Action/Recognition 的推荐集成方案。  
7. [Chaldea / Laplace](https://github.com/chaldea-center/chaldea) —— FGO 数据规划与战斗模拟器能力说明，许可证为 AGPL-3.0。  
8. [FGA](https://github.com/Fate-Grand-Automata/FGA) —— Android FGO 自动战斗项目，MIT License。  
9. [FGA Battle Wiki](https://github.com/Fate-Grand-Automata/FGA/wiki/Battle) —— 技能、目标、宝具、换人、卡优先级与助战配置的功能参考。  
10. [FGA `SkillCommandGroup.kt`](https://raw.githubusercontent.com/Fate-Grand-Automata/FGA/master/app/src/main/java/io/github/fate_grand_automata/ui/battle_config_item/SkillCommandGroup.kt) —— 战斗命令解析和配置校验的 UI/模型参考。  
11. [FGA `CardPriorityViewModel.kt`](https://raw.githubusercontent.com/Fate-Grand-Automata/FGA/master/app/src/main/java/io/github/fate_grand_automata/ui/card_priority/CardPriorityViewModel.kt) —— 分 Wave 卡优先级、从者优先级、重排与 Brave Chain 配置参考。  
12. [FGO Combat Mechanics — GamePress](https://fgo.gamepress.gg/combat-mechanics) —— 卡色、首卡、同色链、Brave/Mighty Chain、宝具与基础战斗机制。  
