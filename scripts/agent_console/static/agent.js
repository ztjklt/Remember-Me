import {el, status, show, api, agentPath, jsonBody, action, refresh} from "./capture.js";

let locked = null, revision = null;
function controls() {
  const current = locked?.state === "LOCKED";
  const stale = revision !== null && locked?.locked_answer.revision !== revision;
  el("human-panel").hidden = !current;
  const changed = current && el("question").value.trim() !== locked.question;
  el("submit").disabled = el("ask").disabled || !current || stale || changed;
  el("human-answer").disabled = el("submit").disabled;
  el("question").disabled = el("ask").disabled;
  el("lock-id").disabled = el("recover").disabled;
  el("lock-note").textContent = current && stale ? "理解已变化，请重新提问后再校正。" : changed ? "问题已修改，请重新提问后再校正。" : current ? "校正上方这次回答，保存后会更新理解。" : "先提问，回答出现后即可填写校正。";
  if (locked?.state === "COMPLETED") el("lock-note").textContent = "本轮校正已完成，可以再次提问。";
}
function question() {
  const text = el("question").value.trim();
  if (!text) throw Error("请先填写问题");
  return {question: text};
}
function viewLock(result) {
  locked = result;
  el("lock-id").value = result.calibration_id;
  el("question").value = result.question;
  show("asked", `你问：${result.question}`);
  show("answer", result.locked_answer);
  el("answer-context").textContent = result.state === "COMPLETED" ? "以下保留校正前的回答；再次提问会使用更新后的理解。" : "";
  show("calibration", result);
  controls();
}
window.addEventListener("consolecontrols", controls);
window.addEventListener("modelchange", (event) => {revision = event.detail.revision; controls();});
window.addEventListener("sessionchange", () => {
  locked = null; revision = null;
  el("lock-id").value = ""; el("human-answer").value = "";
  for (const id of ["answer", "calibration", "plan", "asked", "correction"]) show(id, "会话已变更，请重新读取");
  show("updated", ""); el("answer-context").textContent = "";
  controls();
});
el("question").oninput = controls;
el("lock-id").oninput = () => {locked = null; el("human-answer").value = ""; controls();};

action("ask", async () => {
  const body = question();
  locked = null; el("human-answer").value = ""; el("answer-context").textContent = "";
  for (const id of ["calibration", "updated", "correction"]) show(id, "");
  show("asked", `你问：${body.question}`); show("answer", "正在回答…"); controls();
  status("正在根据当前理解回答…");
  try {
    viewLock(await api(agentPath("/calibrations"), jsonBody(body)));
    status("回答已返回。如有不准确的地方，可在下方校正。");
  } catch (error) {show("answer", "未得到有效回答，请查看错误并重试。"); throw error;}
});
action("recover", async () => {
  const id = el("lock-id").value.trim();
  if (!id) throw Error("请填写 calibration ID");
  viewLock(await api(agentPath(`/calibrations/${encodeURIComponent(id)}`)));
  status(`锁定记录已恢复：${locked.state}`);
});
action("submit", async () => {
  if (locked?.state !== "LOCKED" || el("question").value.trim() !== locked.question) throw Error("请先提问，再校正这次回答");
  const human = el("human-answer").value.trim();
  if (!human) throw Error("请填写本人答案");
  status("正在保存校正并更新理解…");
  viewLock(await api(agentPath(`/calibrations/${encodeURIComponent(locked.calibration_id)}/submit`), jsonBody({human_answer: human, expected_revision: locked.locked_answer.revision})));
  show("correction", `你的校正：${human}`);
  show("updated", await refresh());
  status(`校正已保存，当前理解更新至第 ${revision} 版。可以再次提问。`);
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
