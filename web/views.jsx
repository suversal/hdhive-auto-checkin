function Overview({ store, actions }) {
  const { tasks, accounts, runs } = store,
    enabled = tasks.filter((t) => t.enabled),
    today = runs.filter(
      (r) =>
        dateKey(r.at, store.settings.timezone) ===
        dateKey(Date.now(), store.settings.timezone),
    ),
    attention = today.filter((r) =>
      ["timeout", "error", "failed", "limited", "interrupted"].includes(
        r.status,
      ),
    ),
    todayExecuted = store.summary?.todayExecuted ?? 0,
    attentionCount = store.summary?.attention ?? 0;
  const next = enabled
    .flatMap((t) => getNextRuns(t, 1).map((d) => ({ t, d })))
    .sort((a, b) => a.d - b.d)
    .slice(0, 3);
  if (!tasks.length)
    return (
      <section data-screen-label="概览 · 空白状态">
        <PageHeader
          eyebrow="YOUR LITTLE AUTOMATIONS"
          title="欢迎来到拾刻"
          description="给重复的小事安排时间，从第一个任务开始。"
        />
        <div className="hero mb-24">
          <div>
            <div className="eyebrow">LESS REPEATING. MORE LIVING.</div>
            <h2>把日常小事，轻轻安排好。</h2>
            <p>接入账号，选一个模板，剩下的交给时间。</p>
          </div>
          <div className="hero-art">
            <div className="orbit" />
            <div className="orbit-center">
              <Icon name="check" size={23} />
            </div>
            <div className="orbit-small">
              <Icon name="clock" size={15} />
            </div>
          </div>
        </div>
        <div className="panel">
          <Empty
            title={
              accounts.length
                ? "创建你的第一个任务"
                : "先接入一个 Telegram 账号"
            }
            description={
              accounts.length
                ? "不用写代码，选择目标、内容和时间就好。"
                : "连接你自己的账号后，就可以安排自动签到和定时消息。"
            }
            icon={accounts.length ? "list" : "user"}
            action={
              <Button
                variant="primary"
                icon="plus"
                onClick={
                  accounts.length
                    ? () => actions.create()
                    : () => actions.addAccount()
                }
              >
                {accounts.length ? "创建第一个任务" : "添加 Telegram 账号"}
              </Button>
            }
          />
        </div>
        <div className="help-grid mt-24">
          {[
            ["user", "01 · 接入账号", "连接你自己的 Telegram 账号。"],
            ["layers", "02 · 选择模板", "从常用签到、提醒场景开始。"],
            ["clock", "03 · 安排时间", "设好时间，查看每一次执行。"],
          ].map(([icon, title, text]) => (
            <div className="panel help-tile" key={title}>
              <div className="iconbox">
                <Icon name={icon} />
              </div>
              <h2>{title}</h2>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </section>
    );
  return (
    <section data-screen-label="概览">
      <PageHeader
        eyebrow="YOUR LITTLE AUTOMATIONS"
        title="日常有安排，时间留给你。"
        description="查看今天的任务，或者安排一件新的小事。"
      >
        <Button variant="primary" icon="plus" onClick={() => actions.create()}>
          创建任务
        </Button>
      </PageHeader>
      <div className="dashboard-grid">
        <div>
          <div className="hero">
            <div>
              <div className="row small" style={{ color: "#57704b" }}>
                <span className="workspace-dot" />
                你的自动化日常
              </div>
              <h2>{enabled.length} 件小事，已经安排妥当。</h2>
              <p>
                下一个任务
                {next[0]
                  ? `将在 ${formatAt(next[0].d, true, store.settings.timezone)} 执行`
                  : "等待你的安排"}
                。
              </p>
              <a
                href="#tasks"
                className="text-btn mt-8"
                style={{ fontSize: 11 }}
              >
                查看我的任务
                <Icon name="arrow" size={14} />
              </a>
            </div>
            <div className="hero-art" aria-hidden="true">
              <div className="orbit" />
              <div className="orbit-center">
                <Icon name="check" size={24} />
              </div>
              <div className="orbit-small">
                <Icon name="clock" size={15} />
              </div>
              <div className="orbit-dot" />
            </div>
          </div>
          <div className="stats">
            <div className="stat">
              <div className="stat-label">我的任务</div>
              <div className="stat-value">
                {tasks.length}
                <small>{enabled.length} 个已开启</small>
              </div>
            </div>
            <div className="stat">
              <div className="stat-label">今日已执行</div>
              <div className="stat-value">
                {todayExecuted}
                <small>记录均已留存</small>
              </div>
            </div>
            <div className="stat">
              <div className="stat-label">需要留意</div>
              <button
                className="stat-value"
                style={{
                  padding: 0,
                  color: attentionCount ? "var(--warn)" : "inherit",
                }}
                onClick={() => actions.navigate("runs")}
              >
                {attentionCount}
                <small>
                  查看处理建议
                  <Icon name="chevron" size={10} />
                </small>
              </button>
            </div>
          </div>
          {attentionCount > 0 && (
            <div className="mb-24">
              <Notice>
                <div className="between wrap">
                  <span>
                    有 {attentionCount}{" "}
                    次执行需要留意，请查看原始记录与处理建议。
                  </span>
                  <button
                    className="text-btn"
                    onClick={() =>
                      attention[0]
                        ? actions.openRun(attention[0])
                        : actions.navigate("runs")
                    }
                  >
                    查看详情
                    <Icon name="arrow" size={13} />
                  </button>
                </div>
              </Notice>
            </div>
          )}
          <div className="panel">
            <div className="panel-head">
              <div className="row">
                <h2>正在安排的任务</h2>
                <span className="tag">{enabled.length} 个已开启</span>
              </div>
              <a className="text-btn" href="#tasks" style={{ fontSize: 11 }}>
                全部任务
                <Icon name="chevron" size={12} />
              </a>
            </div>
            <TaskList
              compact
              tasks={tasks.slice(0, 4)}
              accounts={accounts}
              {...actions}
            />
            <div className="panel-footer">
              <button
                className="text-btn"
                onClick={() => actions.create()}
                style={{ fontSize: 11 }}
              >
                <Icon name="plus" size={14} />
                再安排一件小事
              </button>
            </div>
          </div>
          <div className="section-head">
            <h2>最近发生</h2>
            <a href="#runs" className="text-btn" style={{ fontSize: 11 }}>
              查看全部
              <Icon name="chevron" size={12} />
            </a>
          </div>
          <div className="panel" style={{ padding: "8px 22px" }}>
            {runs.slice(0, 3).map((r) => (
              <div
                className="activity-row"
                key={r.id}
                style={{ width: "100%", textAlign: "left" }}
              >
                <div
                  className={
                    "iconbox " + (r.status === "timeout" ? "amber" : "")
                  }
                >
                  <Icon
                    name={r.status === "timeout" ? "clock" : "check"}
                    size={13}
                  />
                </div>
                <div className="grow">
                  <div className="row wrap">
                    <button
                      className="table-name"
                      onClick={() => actions.openRun(r)}
                    >
                      {r.taskName}
                    </button>
                    <Badge status={r.status} />
                  </div>
                  <ReplyPreview run={r} />
                </div>
                <small>{formatAt(r.at, true).split(" ")[1]}</small>
              </div>
            ))}
          </div>
        </div>
        <aside className="dashboard-aside">
          <div className="stack">
            <div className="panel">
              <div className="panel-head">
                <h2>接下来</h2>
                <Icon name="calendar" size={16} />
              </div>
              <div className="timeline">
                {next.map(({ t, d }, i) => (
                  <div className="timeline-item" key={t.id}>
                    <span className="timeline-point" />
                    <div>
                      <div className="timeline-time">
                        {formatAt(d, true, store.settings.timezone)}
                        {i === 0 && (
                          <span className="tag" style={{ marginLeft: 8 }}>
                            下一项
                          </span>
                        )}
                      </div>
                      <button
                        className="timeline-title table-name"
                        style={{ fontSize: 12 }}
                        onClick={() => actions.navigate("task/" + t.id)}
                      >
                        {t.name}
                      </button>
                      <div className="timeline-sub">
                        {t.targetName} ·{" "}
                        {accounts.find((a) => a.id === t.accountId)?.name}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="panel-footer mini-note">
                时间以 {store.settings.timezone} 显示
              </div>
            </div>
            <div className="panel">
              <div className="panel-head">
                <h2>账号状态</h2>
                <a
                  href="#accounts"
                  className="text-btn"
                  style={{ fontSize: 11 }}
                >
                  管理
                  <Icon name="chevron" size={12} />
                </a>
              </div>
              <div className="connection-list">
                {accounts.map((a, i) => (
                  <div className="connection-row" key={a.id}>
                    <span className={"avatar " + (i ? "alt" : "")}>
                      {a.letter}
                    </span>
                    <div className="grow">
                      <p>{a.name}</p>
                      <small>
                        {a.status === "invalid"
                          ? "需要重新登录"
                          : a.status === "limited"
                            ? "限流等待"
                            : "已接入"}
                      </small>
                    </div>
                    {a.status !== "invalid" ? (
                      <Icon
                        name="check"
                        size={15}
                        style={{ color: "var(--success)" }}
                      />
                    ) : (
                      <button
                        className="text-btn"
                        style={{ fontSize: 10, color: "var(--warn)" }}
                        onClick={() => actions.addAccount(a)}
                      >
                        重新登录
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <div style={{ padding: "5px 8px" }}>
              <div className="row" style={{ gap: 7 }}>
                <Icon name="shield" size={14} style={{ color: "#758266" }} />
                <strong style={{ fontSize: 11 }}>由你掌控的自动化</strong>
              </div>
              <p className="mini-note mt-8">
                自部署设计，账号和任务由你管理。
                <br />
                账号和配置保存在当前实例。
              </p>
            </div>
          </div>
        </aside>
      </div>
      <div className="page-footnote">
        <span>拾刻 SHIKE · 为重复的小事，安排一个好时间。</span>
        <span>
          {new Intl.DateTimeFormat("zh-CN", {
            dateStyle: "long",
            timeZone: store.settings.timezone,
          }).format(new Date())}
        </span>
      </div>
    </section>
  );
}
function TasksPage({ store, actions }) {
  const [tab, setTab] = useState("all"),
    [q, setQ] = useState(""),
    [account, setAccount] = useState("all"),
    [selected, setSelected] = useState([]),
    [bulk, setBulk] = useState(null);
  useEffect(() => setSelected([]), [tab, q, account]);
  const tasks = store.tasks.filter(
    (t) =>
      (tab === "all" || (tab === "enabled" ? t.enabled : !t.enabled)) &&
      (!q ||
        [t.name, t.target, t.targetName]
          .join(" ")
          .toLowerCase()
          .includes(q.toLowerCase())) &&
      (account === "all" || t.accountId === account),
  );
  return (
    <section data-screen-label="我的任务">
      <PageHeader
        title="我的任务"
        description="管理每一个定时安排，随时开启、暂停或调整。"
      >
        <Button variant="primary" icon="plus" onClick={() => actions.create()}>
          创建任务
        </Button>
      </PageHeader>
      <SegmentControl
        label="任务状态"
        value={tab}
        onChange={setTab}
        items={[
          { value: "all", label: "全部任务", count: store.tasks.length },
          {
            value: "enabled",
            label: "已开启",
            count: store.tasks.filter((t) => t.enabled).length,
          },
          {
            value: "paused",
            label: "已暂停",
            count: store.tasks.filter((t) => !t.enabled).length,
          },
        ]}
      >
        <div className="toolbar">
          <div className="row grow">
            <label className="search">
              <Icon name="search" size={15} />
              <input
                aria-label="搜索任务"
                placeholder="搜索任务名称或目标会话"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </label>
            <SelectControl
              className="select-filter"
              aria-label="按执行账号筛选"
              value={account}
              onChange={(e) => setAccount(e.target.value)}
            >
              <option value="all">所有账号</option>
              {store.accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </SelectControl>
          </div>
          <Button
            variant="ghost sm"
            icon="upload"
            onClick={() => actions.importTemplate()}
          >
            导入模板
          </Button>
        </div>
        {selected.length > 0 && (
          <div className="bulk-bar">
            <strong>已选择 {selected.length} 个任务</strong>
            <Button variant="sm" icon="pause" onClick={() => setBulk(false)}>
              批量暂停
            </Button>
            <Button variant="sm" icon="play" onClick={() => setBulk(true)}>
              批量开启
            </Button>
            <Button variant="ghost sm" onClick={() => setSelected([])}>
              取消选择
            </Button>
          </div>
        )}
        {bulk !== null && (
          <BulkTaskDialog
            tasks={store.tasks.filter((t) => selected.includes(t.id))}
            enabled={bulk}
            onClose={() => setBulk(null)}
            onConfirm={async () => {
              await actions.bulkTasks(selected, bulk);
              setSelected([]);
              setBulk(null);
            }}
          />
        )}
        {tasks.length ? (
          <>
            <TaskList
              tasks={tasks}
              accounts={store.accounts}
              {...actions}
              selectedIds={selected}
              onSelect={(id, checked) => {
                if (checked && selected.length >= 100) {
                  actions.toast("一次最多选择 100 个任务");
                  return;
                }
                setSelected((ids) =>
                  checked ? [...ids, id] : ids.filter((i) => i !== id),
                );
              }}
              onSelectAll={(checked) =>
                setSelected(checked ? tasks.slice(0, 100).map((t) => t.id) : [])
              }
            />
            <div className="table-footer">
              <span>共 {tasks.length} 个任务</span>
              <span>任务会按照各自设置的时区执行</span>
            </div>
          </>
        ) : (
          <div className="panel">
            <Empty
              title={
                store.tasks.length
                  ? "没有找到对应任务"
                  : "第一条任务，从这里开始"
              }
              description={
                store.tasks.length
                  ? "试试其他关键词或筛选条件。"
                  : "选择一个模板，或者从一条简单消息开始。"
              }
              action={
                store.tasks.length ? (
                  <Button
                    onClick={() => {
                      setQ("");
                      setAccount("all");
                      setTab("all");
                    }}
                  >
                    清除筛选
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    icon="plus"
                    onClick={() => actions.create()}
                  >
                    创建第一个任务
                  </Button>
                )
              }
            />
          </div>
        )}
      </SegmentControl>
    </section>
  );
}
function AccountsPage({ store, actions }) {
  return (
    <section data-screen-label="账号管理">
      <PageHeader
        title="Telegram 账号"
        description="使用你自己的账号执行任务，支持接入多个账号。"
      >
        <Button
          variant="primary"
          icon="plus"
          onClick={() => actions.addAccount()}
        >
          添加账号
        </Button>
      </PageHeader>
      <div className="notice info mb-24">
        <Icon name="shield" size={16} />
        <div>
          账号只用于执行你配置的任务。登录密码和验证码无需长期保存，登录会话由你的实例管理。
        </div>
      </div>
      {!store.accounts.length ? (
        <div className="panel">
          <Empty
            icon="users"
            title="接入你的第一个账号"
            description="用手机 Telegram 扫码登录，也支持验证码和已有会话导入。"
            action={
              <Button variant="primary" onClick={() => actions.addAccount()}>
                添加 Telegram 账号
              </Button>
            }
          />
        </div>
      ) : (
        <div className="account-grid">
          {store.accounts.map((a, i) => {
            const n = store.tasks.filter((t) => t.accountId === a.id).length;
            return (
              <article className="panel account-card" key={a.id}>
                <div className="between account-heading">
                  <div className="row account-identity">
                    <span className={"avatar lg " + (i ? "alt" : "")}>
                      {a.letter}
                    </span>
                    <div className="account-label">
                      <h2>{a.name}</h2>
                      <span className="muted small">@{a.username}</span>
                    </div>
                  </div>
                  <span
                    className={
                      "status " + (a.status === "connected" ? "" : "warn")
                    }
                  >
                    <span className="status-dot" />
                    {a.status === "invalid"
                      ? "需要登录"
                      : a.status === "limited"
                        ? "限流等待"
                        : "已接入"}
                  </span>
                </div>
                <div className="account-info">
                  <div>
                    <small>手机号</small>
                    <span className="small">{a.phone}</span>
                  </div>
                  <div>
                    <small>关联任务</small>
                    <button
                      className="text-btn"
                      style={{ padding: 0, fontSize: 12 }}
                      onClick={() => actions.navigate("tasks")}
                    >
                      {n} 个任务
                      <Icon name="chevron" size={12} />
                    </button>
                  </div>
                </div>
                {a.status === "invalid" && (
                  <div className="mb-24">
                    <Notice>
                      登录会话已失效。关联任务将保留，重新登录后可继续使用。
                    </Notice>
                  </div>
                )}
                <div className="between account-actions">
                  <div className="row">
                    <Button
                      variant={a.status === "connected" ? "" : "primary"}
                      icon={a.status === "connected" ? "refresh" : "key"}
                      onClick={() =>
                        a.status === "invalid"
                          ? actions.addAccount(a)
                          : actions.checkAccount(a)
                      }
                    >
                      {a.status === "invalid" ? "重新登录" : "检查连接"}
                    </Button>
                    <Button
                      variant="ghost"
                      icon="edit"
                      aria-label={"编辑名称：" + a.name}
                      onClick={() => actions.renameAccount(a)}
                    >
                      编辑名称
                    </Button>
                  </div>
                  <button
                    className="text-btn"
                    style={{ color: "var(--muted)", fontSize: 11 }}
                    onClick={() => actions.removeAccount(a)}
                  >
                    移除账号
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
      <p className="mini-note mt-24 row">
        <Icon name="info" size={14} />
        账号是“由谁发送”，任务里的目标会话是“发送给谁”。
      </p>
    </section>
  );
}
function RunsPage({ store, actions }) {
  const [q, setQ] = useState(""),
    [filter, setFilter] = useState("all"),
    [date, setDate] = useState("all");
  const runs = store.runs.filter(
    (r) =>
      (!q ||
        [r.taskName, r.reply, r.error].some((text) =>
          text?.toLowerCase().includes(q.trim().toLowerCase()),
        )) &&
      (filter === "all" ||
        (filter === "attention"
          ? ["error", "timeout", "failed", "limited", "interrupted"].includes(
              r.status,
            )
          : filter === r.status)) &&
      (date === "all" ||
        dateKey(r.at, store.settings.timezone) ===
          dateKey(Date.now(), store.settings.timezone)),
  );
  return (
    <section data-screen-label="执行记录">
      <PageHeader
        title="每一次执行，都有迹可循。"
        description="查看发送内容、原始回复，以及需要处理的情况。"
      >
        <Button
          icon="download"
          onClick={() => {
            exportJSON(runs, "shike-run-records.json");
            actions.toast("已导出当前筛选的执行记录");
          }}
        >
          导出记录
        </Button>
      </PageHeader>
      <div className="toolbar">
        <label className="search">
          <Icon name="search" size={15} />
          <input
            placeholder="搜索任务、回复或异常原因"
            aria-label="搜索执行记录"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <div className="row">
          <SelectControl
            aria-label="按执行结果筛选"
            className="select-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">所有结果</option>
            <option value="attention">需要留意</option>
            <option value="replied">已收到回复</option>
            <option value="sent">已发送</option>
            <option value="success">规则匹配成功</option>
            <option value="timeout">已发送 · 未等到回复</option>
            <option value="error">执行异常</option>
            <option value="failed">规则匹配失败</option>
          </SelectControl>
          <SelectControl
            aria-label="按日期筛选"
            className="select-filter"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          >
            <option value="all">已加载的全部日期</option>
            <option value="today">今天</option>
          </SelectControl>
        </div>
      </div>
      {runs.length ? (
        <RunsTable
          runs={runs}
          accounts={store.accounts}
          onOpen={actions.openRun}
        />
      ) : (
        <div className="panel">
          <Empty
            icon="history"
            title="这里还没有执行记录"
            description={
              store.runs.length
                ? "调整筛选条件，看看其他记录。"
                : "执行一次任务后，发送内容和回复都会保存在这里。"
            }
            action={
              <Button
                onClick={() => {
                  if (store.runs.length) {
                    setQ("");
                    setFilter("all");
                    setDate("all");
                  } else actions.navigate("tasks");
                }}
              >
                {store.runs.length ? "清除筛选" : "去看看任务"}
              </Button>
            }
          />
        </div>
      )}
      <div className="table-footer">
        <span>
          已加载 {runs.length} 条记录 · 默认保留 {store.settings.retention} 天
        </span>
        <Button variant="ghost sm" onClick={actions.loadMore}>
          加载更早记录
        </Button>
      </div>
      <Notice type="info">
        “已收到回复”表示收到了目标会话的消息。只有任务设置了结果匹配规则，才会进一步判定业务结果。
      </Notice>
    </section>
  );
}
function TemplatesPage({ actions }) {
  const [cat, setCat] = useState("全部");
  return (
    <section data-screen-label="任务模板">
      <PageHeader
        eyebrow="A SMALL HEAD START"
        title="从一个现成的安排开始。"
        description="选一个接近你需求的模板，填上自己的账号和目标就好。"
      />
      <div className="tabbar">
        {["全部", "签到", "提醒", "查询"].map((c) => (
          <button
            key={c}
            className={"tab " + (cat === c ? "active" : "")}
            onClick={() => setCat(c)}
          >
            {c}
          </button>
        ))}
      </div>
      <div className="template-grid">
        {TEMPLATES.filter((t) => cat === "全部" || t.category === cat).map(
          (t) => (
            <article className="panel template-card" key={t.id}>
              <div className="between">
                <div className={"iconbox " + t.color}>
                  <Icon name={t.icon} size={21} />
                </div>
                <span className="tag">{t.category}</span>
              </div>
              <h2>{t.name}</h2>
              <p>{t.desc}</p>
              <footer>
                <span className="mini-note">{t.tag}</span>
                <button className="text-btn" onClick={() => actions.create(t)}>
                  使用模板
                  <Icon name="arrow" size={14} />
                </button>
              </footer>
            </article>
          ),
        )}
        <button
          className="panel template-card"
          style={{
            textAlign: "left",
            borderStyle: "dashed",
            background: "transparent",
          }}
          onClick={() => actions.create()}
        >
          <div className="iconbox">
            <Icon name="plus" size={21} />
          </div>
          <h2>按自己的方式来</h2>
          <p>从空白任务开始，安排任意一条消息或一组简单步骤。</p>
          <footer>
            <span className="text-btn">
              创建空白任务
              <Icon name="arrow" size={14} />
            </span>
          </footer>
        </button>
      </div>
      <p className="mini-note mt-24">
        模板只包含配置方式，不包含登录凭证。具体指令和按钮文字请以目标机器人为准。
      </p>
    </section>
  );
}
function TaskDetail({ task, store, actions }) {
  const [tab, setTab] = useState("config");
  if (!task)
    return (
      <Empty
        title="这条任务已经不在这里了"
        description="它可能已被删除，回到任务列表继续查看。"
        action={
          <Button onClick={() => actions.navigate("tasks")}>
            返回我的任务
          </Button>
        }
      />
    );
  const a = store.accounts.find((a) => a.id === task.accountId),
    runs = store.runs.filter((r) => r.taskId === task.id);
  return (
    <section data-screen-label="任务详情">
      <button
        className="text-btn mb-24"
        onClick={() => actions.navigate("tasks")}
      >
        <Icon name="back" size={15} />
        返回我的任务
      </button>
      <PageHeader
        className="detail-header"
        title={task.name}
        description={`${task.targetName || task.target} · ${a?.name || "未选择账号"}`}
      >
        <div className="row">
          <Button icon="edit" onClick={() => actions.onEdit(task)}>
            编辑
          </Button>
          <Button
            variant="primary"
            icon="play"
            onClick={() => actions.onRun(task)}
          >
            立即执行
          </Button>
          <TaskMenu task={task} {...actions} />
        </div>
      </PageHeader>
      <div className="tabbar">
        <button
          className={"tab " + (tab === "config" ? "active" : "")}
          onClick={() => setTab("config")}
        >
          任务配置
        </button>
        <button
          className={"tab " + (tab === "runs" ? "active" : "")}
          onClick={() => setTab("runs")}
        >
          执行记录<span className="tab-number">{runs.length}</span>
        </button>
      </div>
      {tab === "runs" ? (
        runs.length ? (
          <RunsTable
            runs={runs}
            accounts={store.accounts}
            onOpen={actions.openRun}
          />
        ) : (
          <div className="panel">
            <Empty
              icon="history"
              title="准备就绪，等待第一次执行"
              description="可以等待计划时间，也可以立即执行一次。"
              action={
                <Button
                  variant="primary"
                  icon="play"
                  onClick={() => actions.onRun(task)}
                >
                  立即执行
                </Button>
              }
            />
          </div>
        )
      ) : (
        <div className="detail-grid">
          <div className="stack">
            <div className="panel panel-pad">
              <h2 className="mb-24" style={{ fontSize: 16 }}>
                账号与目标
              </h2>
              <dl className="detail-facts">
                <div>
                  <dt>执行账号</dt>
                  <dd>{a?.name}</dd>
                </div>
                <div>
                  <dt>目标会话</dt>
                  <dd>{task.targetName || task.target}</dd>
                </div>
                <div>
                  <dt>会话地址</dt>
                  <dd className="mono">{task.target}</dd>
                </div>
                <div>
                  <dt>通知方式</dt>
                  <dd>
                    {task.notify === "failure"
                      ? "仅异常时通知"
                      : task.notify === "summary"
                        ? "加入每日摘要"
                        : task.notify === "all"
                          ? "每次执行都通知"
                          : "不通知"}
                  </dd>
                </div>
              </dl>
            </div>
            <div className="panel panel-pad">
              <h2 style={{ fontSize: 16 }}>按这个顺序执行</h2>
              {task.steps.map((s, i) => (
                <div className="detail-action" key={i}>
                  <div className="step-number">{i + 1}</div>
                  <div className="grow">
                    <p>
                      <strong>
                        {s.type === "send"
                          ? "发送消息"
                          : s.type === "wait"
                            ? "等待回复"
                            : s.type === "delay"
                              ? "间隔等待"
                              : "点击按钮"}
                      </strong>
                    </p>
                    <div className="reply-block mt-8">
                      {s.type === "send"
                        ? s.text
                        : s.type === "wait"
                          ? `最多等待 ${s.seconds} 秒`
                          : s.type === "delay"
                            ? `等待 ${s.seconds} 秒后继续`
                            : `按文字匹配：${s.text}`}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="panel panel-pad">
              <h2 style={{ fontSize: 16 }}>结果判定</h2>
              <p className="muted small mt-8">
                {!task.steps.some((s) => s.type === "wait")
                  ? "发送完成即结束，不要求对方回复。"
                  : task.successWords
                    ? `成功关键词：${task.successWords}`
                    : "保留原始回复，不自动推断签到是否成功。"}
              </p>
              {task.failureWords && (
                <p className="muted small mt-8">
                  失败关键词：{task.failureWords}
                </p>
              )}
            </div>
          </div>
          <aside className="stack">
            <div className="panel panel-pad">
              <div className="between">
                <h3>自动执行</h3>
                <Toggle
                  label="启用当前任务"
                  checked={task.enabled}
                  onChange={(v) => actions.onToggle(task.id, v)}
                />
              </div>
              <p className="mt-16" style={{ fontSize: 18, fontWeight: 550 }}>
                {scheduleLabel(task)}
              </p>
              <p className="mini-note mt-8">{task.timezone}</p>
              <div className="divider" />
              <strong className="small">接下来执行</strong>
              {task.enabled ? (
                getNextRuns(task).map((d, i) => (
                  <p className="mini-note mt-8" key={i}>
                    {formatAt(d, false, task.timezone)}
                  </p>
                ))
              ) : (
                <p className="mini-note mt-8">
                  任务已暂停，开启后恢复后续计划。
                </p>
              )}
            </div>
            <div className="panel panel-pad">
              <h3>最近一次</h3>
              {runs[0] ? (
                <>
                  <div className="mt-16">
                    <Badge status={runs[0].status} />
                  </div>
                  <p className="mini-note mt-8">{formatAt(runs[0].at)}</p>
                  <button
                    className="text-btn mt-8"
                    onClick={() => actions.openRun(runs[0])}
                  >
                    查看完整回复
                    <Icon name="arrow" size={13} />
                  </button>
                </>
              ) : (
                <p className="mini-note mt-8">还没有执行记录</p>
              )}
            </div>
          </aside>
        </div>
      )}
    </section>
  );
}
function SettingsPage({ store, actions }) {
  const [tab, setTab] = useState("general"),
    [form, setForm] = useState({ ...store.settings }),
    [error, setError] = useState(""),
    [botToken, setBotToken] = useState(""),
    [saving, setSaving] = useState(false);
  const set = (k, v) => setForm({ ...form, [k]: v });
  async function save() {
    if (!form.workspace.trim()) {
      setError("请填写工作空间名称");
      return;
    }
    if (
      tab === "connection" &&
      form.proxyType !== "none" &&
      (!form.proxyHost || !/^\d+$/.test(form.proxyPort))
    ) {
      setError("请填写代理地址和有效端口");
      return;
    }
    setError("");
    setSaving(true);
    try {
      await actions.setSettings(form, botToken);
      setBotToken("");
      actions.toast("设置已保存");
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <section data-screen-label="系统设置">
      <PageHeader title="设置" description="按你的习惯，安排这个工作空间。" />
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="设置分类">
          {[
            ["general", "settings", "通用"],
            ["connection", "connection", "Telegram 连接"],
            ["notifications", "bell", "通知"],
            ["security", "shield", "安全与数据"],
          ].map(([id, icon, name]) => (
            <button
              className={tab === id ? "active" : ""}
              key={id}
              onClick={() => {
                setTab(id);
                setError("");
              }}
            >
              <Icon name={icon} size={16} />
              {name}
            </button>
          ))}
        </nav>
        <div className="panel form-card">
          {error && (
            <div className="mb-24">
              <Notice type="error">{error}</Notice>
            </div>
          )}
          {tab === "general" && (
            <>
              <h2>通用设置</h2>
              <p>工作空间名称和默认时间偏好。</p>
              <Field id="workspace-name" label="工作空间名称">
                <input
                  id="workspace-name"
                  value={form.workspace}
                  maxLength={30}
                  onChange={(e) => set("workspace", e.target.value)}
                />
              </Field>
              <Field
                id="default-tz"
                label="默认时区"
                hint="新建任务会使用这个时区，已有任务保持各自的设置。"
              >
                <TimezonePicker
                  id="default-tz"
                  value={form.timezone}
                  onChange={(e) => set("timezone", e.target.value)}
                />
              </Field>
              <Field id="retention" label="执行记录保留时间">
                <SelectControl
                  id="retention"
                  value={form.retention}
                  onChange={(e) => set("retention", e.target.value)}
                >
                  <option value="7">7 天</option>
                  <option value="30">30 天（推荐）</option>
                  <option value="90">90 天</option>
                </SelectControl>
              </Field>
            </>
          )}
          {tab === "connection" && (
            <>
              <h2>Telegram 连接</h2>
              <p>连接信息由你部署的实例管理。</p>
              <div className="between">
                <div>
                  <h3>Telegram API 凭证</h3>
                  <p className="mini-note mt-8">
                    {store.settings.hasApi
                      ? "已配置 · 凭证不在页面中回显"
                      : "尚未配置"}
                  </p>
                </div>
                <Button onClick={() => actions.openApi()}>更新凭证</Button>
              </div>
              <div className="divider" />
              <Field
                id="proxy-type"
                label="连接方式"
                hint="如果服务器可以直接连接 Telegram，保持默认即可。"
              >
                <SelectControl
                  id="proxy-type"
                  value={form.proxyType}
                  onChange={(e) => set("proxyType", e.target.value)}
                >
                  <option value="none">直接连接（默认）</option>
                  <option value="socks5">通过 SOCKS5 代理</option>
                  <option value="http">通过 HTTP 代理</option>
                </SelectControl>
              </Field>
              {form.proxyType !== "none" && (
                <div className="fields-2">
                  <Field id="proxy-host" label="代理服务器">
                    <input
                      id="proxy-host"
                      value={form.proxyHost}
                      placeholder="例如 192.168.1.10"
                      onChange={(e) => set("proxyHost", e.target.value)}
                    />
                  </Field>
                  <Field id="proxy-port" label="端口">
                    <input
                      id="proxy-port"
                      value={form.proxyPort}
                      inputMode="numeric"
                      onChange={(e) => set("proxyPort", e.target.value)}
                    />
                  </Field>
                </div>
              )}
              <Button
                icon="connection"
                onClick={() => {
                  if (
                    ["proxyType", "proxyHost", "proxyPort"].some(
                      (k) => form[k] !== store.settings[k],
                    )
                  )
                    setError("请先保存连接设置，再进行测试。");
                  else actions.testConnection();
                }}
              >
                测试连接
              </Button>
            </>
          )}
          {tab === "notifications" && (
            <>
              <h2>通知偏好</h2>
              <p>只接收你关心的消息，具体任务可以单独覆盖。</p>
              <Field id="notify-mode" label="新任务默认通知方式">
                <SelectControl
                  id="notify-mode"
                  value={form.notification}
                  onChange={(e) => set("notification", e.target.value)}
                >
                  <option value="failure">仅异常时通知（推荐）</option>
                  <option value="summary">加入每日摘要</option>
                  <option value="all">每次执行都通知</option>
                  <option value="none">不通知</option>
                </SelectControl>
              </Field>
              <Field
                id="summary-time"
                label="每日摘要发送时间"
                hint={`使用工作空间时区 ${form.timezone}。`}
              >
                <TimePicker
                  id="summary-time"
                  value={form.summaryTime}
                  onChange={(e) => set("summaryTime", e.target.value)}
                />
              </Field>
              <Field id="notify-target" label="通知发到哪里">
                <SelectControl
                  id="notify-target"
                  value={form.notifyTarget || "me"}
                  onChange={(e) => set("notifyTarget", e.target.value)}
                >
                  <option value="me">执行账号的收藏夹（推荐）</option>
                  <option value="bot">通过独立通知机器人</option>
                </SelectControl>
              </Field>
              {form.notifyTarget === "bot" && (
                <>
                  <Field
                    id="notify-token"
                    label="通知机器人 Token"
                    hint="保存在服务端，后续不再回显；留空保留已有配置。"
                  >
                    <input
                      id="notify-token"
                      value={botToken}
                      onChange={(e) => setBotToken(e.target.value)}
                      type="password"
                      placeholder="填写后保存，后续不再回显"
                      autoComplete="off"
                    />
                  </Field>
                  <Field
                    id="notify-chat"
                    label="接收会话"
                    hint="请先与通知机器人发起会话。"
                  >
                    <input
                      id="notify-chat"
                      value={form.notifyChat || ""}
                      onChange={(e) => set("notifyChat", e.target.value)}
                      placeholder="会话 ID"
                    />
                  </Field>
                </>
              )}
              <Button
                icon="bell"
                onClick={() => {
                  if (
                    botToken ||
                    form.notifyTarget !== store.settings.notifyTarget ||
                    form.notifyChat !== store.settings.notifyChat
                  )
                    setError("请先保存通知设置，再发送测试通知。");
                  else actions.testNotification();
                }}
              >
                发送测试通知
              </Button>
            </>
          )}
          {tab === "security" && (
            <>
              <h2>安全与数据</h2>
              <p>管理访问密码、任务配置和账号会话。</p>
              <div className="between">
                <div>
                  <h3>管理密码</h3>
                  <p className="mini-note mt-8">
                    访问面板时需要输入，支持密码管理器。
                  </p>
                </div>
                <Button onClick={() => actions.changePassword()}>
                  修改密码
                </Button>
              </div>
              <div className="divider" />
              <div className="between wrap">
                <div>
                  <h3>导出任务配置</h3>
                  <p className="mini-note mt-8">
                    包含任务配置，不包含登录会话和通知凭证。
                  </p>
                </div>
                <Button icon="download" onClick={() => actions.exportAll()}>
                  导出配置
                </Button>
              </div>
              <div className="divider" />
              <div className="between wrap">
                <div>
                  <h3>恢复与迁移</h3>
                  <p className="mini-note mt-8">
                    导入已导出的任务模板，接入账号后重新绑定。
                  </p>
                </div>
                <Button icon="upload" onClick={() => actions.importTemplate()}>
                  导入配置
                </Button>
              </div>
              <div className="divider" />
              <Notice type="info">
                登录会话与 API Hash
                在当前服务端加密保存。备份时请同时保留数据库和独立加密密钥，避免丢失后无法解密。
              </Notice>
              <div className="mt-24">
                <button
                  className="text-btn"
                  style={{ color: "var(--muted)" }}
                  onClick={actions.logout}
                >
                  <Icon name="exit" size={15} />
                  退出管理登录
                </button>
              </div>
            </>
          )}
          {tab !== "security" && (
            <div className="form-footer">
              <span className="mini-note">修改后点击保存生效</span>
              <Button variant="primary" disabled={saving} onClick={save}>
                {saving ? "正在保存…" : "保存设置"}
              </Button>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
function HelpPage({ actions }) {
  return (
    <section data-screen-label="帮助与入门">
      <PageHeader
        eyebrow="A LITTLE HELP"
        title="第一次用，也可以很顺手。"
        description="跟着一个简单的流程，完成你的第一个自动任务。"
      />
      <div className="help-grid">
        {[
          [
            "user",
            "重新体验首次设置",
            "从设置密码、连接 Telegram 开始。",
            () => actions.navigate("setup"),
          ],
          [
            "layers",
            "从一个模板开始",
            "签到、提醒和查询，选择适合你的。",
            () => actions.navigate("templates"),
          ],
          [
            "book",
            "部署与运行说明",
            "管理密码、连接设置与数据维护。",
            () => window.open("/assets/guide.html", "_blank", "noopener"),
          ],
        ].map(([icon, title, text, fn]) => (
          <button className="panel help-tile" key={title} onClick={fn}>
            <div className="iconbox">
              <Icon name={icon} />
            </div>
            <h2>
              {title}
              <Icon name="chevron" size={13} style={{ marginLeft: 8 }} />
            </h2>
            <p>{text}</p>
          </button>
        ))}
      </div>
      <div className="panel panel-pad mt-24">
        <h2 style={{ fontSize: 16, marginBottom: 9 }}>你可能想知道</h2>
        {[
          [
            "Telegram API 信息在哪里获取？",
            "在 my.telegram.org/apps 申请 api_id 和 api_hash。这是你部署的实例连接 Telegram 所需的应用信息，通常只需要配置一次。这些信息在“设置 → Telegram 连接”中配置。",
          ],
          [
            "执行账号和目标会话有什么区别？",
            "执行账号是用谁的身份发送消息，目标会话是消息发给谁。例如：用“我的主账号”，向“HDHive 机器人”发送“赌狗签到”。",
          ],
          [
            "为什么收到回复，不一定显示成功？",
            "不同机器人回复含义不同。拾刻默认保留原始回复，只有你填写了成功或失败关键词，才按规则判定。没有规则时不会替你猜测。",
          ],
          [
            "任务超时了，要立即重试吗？",
            "先看消息是否已发送。等待回复超时不代表对方没有处理，再次执行可能重复签到或重复发消息。记录详情会提供对应建议。",
          ],
          [
            "关闭浏览器以后，任务还会执行吗？",
            "任务由部署服务执行。只要服务器或 NAS 上的服务保持运行，关闭浏览器不影响执行。服务停止期间错过的计划会跳过，恢复后继续后续计划。",
          ],
          [
            "怎么把一个任务给朋友使用？",
            "导出该任务的模板即可。模板不会包含 Telegram 登录会话和通知 Token，朋友导入后选择自己的账号，再确认目标与时间。",
          ],
        ].map(([q, a]) => (
          <details className="faq" key={q}>
            <summary>{q}</summary>
            <p>{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
