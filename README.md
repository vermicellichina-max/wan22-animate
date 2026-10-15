# Wan2.2-Animate 技能包 · 安装说明

把静态人物图 + 参考视频合成动作视频（动作模仿 / 舞蹈复刻 / 动漫角色替身）。
底层是阿里云百炼的 `wan2.2-animate-move` 接口。

```
wan22-animate/
├── SKILL.md              技能本体（Agent 读的就是这个）
├── README.md             本文件
└── scripts/
    └── wan_animate.py    零依赖 Python 脚本，只用标准库
```

---

## 一、装进豆包（电脑版）

> 前置：**必须用豆包电脑客户端，手机版没有入口。**

1. 打开豆包桌面版，左上角从「对话」切到 **「工作」模式**
2. 左侧菜单点 **「技能 / 连接器 / 伙伴」**
3. 右上角 **「+ 新建」** → 选 **「上传技能」**
4. 把整个 `wan22-animate` 文件夹（不用压缩）拖进上传窗口
5. 提示「安装成功」后，**新建一个会话窗口** —— 旧会话识别不到新技能

也可以跳过上传，直接在豆包对话框里说一句话从 GitHub 安装：

> 帮我安装 GitHub 仓库 `vermicellichina-max/wan22-animate` 里的 Wan2.2-Animate 技能

仓库地址：<https://github.com/vermicellichina-max/wan22-animate>

## 二、配置 API Key

技能本身不收钱，但阿里百炼的 API 按生成的视频秒数计费。
去 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 创建 API Key（没有免费额度的新账号需先开通），然后设置环境变量：

```bash
# Windows PowerShell（当前窗口有效）
$env:DASHSCOPE_API_KEY="sk-xxxx"

# 想永久生效，用系统环境变量面板，或：
setx DASHSCOPE_API_KEY "sk-xxxx"

# macOS / Linux
export DASHSCOPE_API_KEY=sk-xxxx
```

**（推荐）使用业务空间专属域名**，性能更稳：

```bash
$env:DASHSCOPE_API_HOST="https://{你的WorkspaceId}.cn-beijing.maas.aliyuncs.com"
```

验证是否配好：

```bash
python scripts/wan_animate.py check
```

看到 `"api_key_set": true` 就成了。

## 三、验证 poc

```bash
python scripts/wan_animate.py run --image 角色.jpg --video 参考动作.mp4 --mode wan-std
```

装好后，日常在豆包里直接说人话就行，不用记命令：

> 让这张图跟着这个视频跳舞：`<图片>` `<视频>`

## 四、计费与限制速查

| 项 | 说明 |
| --- | --- |
| 计费 | **输入不计费**，按成功生成的视频秒数计费；**调用失败不扣费** |
| 模式 | `wan-std` 便宜快 · `wan-pro` 画质好但更慢更贵 |
| 图片 | JPG/PNG/BMP/WEBP，200~4096px，宽高比 1:3~3:1，≤5MB |
| 视频 | MP4/AVI/MOV，**2~30 秒**，200~2048px，≤200MB |
| 时效性 | 结果视频链接 24 小时有效；上传的临时素材 48 小时有效 |

素材不合规会直接失败（不扣费），先对照上表检查再提交。

## 五、通用性

这套 `SKILL.md` 是社区通用技能格式，同一份目录在支持 Skills 标准的 Agent 里都能用（豆包工作、WorkBuddy、Claude Code 等），装一次多处通用。
