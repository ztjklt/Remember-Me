# Persona v8：作者姓名锚点按程序署名核对

本轮只修正一个已复现的程序误拦。没有云请求、运行库变更、启停进程或新增真实验收题；v7 的原始失败不修改。生成/公开提示版本为 `persona-conditional-reviewed-v8`，审阅提示版本为 `persona-semantic-review-v8`，公开格式不变。

## 真实失败与原因

保存的 v7 L01 trace `6a7501fbd4f9480ea8cca26fd8e999d4` 中，初稿两个 ATTRIBUTED 点的 `names` 都含实际作者 `A01 亲友体验`；唯一修正稿第二点仍含该作者。该姓名不在引文正文里，但程序使用所选补记 `author_name` 在引号外添加了完整署名。

原校验只检查 `name in point.text`，因此把正确呈现的作者署名误报成 `name_text_mismatch`。这是可确定的程序范围错误，不需要推测模型语义理由。

## 有界修复

仅在以下条件全部成立时，作者姓名可不重复出现在引文正文：

- 本点为 ATTRIBUTED，并已通过恰好一个所选补记及引用身份校验。
- `names` 项逐字等于该补记完整的 `author_name`。
- 实际呈现文字包含同一渲染器使用此作者与分类构造的精确署名前缀。

其他名字仍须在引文正文及该点所选材料中都有依据；作者名片段、分类标签、未选作者、仅出现在补记其他位置的人名不享有例外。FACT / SIMULATION 的原规则不变。连续原文匹配、姓名来源、语义审阅、否定与条件、相关性、字符/引用预算及 90 秒/最多三次调用限制均不变。

提示同步说明：可以把实际作者列入 `names`，但不应为满足字面检查把作者名塞入原文。机械署名证明谁记录，不证明引文中的其他人就是该作者。

## 离线检查

新增 `test_persona_author_prefix.py` 共 10 项。首次 **3 failed / 7 passed**：两份历史草稿被旧逻辑误拦；包含正确作者和另一个虚构名字的对照先被旧作者检查挡住。实现后 **10 passed**，虚构名字继续由 `name_source_mismatch` 拒绝，其余负面对照保留 `name_text_mismatch`。

直接读取保存的初稿和修正稿，分别与测试 fixture 逐字段核对。两份草稿在 v8 均直接进入语义审阅，无额外结构修正。新回放保存在 Git 忽略的 `services/ai-core/var/persona-v8-author-prefix-replay-20261012.json`。回放的语义结论是明确标注的测试 fixture，不是实际模型新判断；旧失败不能据此追记成功。

最终完整 AI suite：**425 passed**，28.89 秒；两项既有 Starlette/httpx、AnyIO 依赖弃用警告。`git diff --check -- services/ai-core` 通过。

修复不承诺模型对引文相关性、人物关系或部分覆盖总能判断正确；这些仍由既有语义审阅处理。本轮代码已冻结，不再扩题。
