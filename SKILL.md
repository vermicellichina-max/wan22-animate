---
name: wan22-animate
description: 用 Wan2.2-Animate 把静态人物图片和参考视频合成动作视频（动作模仿/舞蹈复刻/动漫角色动画）。输入一张角色图 + 一段参考视频，输出该角色跟着视频做同样动作和表情的 MP4。当用户提到"让这张图动起来""跟着视频跳舞""动作模仿""角色替换"" animate""Wan2.2-Animate""万相图生动作"或要求把某人的动作迁移到另一张图片上时，使用本技能。
---

# Wan2.2-Animate 图生动作

把参考视频里的动作+表情迁移到一张静态人物图上，生成动态视频。走阿里云百炼 API，模型名固定 `wan2.2-animate-move`。

## 前置检查（每次都先做）

本技能需要阿里云百炼 API Key。先把工作目录切到本 SKILL.md 所在目录，然后跑：

```bash
python scripts/wan_animate.py check
```

若该路径报"找不到文件"，改用技能目录的绝对路径重试（把 `scripts/wan_animate.py` 换成 `<技能目录>/scripts/wan_animate.py`）。**不要因为找不到脚本就放弃或改用别的方式自己写请求。**

- 输出 `"api_key_set": true` → 直接继续。
- 输出 `false` → **停下来问用户要 API Key**，不要自己去猜或写死。告知用户去阿里云百炼控制台创建，并设置环境变量：

```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY="sk-xxxx"
# macOS / Linux
export DASHSCOPE_API_KEY=sk-xxxx
```

**不要把用户的 API Key 写进任何文件、笔记或对话总结。**只在当前会话用环境变量传递。

如果用户希望用业务空间专属域名（更快更稳），让用户提供后设置 `DASHSCOPE_API_HOST`：
`https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com` 或新加坡地域
`https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com`。注意北京和新加坡的 API Key 不通用。

## 执行

```bash
python scripts/wan_animate.py run \
  --image <角色图片路径或URL> \
  --video <参考视频路径或URL> \
  --mode wan-std \
  --out ./output
```

参数说明：

| 参数 | 说明 |
| --- | --- |
| `--image` | 必填。角色图片，本地路径或公网 URL 都可以，本地文件由脚本自动上传到百炼临时存储 |
| `--video` | 必填。参考视频，同上。时长 2~30 秒 |
| `--mode` | `wan-std` 标准模式，快、便宜，默认用它；`wan-pro` 专业模式，画面更流畅但更慢更贵 |
| `--watermark` | 加「AI生成」水印，默认不加 |
| `--out` | 输出目录，默认 `./wan_animate_output` |
| `--no-download` | 只返回结果链接，不落盘。结果链接 24 小时有效，通常还是下载到本地更好 |

脚本会自动完成：上传本地素材 → 创建异步任务 → 每 15 秒轮询 → 下载成品到本地。
单个视频通常要等几分钟，**这是正常的**，别中途报错，让轮询跑完。
最终会从 `RESULT_JSON_BEGIN` / `RESULT_JSON_END` 之间输出结果 JSON，把里面的视频路径告诉用户。

## 素材限制（提交前先检查，能省一轮失败）

- **图片**：JPG/JPEG/PNG/BMP/WEBP，宽高都在 200~4096 px，宽高比 1:3 ~ 3:1，**≤ 5MB**
- **视频**：MP4/AVI/MOV，**时长 2~30 秒**，宽高都在 200~2048 px，宽高比 1:3 ~ 3:1，**≤ 200MB**
- **两张素材必须是公网可访问 URL 或本地文件**。普通网址若需要登录/防盗链会失败，这种情况先让用户把文件下载到本地再走本地路径

超出限制就在调用前告诉用户并说明要怎么处理（裁剪、压缩、转码），不要硬着头皮提交。

## 效果优化（出图差时先排查这几条）

1. 图片和参考视频里的人物**画幅占比要接近** —— 一个全身一个半身基本必翻车
2. 两者的人物**身材比例要一致**
3. 参考视频**分辨率和帧率越高越好**，糊视频会直接拉低成品画质
4. 第一次尝试用 `wan-std` 验动作是否对齐，确认满意后再用 `wan-pro` 出终版 —— pro 模式贵，别上来就烧钱

## 常见错误处理

脚本会把百炼的错误码翻译成人话，你只需要转述给用户：

- `UrlOrFileNotReachable` / `downloadFail` → 链接不通或有鉴权，改走本地文件上传
- `DataInspectionFailed` / `IPInfringementSuspect` → 素材没过内容审核或疑似侵权，换素材
- `Arrearage` / `FreeQuotaExhausted` → 账号欠费或免费额度用完，需要充值/开通付费
- `InvalidApiKey` → Key 失效，让用户重新生成
- `Throttling` → 触发限流，稍等重试
- `InvalidParameter` → 素材尺寸/时长不合规，对照上面的限制检查

计费口径：**输入不计费，按成功生成的视频秒数计费，调用失败不扣费。**具体单价以百炼控制台为准，用户问起时让他去看「模型价格」页，不要凭记忆报价。

如果用户还没提供素材，先问清楚图片和视频在哪，别编造文件路径。
