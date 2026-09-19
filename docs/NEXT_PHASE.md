# Remember Me 下一阶段建议

第一阶段完成后先进行视觉与产品反馈，不直接接真实 AI。确认方向后，建议依次推进：

1. 为关键 Feature 引入 ViewModel 与 SavedState，补齐旋转和进程恢复。
2. 实现本地 AudioCaptureService，并保持 Voice Clone 为独立授权。
3. 以 Room 建立 Episode、Memory 与 consent 的本地证据底座。
4. 完成可纠正和可删除的 Memory 详情，以及依赖失效协议。
5. 加入 instrumentation smoke test 与可访问性测试。
6. 在供应商评估后，通过现有 interfaces 接入 STT、Twin 与 Voice 实现。
7. 获得 Work 3200 官方资料后实现 HardwareCaptureAdapter capability profile。

任何真实云端处理开始前，需要先确定数据驻留、声音生物特征授权、审计和级联删除策略。
