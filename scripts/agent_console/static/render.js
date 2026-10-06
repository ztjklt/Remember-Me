// Render provider text as text nodes; raw payloads remain in the debug drawer.
const domains = {IDENTITY: "身份", EPISODIC_MEMORY: "经历", RELATIONSHIPS: "关系", PREFERENCES: "偏好", VALUES: "价值与方向", DECISION_PATTERNS: "决策", EXPRESSION: "表达"};
const states = {SUPPORTED: "有依据", CANDIDATE: "待确认", CONFLICTED: "有冲突"};
function node(tag, text, className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  element.className = className;
  return element;
}
function modelView(target, model) {
  target.append(node("p", `第 ${model.revision} 版理解`, "meta"));
  const traits = model.traits.filter((trait) => trait.status !== "SUPERSEDED");
  if (!traits.length) target.append(node("p", "还没有形成理解，请先上传一段录音。"));
  for (const trait of traits) {
    const item = node("article", "", "trait");
    item.append(node("span", `${domains[trait.domain] || trait.domain} · ${states[trait.status] || trait.status}`, "meta"), node("p", trait.statement));
    target.append(item);
  }
}
export function render(id, value) {
  const target = document.getElementById(`${id}-view`);
  if (!target) return;
  target.replaceChildren();
  if (typeof value === "string") {target.append(node("p", value)); return;}
  if (id === "model" || id === "updated") modelView(target, value);
  if (id === "evidence") {
    const recordings = value.filter((item) => item.source_type === "SUBJECT" && item.episode_id);
    const selected = document.getElementById("episode").value.trim();
    const latest = [...recordings].sort((a, b) => b.observed_at.localeCompare(a.observed_at))[0];
    const episode = selected || latest?.episode_id;
    const excerpts = [...new Set(recordings.filter((item) => item.episode_id === episode).map((item) => item.excerpt))];
    target.append(node("p", excerpts.join("\n") || "暂无这段录音的原文。上传录音或刷新已有理解。"));
    if (excerpts.length) target.append(node("p", "录音转写可能有同音字错误，可在下方校正。", "meta"));
  }
  if (id === "answer") {
    const labels = {ORIGINAL: "引用原话", SIMULATION: "依据记忆生成", INSUFFICIENT: "材料不足"};
    target.append(node("p", `${labels[value.response_type] || value.response_type} · 第 ${value.revision} 版理解`, "meta"), node("p", value.answer));
    if (value.evidence?.length) {
      const details = node("details", "");
      details.append(node("summary", `查看回答依据（${value.evidence.length}）`));
      for (const item of value.evidence) details.append(node("blockquote", `${item.source_type === "CALIBRATION" ? "本人校正" : "原始材料"}：${item.excerpt}`));
      target.append(details);
    }
  }
  if (id === "calibration") {
    target.append(node("p", value.state === "COMPLETED" ? `已保存你的校正，理解更新至第 ${value.resulting_revision} 版。` : "回答已保存，可以填写你的校正。"));
  }
}
