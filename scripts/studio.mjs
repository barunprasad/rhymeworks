#!/usr/bin/env node
// Rhymeworks studio launcher: `npm run studio`
// Starts the Python API (FastAPI + GPU queue, :8765) and the web app (Vite, :5173), prefixes their logs,
// opens the browser once the API answers, and stops both on Ctrl-C (or if either one exits).
// `npm run studio:lan` (LAN=1) also serves the web app on your Wi-Fi so you can review from your phone;
// the API itself stays on 127.0.0.1 and is reached through the web app's proxy.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { networkInterfaces } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { logoArea, qrEncode } from "../packages/studio/src/lib/qr.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const API_PORT = Number(process.env.API_PORT ?? 8765);   // change both to run a second studio side by side
const WEB_PORT = Number(process.env.WEB_PORT ?? 5173);
process.env.RHYMEWORKS_API_PORT = String(API_PORT);       // read by vite.config.ts
const LAN = !!process.env.LAN;
const color = (c, s) => `\x1b[${c}m${s}\x1b[0m`;

if (!existsSync(join(ROOT, "packages/studio/node_modules"))) {
  console.error(color(33, "The studio app isn't installed yet. Run this once:  npm run setup"));
  process.exit(1);
}

// ---------------------------------------------------------------- phone link (LAN mode)
function lanAddresses() {
  const nets = networkInterfaces();
  const all = Object.entries(nets).flatMap(([name, xs]) => (xs ?? []).filter((a) => a.family === "IPv4" && !a.internal).map((a) => ({ name, ip: a.address })));
  const privateIp = (ip) => /^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(ip);
  // Wi-Fi / Ethernet (en*) with a home-network address first; VPN tunnels (utun) last
  return all.sort((a, b) => (privateIp(b.ip) - privateIp(a.ip)) || (/^en/.test(b.name) - /^en/.test(a.name))).map((a) => a.ip);
}

/** The phone link as a QR code drawn with half-block characters, the Rhymeworks ♪ tile in the middle. */
function terminalQR(url) {
  const q = qrEncode(url, "H");               // H = 30 % redundancy, so the logo in the middle doesn't matter
  const a = logoArea(q);
  const Q = 3;                                // quiet zone (light border) in modules
  const N = q.size + 2 * Q;
  const INK = 23, PAPER = 231, TEAL = 44;     // 256-colour palette: dark teal ink, white paper, Rhymeworks teal
  const cell = (x, y) => {
    const mx = x - Q, my = y - Q;
    if (mx < 0 || my < 0 || mx >= q.size || my >= q.size) return PAPER;
    const inLogo = mx >= a.x && mx < a.x + a.n && my >= a.y && my < a.y + a.n && !q.isFunction[my][mx];
    if (inLogo) {
      const edge = mx === a.x || my === a.y || mx === a.x + a.n - 1 || my === a.y + a.n - 1;
      return edge ? PAPER : TEAL;              // white ring around a teal tile
    }
    return q.dark[my][mx] ? INK : PAPER;
  };
  const rows = [];
  const midRow = Math.floor((Q + a.y + a.n / 2) / 2), midCol = Q + a.x + Math.floor(a.n / 2);
  for (let y = 0; y < N; y += 2) {
    let line = "";
    for (let x = 0; x < N; x++) {
      const top = cell(x, y), bottom = y + 1 < N ? cell(x, y + 1) : PAPER;
      if (y / 2 === midRow && x === midCol && top === TEAL) line += `\x1b[38;5;16;48;5;${TEAL}m♪`;
      else line += `\x1b[38;5;${top};48;5;${bottom}m▀`;
    }
    rows.push("   " + line + "\x1b[0m");
  }
  return rows.join("\n");
}

