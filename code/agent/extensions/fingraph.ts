/**
 * FinGraphAgent 的终端品牌、网页定位与工具调用联动。
 *
 * 仅使用 Pi 官方扩展接口：
 * - TUI 启动页与终端标题
 * - /web：检查 FINGRAPH_WEB_URL 的 /api/health 后打开现有网页
 *
 * 研究工具由 MCP 提供，/usage 由用量扩展提供。
 */

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import open from "open";
import { WORDMARK } from "../ui/wordmark.ts";

export const PRODUCT_NAME = "FinGragh Agent";
export const PRODUCT_DESCRIPTION = "金融知识图谱智能体";
export const PRODUCT_VERSION = "0.2.0";

type ThemeLike = {
  fg: (color: string, text: string) => string;
};

type HeaderContext = {
  model?: { name?: string; id?: string };
};

function getModelLabel(ctx: HeaderContext): string {
  const name = ctx.model?.name?.trim();
  if (name) return name;
  const id = ctx.model?.id?.trim();
  return id || "未选择模型";
}

function getResearchDate(): string {
  const value = (process.env.FINGRAPH_AS_OF ?? "").trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : "未设置";
}

function getWebUrl(): string {
  const raw = (process.env.FINGRAPH_WEB_URL ?? "").trim();
  if (!raw) {
    throw new Error("未设置 FINGRAPH_WEB_URL，请由启动器配置研究网页地址");
  }

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("FINGRAPH_WEB_URL 不是有效 URL");
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("FINGRAPH_WEB_URL 只允许 http:// 或 https://");
  }
  if (parsed.username || parsed.password) {
    throw new Error("FINGRAPH_WEB_URL 不应包含用户名或密码");
  }
  return parsed.toString().replace(/\/$/, "");
}

export function buildHeader(theme: ThemeLike, ctx: HeaderContext): {
  invalidate(): void;
  render(width: number): string[];
} {
  const accent = (text: string) => theme.fg("accent", text);
  const muted = (text: string) => theme.fg("muted", text);
  const model = getModelLabel(ctx);
  const asOf = getResearchDate();

  return {
    invalidate() {},
    render(width: number): string[] {
      const columns = Math.max(1, width);
      const indent = columns >= 24 ? "  " : "";
      const wide = WORDMARK.finGragh.map((line, row) =>
        accent(line) + " " + theme.fg("mdHeading", WORDMARK.agent[row]));
      const logo = columns >= visibleWidth(WORDMARK.finGragh[0] + " " + WORDMARK.agent[0]) + indent.length
        ? wide
        : columns >= visibleWidth(WORDMARK.finGragh[0]) + indent.length
          ? [...WORDMARK.finGragh.map(accent), "", ...WORDMARK.agent.map(line => theme.fg("mdHeading", line))]
          : columns >= visibleWidth(WORDMARK.compact[0]) + indent.length
            ? WORDMARK.compact.map(accent)
            : [];
      const fit = (line: string) => truncateToWidth(indent + line, columns);
      return [
        "",
        ...logo.map(fit),
        "",
        fit(`${accent(PRODUCT_NAME)}  ${muted(PRODUCT_VERSION)}  ·  ${PRODUCT_DESCRIPTION}`),
        fit(`${model}  ${muted("·")}  研究日期 ${asOf}`),
        fit(`${accent("/web")} 打开图谱   ${accent("/model")} 模型   ${accent("/usage")} 用量`),
        "",
      ];
    },
  };
}

export default function fingraphExtension(pi: ExtensionAPI) {
  let currentEvent: string | undefined;
  pi.on("session_start", async (_event: unknown, ctx: ExtensionContext) => {
    currentEvent = undefined;
    if (ctx.mode !== "tui") return;
    ctx.ui.setHeader((_tui, theme) => buildHeader(theme, ctx));
    ctx.ui.setTitle(`${PRODUCT_NAME} · ${PRODUCT_DESCRIPTION}`);
    ctx.ui.setStatus("fingraph", "/web · /model · /usage");
  });

  pi.on("tool_execution_end", async event => {
    if (event.isError || event.toolName !== "mcp__fingraph__related_stocks") return;
    for (const item of event.result?.content ?? []) {
      if (item.type !== "text") continue;
      try {
        const result = JSON.parse(item.text);
        if (result.found && typeof result.event?.id === "string") currentEvent = result.event.id;
      } catch { /* Other MCP content does not change the research selection. */ }
    }
  });

  pi.registerCommand("web", {
    description: "检查研究服务并打开图谱网页；--no-open 只检查",
    handler: async (rawArgs: string, ctx: ExtensionContext) => {
      const arg = rawArgs.trim();
      if (arg && arg !== "--no-open") {
        ctx.ui.notify("仅支持 --no-open；网页地址由 FINGRAPH_WEB_URL 配置", "error");
        return;
      }

      let base: string;
      try {
        base = getWebUrl();
      } catch (error) {
        ctx.ui.notify(String(error instanceof Error ? error.message : error), "error");
        return;
      }

      try {
        const response = await fetch(`${base}/api/health`, {
          headers: { accept: "application/json" },
          signal: AbortSignal.timeout(3000),
        });
        if (!response.ok) {
          ctx.ui.notify(`研究服务返回 HTTP ${response.status}：${base}`, "warning");
          return;
        }

        try {
          const payload = (await response.json()) as { status?: string };
          if (payload.status !== "ok") throw new Error("研究服务尚未就绪");
        } catch {
          ctx.ui.notify(`研究服务未返回有效的健康状态：${base}`, "warning");
          return;
        }

        const target = new URL(base);
        if (currentEvent) target.searchParams.set("event", currentEvent);
        const targetUrl = currentEvent ? target.toString() : base;

        if (arg === "--no-open") {
          ctx.ui.notify(`研究服务正常：${targetUrl}（未打开网页）`, "info");
          return;
        }

        try {
          await open(targetUrl, { wait: false });
        } catch (error) {
          ctx.ui.notify(
            `无法打开网页：${String(error instanceof Error ? error.message : error)}`,
            "error",
          );
          return;
        }
        ctx.ui.notify(`已打开研究网页：${targetUrl}`, "info");
      } catch {
        ctx.ui.notify(
          `研究服务不可达：${base}\n请重新运行项目启动命令。`,
          "warning",
        );
      }
    },
  });
}
