# 我开源了一个把长文转成自媒体多图的 Skill：LLM 只管填表，像素交给脚本

大家好，我是 Chendestiny。

【导读】做自媒体图文这件事，现状是两头堵：AI 生图文字必糊（中文尤甚）；让 LLM 自由写 HTML"信息图"，每次都不一样——间距不一致、文字出框、版式一次性，改好一版换个题材又崩。这个 skill 把 LLM 挪到它擅长的地方（读文章、定结构、压文案），像素全部交给确定性脚本：给一篇文章，产出一张封面加每页一个要点，手绘马克笔风、可直接发布。文字 100% 准确，可复现，可手改。

GitHub：https://github.com/Chendestiny/text-to-infographic

## 先看怎么用：三句话

**① 装 —— 一句话**

```
帮我安装 text-to-infographic：
irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
```

macOS / Linux 换成 `curl -fsSL https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.sh | bash`。
脚本会把仓库 clone 到 `~/.agents/skills/`，再逐项自检 Python、浏览器、字体完整性，缺什么打印什么。

**② 用 —— 把文件交给它（路径和文件名换成你自己的）**

```
用 text-to-infographic（~/.agents/skills/text-to-infographic）
把 D:\notes\article.md 转成小红书图文，输出到桌面
```

**③ 偷懒 —— 一句话也行**

```
把这篇总结成自媒体多图
```

Agent 按 SKILL.md 里的纪律读文章、填规格，跑完校验循环后交付：
`card-01.png …` 直接落在桌面，2160×2880，可以立刻发。

## 痛点：两个方向都堵死了

我自己就是从"让 AI 画一张图文卡片"开始的，踩了三层坑：

1. **AI 生图，文字必糊。** 扩散模型对中文文本的渲染基本不可用，标题都拼不对，更别说要点列表。
2. **让 LLM 自由写 HTML，每次都不一样。** 它会写出结构完全正确的 HTML，但间距、字号、框的位置每次都是新的——你没法维护一套视觉风格，更没法复现。
3. **就算固定了模板，文字照样溢出。** 这是最阴的一条：版式摆在那里，LLM 填进来的文案长度不可控，长文案直接出框。我第一版就是这样——文章 3 我边看边调能过，换文章 1 又爆。

第三条最要命。它说明问题不在 LLM 写得好不好，而在**约束从未被声明**：每个版式能装多少字，只存在于代码的隐式行为里。

## text-to-infographic 是什么

一句话：**把"文生图"拆成"LLM 填表 + 脚本渲染"，中间用契约和实测把两道门都焊死。**

```
文章.md ──> [LLM] cards.json ──> build.py ──> measure（真实浏览器实测）──> PNG × N
              只有这一步需要       所有像素决策都             校验循环
              LLM                 写死在脚本里              （LangGraph 风格）
```

- **Agent 只填表，不碰像素。** 13 种版式（四宫格汇总封面/中心圆/步骤链/环形循环/光谱/时间轴/横向链路/清单/对照/四象限/金字塔/结构图/自定义 SVG）全部是确定性代码。同样的规格永远渲染出同样的图，任何一页都能手改。
- **容量契约前置。** 每个版式的每个文字槽位都在 `templates/contracts.yaml` 里声明了字数范围（N-M），数值来自实际渲染好看的真实文案。`validate.py` 在渲染前逐条机械校验，超了报精确路径：`card-03(chain).steps[1].text: 17.5 > max 15`。Agent 拿着报错一次改对。
- **像素门用真实浏览器实测。** 文字宽度靠估算必翻车（拉丁宽、bold、letter-spacing 全是变量），所以 `measure.py` 让 Chrome 渲染后用 `getBBox()` 拿每个文本的真实包围盒，和 build 时埋进 HTML 的方框清单比对。四类问题：出画布、压框、HTML 行溢出，以及**静默吞字**——规格里登记过的文字根本没画出来，这类既不溢出也不压框，只能靠内容清单比对抓出来。
- **校准闭环。** 测出「真实宽 / 估算宽」回写成校准因子，估算器自己越跑越准；仍溢出的文本注入 `textLength` 强制压回框内。
- **LLM 兜底有明确入口。** 3 轮压不下的文案进 `needs_llm` 清单——那不是失败，是"这段该重写文案"的精确信号。实测抓到过一次：封面大字在 248px 的框里放了 5 个汉字加一个英文词，循环 3 轮正确升级，改规格后一轮通过。

## 五个设计决策

**1. LLM 只出规格，不碰像素。** 让 LLM 直接生成 HTML，你得到的是每次都不一样的"信息图"——风格无法维护、结果无法复现、单页无法手改。规格是机器可校验的合同，HTML 是合同的忠实执行。

**2. 字数契约是声明出来的，不是隐式的。** 我最初的版本里，容量藏在代码行为里，于是每篇文章都要我"看图调一调"。把契约写成 YAML 之后，LLM 的任务从"写好文案"变成"在 N-M 字范围内总结"——有硬边界，就能机械校验；能机械校验，就不需要祈祷。

**3. 两道门分开：便宜的在前，贵的在后。** 规格门（字数校验，纯脚本）拦住 90% 的问题；像素门（真实浏览器实测）兜住字体度量估算不准的剩余部分。两道门都不花 token，LLM 只在门报出精确错误时介入。

**4. 装饰和配色也是零件。** 齿轮、星形是纯 SVG path 的零件库，颜色按 蓝→黄→粉→绿→灰→橙 轮换，规则写死——不靠模型"审美"。

**5. 跨平台探测，字体随仓库分发。** Windows/macOS/Linux 的浏览器路径自动探测（Windows 自带 Edge 基本覆盖）；字体用 OFL 许可的站酷快乐体随仓库走，不要求用户装任何东西。

## 上手

```powershell
# Windows：安装（一行）
irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex

# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.sh | bash
```

装完对 Agent 说"把这篇总结成自媒体多图"，或者手动：

```bash
python scripts/pipeline.py examples/prompt-engineering.json -o out/
```

依赖就四样：Python 3.8+、一个 Chromium 系浏览器（Windows 自带 Edge 基本覆盖）、
可选 pyyaml（用 .json 规格则完全不需要）、内置字体。`doctor.py` 会逐项自检。

实测数据（两篇约 5000-6000 字的技术文章）：Agent 阶段（读文 + 填规格）约 2~4.5K tokens 入、
1.2~1.3K 出；确定性脚本 build 0.5s + render 8s 出 8~9 张 2160×2880。
校验循环全部通过时零额外 token，只有升级到 needs_llm 的那几行才花。

## 为什么开源

我的 Agent 系列文章每篇都想配一套图文，手动排版一篇要花一个多小时，还篇篇长得不一样。
把"排版"沉淀成脚本之后，每篇文章的成本降到了"读一遍、填一次表"。

更重要的原因是架构上的：这个项目把「LLM 做什么」和「脚本做什么」划得很清楚——
LLM 负责理解和取舍，脚本负责所有像素决策，中间用机器可校验的契约连接。
这个模式不只在画图文卡上有用，凡是"LLM 产出需要被程序消费"的场景都适用。

与其躺在我机器里只服务我自己的几篇文章，不如开源出来。
GitHub：https://github.com/Chendestiny/text-to-infographic

觉得有用给个 Star 就是最大的支持。