function printPhoneCard(urls) {
  const url = urls[0];
  const teal = (s) => `\x1b[38;5;44m${s}\x1b[0m`, dim = (s) => `\x1b[2m${s}\x1b[0m`, bold = (s) => `\x1b[1m${s}\x1b[0m`;
  const W = 41;
  const pad = (s, n) => s + " ".repeat(Math.max(0, n - [...s].length));
  console.log("");
  console.log("   " + teal("╭" + "─".repeat(W) + "╮"));
  console.log("   " + teal("│") + "  " + bold(teal("♪")) + "  " + bold(pad("Rhymeworks Studio", W - 5)) + teal("│"));
  console.log("   " + teal("│") + "     " + pad("Scan with your phone's camera", W - 5) + teal("│"));
  console.log("   " + teal("╰" + "─".repeat(W) + "╯"));
  console.log(terminalQR(phoneLink(url)));
  console.log("   " + bold(url) + (urls.length > 1 ? dim(`   (also ${urls.slice(1).map((u) => u.replace(/^http:\/\//, "")).join(", ")})`) : ""));
  console.log("   " + dim("Phone and Mac on the same Wi-Fi. The code holds a private key: only phones that scan it"));
  console.log("   " + dim("can open the studio. To unlink them all, use \"Make a new link\" in the studio."));
  console.log("");
}

const LAN_URLS = LAN ? lanAddresses().map((ip) => `http://${ip}:${WEB_PORT}`) : [];
if (LAN_URLS.length) process.env.STUDIO_LAN_URL = LAN_URLS[0];   // the web app's "Open on your phone" shows the same code

/** The phone key (studio/lan_key, this computer only): the QR link sets it as a cookie; see pipeline/kidzone/studio/lock.py. */
function lanKey() {
  const f = join(ROOT, "studio", "lan_key");
  try { const k = readFileSync(f, "utf8").trim(); if (k.length >= 20) return k; } catch { /* first run */ }
  const k = randomBytes(24).toString("base64url");
  mkdirSync(dirname(f), { recursive: true });
  writeFileSync(f, k + "\n", { mode: 0o600 });
  return k;
}
const phoneLink = (base) => `${base}/api/unlock?k=${lanKey()}`;

const procs = [];
function run(name, c, cmd, args) {
  const p = spawn(cmd, args, { cwd: ROOT, env: { ...process.env, FORCE_COLOR: "1" }, detached: true });
  const tag = color(c, `[${name}]`);
  const pipe = (stream) => {
    let buf = "";
    stream.on("data", (d) => {
      buf += d;
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const l of lines) if (l.trim()) console.log(`${tag} ${l}`);
    });
  };
  pipe(p.stdout);
  pipe(p.stderr);
  p.on("exit", (code) => {
    console.log(`${tag} stopped${code && !stopping ? ` (exit ${code})` : ""}`);
    shutdown();
  });
  procs.push(p);
  return p;
}

let stopping = false;
function shutdown() {
  if (stopping) return;
  stopping = true;
  for (const p of procs) {
    try { process.kill(-p.pid, "SIGTERM"); } catch {}
  }
  setTimeout(() => process.exit(0), 4000).unref();
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

console.log(color(36, "Rhymeworks studio starting…  (Ctrl-C stops everything)"));
run("api", 35, "uv", ["run", "--project", "pipeline", "kidzone", "studio", "--port", String(API_PORT)]);
run("web", 36, "npm", ["--prefix", "packages/studio", "run", "dev", "--", "--port", String(WEB_PORT), "--strictPort", ...(LAN ? ["--host", "0.0.0.0"] : [])]);

// open the browser once the API is up
const url = `http://127.0.0.1:${WEB_PORT}`;
for (let i = 0; i < 60 && !stopping; i++) {
  try {
    const r = await fetch(`http://127.0.0.1:${API_PORT}/api/health`);
    if (r.ok) {
      console.log(color(32, `Studio ready → ${url}`));
      if (LAN && LAN_URLS.length) printPhoneCard(LAN_URLS);
      else if (LAN) console.log(color(33, "No Wi-Fi address found: is this Mac on a network?"));
      if (!process.env.NO_OPEN) spawn("open", [url], { stdio: "ignore" });
      break;
    }
  } catch {}
  await new Promise((r) => setTimeout(r, 1000));
}
