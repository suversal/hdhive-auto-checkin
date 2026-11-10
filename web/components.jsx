const { useState, useEffect, useRef, useMemo } = React;
function Button({ children, icon, variant = "", className = "", ...props }) {
  return (
    <button className={`btn ${variant} ${className}`} {...props}>
      {icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  );
}
const IconButton = React.forwardRef(function IconButton(
  { name, label, ...props },
  ref,
) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>
        <button
          type="button"
          className="icon-btn"
          aria-label={label}
          ref={ref}
          {...props}
        >
          <Icon name={name} size={17} />
        </button>
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content className="control-tooltip" sideOffset={7}>
          {label}
          <TooltipPrimitive.Arrow className="tooltip-arrow" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
});
function Badge({ status }) {
  const s = STATUS[status] || STATUS.paused;
  return (
    <span className={`status ${s.type}`}>
      <Icon
        name={s.icon}
        size={11}
        className={status === "running" ? "spinner" : ""}
      />
      {s.text}
    </span>
  );
}
function Toggle({ checked, onChange, label }) {
  return (
    <SwitchPrimitive.Root
      checked={checked}
      onCheckedChange={onChange}
      aria-label={label}
      className="switch-wrap control-switch"
    >
      <SwitchPrimitive.Thumb className={`switch ${checked ? "on" : ""}`} />
    </SwitchPrimitive.Root>
  );
}
function Field({ label, hint, error, optional, id, children }) {
  const child = React.Children.only(children),
    fieldId = id || child.props.id;
  return (
    <div className="field">
      <label htmlFor={fieldId}>
        {label}
        {optional && <span className="optional">选填</span>}
      </label>
      {React.cloneElement(child, {
        "aria-invalid": !!error,
        "aria-describedby": hint || error ? fieldId + "-hint" : undefined,
      })}
      {(hint || error) && (
        <p id={fieldId + "-hint"} className={error ? "error" : "hint"}>
          {error || hint}
        </p>
      )}
    </div>
  );
}
function PageHeader({ eyebrow, title, description, children, className = "" }) {
  return (
    <div className={"page-header " + className}>
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 tabIndex={-1} data-page-heading>
          {title}
        </h1>
        {description && <p>{description}</p>}
      </div>
      {children}
    </div>
  );
}
function Empty({ icon = "list", title, description, action }) {
  return (
    <div className="empty">
      <div className="iconbox">
        <Icon name={icon} size={26} />
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
function Notice({ type = "", children }) {
  return (
    <div
      className={"notice " + type}
      role={type === "error" ? "alert" : undefined}
    >
      <Icon name={type === "info" ? "info" : "alert"} size={16} />
      <div className="grow">{children}</div>
    </div>
  );
}
function Steps({ labels, current }) {
  return (
    <div className="steps" aria-label="当前进度">
      {labels.map((l, i) => (
        <React.Fragment key={l}>
          {i > 0 && <span className="step-line" />}
          <div
            className={`step ${i === current ? "active" : i < current ? "done" : ""}`}
            aria-current={i === current ? "step" : undefined}
          >
            <span className="step-number">
              {i < current ? <Icon name="check" size={12} /> : i + 1}
            </span>
            <span>{l}</span>
          </div>
        </React.Fragment>
      ))}
    </div>
  );
}
function Modal({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
  drawer = false,
}) {
  return (
    <DialogPrimitive.Root open onOpenChange={(open) => !open && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="modal-backdrop dialog-overlay" />
        <DialogPrimitive.Content
          className={`modal dialog-content ${wide ? "wide" : ""} ${drawer ? "drawer" : ""}`}
          aria-describedby={subtitle ? "dialog-description" : undefined}
        >
          <header className="modal-header">
            <div>
              <DialogPrimitive.Title asChild>
                <h2>{title}</h2>
              </DialogPrimitive.Title>
              {subtitle && (
                <DialogPrimitive.Description id="dialog-description">
                  {subtitle}
                </DialogPrimitive.Description>
              )}
            </div>
            <IconButton name="close" label="关闭弹窗" onClick={onClose} />
          </header>
          <div className="modal-body">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
function Menu({ children }) {
  return (
    <MenuPrimitive.Root>
      <MenuPrimitive.Trigger asChild>
        <button
          type="button"
          className="icon-btn task-menu-trigger"
          aria-label="更多任务操作"
        >
          <Icon name="more" size={17} />
        </button>
      </MenuPrimitive.Trigger>
      <MenuPrimitive.Portal>
        <MenuPrimitive.Content
          className="control-menu"
          align="end"
          sideOffset={6}
          collisionPadding={12}
        >
          {React.Children.toArray(children).map((child, i) => (
            <MenuPrimitive.Item asChild key={i}>
              {child}
            </MenuPrimitive.Item>
          ))}
        </MenuPrimitive.Content>
      </MenuPrimitive.Portal>
    </MenuPrimitive.Root>
  );
}
function Nav({ route, store, close }) {
  const items = [
    ["overview", "grid", "概览"],
    ["tasks", "list", "我的任务", store.tasks.length],
    ["accounts", "users", "账号", store.accounts.length],
    ["runs", "history", "执行记录"],
    ["templates", "layers", "任务模板"],
  ];
  return (
    <>
      <div className="nav-label">工作空间</div>
      <nav className="nav" aria-label="主导航">
        {items.map(([id, icon, label, count]) => (
          <a
            key={id}
            href={"#" + id}
            className={
              "nav-link " +
              (route === id ||
              (id === "tasks" && (route === "new" || route.startsWith("task/")))
                ? "active"
                : "")
            }
            onClick={close}
            aria-current={route === id ? "page" : undefined}
          >
            <Icon name={icon} size={17} />
            {label}
            {count !== undefined && <span className="nav-count">{count}</span>}
          </a>
        ))}
      </nav>
    </>
  );
}
function Sidebar({ route, store, mobile, close }) {
  return (
    <>
      {mobile && (
        <button
          className="sidebar-scrim"
          onClick={close}
          aria-label="关闭导航"
        />
      )}
      <aside className={"sidebar " + (mobile ? "mobile-sidebar" : "")}>
        <Brand />
        <div className="workspace">
          <span className="workspace-dot" />
          <span className="grow">{store.settings.workspace}</span>
          <Icon name="shield" size={13} />
        </div>
        <Nav route={route} store={store} close={close} />
        <div className="sidebar-bottom">
          <nav className="nav" aria-label="支持导航">
            <a
              href="#settings"
              className={"nav-link " + (route === "settings" ? "active" : "")}
              onClick={close}
            >
              <Icon name="settings" size={17} />
              设置
            </a>
            <a
              href="#help"
              className={"nav-link " + (route === "help" ? "active" : "")}
              onClick={close}
            >
              <Icon name="help" size={17} />
              帮助与入门
            </a>
          </nav>
          <a className="help-card" href="#templates" onClick={close}>
            <div className="row">
              <Icon name="spark" size={16} />
              <strong>不用从零配置</strong>
            </div>
            <p>从一个现成模板，开始你的自动化。</p>
            <span className="text-btn small">
              看看任务模板
              <Icon name="arrow" size={13} />
            </span>
          </a>
          <div className="sidebar-status">
            <span className="workspace-dot" />
            自部署 · 拾刻
          </div>
        </div>
      </aside>
    </>
  );
}
function BottomNav({ route }) {
  return (
    <nav className="mobile-nav" aria-label="移动导航">
      {[
        ["overview", "grid", "概览"],
        ["tasks", "list", "任务"],
        ["accounts", "users", "账号"],
        ["runs", "history", "记录"],
        ["settings", "settings", "设置"],
      ].map(([id, icon, label]) => (
        <a
          href={"#" + id}
          key={id}
          className={
            route === id ||
            (id === "tasks" && (route === "new" || route.startsWith("task/")))
              ? "active"
              : ""
          }
        >
          <Icon name={icon} size={20} />
          {label}
        </a>
      ))}
    </nav>
  );
}
function TaskMenu({ task, onEdit, onCopy, onDelete, onExport }) {
  return (
    <Menu>
      <button onClick={() => onEdit(task)}>
        <Icon name="edit" size={15} />
        编辑任务
      </button>
      <button onClick={() => onCopy(task)}>
        <Icon name="copy" size={15} />
        复制为新任务
      </button>
      <button onClick={() => onExport(task)}>
        <Icon name="download" size={15} />
        导出任务模板
      </button>
      <button className="danger" onClick={() => onDelete(task)}>
        <Icon name="trash" size={15} />
        删除任务
      </button>
    </Menu>
  );
}
function replyPlaceholder(run) {
  if (!run) return "—";
  if (run.status === "sent") return "本次只发送消息，无需等待回复";
  if (run.status === "running") return "执行中，回复会在这里更新";
  if (run.status === "queued") return "任务排队中，还没有回复";
  if (run.status === "timeout")
    return run.sent ? "已发送，等待回复超时" : "执行超时，未收到回复";
  if (run.status === "skipped") return "错过计划，未发送消息";
  if (run.status === "cancelled") return "执行已取消，暂无回复";
  if (run.status === "interrupted") return "执行中断，暂无回复";
  return run.error || "暂无回复";
}
function ReplyPreview({ run }) {
  const element = useRef(null),
    [overflow, setOverflow] = useState(false),
    [open, setOpen] = useState(false),
    text = run?.status === "skipped" ? "" : run?.reply || "",
    value = text || replyPlaceholder(run);
  useEffect(() => {
    const node = element.current;
    const measure = () => setOverflow(node.scrollWidth > node.clientWidth + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [value]);
  useEffect(() => setOpen(false), [run?.id, value]);
  return (
    <TooltipPrimitive.Root
      open={overflow && open}
      onOpenChange={setOpen}
      delayDuration={180}
    >
      <TooltipPrimitive.Trigger asChild>
        <button
          ref={element}
          type="button"
          className={"reply-value" + (!text ? " is-empty" : "")}
          disabled={!overflow}
          onClick={(e) => {
            e.preventDefault();
            setOpen(!open);
          }}
        >
          {value}
        </button>
      </TooltipPrimitive.Trigger>
      {overflow && (
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            className="reply-tooltip"
            side="top"
            align="start"
            sideOffset={8}
            collisionPadding={16}
          >
            {value}
            <TooltipPrimitive.Arrow className="reply-tooltip-arrow" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      )}
    </TooltipPrimitive.Root>
  );
}
function TaskList({
  tasks,
  accounts,
  onToggle,
  onRun,
  onEdit,
  onCopy,
  onDelete,
  onExport,
  compact = false,
  selectedIds = null,
  onSelect,
  onSelectAll,
}) {
  return compact ? (
    <>
      {tasks.map((t) => (
        <div key={t.id} className="task-row">
          <div
            className={"iconbox " + (t.targetType === "group" ? "blue" : "")}
          >
            <Icon
              name={
                t.targetType === "group"
                  ? "users"
                  : t.target === "me"
                    ? "book"
                    : "bot"
              }
              size={17}
            />
          </div>
          <div className="grow">
            <div className="row wrap">
              <button
                className="table-name"
                onClick={() => (location.hash = "task/" + t.id)}
              >
                {t.name}
              </button>
              {t.lastStatus && <Badge status={t.lastStatus} />}
            </div>
            <div className="task-meta">
              {t.targetName || t.target} <span aria-hidden="true">·</span>{" "}
              {scheduleLabel(t)}
            </div>
            <ReplyPreview run={t.lastRun} />
          </div>
          <IconButton
            name="play"
            label={"执行 " + t.name}
            onClick={() => onRun(t)}
          />
          <Toggle
            label={"启用 " + t.name}
            checked={t.enabled}
            onChange={(v) => onToggle(t.id, v)}
          />
        </div>
      ))}
    </>
  ) : (
    <div className="table-wrap data-table">
      <table className="task-table">
        <colgroup>
          <col className="column-task" />
          <col className="column-schedule" />
          <col className="column-result" />
          <col className="column-reply" />
          <col className="column-toggle" />
          <col className="column-actions" />
        </colgroup>
        <thead>
          <tr>
            <th>
              <div className="row">
                {selectedIds && (
                  <CheckControl
                    label="全选当前筛选的任务"
                    checked={
                      tasks.length > 0 &&
                      tasks.every((t) => selectedIds.includes(t.id))
                        ? true
                        : selectedIds.length
                          ? "indeterminate"
                          : false
                    }
                    onChange={onSelectAll}
                  />
                )}
                任务 / 目标
              </div>
            </th>
            <th>执行时间</th>
            <th>最近执行</th>
            <th>回复内容</th>
            <th>启用</th>
            <th className="actions-heading">操作</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr
              key={t.id}
              data-selected={selectedIds?.includes(t.id) || undefined}
            >
              <td className="task-identity-cell">
                <div className="row">
                  {selectedIds && (
                    <CheckControl
                      label={"选择任务 " + t.name}
                      checked={selectedIds.includes(t.id)}
                      onChange={(checked) => onSelect(t.id, checked)}
                    />
                  )}
                  <div
                    className={
                      "iconbox " +
                      (t.targetType === "group"
                        ? "blue"
                        : t.target === "me"
                          ? "amber"
                          : "")
                    }
                  >
                    <Icon
                      name={
                        t.targetType === "group"
                          ? "users"
                          : t.target === "me"
                            ? "book"
                            : "bot"
                      }
                      size={16}
                    />
                  </div>
                  <div>
                    <button
                      className="table-name"
                      onClick={() => (location.hash = "task/" + t.id)}
                    >
                      {t.name}
                    </button>
                    <div className="task-meta">
                      {t.targetName || t.target} ·{" "}
                      {accounts.find((a) => a.id === t.accountId)?.name ||
                        "账号已移除"}
                    </div>
                  </div>
                </div>
              </td>
              <td className="schedule-cell">
                {scheduleLabel(t)}
                <div className="task-meta">{t.timezone}</div>
              </td>
              <td className="result-cell">
                {t.lastStatus ? (
                  <div className="row wrap result-meta">
                    <Badge status={t.lastStatus} />
                    {t.lastRun && (
                      <span className="task-meta">
                        {formatAt(t.lastRun.at, true)}
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="muted small">还没有执行</span>
                )}
              </td>
              <td className="reply-cell">
                <ReplyPreview run={t.lastRun} />
              </td>
              <td className="toggle-cell">
                <Toggle
                  label={"启用 " + t.name}
                  checked={t.enabled}
                  onChange={(v) => onToggle(t.id, v)}
                />
              </td>
              <td className="actions-cell">
                <div className="row gap-8 table-actions">
                  <IconButton
                    name="play"
                    label={"执行 " + t.name}
                    onClick={() => onRun(t)}
                  />
                  <TaskMenu
                    task={t}
                    onEdit={onEdit}
                    onCopy={onCopy}
                    onDelete={onDelete}
                    onExport={onExport}
                  />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function RunsTable({ runs, accounts, onOpen }) {
  return (
    <div className="table-wrap data-table">
      <table className="runs-table">
        <colgroup>
          <col className="column-task" />
          <col className="column-account" />
          <col className="column-result" />
          <col className="column-reply" />
          <col className="column-duration" />
          <col className="column-actions" />
        </colgroup>
        <thead>
          <tr>
            <th>任务 / 执行时间</th>
            <th>执行账号</th>
            <th>结果</th>
            <th>回复内容</th>
            <th>耗时</th>
            <th className="actions-heading">详情</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td className="task-identity-cell">
                <button className="table-name" onClick={() => onOpen(r)}>
                  {r.taskName}
                </button>
                <div className="task-meta">{formatAt(r.at)}</div>
              </td>
              <td className="account-cell">
                {accounts.find((a) => a.id === r.accountId)?.name || "历史账号"}
              </td>
              <td className="result-cell">
                <Badge status={r.status} />
              </td>
              <td className="reply-cell">
                <ReplyPreview run={r} />
              </td>
              <td className="muted duration-cell">{r.duration}</td>
              <td className="actions-cell">
                <Button
                  className="record-detail-button"
                  variant="ghost sm"
                  onClick={() => onOpen(r)}
                >
                  查看
                  <Icon name="chevron" size={13} />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function TaskPreview({ task, accounts }) {
  const account = accounts.find((a) => a.id === task.accountId),
    next = getNextRuns(task);
  return (
    <aside className="sticky-preview">
      <div className="preview-card">
        <div className="eyebrow">一眼看懂这条任务</div>
        <h3 className="mt-8">{task.name || "给重复的小事，一个安排"}</h3>
        <div className="preview-fact">
          <Icon name="user" size={15} />
          <div>
            <small>谁来执行</small>
            {account?.name || "还未选择账号"}
          </div>
        </div>
        <div className="preview-fact">
          <Icon name="send" size={15} />
          <div>
            <small>发给谁</small>
            {task.targetName || task.target || "还未选择目标"}
          </div>
        </div>
        <div className="preview-fact">
          <Icon name="message" size={15} />
          <div>
            <small>是否等待回复</small>
            {task.steps.some((s) => s.type === "wait")
              ? "需要回复，按步骤继续"
              : "只发送，无需对方回复"}
          </div>
        </div>
        <div className="preview-fact">
          <Icon name="clock" size={15} />
          <div>
            <small>什么时候</small>
            {scheduleLabel(task)}
            <span className="mini-note" style={{ display: "block" }}>
              {task.timezone}
            </span>
          </div>
        </div>
        <div className="next-times">
          <small>后端计算的未来执行时间</small>
          {next.length ? (
            next.map((d, i) => (
              <p key={i}>
                {String(i + 1).padStart(2, "0")}{" "}
                <span style={{ marginLeft: 10 }}>
                  {formatAt(d, true, task.timezone)}
                </span>
                {task.jitter > 0 && (
                  <span className="muted"> + 0–{task.jitter} 分钟</span>
                )}
              </p>
            ))
          ) : (
            <p className="muted">
              {task.previewLoading
                ? "正在计算未来执行时间…"
                : "暂无未来执行时间，请检查时间配置。"}
            </p>
          )}
        </div>
      </div>
      <div className="chat-preview">
        <div className="chat-head">
          <div
            className="iconbox"
            style={{ width: 28, height: 28, borderRadius: 8 }}
          >
            <Icon name="bot" size={15} />
          </div>
          <div>
            <strong>{task.targetName || "目标会话"}</strong>
            <div className="muted" style={{ fontSize: 9 }}>
              消息效果预览
            </div>
          </div>
        </div>
        <div className="chat-body">
          {task.steps
            .filter((s) => s.type === "send")
            .map((s, i) => (
              <div className="bubble" key={i}>
                {s.text || "你填写的内容会显示在这里"}
                <small>按计划发送</small>
              </div>
            ))}
          {task.steps.some((s) => s.type === "click") && (
            <div className="bubble in">
              机器人回复
              <div className="bubble-button">
                {task.steps.find((s) => s.type === "click")?.text || "签到按钮"}
              </div>
            </div>
          )}
        </div>
      </div>
      <p className="mini-note mt-16">
        任务保存后才会按计划启用。预览不会发送消息。
      </p>
    </aside>
  );
}
