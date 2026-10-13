# Paraformer 服务端 ASR 接入（2026-10-09）

依据本轮用户明确授权，将 ECS 转写从临时客户端接力切回服务端。用户提供的北京百炼工作空间主机使用原生 `/api/v1` 音频协议，不把 `/compatible-mode/v1` 当作 ASR。

- 原有 `/api/v1/episodes`、核对、授权、记忆、人物候选及问答接口保持不变；增加服务端 `paraformer` provider，capabilities 使用已有 cloud 模式。
- Paraformer V2 从百炼私有临时 OSS 读取真实音频，临时副本有效期48小时。上传前用户确认完整原音外发，后台每次网络操作前重新校验权限；不公开 ECS 原音链接。
- 手机仍先落盘录音，上传后 ECS 先持久保存原音再转写。保留原始 ASR，简体核对稿可修改；明确确认后才调用原有微信 Deepseek-v4-flash。补充文字和原音来源不混同。
- 各模型密钥只配置在服务端；请求 API、结果 OSS 请求隔离鉴权，禁止重定向及未知文件主机。临时签名、密钥不进入日志。
- 持久任务编号支持轮询超时后继续查询，不重复提交。若提交响应丢失且无任务编号，报告需核查的失败，不自动重复创建收费任务；不切换供应商。
- 不改变数据库 schema。旧客户端转写上传接口保留供历史草稿使用，新录音由 capabilities 路由到服务端。
- 人物理解仍为有来源的候选，需要本人确认；一个小样不能证明数字分身准确率。实体手机与 iOS 本轮未因此自动视为通过。

验收顺序：ECS 真实音频探针 → 适配器与权限/核对回归 → ECS 部署 → Android 公网直连上传/核对/记忆/来源问答。真实探针与替身回归结果分开记录。

官方协议：[录音文件识别](https://help.aliyun.com/zh/model-studio/paraformer-recorded-speech-recognition-restful-api)、[临时文件上传](https://help.aliyun.com/zh/model-studio/get-temporary-file-url)。
