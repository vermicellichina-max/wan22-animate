#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wan2.2-Animate (wan2.2-animate-move) 命令行工具。

作用：给一张人物图片 + 一段参考视频，生成"跟着视频做动作"的视频。
零第三方依赖，只用 Python 标准库，Copy 即用。

用法:
    python wan_animate.py check
    python wan_animate.py run --image 角色图.jpg --video 参考视频.mp4 --out ./out
    python wan_animate.py run --image https://x/y.jpg --video https://x/z.mp4 --mode wan-pro

环境变量:
    DASHSCOPE_API_KEY   必填，阿里云百炼 API Key
    DASHSCOPE_API_HOST  可选，默认 https://dashscope.aliyuncs.com
                        业务空间专属域名如 https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com
"""

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

MODEL = "wan2.2-animate-move"
DEFAULT_HOST = "https://dashscope.aliyuncs.com"
POLL_INTERVAL = 15          # 秒
MAX_WAIT = 30 * 60          # 最多等 30 分钟
DOWNLOAD_TIMEOUT = 600

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
VIDEO_EXT = (".mp4", ".avi", ".mov")


def _ensure_utf8():
    """Windows 终端 GBK 会炸，强制 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _request(method, url, headers=None, body=None, timeout=60):
    """统一的 HTTP 请求，返回 (status_code, bytes)。"""
    req = urllib.request.Request(url, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, data=body, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode("utf-8", errors="replace")


def get_config():
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    host = os.getenv("DASHSCOPE_API_HOST", "").strip() or DEFAULT_HOST
    return api_key, host.rstrip("/")


# --------------------------------------------------------------------------
# 1. 本地文件 -> 百炼临时存储（oss:// 路径，有效期 48 小时）
# --------------------------------------------------------------------------

def get_upload_policy(api_key, host):
    url = "%s/api/v1/uploads?action=getPolicy&model=%s" % (host, MODEL)
    status, raw = _request(
        "GET", url,
        {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    if status != 200:
        raise RuntimeError("获取上传凭证失败 (HTTP %s): %s" % (status, _safe(raw)))
    try:
        data = json.loads(raw)["data"]
    except Exception:
        raise RuntimeError("解析上传凭证失败: %s" % _safe(raw))
    return data


def build_multipart(fields, file_name, file_bytes, content_type):
    """构造 multipart/form-data；file 字段必须是最后一个。"""
    boundary = "----WanAnimateBoundary" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(("--%s\r\n" % boundary).encode("utf-8"))
        parts.append(('Content-Disposition: form-data; name="%s"\r\n\r\n' % name).encode("utf-8"))
        parts.append(str(value).encode("utf-8") + b"\r\n")
    parts.append(("--%s\r\n" % boundary).encode("utf-8"))
    parts.append(
        ('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % file_name).encode("utf-8")
    )
    parts.append(("Content-Type: %s\r\n\r\n" % content_type).encode("utf-8"))
    parts.append(file_bytes + b"\r\n")
    parts.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def upload_local_file(api_key, host, file_path):
    path = Path(file_path)
    if not path.is_file():
        raise RuntimeError("文件不存在: %s" % file_path)

    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > 100:
        raise RuntimeError("文件 %s 超过 100MB（当前 %.1fMB），请压缩后重试" % (path.name, size_mb))

    data = get_upload_policy(api_key, host)

    # OSS key 里出现中文容易出幺蛾子，统一换成 ASCII 随机名 + 真实后缀
    suffix = path.suffix.lower()
    oss_name = uuid.uuid4().hex + (suffix if suffix else ".bin")
    key = "%s/%s" % (data["upload_dir"], oss_name)

    fields = {
        "OSSAccessKeyId": data["oss_access_key_id"],
        "Signature": data["signature"],
        "policy": data["policy"],
        "x-oss-object-acl": data["x_oss_object_acl"],
        "x-oss-forbid-overwrite": data["x_oss_forbid_overwrite"],
        "key": key,
        "success_action_status": "200",
    }
    body, content_type = build_multipart(
        fields, oss_name, path.read_bytes(),
        mimetypes.guess_type(oss_name)[0] or "application/octet-stream",
    )

    status, raw = _request(
        "POST", data["upload_host"], {"Content-Type": content_type}, body=body, timeout=300
    )
    if status != 200:
        raise RuntimeError("上传到 OSS 失败 (HTTP %s): %s" % (status, _safe(raw)))
    return "oss://" + key


def resolve_input(api_key, host, value, kind):
    """输入既可以是公网 URL，也可以是本地文件路径。"""
    if value.startswith(("http://", "https://", "oss://")):
        return value, False

    path = Path(value)
    if not path.is_file():
        raise RuntimeError("%s 既不是有效 URL，本地文件也不存在: %s" % (kind, value))

    expected = IMAGE_EXT if kind == "图片" else VIDEO_EXT
    if path.suffix.lower() not in expected:
        raise RuntimeError("%s 格式不支持：%s，仅支持 %s" % (kind, path.suffix, "、".join(expected)))

    print("[上传] %s -> 百炼临时存储 ..." % path.name, flush=True)
    oss_url = upload_local_file(api_key, host, value)
    print("[上传] 完成：%s" % oss_url, flush=True)
    return oss_url, True


# --------------------------------------------------------------------------
# 2. 创建任务 + 轮询
# --------------------------------------------------------------------------

def create_task(api_key, host, image_url, video_url, mode, watermark):
    url = "%s/api/v1/services/aigc/image2video/video-synthesis" % host
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "X-DashScope-Async": "enable",
        # 只要 URL 可能是 oss:// 就带上，少了这个头服务端解析不了
        "X-DashScope-OssResourceResolve": "enable",
    }
    payload = {
        "model": MODEL,
        "input": {"image_url": image_url, "video_url": video_url, "watermark": watermark},
        "parameters": {"mode": mode},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, raw = _request("POST", url, headers, body=body, timeout=60)

    if status != 200:
        raise RuntimeError("创建任务失败 (HTTP %s): %s" % (status, explain_error(_safe(raw))))

    data = json.loads(raw)
    task_id = data.get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError("创建任务未返回 task_id: %s" % _safe(raw))
    return task_id


def poll_task(api_key, host, task_id):
    url = "%s/api/v1/tasks/%s" % (host, task_id)
    headers = {"Authorization": "Bearer " + api_key}
    waited = 0

    while waited < MAX_WAIT:
        status, raw = _request("GET", url, headers, timeout=60)
        if status != 200:
            raise RuntimeError("查询任务失败 (HTTP %s): %s" % (status, explain_error(_safe(raw))))

        data = json.loads(raw)
        output = data.get("output", {})
        task_status = output.get("task_status")

        if task_status == "SUCCEEDED":
            return data
        if task_status in ("FAILED", "UNKNOWN", "CANCELED"):
            code = output.get("code") or output.get("message") or ""
            raise RuntimeError("任务失败 [%s]: %s" % (task_status, explain_error(str(code))))

        print("[等待] 已 %ds，当前状态 %s ..." % (waited, task_status), flush=True)
        time.sleep(POLL_INTERVAL)
        waited += POLL_INTERVAL

    raise RuntimeError("等待超时（%d 秒），任务可能仍在排队，请稍后手动查询 task_id=%s" % (MAX_WAIT, task_id))


def download_video(url, save_path):
    status, raw = _request("GET", url, timeout=DOWNLOAD_TIMEOUT)
    if status != 200 or len(raw) < 1024:
        raise RuntimeError("下载结果视频失败 (HTTP %s)" % status)
    Path(save_path).write_bytes(raw)
    return len(raw)


# --------------------------------------------------------------------------
# 错误解释：把官方那堆英文错误码翻成人话
# --------------------------------------------------------------------------

ERROR_HINTS = {
    "Throttling": "触发限流，等一会儿再试；生产环境建议申请更高配额。",
    "InvalidApiKey": "DASHSCOPE_API_KEY 无效或已失效，去百炼控制台重新生成。",
    "UrlOrFileNotReachable": "图片/视频 URL 公网访问不了。本地文件请用本地路径交给脚本自动上传。",
    "DataInspectionFailed": "输入内容没过内容安全审核，换素材试试。",
    "IPInfringementSuspect": "输入素材疑似存在侵权风险，换素材试试。",
    "downloadFail": "输入 URL 下载失败，确认链接可公网直连且不带鉴权。",
    "InvalidParameter": "参数不合规，检查图片/视频的尺寸、时长、大小限制。",
    "Arrearage": "账号欠费，充值后重试。",
    "FreeQuotaExhausted": "免费额度用完了，需要开通付费。",
    "does not support synchronous": "请求头缺少 X-DashScope-Async: enable。",
}


def explain_error(text):
    text = str(text)
    hint = ""
    for key, value in ERROR_HINTS.items():
        if key in text:
            hint = "\n提示：%s" % value
            break
    return text + hint


def _safe(raw, limit=800):
    try:
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    except Exception:
        text = "<无法解码的响应>"
    return text[:limit]


# --------------------------------------------------------------------------
# 子命令
# --------------------------------------------------------------------------

def cmd_check(_args):
    api_key, host = get_config()
    result = {"api_key_set": bool(api_key), "host": host, "model": MODEL}
    if api_key:
        result["api_key_preview"] = api_key[:6] + "****" + api_key[-4:]
    else:
        result["hint"] = "请设置环境变量 DASHSCOPE_API_KEY（阿里云百炼控制台获取）"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if api_key else 1


def cmd_run(args):
    api_key, host = get_config()
    if not api_key:
        print("错误：未检测到 DASHSCOPE_API_KEY。\n"
              "请先在阿里云百炼控制台创建 API Key，然后设置环境变量后重试：\n"
              "  Windows PowerShell:  $env:DASHSCOPE_API_KEY=\"sk-xxxx\"\n"
              "  macOS / Linux:       export DASHSCOPE_API_KEY=sk-xxxx")
        return 1

    image_url, _ = resolve_input(api_key, host, args.image, "图片")
    video_url, _ = resolve_input(api_key, host, args.video, "参考视频")

    print("[提交] mode=%s watermark=%s" % (args.mode, args.watermark), flush=True)
    task_id = create_task(api_key, host, image_url, video_url, args.mode, args.watermark)
    print("[提交] 成功，task_id=%s" % task_id, flush=True)

    data = poll_task(api_key, host, task_id)
    output = data.get("output", {})
    result_url = output.get("results", {}).get("video_url") or output.get("video_url")

    if not result_url:
        raise RuntimeError("任务成功但未返回 video_url: %s" % json.dumps(data, ensure_ascii=False))

    usage = data.get("usage", {})
    print("[完成] 时长 %ss / %s，结果链接 24 小时内有效。" % (
        usage.get("video_duration", "?"), usage.get("video_ratio", args.mode)), flush=True)

    if not args.no_download:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        save_path = out_dir / ("wan_animate_%s.mp4" % task_id[:8])
        size = download_video(result_url, str(save_path))
        print("[下载] 已保存：%s（%.2f MB）" % (save_path, size / (1024 * 1024)), flush=True)
        result_url = str(save_path.resolve())

    print("\nRESULT_JSON_BEGIN")
    print(json.dumps({
        "task_id": task_id,
        "mode": args.mode,
        "video": result_url,
        "duration": usage.get("video_duration"),
    }, ensure_ascii=False, indent=2))
    print("RESULT_JSON_END")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="wan_animate", description="Wan2.2-Animate 图生动作（阿里云百炼）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="检查环境变量配置")

    run_cmd = sub.add_parser("run", help="生成动作视频")
    run_cmd.add_argument("--image", required=True, help="角色图片：本地路径或公网 URL")
    run_cmd.add_argument("--video", required=True, help="参考视频：本地路径或公网 URL，2~30 秒")
    run_cmd.add_argument("--mode", default="wan-std", choices=["wan-std", "wan-pro"],
                         help="wan-std 快且便宜（默认），wan-pro 画质更好但更贵更慢")
    run_cmd.add_argument("--watermark", action="store_true", help="右下角添加「AI生成」水印")
    run_cmd.add_argument("--out", default="./wan_animate_output", help="视频保存目录")
    run_cmd.add_argument("--no-download", action="store_true", help="只返回结果链接，不下载到本地")

    return parser


def main():
    _ensure_utf8()
    args = build_parser().parse_args()
    try:
        if args.command == "check":
            return cmd_check(args)
        return cmd_run(args)
    except RuntimeError as exc:
        print("\n错误：%s" % exc, file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
