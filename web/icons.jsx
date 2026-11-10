const ICONS = {
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  list: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="m8 8 1 1 2-2m-3 7 1 1 2-2m3-5h3m-3 6h3" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21v-2a8 8 0 0 1 16 0v2" />
    </>
  ),
  users: (
    <>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      <circle cx="9" cy="7" r="4" />
    </>
  ),
  history: (
    <>
      <path d="M3 11a9 9 0 1 1 2.6 7M3 4v7h7m2-4v5l3 2" />
    </>
  ),
  layers: (
    <>
      <path d="m12 3 10 5-10 5L2 8l10-5Zm-9 9 9 5 9-5M3 16l9 5 9-5" />
    </>
  ),
  settings: (
    <>
      <path d="m9 3-1 3-3 1-2 3 2 3v4l3 2 4-1 3 2 3-2v-4l3-3-1-4-4-1-2-3Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3m.1 4h.01" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  down: <path d="m6 9 6 6 6-6" />,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  back: <path d="M20 12H4m6-6-6 6 6 6" />,
  check: <path d="m5 12 4 4L19 6" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  more: (
    <>
      <circle cx="5" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="19" cy="12" r="1" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M16 3v4M8 3v4M3 11h18m-13 4h2m4 0h2" />
    </>
  ),
  send: (
    <>
      <path d="m22 2-7 20-4-9L2 9 22 2ZM22 2 11 13" />
    </>
  ),
  bot: (
    <>
      <rect x="3" y="7" width="18" height="14" rx="3" />
      <path d="M12 3v4M8 12v3m8-3v3M1 12v5m22-5v5" />
    </>
  ),
  bell: (
    <>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="7.5" />
      <path d="m16 16 5 5" />
    </>
  ),
  play: <path d="m7 4 14 8-14 8V4Z" />,
  pause: (
    <>
      <path d="M7 4v16M17 4v16" />
    </>
  ),
  alert: (
    <>
      <path d="m12 3 10 18H2L12 3Z" />
      <path d="M12 9v4m0 4h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v6m0-10h.01" />
    </>
  ),
  shield: (
    <>
      <path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4Z" />
      <path d="m8 12 3 3 5-6" />
    </>
  ),
  key: (
    <>
      <circle cx="8" cy="9" r="5" />
      <path d="m12 13 8 8m-4-4 3-3m-6 0 3-3" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 7a9 9 0 0 0-15-2L2 8m0-5v5h5m-3 9a9 9 0 0 0 15 2l3-3m0 5v-5h-5" />
    </>
  ),
  loader: (
    <>
      <path d="M12 3a9 9 0 1 1-9 9" />
    </>
  ),
  message: (
    <>
      <path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z" />
    </>
  ),
  click: (
    <>
      <path d="m4 3 7 18 2-8 8-2L4 3Zm10 11 7 7M3 12H1M12 3V1" />
    </>
  ),
  copy: (
    <>
      <rect x="8" y="8" width="13" height="13" rx="2" />
      <path d="M16 8V3H3v13h5" />
    </>
  ),
  trash: (
    <>
      <path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" />
    </>
  ),
  edit: (
    <>
      <path d="m16 3 5 5-12 12-6 1 1-6L16 3ZM14 5l5 5" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4m-5 5 5-5 5 5M4 17v4h16v-4" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <ellipse cx="12" cy="12" rx="4" ry="9" />
      <path d="M3 12h18" />
    </>
  ),
  connection: (
    <>
      <path d="M8 12h8m-6-7H7a7 7 0 0 0 0 14h3m4-14h3a7 7 0 0 1 0 14h-3" />
    </>
  ),
  book: (
    <>
      <path d="M12 6s-4-4-10-2v16c6-2 10 2 10 2s4-4 10-2V4c-6-2-10 2-10 2Zm0 0v16" />
    </>
  ),
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  exit: (
    <>
      <path d="M10 3H3v18h7m5-15 6 6-6 6m6-6H9" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  up: <path d="m6 15 6-6 6 6" />,
  external: (
    <>
      <path d="M14 3h7v7m0-7L10 14M9 3H3v18h18v-6" />
    </>
  ),
  spark: (
    <>
      <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z" />
    </>
  ),
};
function Icon({ name, size = 18, className = "", ...props }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...props}
    >
      {ICONS[name] || ICONS.grid}
    </svg>
  );
}
function Brand() {
  return (
    <a className="brand" href="#overview" title="返回概览">
      <span className="brand-mark">
        <svg
          width="24"
          height="24"
          viewBox="0 0 40 40"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M9 11h22L13 29h18M9 20h21" />
        </svg>
      </span>
      <span>
        拾刻<small>SHIKE</small>
      </span>
    </a>
  );
}
