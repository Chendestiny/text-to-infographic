# 文档索引

给 Agent 和维护者看的细节手册。**SKILL.md 是入口**（做什么、按什么顺序做），
`docs/` 是**为什么这么做、出问题怎么救**。

先看 [../SKILL.md](../SKILL.md)，遇到具体问题时再查这里的对应页。

| 文档 | 回答什么问题 |
|---|---|
| 页数与容量怎么算 | `scripts/plan.py`（页数）· `scripts/capacity.py`（几何容量）—— 先跑脚本，再回来读文档 |
| [architecture.md](architecture.md) | 为什么是"LLM 填表 + 脚本渲染"？四道门（+ 门内的内容门）各自管什么？校准闭环怎么转？ |
| [layouts.md](layouts.md) | 15 种版式每个字段叫什么、能放多少字、什么时候该用哪个；三种封面的取舍 |
| [../assets/style.md](../assets/style.md) | **主题（皮肤）令牌**、两个族的区别、怎么挑皮肤、配色/笔锋/装饰零件库的设计纪律 |
| [contracts.md](contracts.md) | 字数契约怎么读、硬约束和软约束的区别、违规了怎么改 |
| [rendering.md](rendering.md) | 渲染后端（CDP / CLI）、profile 冲突这个坑、`T2I_BACKEND` 怎么用 |
| [troubleshooting.md](troubleshooting.md) | 症状 → 原因 → 处置，全部是实测过的失败模式 |
| [extending.md](extending.md) | 加一种新版式要动哪些文件（5 步清单） |

## 30 秒排障表

| 症状 | 去哪 |
|---|---|
| 截图全失败 / 0 字节 | [rendering.md](rendering.md) → 先跑 `doctor.py` 看后端预检 |
| 页面底部被裁、字压框 | [troubleshooting.md](troubleshooting.md) → 溢出三兄弟 |
| 不知道某个版式有哪些字段 | [layouts.md](layouts.md) |
| 想换个视觉风格 / 觉得图太素 | [../assets/style.md](../assets/style.md) → `python make_theme_gallery.py` |
| `validate.py` 报一堆路径违规 | [contracts.md](contracts.md) |
| 模型能不能看图 / 该不该做视觉检查 | [troubleshooting.md](troubleshooting.md) → 读图能力三态 |
| 想加一种自己的版式 | [extending.md](extending.md) |

## 资产 vs 产物（别搞反）

| 类别 | 判断标准 | 放哪 | 例 |
|---|---|---|---|
| **资产**（随仓库分发） | 内容恒定、要人工审阅、要跨环境一致 | 仓库内 `assets/` `templates/` `docs/` | 字体、探针图、字数契约、版式样张 |
| **产物**（可再生产物） | 每次运行都会变、删了能重跑回来 | `build/` `out/`（已 gitignore） | 中间 HTML、最终 PNG |

**判断法**：把它删掉，跑一次就回来 → 产物；**跑不回来 / 每次生成会漂** → 资产。

踩过的坑：探针图（`assets/vision-probe.png`）一开始是运行时现场生成到临时目录的，
这是错的——它是固定资产（内容恒定、判定标准要可审阅、跨环境必须一致），
必须随仓库走。同类错误还有：把字体放成"首次运行下载"。

## 一条铁律

**本文档与代码同源。** 改了 `scripts/` 或 `templates/contracts.yaml` 之后，
必须回头改这里对应的页——判断有没有漏改的方法：
把文档里提到的脚本名、版式名、常量逐个 `grep` 代码验证。
（这条来自一次真实教训：SKILL.md 曾经停留在两步流程时代，把 Agent 带偏了。）
