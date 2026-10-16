# 设备图示来源

## 2026-10-16 当前素材：黑色设备直接放在统一白色区域

本人进一步要求顶部蓝牙设备区域使用一个白色大容器，直接展示黑色录音豆和耳机，不再给每张图单独加小框。本轮重新启用 2026-10-15 的原始炭黑耳机透明 PNG，没有重新生成或做图像加工。已从本机保留的原始输出 `/Users/jitian/.codex/generated_images/01a13b59-5c5f-79f3-871e-6a1ff3a5aadf/exec-9a0111e0-ce6f-4d4a-8865-710025dfddeb.png` 原样复制至 `apps/ios/RememberMe/Assets.xcassets/DeviceEarbuds.imageset/device.png`。图像本身没有边框，透明背景由统一白色容器承接；完整生成提示见下方原始黑色素材记录。

已目视核对耳机及充电盒为炭黑色，PNG 为 1254 × 1254、RGBA，alpha 范围为 0–255，SHA-256 为 `1363a8248d8042a573fd1996369dc2416a5452f3634f8cc1f95488a16f18c780`。Anker soundcore Work 录音豆仍保留用户原照片，SHA-256 保持 `cbe16553d178e669c91de53cfefcb3088e05ab5452b41648cbb74cda28a89d10`。本轮仅恢复耳机素材与更新本记录，容器布局由界面修改实现；本记录不代表蓝牙真机验证。

## 2026-10-16 较早白色版本（已替换）

录音豆图示：保留用户于 2026-10-15 提供的 Anker soundcore Work 产品照片，未重新生成或改动原图，路径为 `apps/ios/RememberMe/Assets.xcassets/DeviceRecordingBean.imageset/device.jpg`。本轮对照 [soundcore 官方 D3200 产品页](https://www.soundcore.com/products/d3200-soundcore-work-ai-voice-recorder)核对了产品名称及外观；官网仅用于核对，没有重新下载替换照片。

耳机图示：根据本人 2026-10-16 的白色版本要求，使用内置 `image_gen.imagegen` 重新生成珍珠白耳机及充电盒，替换 `apps/ios/RememberMe/Assets.xcassets/DeviceEarbuds.imageset/device.png`。无品牌，仅为耳机类别插图，不表示特定耳机型号已获支持。最终使用白色背景，与录音豆产品照一致；透明背景候选边缘不够干净，未用于 App。

最终生成提示（内置工具，`transparent_background: false`）：

> Use case: product-mockup. Generate a square studio product photograph for an elegant iOS Bluetooth connection card. One pair of pearl-WHITE wireless in-ear earbuds with short rounded stems and WHITE silicone tips, standing in front of a closed pearl-WHITE smooth low oval charging case. Three-quarter front view, balanced arrangement, earbuds slightly separated. Soft satin white polymer surfaces, realistic neutral-grey seams and shadows that give clear dimensional shape. Strong clean silhouette, no noise, no dust, polished industrial design. Seamless pure WHITE background (#FFFFFF), bright neutral studio lighting, very subtle soft contact shadow. All three objects completely within frame with generous clear margins, fill about 74 percent image width. No brand, no logo, no text, no watermark, no interface, no people, no extra objects, no cables. Generic wireless earbuds category illustration, not an existing branded model.

已检查最终图像的白色外观、完整构图及边缘；Pillow 可读取并验证 PNG，尺寸 1254 × 1254，RGB。两个 imageset 的 `Contents.json` 均能解析且引用文件存在。录音豆原图 SHA-256 为 `cbe16553d178e669c91de53cfefcb3088e05ab5452b41648cbb74cda28a89d10`，本轮保持不变。耳机图像 SHA-256 为 `c9a98c381fd688cf373cff01a722aeea8042b4b9ccb6c28134bdcd79e0e0f45f`。本记录只涉及图示，不代表真机蓝牙连接验证。

## 2026-10-15 原始黑色素材（本轮重新使用）

原始耳机图示为内置 `image_gen.imagegen` 生成的炭黑透明背景版本。白色版本一度替换了它，本轮按本人新要求重新启用原图。原始完整提示如下：

> Use case: product-mockup. Create a polished photorealistic product illustration for an iOS personal recording app's small device connection card. Subject: one pair of compact matte charcoal black wireless in-ear earbuds with short stems, sitting naturally beside a closed low oval charcoal charging case. Three-quarter front product view, soft neutral studio light, subtle realistic contact shadow, precise clean silhouette, generous clear margins, centered composition. Restrained industrial design, tactile satin surfaces, no brand, no text, no symbols, no interface, no cables, no people, no extra objects. Transparent background with genuine alpha. Square composition, readable when displayed at 120 points wide. This is an illustrative device image, not a claim of a specific supported earbud model.
