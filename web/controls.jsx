function optionText(value) {
  return React.Children.toArray(value)
    .map((v) =>
      typeof v === "object" ? optionText(v.props.children) : String(v),
    )
    .join("");
}
function SelectControl({
  children,
  value,
  onChange,
  className = "",
  disabled,
  placeholder,
  ...props
}) {
  const options = React.Children.toArray(children).filter(React.isValidElement);
  return (
    <SelectPrimitive.Root
      value={String(value ?? "") || "__empty"}
      disabled={disabled}
      onValueChange={(v) =>
        onChange?.({ target: { value: v === "__empty" ? "" : v } })
      }
    >
      <SelectPrimitive.Trigger
        className={`control-select ${className}`}
        {...props}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <Icon name="down" size={15} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className="control-select-menu"
          position="popper"
          sideOffset={6}
          collisionPadding={12}
        >
          <SelectPrimitive.ScrollUpButton className="select-scroll">
            <Icon name="up" size={14} />
          </SelectPrimitive.ScrollUpButton>
          <SelectPrimitive.Viewport>
            {options.map((o, i) => (
              <SelectPrimitive.Item
                key={i}
                value={String(o.props.value) || "__empty"}
                disabled={o.props.disabled}
                textValue={optionText(o.props.children)}
                className="control-option"
              >
                <SelectPrimitive.ItemText>
                  {o.props.children}
                </SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator>
                  <Icon name="check" size={15} />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
          <SelectPrimitive.ScrollDownButton className="select-scroll">
            <Icon name="down" size={14} />
          </SelectPrimitive.ScrollDownButton>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
function SearchPicker({
  id,
  label,
  value,
  placeholder = "请选择",
  items,
  onChange,
  error,
  loading,
  description,
  allowAddress = false,
  ...props
}) {
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState("");
  const selected = items.find((i) => i.value === value),
    validTarget = /^(?:@[a-zA-Z0-9_]{4,32}|-?\d{1,20}|me)$/.test(query.trim());
  const filtered = items.filter((i) =>
    (i.label + " " + i.value + " " + (i.description || ""))
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  function choose(item) {
    onChange(item);
    setOpen(false);
    setQuery("");
  }
  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Trigger asChild>
        <button
          type="button"
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-label={label}
          className="search-picker"
          {...props}
        >
          <span className="iconbox">
            <Icon
              name={selected?.icon || (value === "me" ? "book" : "search")}
              size={18}
            />
          </span>
          <span className="grow">
            <strong>{selected?.label || value || placeholder}</strong>
            <small>
              {selected?.description || description || "搜索并选择"}
            </small>
          </span>
          <Icon name="down" size={16} />
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          className="control-popover picker-popover"
          aria-label={label}
          align="start"
          sideOffset={8}
          collisionPadding={12}
        >
          <Command shouldFilter={false} label={label + "搜索"}>
            <div className="command-search">
              <Icon name="search" size={17} />
              <Command.Input
                autoFocus
                value={query}
                onValueChange={setQuery}
                placeholder={placeholder}
                aria-label={label + "搜索"}
              />
              <kbd>Esc</kbd>
            </div>
            <Command.List>
              {loading && (
                <div className="picker-status">
                  <Icon name="loader" className="spinner" size={16} />
                  正在读取会话…
                </div>
              )}
              {error && <div className="picker-status error">{error}</div>}
              {filtered.map((i) => (
                <Command.Item
                  key={i.value}
                  value={i.value + " " + i.label}
                  onSelect={() => choose(i)}
                >
                  {i.icon && (
                    <span className="iconbox">
                      <Icon name={i.icon} size={17} />
                    </span>
                  )}
                  <span className="grow">
                    <strong>{i.label}</strong>
                    <small>{i.description || i.value}</small>
                  </span>
                  {value === i.value && <Icon name="check" size={16} />}
                </Command.Item>
              ))}
              {!filtered.length && !loading && (
                <div className="picker-status">
                  没有匹配项
                  {validTarget ? "，可使用下方地址" : "，试试其他关键词"}。
                </div>
              )}
              {allowAddress &&
                validTarget &&
                !items.some((i) => i.value === query.trim()) && (
                  <Command.Item
                    value={"direct-" + query}
                    onSelect={() =>
                      choose({
                        value: query.trim(),
                        label: query.trim(),
                        type: "bot",
                      })
                    }
                  >
                    <Icon name="plus" size={17} />
                    <span>
                      使用会话地址 <strong>{query.trim()}</strong>
                    </span>
                  </Command.Item>
                )}
            </Command.List>
            <div className="picker-footer">
              <span>↑ ↓ 选择</span>
              <span>↵ 确认</span>
            </div>
          </Command>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
function TargetPicker({
  targets,
  value,
  name,
  onSelect,
  error,
  loading,
  ...props
}) {
  const items = targets
    .filter((t) => t.id !== "me")
    .map((t) => ({
      value: t.id,
      label: t.name,
      description: t.sub,
      type: t.type,
      icon: t.icon,
    }));
  items.unshift({
    value: "me",
    label: "发给自己",
    description: "Telegram 收藏夹 · 仅你本人可见",
    type: "self",
    icon: "book",
  });
  if (value && !items.some((i) => i.value === value))
    items.push({
      value,
      label: name || value,
      description: value,
      type: "bot",
      icon: "bot",
    });
  return (
    <SearchPicker
      {...props}
      value={value}
      items={items}
      error={error}
      loading={loading}
      allowAddress
      placeholder="搜索会话，或输入 @用户名 / ID"
      label="目标会话"
      onChange={(i) => onSelect({ id: i.value, name: i.label, type: i.type })}
    />
  );
}
function TimezonePicker({ value, onChange, ...props }) {
  const zones = Intl.supportedValuesOf
    ? Intl.supportedValuesOf("timeZone")
    : ["Asia/Shanghai", "Asia/Tokyo", "UTC"];
  const ordered = ["Asia/Shanghai", "Asia/Tokyo", "UTC", ...zones];
  const names = {
    "Asia/Shanghai": "北京 · Asia/Shanghai",
    "Asia/Tokyo": "东京 · Asia/Tokyo",
    UTC: "协调世界时 · UTC",
  };
  return (
    <SearchPicker
      {...props}
      label="时区"
      value={value}
      placeholder="搜索城市或时区"
      items={[...new Set([...ordered, value])].map((z) => ({
        value: z,
        label: names[z] || z,
        description: "按当地时间计算计划",
        icon: "clock",
      }))}
      onChange={(i) => onChange({ target: { value: i.value } })}
    />
  );
}
function TimePicker({ id, value, onChange, ...props }) {
  const [open, setOpen] = useState(false);
  const [hour, minute] = (value || "08:30").split(":");
  const numbers = (n) =>
    Array.from({ length: n }, (_, i) => String(i).padStart(2, "0"));
  return (
    <div className="time-control">
      <Icon name="clock" size={17} />
      <input
        id={id}
        value={value}
        onChange={onChange}
        placeholder="08:30"
        inputMode="numeric"
        maxLength={5}
        {...props}
      />
      <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
        <PopoverPrimitive.Trigger asChild>
          <button
            type="button"
            aria-label="打开时间选择器"
            className="icon-btn"
          >
            <Icon name="down" size={15} />
          </button>
        </PopoverPrimitive.Trigger>
        <PopoverPrimitive.Portal>
          <PopoverPrimitive.Content
            className="control-popover time-popover"
            aria-label="选择时间"
            align="end"
            sideOffset={8}
            collisionPadding={12}
          >
            <div className="eyebrow">选择时间</div>
            <div className="time-columns">
              <SelectControl
                aria-label="小时"
                value={hour}
                onChange={(e) =>
                  onChange({ target: { value: e.target.value + ":" + minute } })
                }
              >
                {numbers(24).map((n) => (
                  <option value={n} key={n}>
                    {n} 时
                  </option>
                ))}
              </SelectControl>
              <span>:</span>
              <SelectControl
                aria-label="分钟"
                value={minute}
                onChange={(e) =>
                  onChange({ target: { value: hour + ":" + e.target.value } })
                }
              >
                {numbers(60).map((n) => (
                  <option value={n} key={n}>
                    {n} 分
                  </option>
                ))}
              </SelectControl>
            </div>
            <div className="time-presets">
              {["06:00", "08:30", "12:00", "21:00"].map((t) => (
                <button
                  type="button"
                  key={t}
                  onClick={() => {
                    onChange({ target: { value: t } });
                    setOpen(false);
                  }}
                >
                  {t}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="btn primary"
              onClick={() => setOpen(false)}
            >
              确定
            </button>
          </PopoverPrimitive.Content>
        </PopoverPrimitive.Portal>
      </PopoverPrimitive.Root>
    </div>
  );
}
function localDateString(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function DateTimePicker({ id, value, onChange, timezone, ...props }) {
  const [open, setOpen] = useState(false),
    [datePart, timePart = "08:30"] = (value || "").split("T");
  const date = datePart ? new Date(datePart + "T12:00:00") : undefined;
  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Trigger asChild>
        <button type="button" className="date-trigger" id={id} {...props}>
          <Icon name="calendar" size={18} />
          <span className="grow">
            {datePart
              ? `${datePart}　${timePart.slice(0, 5)}`
              : "选择日期与时间"}
          </span>
          <Icon name="down" size={15} />
        </button>
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          className="control-popover date-popover"
          aria-label="选择日期与时间"
          align="start"
          sideOffset={8}
          collisionPadding={12}
        >
          <DayPicker
            mode="single"
            locale={zhCN}
            selected={date}
            defaultMonth={date}
            onSelect={(d) =>
              d &&
              onChange({
                target: {
                  value: localDateString(d) + "T" + timePart.slice(0, 5),
                },
              })
            }
            showOutsideDays
            fixedWeeks
          />
          <div className="calendar-time">
            <span>执行时间</span>
            <TimePicker
              value={timePart.slice(0, 5)}
              onChange={(e) =>
                onChange({
                  target: {
                    value:
                      (datePart || localDateString(new Date())) +
                      "T" +
                      e.target.value,
                  },
                })
              }
            />
          </div>
          <div className="between mt-16">
            <span className="mini-note">时区：{timezone}</span>
            <button
              type="button"
              className="btn primary sm"
              onClick={() => setOpen(false)}
            >
              确定
            </button>
          </div>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
function CheckControl({ checked, onChange, label }) {
  return (
    <CheckboxPrimitive.Root
      checked={checked}
      onCheckedChange={onChange}
      aria-label={label}
      className="control-checkbox"
    >
      <CheckboxPrimitive.Indicator>
        <Icon name="check" size={13} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
function SegmentControl({ value, onChange, items, label, children }) {
  return (
    <TabsPrimitive.Root value={value} onValueChange={onChange}>
      <TabsPrimitive.List className="segmented-control" aria-label={label}>
        {items.map((i) => (
          <TabsPrimitive.Trigger key={i.value} value={i.value}>
            {i.label}
            {i.count !== undefined && <span>{i.count}</span>}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {items.map((i) => (
        <TabsPrimitive.Content
          key={i.value}
          value={i.value}
          className="task-tab-panel"
        >
          {i.value === value ? children : null}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}

function BulkTaskDialog({ tasks, enabled, onClose, onConfirm }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <Modal
      title={`批量${enabled ? "开启" : "暂停"}任务`}
      subtitle={`将影响以下 ${tasks.length} 个任务`}
      onClose={() => !busy && onClose()}
    >
      <Notice type="info">
        {enabled
          ? "开启后按各自的计划执行，此操作不会立即发送消息。"
          : "暂停后不再触发新的计划，正在执行的步骤继续完成。"}
      </Notice>
      <div className="bulk-task-list">
        {tasks.map((t) => (
          <div key={t.id}>
            <strong>{t.name}</strong>
            <div className="mini-note">
              {t.targetName || t.target} · {scheduleLabel(t)}
            </div>
          </div>
        ))}
      </div>
      {error && <Notice type="error">{error}</Notice>}
      <div className="modal-footer">
        <Button onClick={onClose} disabled={busy}>
          取消
        </Button>
        <Button
          variant="primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await onConfirm();
            } catch (e) {
              setError(e.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "正在更新…" : `确认${enabled ? "开启" : "暂停"}`}
        </Button>
      </div>
    </Modal>
  );
}
function CommandPalette({ store, actions, onClose }) {
  function go(route) {
    onClose();
    actions.navigate(route);
  }
  return (
    <Modal
      title="快速查找"
      subtitle="查找任务，或跳转到常用页面"
      onClose={onClose}
    >
      <Command className="command-palette" label="快速查找">
        <div className="command-search">
          <Icon name="search" size={17} />
          <Command.Input
            autoFocus
            placeholder="输入任务名称或页面…"
            aria-label="搜索任务或页面"
          />
          <kbd>Esc</kbd>
        </div>
        <Command.List>
          <Command.Empty className="picker-status">
            没有找到匹配内容
          </Command.Empty>
          <Command.Group heading="工作空间">
            {[
              ["overview", "概览", "grid"],
              ["tasks", "我的任务", "list"],
              ["accounts", "Telegram 账号", "user"],
              ["runs", "执行记录", "history"],
              ["templates", "任务模板", "layers"],
              ["settings", "设置", "settings"],
            ].map(([route, label, icon]) => (
              <Command.Item
                key={route}
                value={label}
                onSelect={() => go(route)}
              >
                <Icon name={icon} size={17} />
                {label}
              </Command.Item>
            ))}
          </Command.Group>
          <Command.Group heading="我的任务">
            {store.tasks.map((t) => (
              <Command.Item
                key={t.id}
                value={t.name + " " + t.target}
                onSelect={() => go("task/" + t.id)}
              >
                <Icon name="bot" size={17} />
                <span className="grow">
                  <strong>{t.name}</strong>
                  <small>{t.targetName || t.target}</small>
                </span>
                <Badge status={t.enabled ? "enabled" : "paused"} />
              </Command.Item>
            ))}
          </Command.Group>
        </Command.List>
      </Command>
    </Modal>
  );
}
