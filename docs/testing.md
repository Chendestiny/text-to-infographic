# 用 hermes 做多轮实测：整套流程

这份文档记录**怎么测量这个技能的端到端耗时、怎么判断一次交付合格、以及踩过哪些坑**。
目标读者是下一个接手的人（或 agent）：照着跑就能复现出同口径的数字。

---

## 一、为什么要测"agent 时间"，而不是"渲染时间"

渲染本身极快：**0.5~0.7 秒/页**（10 页 ≈ 4.6~7s，含起浏览器与实测）。
一轮真实任务的耗时几乎全在 **LLM 侧**：读文章 → 定页数 → 写规格 → 过门 → 改 → 再跑 → 写报告。

实测规律（三轮均值）：**墙钟 ≈ API 调用次数 × 单次延迟**。
所以优化方向是"减少往返"，而不是"优化渲染"。

## 二、被测对象与调用方式

被测技能是安装副本：`%USERPROFILE%\.agents\skills\text-to-infographic`（它是 GitHub 仓库的克隆，
测前请确认 `git -C <该目录> rev-parse --short HEAD` 与你打算测的版本一致）。

```
hermes -z "<提示词>" --yolo \
  --toolsets terminal,file,code_execution,skills,todo,memory,session_search,connections,delegation,clarify \
  --usage-file <usage.json> 2>&1 | Out-File -FilePath <log> -Encoding utf8
```

| 参数 | 为什么 |
|---|---|
| `-z` | one-shot：只把**最终回复**打到 stdout（中间步骤要去 `state.db` 看） |
| `--yolo` | 免审批，否则一次确认超时就能白等一分钟以上 |
| `--toolsets ...` | **把 `vision` 排在外面**：单次看图 40~250 秒，而正确性已由四道门覆盖。想看观感时再单独放行 vision |
| `--usage-file` | 记账：`api_calls / input_tokens / output_tokens / reasoning_tokens / cache_read_tokens` |

提示词用"用户式"的最小写法即可（技能里的流程文档会接管）：
```
用 skill：text-to-infographic（%USERPROFILE%\.agents\skills\text-to-infographic）
把 <文章路径> 转成小红书图文，输出到 <桌面某目录>
```

## 三、驱动脚本

`%USERPROFILE%\.dsh\scratch\t2i-bench\run3.ps1`（连跑 N 轮 + 汇总）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File run3.ps1 `
  -Article "<文章.md>" -OutPrefix "<桌面目录前缀>" -Rounds 3
```

⚠️ **该脚本刻意写成纯 ASCII**：中文当参数传入。原因见"五、坑"。
每轮产出：`<前缀>N\` 里的出图目录 + `dom-rN.log`（最终回复）+ `dom-rN-usage.json`（记账）。

## 四、怎么看结果（两个层面）

### 1) 时间与 token

直接读 `run3.ps1` 的汇总表。历史口径：

| 组 | 三轮墙钟 | 平均 | 张数 |
|---|---|---|---|
| SVG 文字时代（基线） | 434.1 / 317.5 / 412.0 / 346.0 | **377s** | 6 / 7 / 8 |
| DOM 迁移完成 | 216.5 / 255.6 / 211.4 | **227.8s** | 5 / 5 / 6 |
| 入口收敛后 | **169.4** / 287.0 / **139.6** | **198.7s** | 5 / 5 / 6 |

结论：平均 **-47%**；**180s 目标在 2/3 轮达成**；**方差是主导因素**（最快 139.6s、最慢 287s，2.06 倍）。

### 2) 交付质量：**必须用 exit code 复核，不能信 agent 自述**

对每轮交付的 `spec.json` 直接跑真门：

```powershell
$env:T2I_BACKEND='cdp'
python scripts\pipeline.py "<桌面目录>\spec.json" -o "<临时出图目录>"
# 期望：exit=0，且输出里有 measure: 0 处溢出 / verify: 干净，进入渲染
```

进阶：`hermes_timeline.py`（从 `~/AppData/Local/hermes/state.db` 读会话，按停顿归属拆时间与工具分布）、
`round_report.py`（把日志 + 独立门禁复核拼成一张体检表）。

## 五、坑（都是实际踩过的）

1. **PowerShell 5.1 读 `.ps1` 默认按 ANSI** → 脚本里的中文会乱码成语法错误。
   **对策：脚本写成纯 ASCII，中文一律当参数传**（比加 BOM 更彻底）。
2. **PS 5.1 不支持 `??`（PS 7 才有）**；`"$v:"` 会被当成驱动器变量引用而报语法错 → 用 `${v}:`。
3. **`-z` 只输出最终回复**：中间步骤看不见是正常的，要看就查 `state.db`。
4. **别用关键词扫描当验收**：曾出现过 `ink.py` 被裁坏（`NameError`），而 `run.py` 只扫输出关键词，
   于是崩溃的子进程既没有 `measure:` 也没有 `needs_llm` → 照样报"硬问题 0 处（假绿）"。
   现在 `run.py` 已修（非零退出且无 `measure:` 即算硬问题），**但通用纪律是：验收看 exit code**。
5. **一次只让一个进程写同一个文件**：所有版式都在 `scripts/ink.py` 里，并行 subagent 会互相覆盖。
6. **中途别同步安装副本**：测试跑起来后，改仓库不影响它（它读安装副本）；但若在测试进行中
   `git pull` 安装副本，就会中途换版本、数字失去意义。

## 六、复现步骤（照抄）

```powershell
# 0) 确认被测版本
git -C "$env:USERPROFILE\.agents\skills\text-to-infographic" rev-parse --short HEAD

# 1) 连跑三轮（文章路径与输出前缀用参数传，脚本本体是 ASCII）
$article = "<文章路径>"
$prefix  = "%USERPROFILE%\Desktop\文章2-测试"
powershell -NoProfile -ExecutionPolicy Bypass `
  -File "%USERPROFILE%\.dsh\scratch\t2i-bench\run3.ps1" -Article $article -OutPrefix $prefix -Rounds 3

# 2) 用真门复核每一轮交付（exit code 为准）
foreach ($d in 1,2,3) {
  python scripts\pipeline.py "$prefix$d\spec.json" -o "$env:TEMP\v$d"
  "第 $d 轮 exit=$LASTEXITCODE"
}
```