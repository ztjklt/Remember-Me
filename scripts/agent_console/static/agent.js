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
  for (const id of ["answer", "calibration", "plan"]) el(id).textContent = "会话已变更，请重新读取";
  controls();
});
el("lock-id").oninput = () => {locked = null; el("human-answer").value = ""; controls();};

action("ask", async () => {
  const body = question();
  el("answer").textContent = "正在请求 Twin…";
  try {
    show("answer", await api(agentPath("/twin"), jsonBody(body)));
    status("Twin 回答已返回，请核对 response_type 和原文证据。");
  } catch (error) {el("answer").textContent = "未得到有效回答，请查看错误并重试。"; throw error;}
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
  await refresh();
});
action("next", async () => {
  const result = await api(agentPath("/plan"));
  show("plan", result);
  status(result.question);
});
action("revoke", async () => {
  await api(agentPath("/grant"), {method: "DELETE"});
  el("cloud-consent").checked = false; el("episode").value = "";
  for (const id of ["memories", "model", "evidence"]) el(id).textContent = "Cloud Twin 同意已撤回";
  window.dispatchEvent(new Event("sessionchange"));
  status("Cloud Twin 同意已撤回。继续使用前需要再次明确同意。");
});
controls();
