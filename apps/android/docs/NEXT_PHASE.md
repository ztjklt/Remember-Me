# Remember Me Android 下一阶段

当前基线是 [PRD v3.0](../../../docs/PRD/Remember_Me_PRD_v3.0.docx) 与 [Team Development Guide v1.0](../../../docs/team/Remember_Me_Team_Development_Guide_v1.0.docx)。Android 是正式客户端基线，本模块的 Phase 规划见 [Task Brief](../../../docs/team/01_LIUXIUXIAN_ANDROID_HARDWARE.md) 与 [Roadmap](../../../docs/roadmap/ROADMAP.md)。

## Phase 1 — Golden Path（COMMITTED / NOW）

原型评审已完成，不再以「先做视觉反馈」为阻塞条件。Phase 1 的退出 Gate 是真机完成 `录音 → 上传 → Episode → Processing → 真实 Memory 展示`。按顺序推进：

1. 麦克风权限、真实录音、暂停/停止、elapsed time、audio-file persistence 与 metadata。
2. 用 Repository / Service interface 替换 Mock Capture State，接受来自 shared contract 的后端状态。
3. 音频上传、progress、retry、Episode 创建，并把真实 processing state 接到 Processing 页面。
4. 处理 permission denial、missing data、offline storage、upload failure 与 processing failure。
5. 为关键 Feature 引入 ViewModel 与 SavedState，补齐旋转和进程恢复。
6. 以 Room 建立 Episode、Memory 与 consent 的本地证据底座。
7. 加入 instrumentation smoke test 与可访问性测试。

Android 只调用 Backend Contract，不直接接入任何具体供应商 SDK，也不持有 provider secret。任何真实云端处理开始前，需要先确定数据驻留、声音生物特征授权、审计和级联删除策略。

## Phase 2–4（PLANNED，不要提前开工）

Memories 接真实数据与 Person Model/Coverage 可视化；Twin Client 的 Evidence 展示与 Original/Simulation 区分；Calibration 与 Voice Confirmation UI；Work 3200 capability adapter。细节见 Task Brief 的对应 Phase 段。读到这些内容不等于可以开始实现。
