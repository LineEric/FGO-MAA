# MaaFgo 大模型辅助战斗逻辑调研与实施建议

> **文档状态**：调研初稿  
> **调研日期**：2026-07-30  
> **目标仓库**：[xlxyvergil/MaaFgo](https://github.com/xlxyvergil/MaaFgo)（以下称 MaaFgo）  
> **适用范围**：项目内部技术设计、原型验证与离线回放测试。上线前应由项目维护者自行评估目标游戏的服务条款、账号风险及适用法律。

---

## 摘要

MaaFgo 已具备较完整的“战前导航 + 编队/助战配置 + 外部战斗核心执行 + 结算”自动化链路：以 MaaFramework Pipeline 承担页面流程，以 Python Agent 承担自定义动作，以 BBchannel（BBC）承担战斗执行，并已接入 Chaldea 队伍数据导入。

因此，“大模型自动战斗”的合理演进方向**不是**让多模态模型直接看截图并输出任意点击坐标，也不应在短期内替换已经可用的 BBC 周回执行路径；而是新增一个可选的、受约束的 **战术决策层（Tactical Planner）**：

```text
MaaFramework / MaaFgo Pipeline
  └─ 导航、启动关卡、状态切换、错误恢复
       └─ 战斗后端抽象（BBC / MaaFgo 原生 Planner）
            ├─ 视觉观测：Screenshot -> BattleState
            ├─ 规则/搜索：BattleState -> CandidateActions
            ├─ LLM（可选）：CandidateActions -> 选择或策略建议
            ├─ Validator：安全、合法性、置信度、资源约束
            └─ Executor：结构化动作 -> 可验证点击序列
```

核心原则：

1. **LLM 不直接控制坐标、不直接生成可执行脚本。**
2. **本地规则、从者/关卡数据与动作校验器是事实源；LLM 只在有限候选中参与策略选择、离线规划或失败复盘。**
3. **BBC 作为当前稳定战斗后端保留；新 Planner 通过统一接口接入，支持灰度、回退和 A/B 回放比较。**
4. **未知或低置信度视觉状态默认停止/请求人工确认，而非继续点击。**
5. **高风险动作（令咒、圣晶石复活、苹果/石头消耗、抽卡、账号相关确认）必须有硬策略边界。**

---

## 1. 调研范围与问题定义

### 1.1 目标

为 MaaFgo 设计一条可渐进落地的“智能战斗逻辑”路线，使项目可在现有 BBC 战斗能力之外，逐步支持：

- 对当前战斗画面进行结构化观察；
- 根据关卡目标、队伍资源和卡牌状态选择技能、目标、宝具和指令卡；
- 为固定周回提供确定性、可复现的决策；
- 为未知关卡、卡牌补刀或复杂策略提供可选 LLM 辅助；
- 完整记录决策依据、视觉证据、执行结果，以支持离线测试与问题复盘。

### 1.2 非目标

本阶段不建议将以下事项作为目标：

- 让模型从原始截图端到端自由生成坐标点击；
- 依赖模型记忆判断从者技能、宝具效果、敌方机制或伤害数值；
- 绕过目标软件的限制、风控、反作弊或服务条款；
- 在没有回放集、状态确认与硬性安全策略的前提下，直接进入无人值守执行。

---

## 2. MaaFgo 现状调研

### 2.1 仓库概况

截至本次调研，MaaFgo 为公开 MIT 许可证项目，默认分支为 `main`；仓库以 Python 为主。README 将其定位为基于 MaaFramework 的 FGO 图像识别与模拟控制工具，并列出自动登录、主线/活动/迦勒底之门/冠位战导航、队伍配置、苹果补充、Chaldea 联动及多模拟器连接等能力。

> 注：仓库状态和统计数据会持续变动，本文以调研时的 `main` 分支内容为准，不将 Star、Issue 等动态指标作为设计依据。

### 2.2 当前架构（基于仓库代码）

```text
Web / GUI（MWU / MXU）
  │ 通过 interface/options 配置任务
  ▼
MaaFramework Tasker + Pipeline
  │
  ├─ assets/resource/base/pipeline
  │    ├─ 章节、地图、活动、队伍选择、回主界面
  │    └─ 通用战斗调度 -> bbc战斗
  │
  ▼
Python Agent（agent/main.py）
  ├─ custom/general_navigation_action.py 等导航扩展
  ├─ custom/bbc_start.py / bbc_stop.py
  ├─ custom/bbc_action.py
  ├─ custom/bbc_connection_manager.py
  ├─ chaldea/*（Chaldea API、配置转换、游戏数据）
  └─ mission_solver/*
  │
  ▼
BBchannel（外部战斗核心）
  ├─ TCP 命令通道：127.0.0.1:25001
  └─ 回调监听：127.0.0.1:25002
  │
  ▼
模拟器 / 游戏客户端
```

### 2.3 现有战斗路径

`assets/resource/base/pipeline/日常战斗.json` 定义了一个通用调度链：回主界面、队伍选择、章节导航、BBC 战斗、战斗结束。`bbc战斗.json` 中的 `执行BBC任务` 是 MaaFramework `Custom` Action，携带队伍配置、次数、苹果类型、战斗类型、助战排序异常和队伍错误处理等参数。

`agent/custom/bbc_action.py` 的 `ExecuteBbcTask` 已实现：

- 从节点 `attach` 读取 BBC 队伍配置和运行参数；
- 确保 BBC 进程/TCP 链路可用；
- 验证模拟器连接；
- 启动战斗；
- 接收 BBC 弹窗回调并回写 GUI 信息；
- 错误时重启 BBC 后有限重试；
- 通过 `context.override_pipeline` 更新界面提示。

`BbcConnectionManager` 负责 TCP 消息收发、回调端口监听、队列、连接状态及进程相关管理。这说明 MaaFgo 已经有一个明确的“战斗后端边界”，是引入新 Planner 的最佳切入点。

### 2.4 已有数据与扩展基础

| 资产 | 现状 | 对 Planner 的价值 |
|---|---|---|
| Pipeline 与图片资源 | `assets/resource/*` | 场景识别、导航、异常处理、统一调度 |
| BBC 队伍配置 | `assets/bbc_team_config.json` 等 | 固定周回策略与现有执行器兼容 |
| Chaldea 导入 | `agent/chaldea/*` | 获得队伍、从者、礼装、魔术礼装、操作序列等结构化输入的入口 |
| 本地从者/礼装名称缓存 | `agent/utils/Chaldea/*.json` | 扩展为本地静态游戏知识库的落点 |
| Atlas Academy 回退 | `game_data.py` | 数据更新工具与多源 fallback 的已有模式 |
| `mission_solver` | `agent/mission_solver/*` | 现有“结构化数据 + 求解器”范式参考 |
| Maa Agent Custom Action | 已大量使用 | 可承载 Planner、视觉与执行逻辑 |

### 2.5 当前架构的约束与机会

**机会**：

- Pipeline 已经把战前流程和战斗入口抽象清楚；
- BBC 通信与异常重试已被封装，不必重写稳定部分；
- Chaldea 导入已可提供部分队伍上下文；
- Python Agent 适合快速开发状态模型、规则、测试工具和 LLM adapter。

**约束**：

- 目前战斗细粒度控制主要委托给 BBC，MaaFgo 自身没有面向“每回合状态—动作”的统一领域模型；
- BBC 的弹窗/完成状态不是完整的战斗遥测，无法直接用于智能策略学习；
- 现有 `BbcConnectionManager._cleanup_port()` 会按端口终止进程；若未来并行多实例或引入独立战斗服务，需重新审视端口与进程所有权；
- 网络数据源目前存在关闭 SSL 校验的代码路径（Chaldea 与 Atlas fallback）。这与本调研主题不直接相关，但建议在后续安全债治理中改为正常证书校验、重试和缓存策略。

---

## 3. FGO 战斗为何适合“受限智能体”而非自由 Agent

FGO 的指令战斗虽然复杂，但每回合动作空间有限，可被精确定义：

- 选定一个敌方目标；
- 使用可用从者技能和需要指定的目标；
- 使用御主技能、必要时换人；
- 选择可用宝具及其顺序；
- 从五张指令卡中选三张并排序。

关键机制包括卡色（Buster/Arts/Quick）、首卡效果、位置效果、同色 Chain、Brave Chain、Mighty Chain、宝具顺序/Overcharge、职阶克制、敌方 Break 和关卡特殊机制等。

因此这是一个更适合如下范式的问题：

```text
截图 -> 确定/不确定状态 -> 合法候选动作 -> 规则/搜索评分 -> 受限选择 -> 执行确认
```

而不是：

```text
截图 -> 自由文本提示词 -> 模型随意推断 -> 任意坐标点击
```

后者在可复现性、调试、资源安全和错误恢复上都不可接受。

---

## 4. 目标架构

### 4.1 引入战斗后端抽象层

建议在现有 `execute_bbc_task` 之外建立统一的后端接口，避免把新逻辑直接耦合到 BBC Action。

```python
from typing import Protocol

class BattleBackend(Protocol):
    def run(self, request: "BattleRequest", context) -> "BattleResult":
        """执行一次配置的战斗任务；必须返回结构化结果和可审计事件。"""
```

建议最少保留两个实现：

```text
BattleBackend
├── BbcBackend
│   └─ 对现有 ExecuteBbcTask / ConnectionManager 的适配层
└── PlannerBackend
    └─ MaaFramework 截图、结构化识别、规则/LLM 决策、逐步动作执行
```

这样可以：

- 保留当前 BBC 作为默认稳定路径；
- 仅对指定战斗类型、开发者开关或白名单关卡启用 Planner；
- 发生识别/推理失败时回退 BBC 或安全停止；
- 对同一队伍/关卡进行离线或受控 A/B 比较。

### 4.2 推荐分层

```text
┌───────────────────────────────────────────────────────┐
│ UI / Task Profile                                      │
│ 关卡、队伍、运行次数、风险策略、后端类型、LLM 开关       │
└──────────────────────┬────────────────────────────────┘
                       ▼
┌───────────────────────────────────────────────────────┐
│ MaaFgo Orchestrator                                    │
│ Pipeline：导航、启动、场景切换、结算、恢复、停止          │
└───────────────┬───────────────────────────┬───────────┘
                │                           │
                ▼                           ▼
      ┌─────────────────┐       ┌────────────────────────┐
      │ BbcBackend      │       │ PlannerBackend          │
      │ 当前默认实现     │       │ 新增、灰度实现           │
      └─────────────────┘       └───────────┬────────────┘
                                             ▼
                                ┌────────────────────────┐
                                │ Perception              │
                                │ Screenshot -> BattleState│
                                └───────────┬────────────┘
                                             ▼
                                ┌────────────────────────┐
                                │ Decision               │
                                │ Rules/Search + LLM opt │
                                └───────────┬────────────┘
                                             ▼
                                ┌────────────────────────┐
                                │ Validation & Safety    │
                                │ Schema / legal / policy│
                                └───────────┬────────────┘
                                             ▼
                                ┌────────────────────────┐
                                │ Execution              │
                                │ primitive actions + ack│
                                └────────────────────────┘
```

### 4.3 为什么不建议直接改写 `ExecuteBbcTask`

`ExecuteBbcTask` 当前承担了 BBC 生命周期、连接、回调、弹窗和重试。把视觉识别、规划、模型调用和点击状态机直接塞进去会造成：

- 单文件职责膨胀；
- BBC 特有的协议与通用 Planner 逻辑互相污染；
- 难以做单元测试和离线回放；
- 难以独立灰度/回退。

建议将其重构为 `backends/bbc_backend.py` 的适配实现；Planner 则独立放在 `battle/` 领域模块中。

---

## 5. 领域模型设计

### 5.1 BattleState：状态而非截图

视觉层输出的核心不应是“识别到哪些图块”，而应是领域状态。示例：

```json
{
  "schema_version": 1,
  "session_id": "...",
  "battle_id": "...",
  "wave": 2,
  "turn": 3,
  "screen": "COMMAND_SELECTION",
  "confidence": 0.97,
  "enemies": [
    {"slot": 1, "class": "LANCER", "hp": 18432, "max_hp": 55000,
     "break_count": 0, "targeted": true, "confidence": 0.95}
  ],
  "frontline": [
    {"slot": 1, "servant_id": 0, "np": 100, "np_ready": true,
     "skills": [
       {"index": 1, "available": true, "target_type": "SELF"},
       {"index": 2, "available": false, "cooldown": 4},
       {"index": 3, "available": true, "target_type": "ALLY"}
     ]}
  ],
  "command_cards": [
    {"ui_slot": 1, "owner_slot": 1, "color": "B", "critical": 0.0},
    {"ui_slot": 2, "owner_slot": 3, "color": "A", "critical": 0.3},
    {"ui_slot": 3, "owner_slot": 1, "color": "A", "critical": 0.0},
    {"ui_slot": 4, "owner_slot": 2, "color": "Q", "critical": 0.7},
    {"ui_slot": 5, "owner_slot": 1, "color": "B", "critical": 0.0}
  ],
  "uncertainties": [
    {"field": "frontline[1].servant_id", "reason": "not_observable"}
  ]
}
```

设计要求：

- **所有数值与实体字段可附带置信度或未知原因**；
- `unknown` 必须是合法状态，不允许用虚假默认值掩盖识别失败；
- 业务状态和视觉原始证据分离，证据通过截图 ID、ROI、模板命中等事件另存；
- `schema_version` 必须存在，便于演进与回放兼容。

### 5.2 BattleAction：动作必须可验证、可序列化

```json
{
  "target_enemy": 1,
  "skill_sequence": [
    {"actor": "SERVANT", "actor_slot": 1, "skill_index": 3, "target_ally": 1}
  ],
  "master_skill_sequence": [],
  "order_change": null,
  "np_order": [1],
  "card_order": [1, 3, 5],
  "policy_tag": "safe_clear",
  "expected": {"wave_clear_probability": 0.96, "resource_cost": 0}
}
```

约束：

- `card_order` 必须恰有三张、无重复、范围为 1–5；
- 只能使用当前 `BattleState` 标记为可用的技能/NP；
- 技能目标须符合对应技能的目标类型；
- `target_enemy` 必须在存活敌人集合中；
- 禁止由策略层传入绝对坐标；坐标只属于 Executor；
- 每个动作应有可预期的 UI 后置状态，供执行器确认。

### 5.3 StrategyProfile：用户意图与战术事实分离

```json
{
  "id": "farm-safe-v1",
  "mode": "FARM",
  "objective": "CLEAR_FAST",
  "min_wave_clear_probability": 0.95,
  "allow_command_spell": false,
  "allow_sq_revive": false,
  "allow_ap_refill": false,
  "allow_apple_types": ["COPPER", "SILVER", "GOLD", "BLUE"],
  "np_reserve_policy": "USE_IF_CLEAR",
  "llm_mode": "OFF",
  "fallback": "STOP"
}
```

`StrategyProfile` 不应被 LLM 在运行时任意修改；需要用户确认或版本化配置更新。

---

## 6. 感知层（Perception）设计

### 6.1 分阶段实现，不做全屏端到端识别

建议从固定 ROI 的多算法融合开始：

| 信息 | 第一实现 | 后续增强 |
|---|---|---|
| 是否处于选卡界面 | 攻击按钮/固定 UI 模板 | 场景分类器 |
| Wave / Turn | OCR + 模板 | 多服/多语言 OCR 模型 |
| 敌人数量与选中状态 | 固定槽位模板/颜色 | 敌方 UI 检测器 |
| 敌方 HP | ROI OCR | 数字序列校验、时序滤波 |
| NP 是否可用 | 图标状态/颜色模板 | 本地视觉分类器 |
| 技能可用性/CD | 图标状态 + OCR | 专用检测模型 |
| 五张卡色 | 颜色特征/局部分类 | 轻量 ONNX 分类器 |
| 卡归属从者 | 边框/头像区域分类 | 从者卡面特征检测 |
| Buff/Debuff | MVP 不作为硬依赖 | 图标检测 + 本地词典 |
| 特殊弹窗 | 模板集合 + OCR | 异常场景分类器 |

### 6.2 置信度门控

建议定义统一策略：

| 场景 | 建议阈值 | 低于阈值时动作 |
|---|---:|---|
| 选卡页、结算页等场景判断 | 0.95 | 重新截图并等待稳定；仍失败则停止 |
| 高风险按钮/弹窗 | 1.00 或人工白名单 | 禁止自动操作 |
| 技能/NP/卡牌状态 | 0.90 | 重新识别；必要时采用保守方案 |
| HP 等估计量 | 0.80 | 允许标为未知，不可作为“必杀”唯一依据 |

关键原则：**低置信度不是“低质量输入仍继续决策”，而是状态的一部分。**

### 6.3 截图稳定性与时序一致性

应在每次关键点击前后引入：

1. 等待屏幕变化停止或达到最小稳定窗口；
2. 连续两帧对关键 ROI 做一致性检查；
3. 检查前一动作预期的状态变化；
4. 不一致时进行有限重试；
5. 仍不一致则记录截图、状态、事件并安全停止。

MaaFramework Pipeline 已支持 `pre_wait_freezes`、`post_wait_freezes`、`timeout` 与 `on_error` 等控制，适合处理通用页面等待；战斗内复杂确认可由 Custom Action 统一实现。

---

## 7. 决策层：规则优先，LLM 受限

### 7.1 三层决策能力

#### L0：固定脚本 / BBC（现有默认）

适合固定周回队伍和已验证操作序列。优点是稳定、快速、可复现，应继续作为 MaaFgo 的主要生产路径。

#### L1：规则引擎 + 候选搜索（建议优先开发）

输入 `BattleState`，生成合法行动，再使用规则和估值排序。典型步骤：

```text
1. 验证视觉状态是否足够完整
2. 枚举可用目标、技能包、可用 NP 方案、三卡组合与排序
3. 使用约束剪枝：禁止资源、不可用技能、无效目标、风险上限
4. 计算候选收益：清场概率、伤害、NP 回收、星、资源成本、失败风险
5. 选取得分最高且满足策略下限的动作
6. 无合格动作 -> 保守动作或停止
```

可使用一个可解释的评分函数：

\[
Score(a)=w_k P(\text{clear}\mid a)+w_d E(\text{damage})+w_n E(\text{NP gain})+w_s E(\text{stars})-w_r Risk(a)-w_c Cost(a)
\]

周回模式重点是清场概率、耗时与资源成本；高难模式更强调存活、关键技能保留、Break 后状态和容错。

#### L2：LLM 受限策略层（后置功能）

LLM 的适合职责：

- 将用户自然语言偏好转换为待审核的 `StrategyProfile` 草案；
- 在规则引擎给出的少量候选中做高层取舍；
- 离线分析失败回放并提出“建议规则修改”；
- 对用户解释当前战术选择；
- 为新关卡生成**不可直接执行**的初始策略草案。

LLM 不适合：

- 直接输出点击坐标；
- 直接生成并执行 Python、Shell、Pipeline JSON；
- 靠参数记忆推断新从者/新机制；
- 在视觉不确定时强行补全状态；
- 跳过本地合法性与安全检查。

### 7.2 LLM 的安全输入/输出协议

建议 LLM 只接收结构化状态摘要和本地生成的候选，而非原始屏幕截图：

```json
{
  "objective": "FARM_SAFE",
  "constraints": {
    "min_clear_probability": 0.95,
    "forbidden_actions": ["COMMAND_SPELL", "SQ_REVIVE", "APPLE_REFILL"]
  },
  "state": {"...": "BattleState 摘要"},
  "candidates": [
    {
      "id": "candidate-a",
      "expected": {"clear_probability": 0.96, "np_gain": 21, "resource_cost": 0},
      "action": {"...": "BattleAction"}
    }
  ]
}
```

模型只允许返回：

```json
{
  "candidate_id": "candidate-a",
  "reason": "达到清场概率下限，且不使用禁止资源。"
}
```

之后仍须经过：

1. JSON Schema 校验；
2. `candidate_id` 是否确实来自本轮候选集的校验；
3. 战斗状态合法性校验；
4. `StrategyProfile` 策略校验；
5. 执行前视觉确认。

若模型超时、格式错误、选择不存在候选或产生不合规建议：**直接降级至 L1 规则引擎或停止**。

---

## 8. 执行层：原子动作、确认与安全边界

### 8.1 原子动作 API

建议 Planner 不直接持有 Controller，而是通过有限 API 请求操作：

```python
class BattleExecutor:
    def select_enemy(self, slot: int) -> bool: ...
    def cast_servant_skill(self, servant_slot: int, skill_index: int, target: int | None) -> bool: ...
    def cast_master_skill(self, skill_index: int, target: int | None) -> bool: ...
    def order_change(self, out_slot: int, in_slot: int) -> bool: ...
    def select_np(self, servant_slot: int) -> bool: ...
    def select_command_card(self, ui_slot: int) -> bool: ...
    def launch_attack(self) -> bool: ...
```

每个动作内部负责：定位、点击、等待、确认、有限重试和证据记录。

### 8.2 动作确认示例

```text
施放从者 1 的技能 3
  -> 验证是否出现目标选择 UI
  -> 选择友方目标 1
  -> 验证目标选择 UI 消失，且技能图标状态变化/效果出现
  -> 继续下一步

选择第 2 张指令卡
  -> 验证已选卡计数或高亮状态变化
  -> 若未变化：重新截图确认，不重复盲点

点击攻击
  -> 验证选卡界面退出或进入攻击动画/回合转换
  -> 超时：保存证据并停止
```

### 8.3 硬禁止与默认停止

必须建立“无法由 LLM、Profile 或普通配置绕过”的执行器级禁区：

- 令咒；
- 圣晶石复活；
- 圣晶石/付费货币消耗；
- 抽卡；
- 账号登录、绑定、授权；
- 未被识别为白名单的确认弹窗；
- 当 `screen != COMMAND_SELECTION` 却试图执行选卡动作；
- 当关键状态置信度不足时的任何战斗点击。

AP/苹果逻辑应保留 MaaFgo 既有明确配置，但要从战术 Planner 中隔离：Planner 可以报告“无可行战斗资源”，不能自主决定消耗受限资源。

---

## 9. 与 MaaFramework 的落地方式

### 9.1 Pipeline 保持“粗粒度状态机”

建议继续让 Pipeline 负责：

- 登录、导航、选关、选队、助战；
- 进入战斗、等待战斗页、检测结算；
- 通用加载等待、错误页与回主界面；
- 后端选择和故障收敛。

### 9.2 Planner 使用 Custom Recognition / Custom Action

可以增加类似节点：

```jsonc
{
  "原生规划战斗": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "run_planner_battle",
    "attach": {
      "strategy_profile": "farm-safe-v1",
      "max_turns": 20,
      "llm_mode": "off",
      "fallback_backend": "stop"
    },
    "next": ["战斗完成信息"],
    "on_error": ["保存战斗证据并停止"]
  }
}
```

在 Python Agent 中注册：

```python
@AgentServer.custom_action("run_planner_battle")
class RunPlannerBattle(CustomAction):
    def run(self, context, argv):
        # 读取 attach -> 构造 BattleRequest
        # 循环：观测 -> 规划 -> 校验 -> 执行 -> 确认
        # 返回 success / failure
        ...
```

如果某些场景需要由视觉决定 Pipeline 分支，则再加自定义识别器，例如 `BattleCommandScreen`、`BattleResultScreen`、`UnexpectedBattleDialog`。但不应把“每一个卡牌”都变成 Pipeline 节点；回合内组合逻辑应留在 Planner 模块。

### 9.3 建议的目录演进

```text
agent/
├── backends/
│   ├── base.py
│   ├── bbc_backend.py            # 从现有 bbc_action 逐步提取
│   └── planner_backend.py
├── battle/
│   ├── models.py                 # BattleState / BattleAction / Result
│   ├── profiles.py               # StrategyProfile
│   ├── perception/
│   │   ├── scene.py
│   │   ├── cards.py
│   │   ├── skills.py
│   │   ├── enemies.py
│   │   └── confidence.py
│   ├── planning/
│   │   ├── legal_actions.py
│   │   ├── rule_engine.py
│   │   ├── evaluator.py
│   │   ├── damage_model.py
│   │   ├── llm_selector.py
│   │   └── validator.py
│   ├── execution/
│   │   ├── executor.py
│   │   ├── coordinates.py
│   │   ├── confirmations.py
│   │   └── safety.py
│   └── telemetry/
│       ├── events.py
│       ├── replay.py
│       └── evidence.py
├── custom/
│   ├── bbc_action.py             # 过渡期保留兼容入口
│   └── planner_action.py
└── chaldea/                      # 既有模块，后续可提供队伍知识输入
```

---

## 10. 数据与知识库策略

### 10.1 本地数据库优先

从者技能、宝具、卡组、职阶、NP 类型、礼装与魔术礼装信息不能由 LLM 记忆提供。应建立版本化本地数据集，至少支持：

- `servant_id -> class, deck, np_type, np_color, skill metadata`；
- `quest_id -> waves, enemy class, enemy count, 机制标签（可选）`；
- `mystic_code_id -> skills`；
- 已知队伍与战术配置；
- 数据来源、服务器、游戏版本、生效时间。

项目现有 Chaldea 名称缓存与 Atlas Academy fallback 可作为数据获取/更新机制的起点，但 Planner 需要的不只是名称，应单独定义结构化 schema 与更新工具。

### 10.2 将 Chaldea 导入作为“先验”，而非运行时真相

Chaldea 队伍数据可用于：

- 初始化己方从者、礼装、魔术礼装、预设操作；
- 选择对应数据库条目；
- 生成/验证战术 Profile；
- 为用户解释当前计划。

但运行时仍应以游戏画面实际状态为准：从者死亡、换人、技能 CD、NP 值、敌人状态、卡牌都是动态的。

### 10.3 数据版本绑定

每次运行应把以下信息写入 `BattleSession`：

```text
MaaFgo commit / release
MaaFramework version
BBC version（如使用）
游戏服务器与客户端版本（若可获得）
静态数据版本/hash
StrategyProfile version/hash
模型版本（OCR/分类器/LLM adapter）
```

这对“某次版本更新后决策变差”的定位至关重要。

---

## 11. 可观测性、回放与测试

### 11.1 事件日志应成为一等公民

建议所有 Planner 运行输出 NDJSON（每行一个事件），示例：

```json
{
  "ts": "2026-07-30T12:00:00.000Z",
  "session_id": "...",
  "type": "state_observed",
  "state_hash": "...",
  "screenshot_id": "...",
  "confidence": 0.97
}
```

```json
{
  "ts": "2026-07-30T12:00:01.000Z",
  "session_id": "...",
  "type": "decision",
  "planner": "rule_engine_v1",
  "candidates": [{"id": "a", "score": 0.91}],
  "selected": "a",
  "action": {"...": "BattleAction"}
}
```

```json
{
  "ts": "2026-07-30T12:00:02.000Z",
  "session_id": "...",
  "type": "action_confirmed",
  "primitive": "select_command_card",
  "arguments": {"ui_slot": 2},
  "before_screenshot": "...",
  "after_screenshot": "..."
}
```

注意：日志默认不应上传；如将截图共享用于 issue，应先提供脱敏和用户明确选择。

### 11.2 三类测试集

1. **视觉黄金集**：截图 + 标注的 `BattleState` 字段，用于测试 OCR、场景与卡识别。  
2. **决策黄金集**：人工构造/录制的 `BattleState -> 合法候选/期望动作`，用于规则回归。  
3. **回放集**：按时间排序的状态与截图，用于模拟整场战斗状态机，测试超时、误识别、异常弹窗和回退。

### 11.3 指标

建议在任何“智能战斗”公开前先明确指标：

| 指标 | 初期目标 |
|---|---|
| 场景识别关键状态准确率 | ≥ 99%（受控设备/版本） |
| 卡色识别准确率 | ≥ 99% |
| 执行后确认成功率 | ≥ 99.5% |
| 非法 BattleAction 输出率 | 0 |
| 高风险动作误触发 | 0 |
| 低置信度状态的安全停止率 | 100% |
| 回放可复现率 | ≥ 99% |

“单局成功率”不能掩盖高风险误操作；后者必须单独作为阻断指标。

---

## 12. 分阶段实施计划

### Phase A：架构准备与后端解耦

**目标**：不改变现有用户路径，先建立扩展边界。

- 定义 `BattleBackend`、`BattleRequest`、`BattleResult`；
- 把 `ExecuteBbcTask` 逐步适配为 `BbcBackend`；
- 增加 UI/配置中的 `battle_backend = bbc | planner`，默认 `bbc`；
- 增加统一战斗事件与错误码；
- 明确 BBC 失败的回退/停止语义。

**验收**：BBC 行为不回归；同一任务可经新接口执行并产生结构化结果。

### Phase B：只观测、不执行（Shadow Mode）

**目标**：验证截图到 BattleState 的可靠性。

- 开发选卡页、Wave/Turn、NP、卡色、卡归属的识别；
- 在 BBC 实际运行时并行采样截图（不干扰执行）；
- 输出 `BattleState`、置信度和证据；
- 人工标注/回放对比。

**验收**：在限定设备、分辨率、服务器版本和队伍范围内达到视觉指标；低置信度能正确暴露。

### Phase C：离线决策器

**目标**：对历史状态产生合法、可解释的动作，但不点击。

- 实现 `BattleAction` Schema、合法动作生成、Validator；
- 实现卡链基础规则与保守选卡；
- 构建决策黄金集；
- 对 BBC 既有操作序列和 Planner 建议做差异分析。

**验收**：无非法动作；决策回放稳定；输出可解释。

### Phase D：受控实时执行（卡牌层）

**目标**：在固定关卡/固定队伍/禁用高风险资源条件下，让 Planner 仅处理三张指令卡选择。

- 预设技能和宝具流程；
- Planner 只选择目标、卡牌与顺序；
- 每次点击后做 UI 确认；
- 失败即停、保存证据。

**验收**：连续受控运行达到目标成功率，且高风险误触发为零。

### Phase E：技能、NP、换人与资源预算

**目标**：逐步支持完整的回合行动。

- 从者/魔术礼装元数据接入；
- 技能目标和冷却判断；
- NP 排序、预估清场与 NP 回收；
- 换人和复杂技能作为白名单特例逐项加入；
- 引入风险/资源策略 Profile。

**验收**：覆盖指定白名单队伍和关卡，且每项特殊机制有专门回放测试。

### Phase F：LLM（可选、默认关闭）

**目标**：只做受限候选选择、离线规划和解释。

- 实现 provider 抽象、超时、速率限制、本地开关；
- 仅向模型传递结构化摘要与候选 ID；
- 严格 Schema、候选归属和策略校验；
- 断网/超时/异常时降级 L1；
- 增加模型输出审计与可复放模拟。

**验收**：模型异常不会扩大动作权限，不会破坏无模型模式的确定性。

---

## 13. 风险清单与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 游戏 UI / 版本 / 服务器差异 | 模板、OCR、坐标失效 | 资源按服/版本分包；固定运行矩阵；截图回归集 |
| 模拟器缩放/渲染差异 | 点击偏移、识别不稳 | 内容区归一化；固定推荐配置；执行前锚点校准 |
| 动画、加载、网络延迟 | 连点、错状态 | 稳定帧、后置确认、超时、有限重试 |
| 视觉误识别 | 策略基于错误状态 | 置信度、二次观测、未知值、关键字段 fail-closed |
| 复杂机制不可观测 | 伤害估计偏差 | 白名单关卡；机制 Profile；保守规划；逐步扩展 |
| LLM 幻觉或不稳定 | 非法/不一致策略 | 候选选择模式、Schema、Validator、规则回退 |
| 外部服务不可用 | 队伍数据/LLM 请求失败 | 本地缓存优先；离线可运行；明确 fallback |
| 进程/端口资源竞争 | BBC 或 Agent 互相影响 | 明确所有权、单实例锁、端口配置化、避免按端口粗暴终止无关进程 |
| 高风险资源误触 | 不可逆损失 | 执行器硬禁区、独立确认、未知弹窗即停 |
| 数据/隐私 | 截图或配置泄露 | 本地默认保存、可选上传、脱敏、保留期和导出控制 |
| 条款/账号风险 | 项目与用户风险 | 文档明确边界；不开发规避/对抗功能；由使用者评估授权与风险 |

---

## 14. 关键设计决策建议

1. **继续保留 BBC，且将其视为战斗后端，而不是要立即淘汰的旧实现。**  
   MaaFgo 当前的主要价值是完整自动化链路；智能 Planner 应先以增量能力出现。

2. **先 Shadow Mode，再离线回放，再小范围执行。**  
   视觉和执行可靠性没有量化前，不应把 LLM 接入实时控制。

3. **先规则、后 LLM。**  
   对大多数稳定周回，确定性策略更快、更可控；LLM 只解决“策略表达、候选取舍、复盘”的增量问题。

4. **坚持 `BattleState` / `BattleAction` 两个明确契约。**  
   这是视觉、策略、执行、测试和日志能够独立演进的基础。

5. **所有不可逆或高价值资源从 Planner 权限中剥离。**  
   即使未来扩展 LLM，也不应放开此边界。

6. **将数据版本、截图证据、决策链路纳入发布质量门槛。**  
   智能逻辑没有可复放证据，就无法可靠维护。

---

## 15. 建议的近期 Issue / Milestone 拆分

### Milestone 1：`battle-backend-abstraction`

- [ ] 定义 backend/request/result/error code
- [ ] 抽取 BBC backend adapter
- [ ] 保持现有 `execute_bbc_task` 兼容入口
- [ ] UI 增加隐藏/开发开关
- [ ] 新增 backend 单元测试

### Milestone 2：`planner-shadow-perception`

- [ ] BattleState Pydantic/dataclass schema
- [ ] 截图证据与 NDJSON 事件格式
- [ ] 选卡场景、NP、五卡色识别
- [ ] 置信度与 unknown 语义
- [ ] 截图黄金集及评测脚本

### Milestone 3：`planner-offline-rules`

- [ ] BattleAction schema
- [ ] 合法动作生成器
- [ ] 三卡链评分器
- [ ] Validator 与安全策略
- [ ] 回放测试框架

### Milestone 4：`planner-live-card-only`

- [ ] 原子执行器与逐步确认
- [ ] 固定关卡白名单
- [ ] 失败证据收集与 fail-closed
- [ ] 连续稳定性测试

### Milestone 5：`planner-llm-advisory`

- [ ] LLM provider interface
- [ ] 候选选择 JSON schema
- [ ] 超时/限流/缓存/脱敏
- [ ] 安全降级和审计
- [ ] 默认关闭、实验性标签

---

## 16. 参考资料

1. [MaaFgo 仓库](https://github.com/xlxyvergil/MaaFgo) —— 本调研的项目基线；README、Agent、Pipeline 和资源结构均以该仓库 `main` 分支为准。  
2. [MaaFgo README](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/README.md) —— 项目定位、功能清单、技术栈与现有战斗核心说明。  
3. [MaaFgo `bbc_action.py`](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/agent/custom/bbc_action.py) —— 当前 BBC 战斗 Custom Action、参数读取、重试和 GUI 提示回写。  
4. [MaaFgo `bbc_connection_manager.py`](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/agent/custom/bbc_connection_manager.py) —— BBC TCP/回调通道、进程和消息队列的实现。  
5. [MaaFgo `bbc战斗.json`](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/assets/resource/base/pipeline/bbc%E6%88%98%E6%96%97.json) —— BBC 战斗入口和 `attach` 参数。  
6. [MaaFgo `日常战斗.json`](https://raw.githubusercontent.com/xlxyvergil/MaaFgo/main/assets/resource/base/pipeline/%E6%97%A5%E5%B8%B8%E6%88%98%E6%96%97.json) —— 战前导航、BBC 战斗及结算的通用调度链。  
7. [MaaFramework Pipeline Protocol](https://maafw.com/en/docs/3.1-PipelineProtocol/) —— Pipeline 节点、识别/动作类型、错误处理、等待与扩展机制。  
8. [MaaFramework 快速开始（中文）](https://raw.githubusercontent.com/MaaXYZ/MaaFramework/refs/heads/main/docs/zh_cn/1.1-%E5%BF%AB%E9%80%9F%E5%BC%80%E5%A7%8B.md) —— JSON + Custom Action/Recognition 的推荐集成方式、资源组织和调试能力。  
9. [FGO Combat Mechanics — GamePress](https://fgo.gamepress.gg/combat-mechanics) —— 卡色、首卡、同色链、Brave/Mighty Chain、NP 等基础战斗机制参考。  
10. [Fate/Grand Automata Battle Wiki](https://github.com/Fate-Grand-Automata/FGA/wiki/Battle) —— 技能、目标、NP、换人、Wave/Turn、卡优先级等动作维度的工程化参考。  

---

## 附录 A：建议的最小 Planner 伪代码

```python
def run_turn(context, profile: StrategyProfile) -> TurnResult:
    state = perceive_battle_state(context.controller.cached_image)

    if state.screen != "COMMAND_SELECTION":
        return TurnResult.fail("unexpected_screen")
    if not state.is_confident_for_execution():
        return TurnResult.fail("insufficient_confidence")

    candidates = generate_legal_actions(state, profile)
    candidates = [c for c in candidates if validate_action(c.action, state, profile).ok]

    if not candidates:
        return TurnResult.fail("no_legal_action")

    ranked = rank_with_rules(candidates, state, profile)
    selected = ranked[0]

    if profile.llm_mode == "CANDIDATE_SELECTOR":
        selected = try_llm_select_or_fallback(ranked, state, profile)

    verdict = validate_action(selected.action, state, profile)
    if not verdict.ok:
        return TurnResult.fail(f"validator_reject:{verdict.reason}")

    return execute_action_with_confirmation(context, selected.action, state, profile)
```

## 附录 B：发布前的强制检查表

- [ ] LLM 断网时，Planner 不会崩溃且能规则回退或停止。  
- [ ] 所有模型输出都不能绕过本地 Validator。  
- [ ] 所有高风险 UI 都在执行器硬禁区内。  
- [ ] 任一关键视觉字段低置信度都会阻止战斗点击。  
- [ ] 每一次动作都保存前/后状态或截图引用。  
- [ ] 回放集覆盖网络慢、动画、异常弹窗、敌人残血、NP 未满、技能目标选择等情形。  
- [ ] 新服务器/新分辨率/新 UI 版本未通过黄金集前，不进入 Planner 白名单。  
- [ ] BBC 默认路径的行为和性能没有回归。  
