# 花田与人物阅读调整（0.9.1）

本轮以 Android 原生界面为实现对象；共享接口、数据库和服务端发布目录不变。不是另一张静态网页样板。

## 空间、身份与两个账号

账号和人物空间不是一一对应。一个账号可以管理自己的空间，同时作为亲友阅读另一个人的空间。

2026-10-11 重新读取 ECS：陈守义记录者有 10 段录音、10 个已核对故事；亲友有 8 段获授权录音、8 个已核对故事。亲友账号还拥有一个空白的个人空间。旧客户端登录直接选第一个空间，容易进入这个空白空间。

- 多空间首次登录必须选择；之后按服务地址和账号记住所选空间。保存的 ID 必须仍在服务端返回的可见空间列表中才可恢复。
- 右上角收纳人物名称与当前角色。展开后显示完整空间名称，以及“我的空间／亲友空间”。角色依据服务端返回值，不凭账号名推断。
- 亲友首页的“进入花田”明确切到花田，不继承上次的人物标签页。
- 两端都能访问花田，但亲友只能看到获授权的内容。不能以视觉一致为由扩大授权。

## 浏览方式

- 人物页的“了解这个人／记忆侧面”和四个视角留在内容区上方。
- 每次阅读一张故事卡；左右滑动换故事，卡片内部上下滚动。提供上一段、下一段和页码，不自动轮播。
- 八侧面统一为暖白、苔绿材质，保留真实内容预览。
- 整理、候选核对和寄语入口收进工具面板；来源、历史与编辑功能保留。
- 花朵仍可点开、花瓣仍可点读。移除双指缩放、拖拽放大和缩放操作条，避免与阅读滚动争抢手势。
- 藤蔓属于花径装饰，不表示两段故事已经被模型认定存在因果或人物关系。
- 200% 字号采用可横向滚动的视角栏和独立阅读区，不缩小系统字号。

参考：[Android Compose Pager](https://developer.android.com/develop/ui/compose/layouts/pager) 的分页与独立页状态；[Material 3 Carousel 设计说明](https://m3.material.io/blog/material-3-carousel-research-design) 的可预期横向浏览。本实现没有引入额外轮播库。

## 素材来源

新增 `apps/android/app/src/main/res/drawable-nodpi/rm_garden_vine.png`，1024×1536，透明 PNG。使用内置 imagegen 生成，复制入仓库；不是来源照片或用户历史材料。原有三种花形与枝叶保留。

最终提示词：

> Create a production-ready transparent botanical UI asset for a poetic realistic forget-me-not memory garden mobile app. Portrait 2:3 composition. A single delicate S-curving trailing vine, viewed straight-on, beginning at 28% horizontal / 5% vertical, curving gracefully across to 76% horizontal at midpoint, ending at 28% horizontal / 95% vertical. Continuous slim stem, about 12 small natural oval-lanceolate sage and moss green leaves, exceptionally detailed realistic venation, softly rim-lit warm afternoon light, restrained muted greens matching living garden stems. Elegant asymmetric spacing, a few small fine tendrils, a little dimensionality with natural leaf turns. Fine botanical photograph-like realism, not a vector illustration. No flowers, no colored petals, no text, no borders, no earth, no background, no background haze, no cast shadow onto a background. True transparent background with clean alpha; empty air around vine. The entire vine and all leaves fully inside frame with comfortable margin. Designed as a graceful linkage behind existing large blue flowers, slim rather than bushy; leaf width under 10% of canvas.

iOS 本轮只有页面语义对照：顶部空间切换、固定视角、横向故事阅读、无缩放花朵。尚未移植编译，不能宣称双端视觉已经同步。
