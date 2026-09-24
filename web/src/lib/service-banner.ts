import type { Health } from "../types/chat";

export function serviceBanner(health: Health | null | undefined): string | null {
  const state = health?.gateway?.state;
  if (state === "API_UNREACHABLE") return "Kiln 接口没有响应。这不能说明模型进程已经退出。";
  if (state === "VIDEO_SUSPENDED") return "视频任务正在使用内存，文本模型被主动暂停。";
  if (state === "STARTING") return "文本模型正在重新加载。";
  if (state === "OFFLINE") return "连不上本机模型端口。";
  if (state === "DEGRADED") return "模型端口还在，但最近的生成没有正常完成。";
  if (state === "BUSY") return "模型正在回答上一条。";
  const chatState = health?.chat?.state;
  if (!state && chatState && chatState !== "running") {
    return "视频任务正在使用内存，文本模型被主动暂停。";
  }
  if (!state && health && health.provider?.reachable === false) {
    return "模型暂时离线。Mac 上的 mlx 由 LaunchAgent 常驻，通常会在一两分钟内自动拉起，请稍后再发。";
  }
  return null;
}
