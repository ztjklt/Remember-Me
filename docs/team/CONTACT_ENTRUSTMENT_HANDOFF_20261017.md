# 安卓亲友托付交接

本次只实现联系方式托付；不修改 Agent、AI Core、火山配置、人物画像或录音豆链路。
独立工作树：`D:/JOB/hack/Remember-Me-entrustment`，分支 `codex/contact-entrustment-20261017`。

## 用户能做什么

“档案 → 亲友 → 留给你 → 新建托付”：填写称呼与邮箱/大陆手机号，专门录音或选最多30段已有完整录音，可以加留言，也可以只留文字。预览全部开放内容、选7/30/90天有效期，确认生成领取链接。专属录音不要求先转写；已有录音须已核对、完成整理且许可有效。

本人可以用系统分享面板发送链接，或明确点击发送邮件/短信通知。接收人用自己的浏览器打开链接，输入预先指定的联系方式并接收验证码，无需注册。领取后只能看到这份托付里的完整原音、已核对文字与补充。无法访问其他录音、画像、Twin或账号功能。

列表分别显示待领取、通知已提交、已验证领取、已打开、失效与撤销；“通知已提交”不冒充送达，“已打开”不冒充听完。撤销阻止后续读取。原有“已有账号的专属信”和亲友补记保留。

## 与 iOS 的关系

已检查 iOS `codex/ios-latest-20261016` 的 `c401834`：其 guest entrustment 使用访客/私密口令、选定录音范围、限时访问与撤销；其文档明确当时没有跨设备电话/邮箱验证码邀请。本实现借用范围隔离思路，新增独立的 contact-entrustment-v1 合同，不覆盖其协议，也不直接合并 iOS 分支。

参考：[iOS guest entrustment 设计](https://github.com/ztjklt/Remember-Me/blob/c401834334705ed02e8a19b3f9f74ce3b08a11bc/docs/architecture/guest-entrustment-contract-2026-10-16.md)。详细接口与边界见 `docs/architecture/contact-entrustment-20261017.md` 和 `packages/contracts/schemas/contact-entrustment-v1.schema.json`。

## 配置后才可投入使用

模板：`services/backend/.env.contact.example`。所有配置使用 `REMEMBER_` 前缀。未配置时接口返回能力关闭，安卓可预览但不生成无法领取的链接；没有生产环境“模拟发信成功”模式。

1. 合入本分支，更新后端依赖（`uv sync --frozen`），按既有流程备份数据库并运行 `uv run alembic upgrade head`。新增0022四张独立表，不迁移或覆盖原信件。若主分支已有别的迁移头，先解决迁移父关系，不能覆盖同事迁移。
2. 设置 `REMEMBER_CONTACT_ENTRUSTMENT_PUBLIC_URL` 为浏览器可正常验证证书的 HTTPS 服务根域名，反向代理放行 `/receive/` 和 `/api/v1/entrustment-receipts/`，保留正常主人身份接口认证。无需开放注册。
3. 生成一次 Fernet 随机密钥，私密保存在服务器的 `REMEMBER_CONTACT_ENTRUSTMENT_KEY` 并备份；不要随进程启动重生成。它保护接收地址与邀请令牌，更换密钥会让旧链接与会话不可用。
4. 至少配置一种发送渠道：邮件使用 SMTP SSL 或 STARTTLS；短信适配阿里云 SendSms，必须自行配好账户、获批签名和验证码模板（参数 `code`）。短信通知另需获批通知模板（参数 `url`）；未配通知模板仍可手动分享链接。发送服务的费用、额度和送达需按实际供应商账号核实，本改动没有开通或购买服务。
5. 反向代理只信任明确的代理 IP，正确传递真实客户端地址；应用不自行信任任意 X-Forwarded-For。否则同一代理后的所有人会共享 IP 限流。不要记录请求正文、Authorization、邮箱、手机号或验证码。
6. 重启服务后读取自己的 contact-entrustments capabilities。用两台设备、两个实际收件地址验证：能收到码、只能打开指定包、播放真实专属录音、错误码拒绝、撤销后拒绝再次取音频。真实发送与真机这一步尚未执行。

短信参考：[阿里云 SendSms](https://help.aliyun.com/zh/sms/developer-reference/api-dysmsapi-2017-05-25-sendsms)、[RPC 签名](https://www.alibabacloud.com/help/en/sms/signature-method)。邮件发送回执和短信 Code=OK 只表示供应商接受请求。失败或超时不自动重发，避免重复通知。

## 已验证和待验证

- 后端新增功能及原亲友回归：51项，包括账号隔离、源变更、许可撤销、到期、OTP错误/重发限流/复用、失败不假成功、幂等、迁移保留旧信；包含发码期间撤销和取音频期间撤销的并发检查。
- 合同：17项。网页异步状态逻辑：4项，使用Node DOM stub，不是浏览器实拍。
- Android JVM单元测试：155项；Debug构建通过。再以私有 Soundcore 1.3.02 AAR 开启硬件模式编译并运行155项测试，也通过。此结果不作为签名发布或实体录音豆验收证据。
- 本次没有部署、发送真实短信/邮件、安装到用户手机或覆盖主线程模拟器。浏览器扩展拒绝附加，未完成浏览器渲染/真机视觉验收，无页面实拍。

测试命令：后端 `python -m pytest tests/test_contact_entrustment.py tests/test_contact_delivery.py tests/test_companion.py tests/test_companion_audio.py`；`node --test tests/receipt-ui.test.cjs`；contracts目录 `npm ci && npm test`；Android `gradle :app:testDebugUnitTest :app:assembleDebug`。

## 合并注意

主体是新文件。少量集成点：CompanionScreen入口/AudioDraft可选原音模式、NativeWorkbenchModel两条请求方法、后端Settings/main/migrations/env和cryptography显式依赖。后端音频对象读取在锁外完成，回传前重验权限，避免阻塞主线程Agent的数据更新。主对话在其当前工作结束后合入本分支，再按现有带Soundcore SDK的签名构建流程出统一APK。

边界：这版是即时、可撤销的选定内容托付，不包括身后触发、法律身份认定、语音片段裁切或访客AI分身。验证码只证明接收渠道控制权。已被对方复制的内容无法远程收回；播放器失效检查间隔30秒，服务端每个新请求即时检查。草稿选择仅驻留当前页面，生成后的托付记录持久化。
