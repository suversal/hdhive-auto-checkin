// npm ci && npm run build. The shipped bundle runs without a CDN.
import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import path from "node:path";
const require = createRequire(import.meta.url);
const esbuild = process.env.SHIKE_ESBUILD_PATH
  ? require(process.env.SHIKE_ESBUILD_PATH)
  : require("esbuild");
const dir = path.dirname(fileURLToPath(import.meta.url));
const files = [
  "icons.jsx",
  "data.js",
  "api.js",
  "components.jsx",
  "controls.jsx",
  "views.jsx",
  "flows.jsx",
  "app.jsx",
];
const source = files
  .map((file) => readFileSync(path.join(dir, file), "utf8"))
  .join("\n");
const imports = `import * as React from 'react';
import * as ReactDOM from 'react-dom/client';
import * as SelectPrimitive from '@radix-ui/react-select';
import * as PopoverPrimitive from '@radix-ui/react-popover';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import * as MenuPrimitive from '@radix-ui/react-dropdown-menu';
import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import * as SwitchPrimitive from '@radix-ui/react-switch';
import * as TabsPrimitive from '@radix-ui/react-tabs';
import * as CheckboxPrimitive from '@radix-ui/react-checkbox';
import { Command } from 'cmdk';
import { DayPicker } from 'react-day-picker';
import { zhCN } from 'react-day-picker/locale';\n`;
esbuild.buildSync({
  stdin: { contents: imports + source, loader: "jsx", resolveDir: dir },
  outfile: path.join(dir, "app.js"),
  bundle: true,
  format: "iife",
  platform: "browser",
  target: "es2020",
  minify: true,
  legalComments: "eof",
  define: { "process.env.NODE_ENV": '"production"' },
});
writeFileSync(
  path.join(dir, "calendar.css"),
  readFileSync(require.resolve("react-day-picker/style.css"), "utf8"),
);
console.log("Built app.js from " + files.length + " source files.");
const packageRoot = path.join(dir, "node_modules");
const packageDirs = readdirSync(packageRoot)
  .filter((name) => !name.startsWith("."))
  .flatMap((name) =>
    name.startsWith("@")
      ? readdirSync(path.join(packageRoot, name)).map((child) =>
          path.join(packageRoot, name, child),
        )
      : [path.join(packageRoot, name)],
  );
const notices = packageDirs.sort().flatMap((folder) => {
  const manifest = path.join(folder, "package.json");
  if (!existsSync(manifest)) return [];
  const pkg = JSON.parse(readFileSync(manifest, "utf8"));
  if (
    pkg.name === "esbuild" ||
    pkg.name === "axe-core" ||
    pkg.name.startsWith("@esbuild/")
  )
    return [];
  const license = [
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "license",
    "license.md",
    "LICENSE-MIT",
  ].find((name) => existsSync(path.join(folder, name)));
  return [
    `${pkg.name} ${pkg.version}\n${"=".repeat(60)}\n${license ? readFileSync(path.join(folder, license), "utf8") : "License: " + pkg.license}\n`,
  ];
});
writeFileSync(
  path.join(dir, "THIRD_PARTY_NOTICES.txt"),
  (
    "Third-party runtime package notices. Versions are locked in package-lock.json.\n\n" +
    notices.join("\n")
  )
    .replace(/\r\n?/g, "\n")
    .trimEnd() + "\n",
);
