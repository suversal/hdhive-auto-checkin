let bootstrapToken = "";
const bootstrapParams = new URLSearchParams(location.hash.split("?")[1] || "");
if (bootstrapParams.has("bootstrap")) {
  bootstrapToken = bootstrapParams.get("bootstrap") || "";
  history.replaceState(null, "", location.pathname + "#setup");
}
let csrfToken = "";
class ApiError extends Error {
  constructor(message, code, status, details = {}) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}
async function api(path, { method = "GET", body, headers = {} } = {}) {
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-CSRF-Token": csrfToken } : {}),
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(
      "服务返回了无法识别的响应，请检查服务状态。",
      "BAD_RESPONSE",
      response.status,
    );
  }
  if (!response.ok) {
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      path !== "/auth/status"
    )
      window.dispatchEvent(new Event("shike:unauthorized"));
    throw new ApiError(
      data.message || "操作未完成，请稍后重试。",
      data.code,
      response.status,
      data,
    );
  }
  if (data.csrfToken) csrfToken = data.csrfToken;
  return data;
}
const TASK_FIELDS = [
  "name",
  "accountId",
  "kind",
  "target",
  "targetName",
  "targetType",
  "steps",
  "schedule",
  "time",
  "timezone",
  "weekdays",
  "interval",
  "once",
  "cron",
  "jitter",
  "notify",
  "successWords",
  "failureWords",
  "enabled",
  "revision",
];
function taskPayload(task) {
  return Object.fromEntries(
    TASK_FIELDS.filter((k) => task[k] !== undefined && task[k] !== null).map(
      (k) => [k, task[k]],
    ),
  );
}
function activeRun(run) {
  return ["queued", "running"].includes(run?.status);
}
function sentLabel(run) {
  return run.sendState === "unknown"
    ? "发送结果未确认"
    : run.sent
      ? "已发送"
      : "未发送";
}
function useLiveRun(initial, onComplete) {
  const [run, setRun] = useState(initial),
    [error, setError] = useState("");
  const done = useRef(null),
    callback = useRef(onComplete);
  callback.current = onComplete;
  useEffect(() => {
    if (!run?.id) return;
    let alive = true,
      timer;
    async function refresh() {
      try {
        const latest = await api("/runs/" + run.id);
        if (!alive) return;
        setRun(latest);
        setError("");
        if (!activeRun(latest)) {
          clearInterval(timer);
          if (done.current !== latest.id) {
            done.current = latest.id;
            callback.current?.(latest);
          }
        }
      } catch (e) {
        if (alive) setError(e.message);
      }
    }
    timer = setInterval(refresh, 1000);
    refresh();
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [run?.id]);
  return { run, setRun, error };
}
