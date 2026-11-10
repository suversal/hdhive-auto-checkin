function App() {
  const [auth, setAuth] = useState(null),
    [store, setStore] = useState(null),
    [route, setRoute] = useState(location.hash.slice(1) || "overview"),
    [connectionError, setConnectionError] = useState(""),
    [modal, setModal] = useState(null),
    [draft, setDraft] = useState(null),
    [editorKey, setEditorKey] = useState(0),
    [mobile, setMobile] = useState(false),
    [toast, setToast] = useState(""),
    [refreshing, setRefreshing] = useState(false);
  const toastTimer = useRef(),
    fileRef = useRef(),
    leaveGuard = useRef(null),
    routeRef = useRef(route);
  routeRef.current = route;
  const names = {
    overview: "概览",
    tasks: "我的任务",
    accounts: "Telegram 账号",
    runs: "执行记录",
    templates: "任务模板",
    settings: "设置",
    help: "帮助与入门",
    new: "创建任务",
  };
  const notify = (message, type = "info") => {
    setToast({ message, type });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 4200);
  };
  function navigate(destination, force = false) {
    if (force) leaveGuard.current = null;
    else if (leaveGuard.current) {
      leaveGuard.current(() => navigate(destination, true));
      return;
    }
    if (destination === routeRef.current) {
      window.scrollTo(0, 0);
      return;
    }
    location.hash = destination;
  }
  async function refresh() {
    try {
      const data = await api("/state");
      setStore((old) => {
        const ids = new Set(data.runs.map((r) => r.id));
        const older = (old?.runs || []).filter(
          (r) =>
            !ids.has(r.id) &&
            Date.parse(r.at) >=
              Date.now() - Number(data.settings.retention) * 86400000,
        );
        return { ...data, runs: [...data.runs, ...older] };
      });
      setConnectionError("");
      return data;
    } catch (e) {
      setConnectionError(e.message);
      throw e;
    }
  }
  async function boot() {
    try {
      const status = await api("/auth/status");
      setAuth(status);
      if (status.authenticated) await refresh();
      setConnectionError("");
    } catch (e) {
      setConnectionError(e.message);
    }
  }
  useEffect(() => {
    boot();
    const expired = () => {
      csrfToken = "";
      setAuth((a) => ({ ...a, authenticated: false }));
      setStore(null);
      setModal(null);
    };
    window.addEventListener("shike:unauthorized", expired);
    return () => {
      window.removeEventListener("shike:unauthorized", expired);
      clearTimeout(toastTimer.current);
    };
  }, []);
  useEffect(() => {
    const key = (e) => {
      if (
        (e.metaKey || e.ctrlKey) &&
        e.key.toLowerCase() === "k" &&
        auth?.authenticated
      ) {
        e.preventDefault();
        setModal((m) => (m?.type === "command" ? null : { type: "command" }));
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [auth?.authenticated]);
  useEffect(() => {
    if (!auth?.authenticated) return;
    const timer = setInterval(() => {
      if (!document.hidden) refresh().catch(() => {});
    }, 3000);
    const visible = () => {
      if (!document.hidden) refresh().catch(() => {});
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [auth?.authenticated]);
  useEffect(() => {
    const changed = () => {
      const destination = location.hash.slice(1) || "overview";
      if (leaveGuard.current && destination !== "new") {
        history.replaceState(null, "", "#new");
        leaveGuard.current(() => navigate(destination, true));
        return;
      }
      setRoute(destination);
      setMobile(false);
      window.scrollTo(0, 0);
      setTimeout(
        () =>
          document
            .querySelector("[data-page-heading]")
            ?.focus({ preventScroll: true }),
        30,
      );
    };
    const links = (e) => {
      const a = e.target.closest?.("a[href]"),
        href = a?.getAttribute("href");
      if (leaveGuard.current && href?.startsWith("#") && href !== "#new") {
        e.preventDefault();
        navigate(href.slice(1));
      }
    };
    window.addEventListener("hashchange", changed);
    document.addEventListener("click", links, true);
    return () => {
      window.removeEventListener("hashchange", changed);
      document.removeEventListener("click", links, true);
    };
  }, []);
  useEffect(() => {
    document.title =
      (auth && !auth.authenticated ? "管理员登录" : names[route] || "拾刻") +
      " · 拾刻";
  }, [route, auth?.authenticated]);
  function draftFrom(template, accountId) {
    const data = {
      ...structuredClone(EMPTY_TASK),
      accountId:
        accountId ||
        store.accounts.find((a) => a.status === "connected")?.id ||
        "",
      timezone: store.settings.timezone,
      notify: store.settings.notification,
    };
    if (template)
      Object.assign(
        data,
        {
          name: template.name,
          steps: structuredClone(template.steps),
          kind: template.id === "button" ? "buttons" : "message",
          fromTemplate: true,
        },
        template.id === "weekly"
          ? {
              schedule: "weekly",
              weekdays: [5],
              target: "me",
              targetName: "发给自己（Telegram 收藏夹）",
              targetType: "self",
            }
          : {},
      );
    return data;
  }
  function create(template) {
    if (!store.accounts.length) {
      setModal({ type: "needAccount", template });
      return;
    }
    beginEdit(draftFrom(template));
  }
  function addAccount(account, extra = {}) {
    setModal(
      store.settings.hasApi
        ? { type: "account", account, ...extra }
        : { type: "api", account, afterAccount: true, ...extra },
    );
  }
  async function saveAccount() {
    const resume = modal?.afterCreate,
      template = modal?.template;
    const updated = await refresh();
    setModal(null);
    if (resume) {
      setDraft(
        draftFrom(
          template,
          updated.accounts.find((a) => a.status === "connected")?.id,
        ),
      );
      setEditorKey((k) => k + 1);
      navigate("new", true);
    }
    notify("Telegram 账号已接入");
  }
  function beginEdit(data) {
    const enter = () => {
      setDraft(data);
      setEditorKey((k) => k + 1);
      navigate("new", true);
    };
    if (leaveGuard.current) leaveGuard.current(enter);
    else enter();
  }
  function edit(task) {
    beginEdit(structuredClone(task));
  }
  function copy(task) {
    const copy = {
      ...taskPayload(task),
      name: task.name + "（副本）",
      enabled: false,
      revision: undefined,
      fromTemplate: true,
    };
    beginEdit(copy);
    notify("配置已复制，保存后成为新任务");
  }
  async function saveTask(task) {
    const updated = await api("/tasks" + (task.id ? "/" + task.id : ""), {
      method: task.id ? "PUT" : "POST",
      body: taskPayload(task),
    });
    setDraft(null);
    navigate("task/" + updated.id, true);
    await refresh();
    notify(
      task.id
        ? "任务修改已保存"
        : task.enabled
          ? "任务已创建，将按计划执行"
          : "任务已保存，保持暂停",
    );
  }
  async function toggle(id, enabled) {
    try {
      await api("/tasks/" + id + "/enabled", {
        method: "PATCH",
        body: { enabled },
      });
      await refresh();
      notify(enabled ? "任务已开启" : "后续计划已暂停，当前执行不受影响");
    } catch (e) {
      notify(e.message, "error");
    }
  }
  function run(task) {
    const account = store.accounts.find((a) => a.id === task.accountId);
    if (!account) {
      notify("请先为任务选择执行账号");
      edit(task);
      return;
    }
    if (account.status === "invalid") {
      addAccount(account);
      return;
    }
    setModal({ type: "run", task, account });
  }
  function confirmDelete(task) {
    setModal({
      type: "confirm",
      title: "删除“" + task.name + "”？",
      text: "后续计划将停止，历史执行记录会继续保留。执行中的任务需先取消或等待结束。",
      button: "删除任务",
      action: async () => {
        await api("/tasks/" + task.id, { method: "DELETE" });
        setModal(null);
        if (route.startsWith("task/")) navigate("tasks");
        await refresh();
        notify("任务已删除，历史记录已保留");
      },
    });
  }
  function removeAccount(account) {
    const count = store.tasks.filter((t) => t.accountId === account.id).length;
    setModal({
      type: "confirm",
      title: "移除“" + account.name + "”？",
      text: `将清除本实例保存的账号会话，并暂停 ${count} 个关联任务。若需撤销 Telegram 授权，可在 Telegram 的设备列表中结束此会话。`,
      button: "移除账号",
      action: async () => {
        await api("/accounts/" + account.id, { method: "DELETE" });
        setModal(null);
        await refresh();
        notify("账号已移除，关联任务已暂停");
      },
    });
  }
  async function exportAll() {
    try {
      exportJSON(await api("/templates/export"), "shike-task-templates.json");
      notify("任务配置已导出，不包含账号登录凭证");
    } catch (e) {
      notify(e.message, "error");
    }
  }
  function exportTask(task) {
    const out = taskPayload(task);
    delete out.accountId;
    delete out.revision;
    exportJSON(
      { format: "shike-task-v1", tasks: [out] },
      task.name + "-template.json",
    );
    notify("已导出任务模板");
  }
  async function importFile(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 1024 * 1024) {
      notify("请选择小于 1 MB 的 JSON 模板");
      return;
    }
    try {
      const body = JSON.parse(await file.text());
      const result = await api("/templates/import", { method: "POST", body });
      await refresh();
      navigate("tasks");
      notify(`已导入 ${result.imported} 个任务，保持暂停，请先确认账号与目标`);
    } catch (e) {
      notify(e instanceof SyntaxError ? "配置文件不是有效 JSON。" : e.message);
    }
  }
  async function checkAccount(account) {
    notify("正在检查 Telegram 连接…");
    try {
      await api("/accounts/" + account.id + "/check", { method: "POST" });
      await refresh();
      notify("账号连接检查通过");
    } catch (e) {
      await refresh().catch(() => {});
      notify(e.message, "error");
    }
  }
  async function saveSettings(settings, botToken = "") {
    const keys = [
      "workspace",
      "timezone",
      "language",
      "proxyType",
      "proxyHost",
      "proxyPort",
      "notification",
      "summaryTime",
      "retention",
      "notifyTarget",
      "notifyChat",
    ];
    const body = Object.fromEntries(
      keys
        .filter((k) => settings[k] !== undefined)
        .map((k) => [k, settings[k]]),
    );
    await api("/settings", { method: "PUT", body });
    if (botToken)
      await api("/settings/notification-token", {
        method: "PUT",
        body: { token: botToken.trim() },
      });
    await refresh();
  }
  async function login(password) {
    const result = await api("/auth/login", {
      method: "POST",
      body: { password },
    });
    setAuth({ initialized: true, ...result });
    const data = await refresh();
    if (!data.settings.hasApi) navigate("setup", true);
    else if (route === "login" || route === "setup") navigate("overview", true);
  }
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      csrfToken = "";
      setAuth({ initialized: true, authenticated: false });
      setStore(null);
      setModal(null);
      navigate("login", true);
    } catch (e) {
      notify(e.message, "error");
    }
  }
  async function loadMore() {
    try {
      const page = await api("/runs?limit=200&offset=" + store.runs.length);
      setStore((s) => ({
        ...s,
        runs: [
          ...s.runs,
          ...page.items.filter((r) => !s.runs.some((x) => x.id === r.id)),
        ],
      }));
      notify(page.items.length ? "已加载更早的执行记录" : "已经是全部记录");
    } catch (e) {
      notify(e.message, "error");
    }
  }
  const actions = {
    navigate,
    registerGuard: (guard) => {
      leaveGuard.current = guard;
    },
    create,
    addAccount,
    removeAccount,
    checkAccount,
    toast: notify,
    saveApi: async (body) => {
      await api("/settings/telegram", { method: "PUT", body });
      await refresh();
    },
    setSettings: saveSettings,
    testConnection: async () => {
      notify("正在检测服务器连接…");
      try {
        await api("/settings/test-connection", { method: "POST" });
        notify("服务器已连接到 Telegram");
      } catch (e) {
        notify(e.message, "error");
      }
    },
    testNotification: async () => {
      notify("正在发送测试通知…");
      try {
        await api("/settings/test-notification", { method: "POST" });
        notify("测试通知已发送");
      } catch (e) {
        notify(e.message, "error");
      }
    },
    loadMore,
    logout,
    bulkTasks: async (taskIds, enabled) => {
      await api("/tasks/bulk", { method: "POST", body: { taskIds, enabled } });
      await refresh();
      notify(`已${enabled ? "开启" : "暂停"} ${taskIds.length} 个任务`);
    },
    onToggle: toggle,
    onRun: run,
    onEdit: edit,
    onCopy: copy,
    onDelete: confirmDelete,
    onExport: exportTask,
    exportAll,
    importTemplate: () => fileRef.current?.click(),
    openApi: () => setModal({ type: "api" }),
    changePassword: () => setModal({ type: "password" }),
    openRun: (record) => setModal({ type: "record", run: record }),
    onOpen: (record) => setModal({ type: "record", run: record }),
  };
  let page;
  if (auth === null) {
    page = (
      <div className="empty" style={{ paddingTop: "20vh" }}>
        <Brand />
        <h2 className="mt-24">
          {connectionError ? "暂时无法连接服务" : "正在打开你的工作空间…"}
        </h2>
        <p>{connectionError || "请稍候"}</p>
        {connectionError && (
          <Button variant="primary" onClick={boot}>
            重新连接
          </Button>
        )}
      </div>
    );
  } else if (!auth.authenticated) {
    page = (
      <LoginPage
        initialized={auth.initialized}
        onLogin={login}
        onRefresh={boot}
      />
    );
  } else if (!store) {
    page = (
      <Empty
        icon="connection"
        title="正在读取工作空间"
        description={connectionError || "账号、任务与记录从服务器加载。"}
        action={
          connectionError && (
            <Button onClick={() => refresh().catch(() => {})}>重试</Button>
          )
        }
      />
    );
  } else if (route === "setup") {
    page = (
      <SetupPage
        store={store}
        actions={actions}
        onDone={() => navigate("overview")}
      />
    );
  } else {
    uiTimezone = store.settings.timezone;
    const view =
      route === "overview" ? (
        <Overview store={store} actions={actions} />
      ) : route === "tasks" ? (
        <TasksPage store={store} actions={actions} />
      ) : route === "accounts" ? (
        <AccountsPage store={store} actions={actions} />
      ) : route === "runs" ? (
        <RunsPage store={store} actions={actions} />
      ) : route === "templates" ? (
        <TemplatesPage actions={actions} />
      ) : route === "settings" ? (
        <SettingsPage store={store} actions={actions} />
      ) : route === "help" ? (
        <HelpPage actions={actions} />
      ) : route === "new" ? (
        <TaskEditor
          key={editorKey}
          draft={draft}
          store={store}
          actions={actions}
          onSave={saveTask}
          onCancel={() => {
            setDraft(null);
            navigate("tasks", true);
          }}
        />
      ) : route.startsWith("task/") ? (
        <TaskDetail
          task={store.tasks.find((t) => t.id === route.split("/")[1])}
          store={store}
          actions={actions}
        />
      ) : (
        <Empty
          title="这个页面不存在"
          description="返回工作空间继续查看。"
          action={
            <Button onClick={() => navigate("overview")}>返回概览</Button>
          }
        />
      );
    page = (
      <>
        <Sidebar route={route} store={store} />
        {mobile && (
          <Sidebar
            route={route}
            store={store}
            mobile
            close={() => setMobile(false)}
          />
        )}
        <main className="main">
          <header className="topbar">
            <div className="row">
              <button
                className="icon-btn mobile-menu"
                aria-label="展开导航"
                onClick={() => setMobile(true)}
              >
                <Icon name="menu" size={19} />
              </button>
              <div className="breadcrumb">
                <span className="workspace-label">工作空间</span>
                <Icon name="chevron" size={12} />
                <span>{names[route] || "任务详情"}</span>
              </div>
            </div>
            <div className="row topbar-actions">
              <button
                type="button"
                className="command-launch"
                onClick={() => setModal({ type: "command" })}
                aria-label="快速查找 ⌘ K"
              >
                <Icon name="search" size={15} />
                <span>快速查找</span>
                <kbd aria-hidden="true">⌘ K</kbd>
              </button>
              <span className="demo-badge">
                <span className="workspace-dot" />
                {store.adapter === "test"
                  ? "自动化测试环境"
                  : connectionError
                    ? "服务连接中断"
                    : "服务已连接"}
              </span>
              <IconButton
                name="refresh"
                label="刷新工作空间"
                disabled={refreshing}
                onClick={async () => {
                  setRefreshing(true);
                  try {
                    await refresh();
                    notify("工作空间已更新");
                  } catch {
                  } finally {
                    setRefreshing(false);
                  }
                }}
              />
              <button
                className="avatar"
                aria-label="管理工作空间"
                onClick={() => navigate("settings")}
              >
                S
              </button>
            </div>
          </header>
          <div className="content">
            {connectionError && (
              <div className="mb-24">
                <Notice type="error">
                  {connectionError}，页面暂时保留上次数据。
                  <button
                    className="text-btn"
                    onClick={() => refresh().catch(() => {})}
                  >
                    重试连接
                  </button>
                </Notice>
              </div>
            )}
            {view}
          </div>
        </main>
        <BottomNav route={route} />
      </>
    );
  }
  return (
    <>
      {page}
      {auth?.authenticated && (
        <input
          ref={fileRef}
          type="file"
          accept=".json,application/json"
          className="screen-reader"
          tabIndex={-1}
          aria-label="导入任务配置文件"
          onChange={importFile}
        />
      )}
      {toast && (
        <div
          className={"toast " + toast.type}
          role={toast.type === "error" ? "alert" : "status"}
        >
          <Icon name={toast.type === "error" ? "alert" : "info"} size={16} />
          {toast.message}
        </div>
      )}
      {modal?.type === "command" && store && (
        <CommandPalette
          store={store}
          actions={actions}
          onClose={() => setModal(null)}
        />
      )}
      {modal?.type === "account" && (
        <AccountDialog
          account={modal.account}
          onClose={() => setModal(null)}
          onSave={saveAccount}
        />
      )}
      {modal?.type === "run" && (
        <RunDialog
          task={modal.task}
          account={modal.account}
          onClose={() => setModal(null)}
          onFinish={() => refresh().catch(() => {})}
        />
      )}
      {modal?.type === "record" && (
        <RunDetail
          run={modal.run}
          store={store}
          onClose={() => setModal(null)}
          onTask={(t) => {
            setModal(null);
            navigate("task/" + t.id);
          }}
        />
      )}
      {modal?.type === "confirm" && (
        <ConfirmDialog modal={modal} onClose={() => setModal(null)} />
      )}
      {modal?.type === "needAccount" && (
        <Modal title="先接入一个 Telegram 账号" onClose={() => setModal(null)}>
          <p className="muted small">
            接入后即可选择目标、内容和时间。刚选择的模板会继续保留。
          </p>
          <div className="modal-footer">
            <Button onClick={() => setModal(null)}>稍后再说</Button>
            <Button
              variant="primary"
              onClick={() =>
                addAccount(null, {
                  afterCreate: true,
                  template: modal.template,
                })
              }
            >
              添加账号
            </Button>
          </div>
        </Modal>
      )}
      {["api", "password"].includes(modal?.type) && (
        <CredentialDialog
          type={modal.type}
          onClose={() => setModal(null)}
          onDone={async () => {
            const previous = modal;
            await refresh();
            setModal(
              previous.afterAccount ? { ...previous, type: "account" } : null,
            );
            notify("设置已更新");
          }}
        />
      )}
    </>
  );
}
function ConfirmDialog({ modal, onClose }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal title={modal.title} onClose={onClose}>
      <p className="muted small">{modal.text}</p>
      {error && (
        <div className="mt-16">
          <Notice type="error">{error}</Notice>
        </div>
      )}
      <div className="modal-footer">
        <Button onClick={onClose}>取消</Button>
        <Button
          variant="danger"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await modal.action();
            } catch (e) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "正在处理…" : modal.button}
        </Button>
      </div>
    </Modal>
  );
}
ReactDOM.createRoot(document.getElementById("root")).render(
  <TooltipPrimitive.Provider delayDuration={350} skipDelayDuration={100}>
    <App />
  </TooltipPrimitive.Provider>,
);
