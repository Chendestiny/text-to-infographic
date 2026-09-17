# 渲染后端与 profile 冲突

## 两种后端

| 后端 | 怎么工作 | 优点 | 缺点 |
|---|---|---|---|
| **CDP**（默认） | 起一个 headless 实例，用 WebSocket 发 DevTools Protocol 命令 | 不依赖 stdout、可复用实例、**0.7s/张** | 需要能连本地端口 |
| **CLI** | `chrome --headless=new --screenshot=out.png` | 零依赖、最原始 | 每次重启浏览器（0.9~2.5s/张）；**依赖 stdout / 文件落盘，受限环境容易被拦** |

用环境变量强制指定：

```bash
T2I_BACKEND=cdp    # 强制 CDP
T2I_BACKEND=cli    # 强制 CLI
T2I_BACKEND=auto   # 默认：CDP 优先，失败回落 CLI
```

## ★ profile 冲突：CLI 静默返回 0 字节的真正原因

**这是最容易误判成"Chrome 坏了"的坑。** 实测数据（本机 Chrome 152.0.7977.84）：

| 场景 | `--dump-dom` 结果 |
|---|---|
| fresh profile，连续跑 3 次 | **15462 bytes，每次都成功** |
| profile 被**正在运行的 Chrome 实例**占用 | **0 bytes**（exit code 是 0，什么都没输出） |
| `--screenshot` + fresh profile | **131821 bytes，正常落盘** |

**机制**：Chrome 是「一个 profile 一个实例」。当你指定的 `--user-data-dir`
已经被另一个正在运行的 Chrome 占用时，新启动的进程会把命令行**交给那个实例**
然后自己静默退出——于是没有任何输出、退出码还是 0。

**哪些情况会撞上**：

1. 你的代码复用了同一个 `--user-data-dir`（比如写死了路径、或用了固定的临时目录）
2. **受限沙箱让 `--user-data-dir` 没生效**（创建目录被拒、路径被改写），
   于是 Chrome 回落到**默认 profile**——而用户自己的浏览器正在用那个默认 profile →
   必然 hand-off → 0 字节。这种情况最容易误诊，因为看起来"参数都传对了"。

**本项目的处理**：

- `render.py` 每次截图都 `tempfile.mkdtemp()` 生成**全新 profile**，所以从设计上不会撞
- CDP 后端启动自己的实例（自己的 profile），也不受影响，所以默认走 CDP
- `doctor.py` 的**渲染后端预检**实测两种后端并给出耗时，3 秒告诉你环境行不行

## 排障三步

```bash
# 1) 后端预检：谁能用、多快、该设什么
python scripts/doctor.py

# 2) 如果两个后端都出不了图，手动验证 CLI 到底行不行
#    （用全新 profile，并确认输出文件真的落盘）
chrome --headless=new --screenshot=/abs/path/out.png file:///abs/path/card-01.html
#    期望看到 "NNNNN bytes written to file ..."，这是 Chrome 自己的成功回执

# 3) 如果 CLI 时好时坏 → 检查有没有别的 Chrome 正在用同一个 profile
```

## 输出尺寸与体积（@1x / @2x / 量化）

`render.py --scale N` 控制设备像素比（默认 2）。同一份 HTML（10 页）实测：

| 输出 | 单张 | 10 页合计 | 送视觉模型时的实际像素 |
|---|---|---|---|
| `--scale 1`（1080×1440） | 150 KB | 1.47 MB | 1080×1440 ≈ 2,073 token/张（粗估） |
| `--scale 2`（2160×2880，默认） | 329 KB | 3.22 MB | 先被压到 1536×2048 ≈ 4,194 token/张 |
| `--scale 1` + 调色板量化 256 色 | 57 KB | 0.56 MB | 同上 |
| 复核缩略图 720px（JPEG q88） | 85 KB | 0.83 MB | 720×960 ≈ 921 token/张 |

两点结论：

1. **2 倍图对视觉模型是纯浪费**：harness 会把 2160×2880 先缩到 1536×2048 再送，
   分辨率优势全被吃掉、token 反而翻倍。复核读图用 720px 缩略图就够。
2. **交付用 @1x 即可**：1080×1440 正是小红书推荐尺寸，平台还会再压一次。
   这类"纯色块 + 描边"的图用调色板量化（`PIL: convert("RGB").quantize(colors=256)`）
   能再掉 60%+，肉眼看不出差别。不必上 TinyPNG 这类在线服务——本地就能做，也不用把图传出去。

## 什么时候该怀疑不是后端的问题

- `doctor.py` 预检**通过**，但 `pipeline.py` 报某个后端失败 →
  看是不是并发跑了多个 pipeline（多进程抢同一个 profile 目录）
- 只有**某一张**失败 → 那张的 HTML 有问题，看 `build/<spec>/card-XX.html`
- 图出来了但内容不对 → 那是契约或文案问题，不归后端管

## 历史教训（写在代码注释里，避免重复踩）

曾经把这个现象误判为「**Chrome 132+ 移除了 CLI 导出 flag**」，并写进了代码注释。
**这个结论是错的**——同期实测 Chrome 152 的 `--screenshot` 完全正常。
真相是上面说的环境/profile 冲突。

教训：**「某版本移除了某功能」这类结论必须自己实测验证**，
否则一条错误的根因注释会污染仓库、误导后来者（比代码 bug 更难发现）。
