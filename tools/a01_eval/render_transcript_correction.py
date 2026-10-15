"""Publish all fixed-run results and a separately labelled final-guard replay."""
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/ai-core"))
from app.transcript_correction import TranscriptCorrector, CorrectionInput, CorrectionOutput


class FrozenChat:
    def __init__(self, result): self.result = result
    def complete(self, system, payload):
        keys = ("before", "after", "category", "action", "reason")
        return {"edits":[{k:e[k] for k in keys} for e in self.result["edits"]]}, self.result["model_version"]


def main():
    source = ROOT / "services/backend/var/asr-proofread-20261015/run-v1"
    target = ROOT / "docs/agent-loop/evaluations/asr-proofread-20261015"
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for path in sorted(source.glob("*.json")):
        if path.name == "manifest.json": continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["status"] == "completed":
            record["final_guard_replay"] = TranscriptCorrector(FrozenChat(record["result"])).correct(
                CorrectionInput(transcript=record["text"])).model_dump()
        records.append(record)
    done = [r for r in records if r["status"] == "completed"]
    auto = sum(e["action"] == "auto" for r in done for e in r["final_guard_replay"]["edits"])
    review = sum(e["action"] == "review" for r in done for e in r["final_guard_replay"]["edits"])
    data = dict(model="Deepseek-v4-flash", original_calls=records,
        final_guard_code_sha256=hashlib.sha256((ROOT/"services/ai-core/app/transcript_correction.py").read_bytes()).hexdigest(),
        guard_replay_is_new_model_call=False,
        downstream=[json.loads(p.read_text(encoding="utf-8")) for p in sorted((source/"downstream").glob("*.json"))])
    (target/"results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    durations = [r["seconds"] for r in done]
    lines = ["# 自动 ASR 纠错：实际结果（2026-10-15）", "",
        "本轮新增了一次微信 Deepseek-v4-flash LLM API 检查，位于 ASR 与确认文字之间。模型只看到实际机器稿，不读取创作稿或测试答案。纠错内容是修订草稿，不是已听音核实的事实。", "",
        "## 实际运行", "",
        f"- 固定十段历史真实 ASR（虚构人物、合成音频）和六条正确文本对照，每条一次调用：{len(done)}/{len(records)} 返回；A01_10 超时45.015秒，记录原样保留。",
        f"- 成功调用耗时中位数 {statistics.median(durations):.3f} 秒，范围 {min(durations):.3f}—{max(durations):.3f} 秒。超时不计入成功中位数，必须单独报告；这不是实时聊天耗时。",
        f"- 用最终保护规则重新检查同一批模型输出：{auto} 处可自动修订、{review} 处保留疑点。该步骤没有再次调用模型、没有挑选最好结果。原调用输出和重放结果分别保存。",
        "- 六条正确文本对照均未修改，包括真实被电击、否定与例外、年份纠正、姓名字形未知和含命令的引用句。小样结果不代表一般准确率。",
        "- 两份自动修订稿又完成真实模型记忆提取：A01_02 为5条，A01_08为8条。修复了电机、认死理、清福、歇息、搪瓷杯；保留‘不是电机坏’‘不一定都是对的’‘不是冲你’等限定。",
        "- 以上是历史 ASR 重放和模型调用；没有重新录音或重新调用 Paraformer，没有把人工创作稿覆盖为ASR。", "",
        "## 用户看到的变化", "",
        "新版本在转文字时一次说明‘用文字模型修正错词’。后台自动完成检查，核对页先展示修订稿和‘查看修改’，可以恢复机器稿。不必逐条点击接受明显错词；最终确认后才开始记忆整理。未改变录音、转写与记忆整理的授权边界。", "",
        "## 尚未解决", "",
        "- A01_07 的‘冻我东西’漏检；A01_04 的‘画的挺像呀’只改了‘的→得’，没有完整恢复创作稿中的‘画得挺像样’。读起来通顺但已经偏义的错词，单看文字往往难以发现。",
        "- 一条‘她→他’建议不可靠，被保护规则保留为疑点；部分代词建议和‘可她住院’疑点不必要。不能把疑点建议等同于事实纠正。",
        "- 姓名如‘小宁/晓宁’无法仅凭字音定字，不自动换名；需要本人词表或音频／其他有据资料。",
        "- 一次超时说明服务稳定性仍须关注。失败保留原稿，不重复ASR；本轮没有自动无限重试。",
        "- 单条超过12,000字符暂不自动纠错，明确显示保留原稿；长录音分段纠错、亲友补记与实时字幕接入尚未实现。",
        "- 旧记忆不会自动被改写；历史修复须通过已有修订与派生失效机制。", "",
        "## 验证与发布范围", "",
        "AI Core新增18项、后台新增9项针对性测试通过；此前相关AI回归66项、后台78项通过。保护规则额外覆盖局部字修改删除‘也许’、标点移动改变主体和否定范围。审查发现的总超时问题已修复，本地慢速HTTP复现1秒限制在约1.01秒中止。",
        "Android编译及114项单元测试通过；末次文案修订重新编译。尚未做本轮模拟器／实体手机操作验收，也没有部署ECS或生成对外发布安装包。默认功能开关关闭；要启用需同时部署新AI Core、后端worker与新版Android，并开启配置。", "",
        "本轮未推送GitHub，未修改生产数据库或历史录音。", "",
        "## 完整逐条结果", ""]
    for r in records:
        lines.extend([f"### {r['id']} · {r['status']} · {r['seconds']}秒", "", "机器稿：", "", r["text"], ""])
        if r["status"] != "completed":
            lines.extend(["未返回修订；保留机器稿。", ""])
            continue
        final = r["final_guard_replay"]
        lines.extend(["自动修订稿：", "", final["draft"], ""])
        for e in final["edits"]:
            lines.append(f"- {'自动修订' if e['action']=='auto' else '保留疑点'}：{e['before']} → {e['after']}；{e['reason']}")
        lines.append("")
    report = ROOT / "docs/agent-loop/ASR_PROOFREAD_RESULTS_2026-10-15.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    # Machine-readable shared additive schema, separate from the frozen episode contract.
    output_schema = CorrectionOutput.model_json_schema()
    defs = output_schema.pop("$defs", {})
    defs.update(CorrectionInput=CorrectionInput.model_json_schema(), CorrectionOutput=output_schema)
    (ROOT/"packages/contracts/schemas/transcript-correction-v1.schema.json").write_text(json.dumps({
        "$schema":"https://json-schema.org/draft/2020-12/schema", "$defs":defs,
        "description":"Internal ASR proofreading input/output; drafts require the existing owner confirmation."},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"completed":len(done), "total":len(records), "auto":auto, "review":review,
                      "median_success_seconds":statistics.median(durations)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
