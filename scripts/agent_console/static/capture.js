import {render} from "./render.js";
export const el = (id) => document.getElementById(id);
let busy = false, recorder, stream, timer, recording, preview;
const stages = {uploaded: "已接收", transcribing: "正在转写", extracting: "正在提取记忆", modeling: "正在更新理解", ready: "处理完成"};

export function status(text, error = false) {
  el("status").textContent = text;
  el("status").dataset.error = error;
}
export function show(id, value) {
  if (el(id)) el(id).textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  render(id, value);
}
export function agentPath(path) {
  if (!el("subject").value.trim()) throw Error("请先加载会话");
  return `/experimental/agent/v1/subjects/${encodeURIComponent(el("subject").value.trim())}${path}`;
}
export async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${el("token").value.trim()}`);
  const response = await fetch(path, {...options, headers, signal: AbortSignal.timeout(130000)});
  if (response.status === 204) return null;
  const body = await response.json();
  if (!response.ok) throw Error(`HTTP ${response.status} · ${body.error_code || ""} · ${body.error_message || body.detail || "请求失败"}`);
  return body;
}
export function jsonBody(value) {
  return {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(value)};
}
function controls() {
  const active = recorder?.state === "recording";
  document.querySelectorAll("button").forEach((button) => {button.disabled = busy || active;});
  el("stop").disabled = !active;
  el("session-fields").disabled = busy || active;
  for (const id of ["microphone", "file", "episode"]) el(id).disabled = busy || active;
  window.dispatchEvent(new Event("consolecontrols"));
}
export function action(id, fn) {
  el(id).onclick = async () => {
    if (busy) return;
    busy = true; controls();
    try { await fn(); } catch (error) { status(error.message, true); }
    finally { busy = false; controls(); }
  };
}
function clearResults() {
  recording = null; el("file").value = "";
  if (preview) {URL.revokeObjectURL(preview); preview = null;}
  el("preview").removeAttribute("src"); el("preview").load();
  el("episode").value = "";
  for (const id of ["memories", "model", "evidence"]) show(id, "会话已变更，请重新读取");
  window.dispatchEvent(new Event("sessionchange"));
}
for (const id of ["token", "subject", "consent"]) el(id).oninput = clearResults;
action("connect", async () => {
  const response = await fetch("session", {cache: "no-store"});
  if (!response.ok) throw Error("本地演示会话不可用，请检查启动日志");
  const data = await response.json();
  el("token").value = data.actor_token; el("subject").value = data.subject_id;
  el("consent").value = data.recording_consent_id;
  clearResults();
  el("mode").textContent = data.mode === "fixture" ? "离线测试：录音不会被真实转写，返回固定测试材料。" : "真实模式：上传后调用服务端配置的 ASR 与 Agent。";
  status("会话已加载，可以开始录音。");
});

async function devices() {
  const selected = el("microphone").value;
  el("microphone").replaceChildren(new Option("系统默认麦克风", ""));
  for (const device of await navigator.mediaDevices.enumerateDevices()) {
    if (device.kind === "audioinput") el("microphone").add(new Option(device.label || "麦克风", device.deviceId));
  }
  el("microphone").value = selected;
}
action("devices", async () => {
  const probe = await navigator.mediaDevices.getUserMedia({audio: true});
  try { await devices(); status("请选择耳机麦克风，或保留系统默认设备。"); }
  finally { probe.getTracks().forEach((track) => track.stop()); }
});
function captured(blob, name, started, duration) {
  if (preview) URL.revokeObjectURL(preview);
  preview = URL.createObjectURL(blob); el("preview").src = preview;
  recording = {blob, name, started, duration, key: crypto.randomUUID()};
  el("episode").value = "";
  status(`录音已保留在页面，${Math.round(blob.size / 1024)} KB。请检查声音并确认同意后上传。`);
}
action("record", async () => {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw Error("请用 Chrome 或 Edge 打开本机 localhost 地址，并允许麦克风。");
  const deviceId = el("microphone").value;
  stream = await navigator.mediaDevices.getUserMedia({audio: deviceId ? {deviceId: {exact: deviceId}} : true});
  try {
    const mimeType = ["audio/webm;codecs=opus", "audio/mp4"].find((type) => MediaRecorder.isTypeSupported(type));
    if (!mimeType) throw Error("浏览器没有支持的录音格式，请改用 Chrome 或 Edge。");
    const chunks = [], started = new Date(), monotonic = performance.now();
    recorder = new MediaRecorder(stream, {mimeType, audioBitsPerSecond: 64000});
    recorder.ondataavailable = (event) => {if (event.data.size) chunks.push(event.data);};
    recorder.onstop = () => {
      clearTimeout(timer); stream.getTracks().forEach((track) => track.stop());
      captured(new Blob(chunks, {type: mimeType}), mimeType.startsWith("audio/webm") ? "capture.webm" : "capture.m4a", started, Math.round(performance.now() - monotonic));
      controls();
    };
    recorder.start(1000); timer = setTimeout(() => recorder.stop(), 299000);
    status("正在录音，请说话。完成后点击停止录音。");
  } catch (error) {stream.getTracks().forEach((track) => track.stop()); throw error;}
});
el("stop").onclick = () => recorder?.state === "recording" && recorder.stop();
el("file").onchange = () => {
  const file = el("file").files[0];
  if (file) captured(file, file.name, new Date(), null);
};
export async function refresh() {
  const [model, evidence] = await Promise.all([api(agentPath("/model")), api(agentPath("/evidence"))]);
  show("model", model); show("evidence", evidence);
  window.dispatchEvent(new CustomEvent("modelchange", {detail: model}));
  status(`已读取第 ${model.revision} 版理解。`);
  return model;
}
async function processEpisode(id) {
  const deadline = Date.now() + 360000;
  while (Date.now() < deadline) {
    const current = await api(`/api/v1/episodes/${encodeURIComponent(id)}`);
    status(`${stages[current.status] || current.status} · ${id}`);
    if (current.status === "failed") throw Error(`${current.error_code}: ${current.error_message}`);
    if (current.status === "ready") {
      show("memories", await api(`/api/v1/episodes/${encodeURIComponent(id)}/result`));
      await refresh(); return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }
  throw Error("处理还未完成，可以稍后点击继续查看处理。");
}
action("upload", async () => {
  if (!recording?.blob.size) throw Error("请先录音或选择音频文件");
  if (recording.blob.size > 7 * 1024 * 1024) throw Error("请使用 7 MB 以内的短录音");
  if (!el("recording-consent").checked || !el("cloud-consent").checked) throw Error("请先确认录音处理同意和本人单人录音声明");
  await api(agentPath("/grant"), jsonBody({recording_consent_id: el("consent").value.trim(), cloud_twin_consent: true, subject_single_speaker: true}));
  const form = new FormData();
  for (const [key, value] of Object.entries({subject_id: el("subject").value.trim(), recording_consent_id: el("consent").value.trim(), source: "IMPORT", audio_ref: recording.name, recorded_at: recording.started.toISOString(), idempotency_key: recording.key, metadata: JSON.stringify({agent_subject_single_speaker: true})})) form.set(key, value);
  if (recording.duration !== null) form.set("duration_ms", String(recording.duration));
  form.set("file", recording.blob, recording.name);
  status("正在上传录音…");
  const result = await api("/api/v1/episodes", {method: "POST", body: form});
  el("episode").value = result.episode_id;
  await processEpisode(result.episode_id);
});
action("check", async () => {
  const id = el("episode").value.trim();
  if (!id) throw Error("请填写 Episode ID，或先上传录音");
  await processEpisode(id);
});
action("refresh", refresh);
window.addEventListener("pagehide", () => {
  clearTimeout(timer); stream?.getTracks().forEach((track) => track.stop());
  if (preview) URL.revokeObjectURL(preview);
});
