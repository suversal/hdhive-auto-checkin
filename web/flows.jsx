function TaskEditor({ draft, store, actions, onSave, onCancel }) {
  const [task, setTask] = useState(() => ({
    ...structuredClone(EMPTY_TASK),
    timezone: store.settings.timezone,
    notify: store.settings.notification,
    accountId: store.accounts.find((a) => a.status === "connected")?.id || "",
    ...structuredClone(draft || {}),
    ...(draft?.once
      ? {
          once: localOnce(
            draft.once,
            draft.timezone || store.settings.timezone,
          ),
        }
      : {}),
  }));
  const [step, setStep] = useState(draft?.id ? 1 : draft?.fromTemplate ? 1 : 0),
    [errors, setErrors] = useState({}),
    [targetSearch, setTargetSearch] = useState(""),
    [showTargets, setShowTargets] = useState(!task.target),
    [showDiscard, setShowDiscard] = useState(false),
    [exitAction, setExitAction] = useState(null),
    [targets, setTargets] = useState([]),
    [targetsError, setTargetsError] = useState(""),
    [targetsLoading, setTargetsLoading] = useState(false),
    [busy, setBusy] = useState(false),
    [submitError, setSubmitError] = useState("");
  const original = useRef(JSON.stringify(taskPayload(task)));
  const change = (key, value) => {
    setTask((t) => ({ ...t, [key]: value }));
    setErrors((e) => ({ ...e, [key]: null }));
  };
  useEffect(() => {
    actions.registerGuard(
      JSON.stringify(taskPayload(task)) !== original.current
        ? (proceed) => {
            setExitAction(() => proceed);
            setShowDiscard(true);
          }
        : null,
    );
    return () => actions.registerGuard(null);
  }, [task]);

  useEffect(() => {
    if (step !== 1 || !task.accountId) return;
    let alive = true;
    setTargetsError("");
    setTargets([]);
    setTargetsLoading(true);
    api("/accounts/" + task.accountId + "/dialogs")
      .then((data) => {
        if (alive) {
          setTargets(data);
          setTargetsLoading(false);
        }
      })
      .catch((e) => {
        if (alive) {
          setTargetsError(e.message);
          setTargetsLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [step, task.accountId]);
  const scheduleKey = JSON.stringify([
    task.schedule,
    task.time,
    task.timezone,
    task.weekdays,
    task.interval,
    task.once,
    task.cron,
  ]);
  useEffect(() => {
    let alive = true;
    setTask((t) => ({ ...t, nextRuns: [], previewLoading: true }));
    if (
      (task.schedule === "once" && !task.once) ||
      (task.schedule === "cron" && task.cron.trim().split(/\s+/).length !== 5)
    ) {
      setTask((t) => ({ ...t, previewLoading: false }));
      return;
    }
    const timer = setTimeout(() => {
      api("/tasks/preview", {
        method: "POST",
        body: {
          ...taskPayload(task),
          name: "时间预览",
          accountId: "",
          target: "me",
          steps: [{ type: "send", text: "时间预览" }],
          enabled: false,
        },
      })
        .then((data) => {
          if (alive)
            setTask((t) => ({
              ...t,
              nextRuns: data.nextRuns,
              previewLoading: false,
            }));
        })
        .catch(() => {
          if (alive)
            setTask((t) => ({ ...t, nextRuns: [], previewLoading: false }));
        });
    }, 300);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [scheduleKey]);
  function cancel() {
    if (JSON.stringify(taskPayload(task)) !== original.current)
      setShowDiscard(true);
    else onCancel();
  }
  useEffect(() => {
    const warn = (e) => {
      if (JSON.stringify(taskPayload(task)) !== original.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [task]);
  function validate() {
    let err = {};
    if (step === 1) {
      if (!task.name.trim()) err.name = "给任务起个容易记住的名字";
      if (!task.accountId) err.accountId = "请先添加并选择一个 Telegram 账号";
      else if (
        store.accounts.find((a) => a.id === task.accountId)?.status !==
        "connected"
      )
        err.accountId = "这个账号需要重新登录，才能执行任务";
      if (!task.target.trim()) err.target = "请选择一个会话，或填写目标地址";
      else if (!/^(@[A-Za-z0-9_]{4,}|-?\d+|me)$/.test(task.target.trim()))
        err.target = "填写 @用户名、数字会话 ID，或选择收藏夹";
    }
    if (step === 2) {
      if (!task.steps.length) err.steps = "至少添加一个发送消息步骤";
      if (task.steps[0]?.type !== "send") err.steps = "第一步需要先发送消息";
      task.steps.forEach((s, i) => {
        if (["send", "click"].includes(s.type) && !s.text.trim())
          err["step" + i] =
            s.type === "send" ? "请输入要发送的消息" : "填写需要点击的按钮文字";
        if (s.type === "send" && s.text.length > 4096)
          err["step" + i] = "消息最长支持 4096 个字符";
        if (
          ["wait", "delay"].includes(s.type) &&
          (!s.seconds || s.seconds < 1 || s.seconds > 600)
        )
          err["step" + i] = "等待时间应为 1–600 秒";
        if (
          s.type === "click" &&
          [...task.steps.slice(0, i)].reverse().find((s) => s.type !== "delay")
            ?.type !== "wait"
        )
          err["step" + i] = "点击按钮前，请先添加“等待回复”步骤";
      });
    }
    if (step === 3) {
      if (["daily", "weekly"].includes(task.schedule) && !task.time)
        err.time = "请选择执行时间";
      if (task.schedule === "weekly" && !task.weekdays.length)
        err.weekdays = "至少选择一天";
      if (
        task.schedule === "interval" &&
        (!task.interval || task.interval < 1 || task.interval > 720)
      )
        err.interval = "间隔应为 1–720 小时";
      if (task.schedule === "once" && !task.once)
        err.once = "请选择未来的执行时间";
      if (
        task.schedule === "cron" &&
        task.cron.trim().split(/\s+/).length !== 5
      )
        err.cron = "请填写五位 Cron，例如 30 8 * * *";
      if (task.jitter < 0 || task.jitter > 120)
        err.jitter = "随机延迟应为 0–120 分钟";
    }
    setErrors(err);
    if (Object.keys(err).length) {
      setTimeout(
        () => document.querySelector('[aria-invalid="true"]')?.focus(),
        0,
      );
      return false;
    }
    return true;
  }
  const move = async () => {
    if (!validate()) return;
    setBusy(true);
    setSubmitError("");
    try {
      if (step === 1) {
        const resolved = await api("/targets/resolve", {
          method: "POST",
          body: { accountId: task.accountId, target: task.target },
        });
        setTask((t) => ({ ...t, ...resolved }));
      }
      if (step < 3) {
        setStep(step + 1);
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else
        await onSave({
          ...task,
          name: task.name.trim(),
          target: task.target.trim(),
        });
    } catch (e) {
      setSubmitError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const updateStep = (i, key, value) =>
    change(
      "steps",
      task.steps.map((s, j) => (j === i ? { ...s, [key]: value } : s)),
    );
  const reorder = (i, delta) => {
    const list = [...task.steps],
      other = i + delta;
    if (other < 0 || other >= list.length) return;
    [list[i], list[other]] = [list[other], list[i]];
    change("steps", list);
  };
  const waitsForReply = task.steps.some((s) => s.type === "wait");
  const simpleMessage =
    task.steps[0]?.type === "send" &&
    (task.steps.length === 1 ||
      (task.steps.length === 2 && task.steps[1].type === "wait"));
  return (
    <section data-screen-label={draft?.id ? "编辑任务" : "创建任务"}>
      <PageHeader
        title={draft?.id ? "调整这个安排" : "安排一件新的小事"}
        description="不用写代码，一步一步填好就可以。"
      >
        <Button variant="ghost" onClick={cancel}>
          取消
        </Button>
      </PageHeader>
      <Steps
        labels={["选择方式", "账号与目标", "操作内容", "时间与确认"]}
        current={step}
      />
      <div className="form-layout">
        <div className="panel form-card">
          {submitError && (
            <div className="mb-24">
              <Notice type="error">{submitError}</Notice>
            </div>
          )}
          <h2>
            {
              [
                "想让它帮你做什么？",
                "用谁的账号，发送给谁？",
                "按这个顺序做。",
                "最后，给它安排一个时间。",
              ][step]
            }
          </h2>
          <p>
            {
              [
                "从最简单的一条消息开始，也可以加上按钮操作。",
                "选择账号和目标会话，不需要记住一串 ID。",
                "消息会按原文发送。保存之前，还可以检查完整配置。",
                "确认后开启计划，保存操作不会立即发送消息。",
              ][step]
            }
          </p>
          {step === 0 && (
            <>
              <div className="choice-grid">
                {[
                  [
                    "message",
                    "message",
                    "发送一条消息",
                    "默认只发送，发给个人、群组或自己的收藏夹。",
                  ],
                  [
                    "buttons",
                    "click",
                    "消息＋按钮操作",
                    "先发指令，再点击回复里的按钮。",
                  ],
                ].map(([kind, icon, title, desc]) => (
                  <button
                    key={kind}
                    className={"choice " + (task.kind === kind ? "active" : "")}
                    aria-label={title}
                    aria-pressed={task.kind === kind}
                    onClick={() => {
                      change("kind", kind);
                      change(
                        "steps",
                        kind === "buttons"
                          ? [
                              { type: "send", text: "/start" },
                              { type: "wait", seconds: 60 },
                              { type: "click", text: "每日签到" },
                              { type: "wait", seconds: 60 },
                            ]
                          : [{ type: "send", text: "" }],
                      );
                    }}
                  >
                    <div
                      className={
                        "iconbox " + (kind === "buttons" ? "blue" : "")
                      }
                    >
                      <Icon name={icon} />
                    </div>
                    {task.kind === kind && (
                      <span className="checkmark">
                        <Icon name="check" size={15} />
                      </span>
                    )}
                    <h3>{title}</h3>
                    <p>{desc}</p>
                  </button>
                ))}
              </div>
              <div className="divider" />
              <div className="between wrap">
                <div>
                  <h3>还没想好怎么配置？</h3>
                  <p className="mini-note mt-8">看看常见场景的现成模板。</p>
                </div>
                <Button
                  variant="soft"
                  icon="layers"
                  onClick={() => actions.navigate("templates")}
                >
                  从模板开始
                </Button>
              </div>
            </>
          )}
          {step === 1 && (
            <>
              <Field
                label="任务名称"
                id="task-name"
                error={errors.name}
                hint="建议写清楚用途，例如“HDHive 每日签到”。"
              >
                <input
                  id="task-name"
                  placeholder="给这件小事起个名字"
                  maxLength={60}
                  value={task.name}
                  onChange={(e) => change("name", e.target.value)}
                  onBlur={() => {
                    if (!task.name.trim())
                      setErrors((e) => ({ ...e, name: "请输入任务名称" }));
                  }}
                />
              </Field>
              <Field
                label="执行账号"
                id="task-account"
                error={errors.accountId}
                hint="消息将以这个 Telegram 账号的身份发送。"
              >
                <SelectControl
                  id="task-account"
                  value={task.accountId}
                  onChange={(e) => {
                    change("accountId", e.target.value);
                    change("target", "");
                    change("targetName", "");
                  }}
                >
                  <option value="">选择一个 Telegram 账号</option>
                  {store.accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                      {a.status !== "connected" ? " · 需要重新登录" : ""}
                    </option>
                  ))}
                </SelectControl>
              </Field>
              {(!store.accounts.length ||
                store.accounts.find((a) => a.id === task.accountId)?.status !==
                  "connected") && (
                <button
                  className="text-btn"
                  style={{ marginTop: -10, marginBottom: 20 }}
                  onClick={() =>
                    actions.addAccount(
                      store.accounts.find((a) => a.id === task.accountId),
                    )
                  }
                >
                  <Icon name="plus" size={14} />
                  {store.accounts.length
                    ? "重新登录这个账号"
                    : "添加 Telegram 账号"}
                </button>
              )}
              <Field
                label="目标会话"
                id="task-target"
                error={errors.target}
                hint="确认接收方后再继续。发给自己会进入 Telegram 收藏夹，仅你本人可见。"
              >
                <TargetPicker
                  id="task-target"
                  value={task.target}
                  name={task.targetName}
                  targets={targets}
                  error={targetsError}
                  loading={targetsLoading}
                  onSelect={(t) => {
                    change("target", t.id);
                    change("targetName", t.name);
                    change("targetType", t.type);
                  }}
                />
              </Field>
            </>
          )}
          {step === 2 && (
            <>
              <div className="mb-24">
                {simpleMessage && (
                  <div className="between mb-16" style={{ gap: 20 }}>
                    <div>
                      <h3>等待对方回复</h3>
                      <p className="mini-note mt-8">
                        机器人签到或查询需要回复时再开启。
                      </p>
                    </div>
                    <Toggle
                      label="等待对方回复"
                      checked={waitsForReply}
                      onChange={(enabled) => {
                        change(
                          "steps",
                          enabled
                            ? [task.steps[0], { type: "wait", seconds: 60 }]
                            : [task.steps[0]],
                        );
                        setErrors({});
                      }}
                    />
                  </div>
                )}
                <Notice type={waitsForReply ? "" : "info"}>
                  {waitsForReply ? (
                    <>
                      当前流程需要收到回复才会继续。普通账号、群组和收藏夹不一定会回复。
                      {simpleMessage
                        ? "如果只想发消息，关闭上方开关即可。"
                        : "如果只想发消息，请移除等待回复步骤；按钮操作需要先收到回复。"}
                    </>
                  ) : (
                    "消息发送完成后即结束，不要求对方回复。"
                  )}
                </Notice>
              </div>
              {errors.steps && (
                <div className="mb-24">
                  <Notice type="error">{errors.steps}</Notice>
                </div>
              )}
              {task.steps.map((s, i) => (
                <div className="action-step" key={i}>
                  <span className="action-step-index">{i + 1}</span>
                  <div className="action-step-card">
                    <div className="between">
                      <h3 className="row" style={{ gap: 7 }}>
                        <Icon
                          name={
                            s.type === "send"
                              ? "message"
                              : ["wait", "delay"].includes(s.type)
                                ? "clock"
                                : "click"
                          }
                          size={14}
                        />
                        {s.type === "send"
                          ? "发送消息"
                          : s.type === "wait"
                            ? "等待回复"
                            : s.type === "delay"
                              ? "间隔等待"
                              : "点击按钮"}
                      </h3>
                      <div className="row" style={{ gap: 0 }}>
                        <IconButton
                          name="up"
                          label={"上移第 " + (i + 1) + " 步"}
                          disabled={i === 0}
                          onClick={() => reorder(i, -1)}
                        />
                        <IconButton
                          name="down"
                          label={"下移第 " + (i + 1) + " 步"}
                          disabled={i === task.steps.length - 1}
                          onClick={() => reorder(i, 1)}
                        />
                        <IconButton
                          name="trash"
                          label={"移除第 " + (i + 1) + " 步"}
                          disabled={task.steps.length === 1}
                          onClick={() =>
                            change(
                              "steps",
                              task.steps.filter((_, j) => i !== j),
                            )
                          }
                        />
                      </div>
                    </div>
                    {s.type === "send" ? (
                      <>
                        <Field
                          label="消息内容"
                          id={"action-" + i}
                          error={errors["step" + i]}
                          hint={`${s.text.length} / 4096 · 日期变量在执行时按任务时区替换`}
                        >
                          <textarea
                            id={"action-" + i}
                            value={s.text}
                            placeholder="例如 /checkin，或者你想发送的一句话"
                            onChange={(e) =>
                              updateStep(i, "text", e.target.value)
                            }
                          />
                        </Field>
                        <div className="variable-chips">
                          <span>插入变量</span>
                          {[
                            ["{{date}}", "日期"],
                            ["{{time}}", "时间"],
                            ["{{weekday}}", "星期"],
                          ].map(([token, label]) => (
                            <button
                              type="button"
                              key={token}
                              onClick={() =>
                                updateStep(i, "text", s.text + token)
                              }
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      </>
                    ) : ["wait", "delay"].includes(s.type) ? (
                      <Field
                        label={
                          s.type === "delay" ? "间隔秒数" : "最长等待时间（秒）"
                        }
                        id={"action-" + i}
                        error={errors["step" + i]}
                        hint={
                          s.type === "delay"
                            ? "等待指定秒数后继续下一步，不要求对方回复。"
                            : "仅在需要对方回复时使用；超时只表示没等到回复，已发送的消息不会重发。"
                        }
                      >
                        <input
                          type="number"
                          min="1"
                          max="600"
                          id={"action-" + i}
                          value={s.seconds}
                          onChange={(e) =>
                            updateStep(i, "seconds", Number(e.target.value))
                          }
                        />
                      </Field>
                    ) : (
                      <Field
                        label="按钮上的文字"
                        id={"action-" + i}
                        error={errors["step" + i]}
                        hint="从上一步收到的消息中，查找文字完全相同的按钮。"
                      >
                        <input
                          id={"action-" + i}
                          value={s.text}
                          placeholder="例如 每日签到"
                          onChange={(e) =>
                            updateStep(i, "text", e.target.value)
                          }
                        />
                      </Field>
                    )}
                  </div>
                </div>
              ))}
              <div className="row" style={{ paddingLeft: 37 }}>
                <SelectControl
                  className="select-filter"
                  aria-label="添加操作步骤"
                  value=""
                  onChange={(e) => {
                    if (e.target.value)
                      change("steps", [
                        ...task.steps,
                        ["wait", "delay"].includes(e.target.value)
                          ? {
                              type: e.target.value,
                              seconds: e.target.value === "delay" ? 3 : 60,
                            }
                          : { type: e.target.value, text: "" },
                      ]);
                  }}
                >
                  <option value="">＋ 添加一个步骤</option>
                  <option value="send">发送消息</option>
                  <option value="wait">等待回复</option>
                  <option value="click">点击按钮</option>
                  <option value="delay">间隔等待</option>
                </SelectControl>
              </div>
              <details className="advanced">
                <summary>进阶：如何判断业务结果</summary>
                <p className="mini-note mb-24">
                  默认保留原始回复。只在你知道机器人回复含义时，设置关键词规则；多个关键词用逗号分隔，任意一个匹配即命中。失败规则优先。
                </p>
                <Field label="成功关键词" id="success-words" optional>
                  <input
                    id="success-words"
                    value={task.successWords}
                    placeholder="例如 签到成功,已经签到"
                    onChange={(e) => change("successWords", e.target.value)}
                  />
                </Field>
                <Field label="失败关键词" id="failure-words" optional>
                  <input
                    id="failure-words"
                    value={task.failureWords}
                    placeholder="例如 余额不足,未绑定"
                    onChange={(e) => change("failureWords", e.target.value)}
                  />
                </Field>
              </details>
            </>
          )}
          {step === 3 && (
            <>
              <Field label="什么时候执行" id="schedule-mode">
                <SelectControl
                  id="schedule-mode"
                  value={task.schedule}
                  onChange={(e) => change("schedule", e.target.value)}
                >
                  <option value="daily">每天固定时间</option>
                  <option value="weekly">每周指定日期</option>
                  <option value="interval">固定时间间隔</option>
                  <option value="once">只执行一次</option>
                  <option value="cron">自定义 Cron（进阶）</option>
                </SelectControl>
              </Field>
              {task.schedule === "weekly" && (
                <div>
                  <div className="field-label">选择星期</div>
                  <div className="weekday-picker">
                    {[1, 2, 3, 4, 5, 6, 0].map((d) => (
                      <button
                        aria-pressed={task.weekdays.includes(d)}
                        className={task.weekdays.includes(d) ? "active" : ""}
                        key={d}
                        onClick={() =>
                          change(
                            "weekdays",
                            task.weekdays.includes(d)
                              ? task.weekdays.filter((x) => x !== d)
                              : [...task.weekdays, d],
                          )
                        }
                      >
                        周{"日一二三四五六"[d]}
                      </button>
                    ))}
                  </div>
                  {errors.weekdays && (
                    <p
                      className="error"
                      style={{ color: "var(--danger)", fontSize: 11 }}
                    >
                      {errors.weekdays}
                    </p>
                  )}
                </div>
              )}
              <div className="fields-2">
                {["daily", "weekly"].includes(task.schedule) ? (
                  <Field
                    label="执行时间"
                    id="schedule-time"
                    error={errors.time}
                  >
                    <TimePicker
                      id="schedule-time"
                      value={task.time}
                      onChange={(e) => change("time", e.target.value)}
                    />
                  </Field>
                ) : task.schedule === "interval" ? (
                  <Field
                    label="间隔小时数"
                    id="interval-hours"
                    error={errors.interval}
                    hint="以任务保存或重新开启时的时间为间隔起点。"
                  >
                    <input
                      type="number"
                      min="1"
                      max="720"
                      id="interval-hours"
                      value={task.interval}
                      onChange={(e) =>
                        change("interval", Number(e.target.value))
                      }
                    />
                  </Field>
                ) : task.schedule === "once" ? (
                  <Field label="日期与时间" id="once-date" error={errors.once}>
                    <DateTimePicker
                      timezone={task.timezone}
                      id="once-date"
                      value={task.once}
                      onChange={(e) => change("once", e.target.value)}
                    />
                  </Field>
                ) : (
                  <Field
                    label="Cron 表达式"
                    id="cron-value"
                    error={errors.cron}
                  >
                    <input
                      id="cron-value"
                      className="mono"
                      value={task.cron}
                      onChange={(e) => change("cron", e.target.value)}
                    />
                  </Field>
                )}
                <Field label="时区" id="task-timezone">
                  <TimezonePicker
                    id="task-timezone"
                    value={task.timezone}
                    onChange={(e) => change("timezone", e.target.value)}
                  />
                </Field>
              </div>
              {task.schedule === "cron" && (
                <>
                  <div className="cron-presets">
                    {[
                      ["30 8 * * *", "每天 08:30"],
                      ["30 8 * * 1-5", "工作日 08:30"],
                      ["0 */6 * * *", "每 6 小时"],
                    ].map(([value, label]) => (
                      <button
                        type="button"
                        key={value}
                        onClick={() => change("cron", value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <p className="mini-note mb-24">
                    五位顺序：分钟、小时、日期、月份、星期。例：30 8 * * *
                    表示每天 08:30。
                  </p>
                </>
              )}
              <Field label="通知方式" id="task-notify">
                <SelectControl
                  id="task-notify"
                  value={task.notify}
                  onChange={(e) => change("notify", e.target.value)}
                >
                  <option value="failure">仅异常时通知（推荐）</option>
                  <option value="summary">加入每日摘要</option>
                  <option value="all">每次执行都通知</option>
                  <option value="none">不通知</option>
                </SelectControl>
              </Field>
              <details className="advanced">
                <summary>进阶：时间与恢复策略</summary>
                <Field
                  label="随机延迟（分钟）"
                  id="task-jitter"
                  hint="每次在计划时间之后随机延迟，设为 0 表示准时执行。"
                  error={errors.jitter}
                >
                  <input
                    type="number"
                    min="0"
                    max="120"
                    id="task-jitter"
                    value={task.jitter}
                    onChange={(e) => change("jitter", Number(e.target.value))}
                  />
                </Field>
                <p className="mini-note">
                  恢复规则：同一账号依次执行；尊重 Telegram
                  限流等待；发送结果不确定时不自动重发。服务错过的计划默认跳过，避免恢复时集中发送。
                </p>
              </details>
              <div className="divider" />
              <div className="between">
                <div>
                  <h3>保存后自动执行</h3>
                  <p className="mini-note mt-8">
                    也可以先关闭，确认配置后再开启。
                  </p>
                </div>
                <Toggle
                  label="保存后开启任务"
                  checked={task.enabled}
                  onChange={(v) => change("enabled", v)}
                />
              </div>
              <div className="notice info mt-24">
                <Icon name="check" size={15} />
                <div>
                  <strong>{task.name || "新任务"}</strong> 将由{" "}
                  <strong>
                    {store.accounts.find((a) => a.id === task.accountId)?.name}
                  </strong>{" "}
                  向 <strong>{task.targetName || task.target}</strong> 执行{" "}
                  {task.steps.length} 个步骤。
                  <div className="mini-note mt-8">
                    {scheduleLabel(task)} · {task.timezone}
                  </div>
                </div>
              </div>
              <div
                className="mobile-schedule-preview mt-16"
                style={{ fontSize: 11, color: "var(--muted)" }}
              >
                接下来：
                {getNextRuns(task, 1)[0]
                  ? formatAt(getNextRuns(task, 1)[0], false, task.timezone)
                  : "暂无匹配时间"}
                {task.jitter > 0 ? `，再随机延迟 0–${task.jitter} 分钟` : ""}
              </div>
            </>
          )}
          <div className="form-footer">
            <div>
              {step > 0 ? (
                <Button
                  icon="back"
                  variant="ghost"
                  onClick={() => {
                    setErrors({});
                    setStep(step - 1);
                  }}
                >
                  上一步
                </Button>
              ) : (
                <span className="mini-note">配置可以随时修改</span>
              )}
            </div>
            <Button variant="primary" disabled={busy} onClick={move}>
              {busy
                ? "正在保存与验证…"
                : step === 3
                  ? draft?.id
                    ? "保存修改"
                    : task.enabled
                      ? "创建并开启"
                      : "保存为暂停任务"
                  : "下一步"}
              <Icon name={step === 3 ? "check" : "arrow"} size={15} />
            </Button>
          </div>
        </div>
        <TaskPreview task={task} accounts={store.accounts} />
      </div>
      {showDiscard && (
        <Modal title="先保留这个安排？" onClose={() => setShowDiscard(false)}>
          <p className="muted small">
            当前内容还没有保存。继续编辑可以保留已填写的信息，放弃后会返回任务列表。
          </p>
          <div className="modal-footer">
            <Button
              onClick={() => {
                setShowDiscard(false);
                if (exitAction) exitAction();
                else onCancel();
              }}
            >
              放弃修改
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setShowDiscard(false);
                setExitAction(null);
              }}
            >
              继续编辑
            </Button>
          </div>
        </Modal>
      )}
    </section>
  );
}
function AccountNameDialog({ account, onClose, onSave }) {
  const [name, setName] = useState(account.name),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    if (busy) return;
    const value = name.trim();
    if (!value || Array.from(value).length > 30) {
      setError("请填写 1 到 30 个字符的账号名称。");
      return;
    }
    setError("");
    setBusy(true);
    try {
      await onSave(account.id, value);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }
  return (
    <Modal
      title="编辑账号名称"
      subtitle="这个名称用于在拾刻中区分账号，Telegram 昵称和用户名保持不变。"
      onClose={busy ? () => {} : onClose}
    >
      <form onSubmit={submit} aria-busy={busy}>
        <Field
          label="账号名称"
          id="account-remark"
          hint="最多 30 个字符，保存后立即生效。"
          error={error}
        >
          <input
            id="account-remark"
            value={name}
            autoFocus
            autoComplete="off"
            maxLength={30}
            disabled={busy}
            onChange={(e) => {
              setName(e.target.value);
              if (error) setError("");
            }}
          />
        </Field>
        <div className="modal-footer">
          <Button type="button" disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={busy || !name.trim() || name.trim() === account.name}
          >
            {busy ? "正在保存…" : "保存名称"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function AccountDialog({ account, onClose, onSave }) {
  const [mode, setMode] = useState("qr"),
    [step, setStep] = useState(0),
    [name, setName] = useState(account?.name || "我的 Telegram"),
    [phone, setPhone] = useState(""),
    [code, setCode] = useState(""),
    [password, setPassword] = useState(""),
    [session, setSession] = useState(""),
    [loginId, setLoginId] = useState(""),
    [qrImage, setQrImage] = useState(""),
    [expiresAt, setExpiresAt] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const pending = useRef("");
  useEffect(
    () => () => {
      if (pending.current)
        api("/accounts/login/" + pending.current, { method: "DELETE" }).catch(
          () => {},
        );
    },
    [],
  );
  async function completed(account) {
    pending.current = "";
    setPassword("");
    setCode("");
    setSession("");
    setQrImage("");
    await onSave(account);
  }
  useEffect(() => {
    if (mode !== "qr" || !loginId || step !== 0) return;
    let alive = true,
      timer;
    async function poll() {
      try {
        const result = await api("/accounts/login/" + loginId);
        if (!alive) return;
        if (result.step === "complete") {
          clearInterval(timer);
          await completed(result.account);
        } else if (result.step === "password") {
          clearInterval(timer);
          setQrImage("");
          setStep(2);
        } else if (result.step === "error") {
          clearInterval(timer);
          setError(result.message);
        } else {
          setQrImage(result.qrImage);
          setExpiresAt(result.expiresAt);
        }
      } catch (e) {
        if (alive) {
          setError(e.message);
          clearInterval(timer);
        }
      }
    }
    timer = setInterval(poll, 1000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [mode, loginId, step]);
  async function changeMode(nextMode) {
    if (pending.current)
      await api("/accounts/login/" + pending.current, {
        method: "DELETE",
      }).catch(() => {});
    pending.current = "";
    setLoginId("");
    setQrImage("");
    setStep(0);
    setError("");
    setMode(nextMode);
  }
  async function next(e) {
    e.preventDefault();
    setError("");
    if (!name.trim()) {
      setError("请填写账号名称");
      return;
    }
    setBusy(true);
    try {
      let result;
      if (mode === "session") {
        result = {
          account: await api("/accounts/import", {
            method: "POST",
            body: {
              name: name.trim(),
              session,
              ...(account ? { accountId: account.id } : {}),
            },
          }),
        };
      } else if (mode === "qr" && step === 0) {
        if (pending.current)
          await api("/accounts/login/" + pending.current, {
            method: "DELETE",
          }).catch(() => {});
        result = await api("/accounts/login/qr", {
          method: "POST",
          body: {
            name: name.trim(),
            ...(account ? { accountId: account.id } : {}),
          },
        });
        if (result.step === "complete") {
          await completed(result.account);
          return;
        }
        setLoginId(result.loginId);
        pending.current = result.loginId;
        setQrImage(result.qrImage);
        setExpiresAt(result.expiresAt);
        return;
      } else if (step === 0) {
        result = await api("/accounts/login/start", {
          method: "POST",
          body: {
            name: name.trim(),
            phone: phone.replace(/[ -]/g, ""),
            ...(account ? { accountId: account.id } : {}),
          },
        });
        setLoginId(result.loginId);
        pending.current = result.loginId;
        setStep(1);
        return;
      } else if (step === 1) {
        result = await api("/accounts/login/" + loginId + "/code", {
          method: "POST",
          body: { code },
        });
        if (result.step === "password") {
          setCode("");
          setStep(2);
          return;
        }
      } else {
        result = await api("/accounts/login/" + loginId + "/password", {
          method: "POST",
          body: { password },
        });
      }
      await completed(result.account);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={account ? "重新登录账号" : "添加 Telegram 账号"}
      subtitle={
        step === 2
          ? "此账号开启了两步验证。"
          : mode === "qr"
            ? "用手机 Telegram 扫一扫，即可接入当前实例。"
            : "会话由当前自部署服务加密保存。"
      }
      onClose={onClose}
    >
      {step === 0 && (
        <div className="tabbar">
          {[
            ["qr", "扫码登录"],
            ["phone", "手机号登录"],
            ["session", "导入已有会话"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={"tab " + (mode === id ? "active" : "")}
              disabled={busy}
              onClick={() => changeMode(id)}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={next}>
        <Field id="account-name" label="账号名称">
          <input
            id="account-name"
            value={name}
            maxLength={30}
            onChange={(e) => setName(e.target.value)}
            disabled={step > 0 || !!loginId || busy}
          />
        </Field>
        {mode === "qr" && step === 0 ? (
          <>
            <div className="qr-panel">
              {qrImage ? (
                <>
                  <img
                    src={qrImage}
                    width="232"
                    height="232"
                    alt="用 Telegram 扫描，登录当前拾刻实例"
                  />
                  <p className="mini-note">
                    请用 Telegram 的“设置 → 设备 → 连接桌面设备”扫描。
                  </p>
                  <p className="mini-note mt-8">
                    {Math.max(
                      0,
                      Math.ceil((Date.parse(expiresAt) - Date.now()) / 1000),
                    )}{" "}
                    秒后自动更新
                  </p>
                </>
              ) : (
                <div className="empty" style={{ padding: "20px 10px" }}>
                  <div className="iconbox">
                    <Icon name="user" size={25} />
                  </div>
                  <p style={{ marginBottom: 0 }}>
                    点击下方生成二维码，在 Telegram 中扫码并确认。
                  </p>
                </div>
              )}
            </div>
            <p className="mini-note mt-16">
              扫码不会跳过 Telegram 两步验证；请仅扫描自己部署的实例。
            </p>
          </>
        ) : mode === "session" ? (
          <Field
            label="Telethon StringSession"
            id="session-input"
            hint="此字符串等同账号登录凭证，验证后在服务器加密保存。"
          >
            <textarea
              id="session-input"
              value={session}
              onChange={(e) => setSession(e.target.value)}
              disabled={busy}
            />
          </Field>
        ) : step === 0 ? (
          <Field
            label="手机号"
            id="phone-input"
            hint="包含国家区号，例如 +86。验证码可能发到已登录的 Telegram 设备。"
          >
            <input
              type="tel"
              id="phone-input"
              autoComplete="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+86 138 0000 0000"
              disabled={busy}
            />
          </Field>
        ) : step === 1 ? (
          <>
            <Field
              label="Telegram 验证码"
              id="login-code"
              hint="请在 10 分钟内完成，服务重启后需要重新获取。"
            >
              <input
                id="login-code"
                autoComplete="one-time-code"
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                maxLength={8}
                disabled={busy}
              />
            </Field>
            <button
              type="button"
              className="text-btn"
              disabled={busy}
              onClick={() => changeMode("phone")}
            >
              更换号码或重新获取
            </button>
          </>
        ) : (
          <Field
            label="两步验证密码"
            id="twofactor"
            hint="这是 Telegram 的两步验证密码，与面板管理密码不同。"
          >
            <input
              id="twofactor"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
            />
          </Field>
        )}
        {error && (
          <div className="mt-16">
            <Notice type="error">{error}</Notice>
          </div>
        )}
        <div className="modal-footer">
          <Button type="button" onClick={onClose}>
            取消
          </Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy
              ? "正在连接与验证…"
              : step === 2
                ? "完成登录"
                : mode === "qr"
                  ? qrImage
                    ? "重新生成二维码"
                    : "生成登录二维码"
                  : mode === "session"
                    ? "验证并接入"
                    : step === 0
                      ? "获取验证码"
                      : "验证并继续"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
function RunDialog({ task, account, onClose, onFinish }) {
  const { run, setRun, error: pollError } = useLiveRun(null, onFinish);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const requestId = useRef(crypto.randomUUID());
  async function start() {
    setBusy(true);
    setError("");
    try {
      setRun(
        await api("/tasks/" + task.id + "/run", {
          method: "POST",
          headers: { "Idempotency-Key": requestId.current },
        }),
      );
    } catch (e) {
      if (e.code === "RUN_EXISTS" && e.details.runId) {
        setRun(await api("/runs/" + e.details.runId));
      } else setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    setBusy(true);
    try {
      setRun(await api("/runs/" + run.id + "/cancel", { method: "POST" }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={
        !run
          ? "立即执行一次？"
          : activeRun(run)
            ? run.status === "queued"
              ? "任务正在排队"
              : "任务正在执行"
            : "这次执行，已记录。"
      }
      subtitle={task.name + " · " + account?.name}
      onClose={onClose}
    >
      {!run ? (
        <>
          <Notice>
            本次会以所选账号向目标会话真实发送消息。它独立于定时计划，不会改变下次执行时间。
          </Notice>
          <dl className="detail-facts mt-24">
            <div>
              <dt>执行账号</dt>
              <dd>
                {account?.name}
                {account?.username ? ` · @${account.username}` : ""}
              </dd>
            </div>
            <div>
              <dt>接收方</dt>
              <dd>
                {task.target === "me"
                  ? "自己 · Telegram 收藏夹"
                  : task.targetName || task.target}
              </dd>
            </div>
            <div>
              <dt>接收地址</dt>
              <dd className="mono">
                {task.target === "me" ? "me（仅你本人）" : task.target}
              </dd>
            </div>
            <div>
              <dt>本次发送</dt>
              <dd>
                {task.steps.filter((s) => s.type === "send").length} 条消息 · 共{" "}
                {task.steps.length} 步
              </dd>
            </div>
            <div>
              <dt>是否等待回复</dt>
              <dd>
                {task.steps.some((s) => s.type === "wait")
                  ? "是 · 未收到回复会停止后续步骤"
                  : "否 · 消息发送完成即结束"}
              </dd>
            </div>
          </dl>
          {task.target === "me" && (
            <Notice type="info">
              收藏夹就是 Telegram 的“已保存的消息”，内容只发给你自己。
            </Notice>
          )}
          <div className="reply-block mt-24">
            <small>将发送以下内容</small>
            {task.steps
              .filter((s) => s.type === "send")
              .map((s) => s.text)
              .join("\n\n")}
          </div>
          {task.steps.some((s) =>
            /\{\{(date|time|weekday)\}\}/.test(s.text || ""),
          ) && (
            <p className="mini-note mt-16">
              日期、时间和星期将在执行时按 {task.timezone}{" "}
              替换；记录中保留实际发送内容。
            </p>
          )}
          {(error || pollError) && (
            <div className="mt-16">
              <Notice type="error">{error || pollError}</Notice>
            </div>
          )}
          <div className="modal-footer">
            <Button onClick={onClose}>暂不执行</Button>
            <Button
              variant="primary"
              icon="play"
              disabled={busy}
              onClick={start}
            >
              {busy ? "正在提交…" : "确认并执行"}
            </Button>
          </div>
        </>
      ) : (
        <>
          <div className="between mt-16">
            <Badge status={run.status} />
            <span className="mini-note">
              {sentLabel(run)} · {run.duration}
            </span>
          </div>
          <RunLogs run={run} />
          {!!run.replies?.length && (
            <div className="reply-block">
              <small>原始回复</small>
              {run.reply}
            </div>
          )}
          {run.error && run.status !== "timeout" && (
            <div className="mt-16">
              <Notice type="error">{run.error}</Notice>
            </div>
          )}
          {run.sendState === "unknown" && (
            <div className="mt-16">
              <Notice>
                发送结果尚未确认。请先检查 Telegram
                会话，再决定是否执行一次新的操作。
              </Notice>
            </div>
          )}
          {run.status === "timeout" && (
            <div className="mt-16">
              <ReplyTimeoutNotice />
            </div>
          )}
          {run.status === "sent" && !run.replies?.length && (
            <div className="mt-16">
              <Notice type="info">
                消息已发送，流程已结束，无需等待对方回复。
              </Notice>
            </div>
          )}
          {run.status === "replied" && (
            <p className="mini-note mt-16">
              没有命中业务结果规则，保留原始回复供你确认。
            </p>
          )}
          {run.matchedRule && (
            <p className="mini-note mt-16">命中规则：{run.matchedRule}</p>
          )}
          {pollError && (
            <p className="mini-note mt-16">
              暂时无法刷新：{pollError}。后台任务继续执行。
            </p>
          )}
          <div className="modal-footer">
            {activeRun(run) && (
              <Button variant="danger" disabled={busy} onClick={cancel}>
                取消后续步骤
              </Button>
            )}
            <Button variant="primary" onClick={onClose}>
              {activeRun(run) ? "关闭，后台继续" : "完成"}
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
}
function ReplyTimeoutNotice() {
  return (
    <Notice>
      <strong>消息已发送，超时的是等待回复。</strong>
      <p className="mt-8">
        Telegram 已确认发送，但在设定时间内未收到符合条件的回复。
        只需发送消息时，在任务的“操作内容”中关闭“等待对方回复”；复杂流程请移除不需要的等待步骤。
        再次执行会重复发送，本次不会自动重发。
      </p>
    </Notice>
  );
}
function RunLogs({ run }) {
  return (
    <div className="run-progress" aria-live="polite">
      {run.logs?.length ? (
        run.logs.map((log, i) => (
          <div
            className={
              "run-step " +
              (log.state === "running" &&
              i === run.logs.length - 1 &&
              activeRun(run)
                ? "active"
                : "done")
            }
            key={i}
          >
            <span className="run-circle">
              <Icon
                name={
                  log.state === "error"
                    ? "alert"
                    : log.state === "running" &&
                        i === run.logs.length - 1 &&
                        activeRun(run)
                      ? "loader"
                      : "check"
                }
                size={12}
                className={
                  log.state === "running" &&
                  i === run.logs.length - 1 &&
                  activeRun(run)
                    ? "spinner"
                    : ""
                }
              />
            </span>
            <div>
              <p>
                {log.step ? "步骤 " + log.step + " · " : ""}
                {log.message}
              </p>
              <small>{formatAt(log.at, true)}</small>
            </div>
          </div>
        ))
      ) : (
        <p className="mini-note">
          {run.status === "queued"
            ? "正在等待当前账号前面的任务完成。"
            : "这次执行没有步骤日志。"}
        </p>
      )}
    </div>
  );
}
function RunDetail({ run: initialRun, store, onClose, onTask }) {
  const { run, error } = useLiveRun(initialRun);
  const [copy, setCopy] = useState("复制回复");
  const account = store.accounts.find((a) => a.id === run.accountId),
    task = store.tasks.find((t) => t.id === run.taskId);
  return (
    <Modal title="执行详情" subtitle={run.taskName} onClose={onClose} drawer>
      <div className="between">
        <Badge status={run.status} />
        <span className="mini-note">{run.duration}</span>
      </div>
      <dl className="detail-facts mt-24">
        <div>
          <dt>执行时间</dt>
          <dd>{formatAt(run.at)}</dd>
        </div>
        <div>
          <dt>触发方式</dt>
          <dd>{run.source === "scheduled" ? "定时执行" : "手动执行"}</dd>
        </div>
        {run.scheduledAt && (
          <div>
            <dt>计划时间</dt>
            <dd>{formatAt(run.scheduledAt)}</dd>
          </div>
        )}
        <div>
          <dt>执行账号</dt>
          <dd>{account?.name || "历史账号"}</dd>
        </div>
        <div>
          <dt>目标会话</dt>
          <dd className="mono">{run.target}</dd>
        </div>
        <div>
          <dt>消息发送状态</dt>
          <dd>{sentLabel(run)}</dd>
        </div>
      </dl>
      <div className="divider" />
      <h3>发送内容</h3>
      <div className="reply-block mt-16">{run.message || "本次尚未发送"}</div>
      <h3 className="mt-24">原始回复</h3>
      <div className="reply-block mt-16">
        {run.replies?.length
          ? run.reply || "[非文本回复]"
          : run.status === "sent"
            ? "本次流程无需等待回复。"
            : "没有收到回复"}
      </div>
      {run.error && run.status !== "timeout" && (
        <div className="mt-16">
          <Notice type="error">{run.error}</Notice>
        </div>
      )}
      {["timeout", "interrupted"].includes(run.status) ||
      run.sendState === "unknown" ? (
        <div className="mt-24">
          {run.status === "timeout" ? (
            <ReplyTimeoutNotice />
          ) : (
            <Notice>
              <strong>先确认会话，再决定是否执行。</strong>
              <p className="mt-8">
                当前状态：{sentLabel(run)}
                。再次执行可能产生重复操作，本次不会自动重发。
              </p>
            </Notice>
          )}
        </div>
      ) : run.status === "replied" ? (
        <div className="mt-24">
          <Notice type="info">
            没有命中业务结果规则，因此不推断业务成功或失败。
          </Notice>
        </div>
      ) : null}
      {run.matchedRule && (
        <p className="mini-note mt-16">命中的业务规则：{run.matchedRule}</p>
      )}
      {run.notificationStatus === "failed" && (
        <p className="mini-note mt-16">任务结果已保存，但通知发送失败。</p>
      )}
      <div className="divider" />
      <h3>执行过程</h3>
      <RunLogs run={run} />
      {error && <p className="mini-note">刷新暂不可用：{error}</p>}
      <div className="modal-footer">
        <Button
          icon="copy"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(run.reply || run.error || "");
              setCopy("已复制");
            } catch {
              setCopy("复制失败，请手动选择");
            }
          }}
        >
          {copy}
        </Button>
        {task && (
          <Button variant="primary" onClick={() => onTask(task)}>
            查看任务
          </Button>
        )}
      </div>
    </Modal>
  );
}
function SetupPage({ store, actions, onDone }) {
  const [step, setStep] = useState(store?.settings.hasApi ? 1 : 0),
    [apiId, setApiId] = useState(""),
    [apiHash, setApiHash] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function go() {
    setError("");
    setBusy(true);
    try {
      if (step === 0) {
        await actions.saveApi({
          apiId: Number(apiId),
          apiHash: apiHash.trim(),
        });
        setApiHash("");
      }
      setStep(step + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="setup-shell" data-screen-label="首次设置">
      <aside className="setup-side">
        <Brand />
        <h1>
          给重复的小事，
          <br />
          安排一个好时间。
        </h1>
        <p>欢迎来到拾刻。几步简单设置，就能拥有自己的自动任务空间。</p>
        <div className="setup-check">
          <Icon name="check" size={16} />
          账号凭证由本实例加密保存
        </div>
        <div className="setup-check">
          <Icon name="check" size={16} />
          浏览器配置，无需写代码
        </div>
        <div className="setup-check">
          <Icon name="check" size={16} />
          每次执行都有记录
        </div>
        <footer>
          拾刻 SHIKE
          <br />A little less repeating.
        </footer>
      </aside>
      <main className="setup-main">
        <div className="setup-demo">
          <span className="demo-badge">
            <Icon name="shield" size={12} />
            你的自部署工作空间
          </span>
          <button className="text-btn" onClick={onDone}>
            稍后继续
            <Icon name="arrow" size={13} />
          </button>
        </div>
        <Steps
          labels={["连接 Telegram", "添加账号", "准备就绪"]}
          current={step}
        />
        <h1>
          {
            [
              "让拾刻连接到 Telegram。",
              "现在，接入你的账号。",
              "一切就绪，安排第一件小事。",
            ][step]
          }
        </h1>
        <p className="subtitle">
          {
            [
              "这组应用连接信息通常只需配置一次。",
              "推荐用手机 Telegram 扫码，也可以使用手机号验证码或导入会话。",
              "从一个现成模板开始，确认目标与时间后再启用。",
            ][step]
          }
        </p>
        {step === 0 && (
          <>
            <Notice type="info">
              在{" "}
              <a
                href="https://my.telegram.org/apps"
                target="_blank"
                rel="noopener noreferrer"
                className="text-btn"
                style={{ fontSize: 12, padding: 0 }}
              >
                my.telegram.org/apps
              </a>{" "}
              创建应用，可获取 API ID 和 API Hash。这不是机器人 Token。
            </Notice>
            <div className="mt-24">
              <Field label="API ID" id="setup-api-id">
                <input
                  id="setup-api-id"
                  inputMode="numeric"
                  value={apiId}
                  placeholder="应用 ID"
                  onChange={(e) => setApiId(e.target.value)}
                />
              </Field>
            </div>
            <Field
              label="API Hash"
              id="setup-api-hash"
              hint="保存后不再回显，服务器会加密保存。"
            >
              <input
                id="setup-api-hash"
                type="password"
                value={apiHash}
                autoComplete="off"
                placeholder="32 位应用 Hash"
                onChange={(e) => setApiHash(e.target.value)}
              />
            </Field>
            <p className="mini-note">
              若服务器不能直接连接 Telegram，可以先完成此步，再到设置配置代理。
            </p>
          </>
        )}
        {step === 1 && (
          <div className="setup-complete">
            <div className="iconbox large">
              <Icon name="users" size={24} />
            </div>
            <h2>
              {store?.accounts.length
                ? "账号已准备好"
                : "添加第一个 Telegram 账号"}
            </h2>
            <p className="mini-note mt-8">
              {store?.accounts.map((a) => a.name).join("、") ||
                "验证码会发送到你的 Telegram 已登录设备或 Telegram 指定渠道。"}
            </p>
            <Button
              className="mt-24"
              variant="primary"
              icon="plus"
              onClick={() => actions.addAccount()}
            >
              添加 Telegram 账号
            </Button>
          </div>
        )}
        {step === 2 && (
          <div className="setup-complete">
            <div className="iconbox large">
              <Icon name="check" size={25} />
            </div>
            <h2>欢迎，{store?.settings.workspace}。</h2>
            <p className="mini-note mt-8">
              先创建一条任务，查看内容和目标后再执行。
            </p>
            <Button
              variant="primary"
              className="mt-24"
              icon="layers"
              onClick={() => actions.navigate("templates")}
            >
              从模板创建第一个任务
            </Button>
            <div className="mt-16">
              <button className="text-btn" onClick={onDone}>
                进入工作空间
                <Icon name="arrow" size={13} />
              </button>
            </div>
          </div>
        )}
        {error && (
          <div className="mt-16">
            <Notice type="error">{error}</Notice>
          </div>
        )}
        {step < 2 && (
          <div className="form-footer">
            <div>
              {step > 0 && (
                <Button variant="ghost" onClick={() => setStep(step - 1)}>
                  上一步
                </Button>
              )}
            </div>
            {step === 1 ? (
              <Button variant="primary" onClick={() => setStep(2)}>
                {store?.accounts.length ? "继续" : "稍后添加"}
                <Icon name="arrow" size={14} />
              </Button>
            ) : (
              <Button variant="primary" disabled={busy} onClick={go}>
                {busy ? "正在保存…" : "保存连接信息并继续"}
                <Icon name="arrow" size={14} />
              </Button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
function LoginPage({ initialized, onLogin, onRefresh }) {
  const [password, setPassword] = useState(""),
    [visible, setVisible] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="setup-shell" data-screen-label="管理员登录">
      <aside className="setup-side">
        <Brand />
        <h1>
          日常有安排，
          <br />
          时间留给你。
        </h1>
        <p>欢迎回来，登录你的工作空间。</p>
        <footer>自部署的 Telegram 自动任务工具</footer>
      </aside>
      <main className="setup-main" style={{ maxWidth: 530 }}>
        <div className="demo-badge" style={{ width: "fit-content" }}>
          <Icon name="shield" size={13} />
          管理员登录
        </div>
        <h1>登录你的工作空间。</h1>
        <p className="subtitle">输入管理密码，继续你的自动化日常。</p>
        {!initialized && (
          <div className="mb-24">
            <Notice type="info">
              部署者尚未设置管理密码。请在服务器的安装目录运行
              <code> sh shike.sh init </code>，按提示设置后刷新本页。
              <button type="button" className="text-btn" onClick={onRefresh}>
                刷新登录状态
              </button>
            </Notice>
          </div>
        )}
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!initialized || busy) return;
            setError("");
            setBusy(true);
            try {
              await onLogin(password);
              setPassword("");
            } catch (e) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <input
            type="hidden"
            name="username"
            value="admin"
            autoComplete="username"
          />
          <Field label="管理密码" id="admin-password" error={error}>
            <div className="password-input">
              <input
                type={visible ? "text" : "password"}
                id="admin-password"
                name="password"
                aria-invalid={!!error}
                aria-describedby={error ? "admin-password-hint" : undefined}
                value={password}
                autoComplete="current-password"
                maxLength={1024}
                disabled={!initialized || busy}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <IconButton
                name="eye"
                label={visible ? "隐藏密码" : "显示密码"}
                aria-pressed={visible}
                disabled={!initialized}
                onClick={() => setVisible(!visible)}
              />
            </div>
          </Field>
          <Button
            variant="primary"
            type="submit"
            className="wide"
            disabled={busy || !initialized}
          >
            {busy ? "正在登录…" : "进入工作空间"}
            <Icon name="arrow" size={16} />
          </Button>
        </form>
        <details className="advanced">
          <summary>忘记密码了？</summary>
          <p className="mini-note">
            在部署目录运行 sh shike.sh
            reset-password，按提示重设管理密码。旧面板登录会失效，Telegram
            账号和任务保留。源码安装请先停止服务，再运行 python -m shike
            reset-password。
          </p>
        </details>
      </main>
    </div>
  );
}
function CredentialDialog({ type, onClose, onDone }) {
  const [first, setFirst] = useState(""),
    [second, setSecond] = useState(""),
    [third, setThird] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setError("");
    if (type === "password" && (second.length < 10 || second !== third)) {
      setError("新密码至少 10 位，且两次输入需一致。");
      return;
    }
    setBusy(true);
    try {
      if (type === "api")
        await api("/settings/telegram", {
          method: "PUT",
          body: { apiId: Number(first), apiHash: second.trim() },
        });
      else
        await api("/auth/password", {
          method: "POST",
          body: { current: first, password: second },
        });
      setFirst("");
      setSecond("");
      setThird("");
      await onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={type === "api" ? "配置 Telegram 连接" : "修改管理密码"}
      onClose={onClose}
    >
      {type === "api" ? (
        <Notice type="info">
          前往{" "}
          <a
            className="text-btn"
            href="https://my.telegram.org/apps"
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 12, padding: 0 }}
          >
            my.telegram.org/apps
          </a>{" "}
          创建应用，获取 API ID 和 API Hash。保存后不再回显。
        </Notice>
      ) : (
        <Notice>
          修改后其他管理登录立即失效，当前页面会换用新的管理会话。
        </Notice>
      )}
      <form onSubmit={submit} className="mt-24">
        <Field
          label={type === "api" ? "API ID" : "当前管理密码"}
          id="credential-first"
        >
          <input
            id="credential-first"
            type={type === "api" ? "text" : "password"}
            autoComplete={type === "api" ? "off" : "current-password"}
            value={first}
            onChange={(e) => setFirst(e.target.value)}
            required
          />
        </Field>
        <Field
          label={type === "api" ? "API Hash" : "新的管理密码"}
          id="credential-second"
        >
          <input
            id="credential-second"
            type="password"
            autoComplete={type === "api" ? "off" : "new-password"}
            value={second}
            onChange={(e) => setSecond(e.target.value)}
            required
          />
        </Field>
        {type === "password" && (
          <Field label="再次输入新的密码" id="credential-third">
            <input
              id="credential-third"
              type="password"
              autoComplete="new-password"
              value={third}
              onChange={(e) => setThird(e.target.value)}
              required
            />
          </Field>
        )}
        {error && <Notice type="error">{error}</Notice>}
        <div className="modal-footer">
          <Button onClick={onClose} type="button">
            取消
          </Button>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? "正在保存…" : "保存"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
