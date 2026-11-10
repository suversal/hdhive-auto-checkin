let uiTimezone = "Asia/Shanghai";
const EMPTY_TASK = {
  name: "",
  accountId: "",
  kind: "message",
  target: "",
  targetName: "",
  targetType: "bot",
  steps: [{ type: "send", text: "" }],
  schedule: "daily",
  time: "08:30",
  timezone: "Asia/Shanghai",
  weekdays: [1, 2, 3, 4, 5],
  interval: 24,
  once: "",
  cron: "30 8 * * *",
  jitter: 0,
  notify: "failure",
  successWords: "",
  failureWords: "",
  enabled: true,
};
const TEMPLATES = [
  {
    id: "text",
    name: "机器人文字签到",
    category: "签到",
    icon: "bot",
    color: "",
    desc: "每天给机器人发一句签到指令，收到回复后留档。",
    tag: "最适合第一次使用",
    message: "/checkin",
    steps: [
      { type: "send", text: "/checkin" },
      { type: "wait", seconds: 60 },
    ],
  },
  {
    id: "button",
    name: "带按钮的签到",
    category: "签到",
    icon: "click",
    color: "blue",
    desc: "先发指令，再点击回复中的签到按钮，按顺序完成。",
    tag: "2 分钟配置",
    message: "/start",
    steps: [
      { type: "send", text: "/start" },
      { type: "wait", seconds: 60 },
      { type: "click", text: "每日签到" },
      { type: "wait", seconds: 60 },
    ],
  },
  {
    id: "remind",
    name: "群组定时提醒",
    category: "提醒",
    icon: "users",
    color: "amber",
    desc: "把固定的提醒按时发到群里，省去每天重复输入。",
    tag: "只发送，不等回复",
    message: "新的一天，记得记录今天的进展。",
    steps: [{ type: "send", text: "新的一天，记得记录今天的进展。" }],
  },
  {
    id: "query",
    name: "周期查询",
    category: "查询",
    icon: "search",
    color: "lavender",
    desc: "定期查询积分、配额或服务状态，集中查看原始返回。",
    tag: "保留原始回复",
    message: "/balance",
    steps: [
      { type: "send", text: "/balance" },
      { type: "wait", seconds: 60 },
    ],
  },
  {
    id: "weekly",
    name: "每周备忘",
    category: "提醒",
    icon: "calendar",
    color: "",
    desc: "每周固定时间，把需要记住的事情发给自己。",
    tag: "发送到收藏夹",
    message: "留一点时间，回顾这一周。",
    steps: [{ type: "send", text: "留一点时间，回顾这一周。" }],
  },
];
const STATUS = {
  success: { text: "规则匹配成功", type: "", icon: "check" },
  replied: { text: "已收到回复", type: "blue", icon: "message" },
  sent: { text: "已发送", type: "", icon: "check" },
  timeout: { text: "已发送 · 未等到回复", type: "warn", icon: "clock" },
  failed: { text: "规则匹配失败", type: "danger", icon: "alert" },
  error: { text: "执行异常", type: "danger", icon: "alert" },
  running: { text: "执行中", type: "blue", icon: "loader" },
  queued: { text: "排队中", type: "neutral", icon: "clock" },
  limited: { text: "Telegram 限流", type: "warn", icon: "clock" },
  interrupted: { text: "执行已中断", type: "warn", icon: "alert" },
  skipped: { text: "已跳过过期计划", type: "neutral", icon: "clock" },
  paused: { text: "已暂停", type: "neutral", icon: "pause" },
  cancelled: { text: "已取消", type: "neutral", icon: "close" },
};
function uid(prefix = "id") {
  return (
    prefix +
    "-" +
    Date.now().toString(36) +
    "-" +
    Math.random().toString(36).slice(2, 6)
  );
}
function localOnce(value, timezone) {
  if (!value || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return value || "";
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  })
    .format(new Date(value))
    .replace(" ", "T");
}
function scheduleLabel(t) {
  if (t.schedule === "once") {
    if (!t.once) return "选择单次执行时间";
    if (/(?:Z|[+-]\d{2}:\d{2})$/.test(t.once))
      return `仅一次 · ${formatAt(t.once, false, t.timezone)}`;
    return `仅一次 · ${t.once.replace("T", " ").slice(0, 16)}`;
  }
  return t.schedule === "daily"
    ? `每天 ${t.time}`
    : t.schedule === "weekly"
      ? `每周${t.weekdays.map((x) => "日一二三四五六"[x]).join("、")} ${t.time}`
      : t.schedule === "interval"
        ? `每 ${t.interval} 小时`
        : `Cron · ${t.cron}`;
}
function formatAt(iso, short = false, tz = uiTimezone) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: tz,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    ...(short ? {} : { year: "numeric" }),
  }).format(new Date(iso));
}

function getNextRuns(task, count = 3) {
  return (task.nextRuns || []).slice(0, count).map((d) => new Date(d));
}
function exportJSON(data, name) {
  const a = document.createElement("a"),
    url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
    );
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function dateKey(value, tz = uiTimezone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  return ["year", "month", "day"]
    .map((k) => parts.find((p) => p.type === k).value)
    .join("-");
}
