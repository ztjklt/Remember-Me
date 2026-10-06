import {el, status, show, api, agentPath, jsonBody, action, refresh} from "./capture.js";

let locked = null, revision = null;
function controls() {
  const current = locked?.state === "LOCKED";
  const stale = revision !== null && locked?.locked_answer.revision !== revision;
  el("human-panel").hidden = !current;
  el("submit").disabled ||= !current || stale;
  el("human-answer").disabled = el("submit").disabled;
  el("question").disabled = el("ask").disabled;
  el("lock-id").disabled = el("recover").disabled;
  el("lock-note").textContent = current && stale ? "理解版本已变化，请重新锁定当前问题再校准。" : "先锁定 Twin 答案，再填写本人答案。";
  if (locked?.state === "COMPLETED") el("lock-note").textContent = "本轮校准已完成；后续问答使用当前理解，锁定记录保留当时版本。";
}
function question() {
  const text = el("question").value.trim();
  if (!text) throw Error("请先填写问题");
  return {question: text};
}
function viewLock(result) {
  locked = result;
  el("lock-id").value = result.calibration_id;
  show("calibration", result);
  controls();
}
window.addEventListener("consolecontrols", controls);
window.addEventListener("modelchange", (event) => {revision = event.detail.revision; controls();});
window.addEventListener("sessionchange", () => {
  locked = null; revision = null;
  el("lock-id").value = ""; el("human-answer").value = "";
  for (const id of ["answer", "calibration", "plan"]) show(id, "会话已变更，请重新读取");
  show("updated", "");
  controls();
});
el("lock-id").oninput = () => {locked = null; el("human-answer").value = ""; controls();};

action("ask", async () => {
  const body = question();
  show("answer", "正在回答…");
  status("正在根据当前理解检索证据并回答…");
  try {
    show("answer", await api(agentPath("/twin"), jsonBody(body)));
    status("Twin 回答已返回，请核对 response_type 和原文证据。");
  } catch (error) {show("answer", "未得到有效回答，请查看错误并重试。"); throw error;}
});
action("lock", async () => {
  const body = question();
  locked = null; el("human-answer").value = ""; controls();
  status("正在生成并锁定 Twin 答案…");
  viewLock(await api(agentPath("/calibrations"), jsonBody(body)));
  status("答案已锁定，现在可以填写本人答案。");
});
action("recover", async () => {
  const id = el("lock-id").value.trim();
  if (!id) throw Error("请填写 calibration ID");
  viewLock(await api(agentPath(`/calibrations/${encodeURIComponent(id)}`)));
  status(`锁定记录已恢复：${locked.state}`);
});
action("submit", async () => {
  if (locked?.state !== "LOCKED") throw Error("请先锁定答案");
  const human = el("human-answer").value.trim();
  if (!human) throw Error("请填写本人答案");
  status("正在比较五维差异并更新理解…");
  viewLock(await api(agentPath(`/calibrations/${encodeURIComponent(locked.calibration_id)}/submit`), jsonBody({human_answer: human, expected_revision: locked.locked_answer.revision})));
  show("updated", await refresh());
  show("answer", "校准已保存。再次提问可检查更新后的回答。");
  status(`校准已保存，当前理解 revision ${revision}。历史提取结果保留原样，可以再次问 Twin。`);
});
action("next", async () => {
  const result = await api(agentPath("/plan"));
  show("plan", result);
  status(result.question);
});
action("revoke", async () => {
  await api(agentPath("/grant"), {method: "DELETE"});
  el("cloud-consent").checked = false; el("episode").value = "";
  for (const id of ["memories", "model", "evidence"]) show(id, "Cloud Twin 同意已撤回");
  window.dispatchEvent(new Event("sessionchange"));
  status("Cloud Twin 同意已撤回。继续使用前需要再次明确同意。");
});
controls();
