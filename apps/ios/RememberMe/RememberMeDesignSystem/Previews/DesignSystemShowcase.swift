import SwiftUI

struct DesignSystemShowcase: View {
    @State private var input = ""
    @State private var multiline = ""
    @State private var search = ""
    @State private var selection = "记忆"
    @State private var flowerState = RMFlowerState.idle
    @State private var playing = false
    @State private var position = 0.0
    @State private var toast = false

    var body: some View {
        List {
            Section("勿忘我") {
                HStack {
                    Spacer()
                    VoiceReactiveFlower(state: flowerState)
                        .accessibilityIdentifier("design.flower")
                    Spacer()
                }.padding(.vertical, RMSpacing.lg)
                Picker("花朵状态", selection: $flowerState) {
                    ForEach(RMFlowerState.allCases) { Text($0.label).tag($0) }
                }.accessibilityIdentifier("design.flowerState")
                ForgetMeNotSprig().frame(height: RMMetrics.heroFlower)
            }
            Section("花园插画") {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: RMSpacing.md) {
                    ForEach(GardenArtwork.allCases) { artwork in
                        VStack(spacing: RMSpacing.xs) {
                            GardenArtworkImage(artwork: artwork).frame(height: 112)
                            Text(artwork.title).font(RMTypography.caption)
                        }.frame(maxWidth: .infinity).accessibilityElement(children: .combine)
                    }
                }
            }
            Section("颜色") {
                colorRow("品牌", color: RMColors.brand)
                colorRow("操作", color: RMColors.action)
                colorRow("花心", color: RMColors.flowerCenter)
                colorRow("正文", color: RMColors.text)
                colorRow("辅助文字", color: RMColors.secondaryText)
                Text("勿忘我").font(RMTypography.display)
                Text("记忆标题").font(RMTypography.title)
                Text("本人原话与记忆来源").font(RMTypography.body)
                Text("时间与状态").font(RMTypography.caption)
            }
            Section("按钮") {
                RMButton(title: "开始录音", icon: "mic") { toast.toggle() }
                RMButton(title: "回听", icon: "play", kind: .secondary) { playing.toggle() }
                RMButton(title: "查看原话", kind: .text) { toast.toggle() }
                RMButton(title: "删除", icon: "trash", kind: .destructive) { toast.toggle() }
                RMButton(title: "正在保存", isLoading: true) { }
                RMButton(title: "暂不可用", icon: "mic") { }.disabled(true)
                HStack {
                    RMIconButton(title: "刷新", icon: "arrow.clockwise") { }
                    RMIconButton(title: "正在加载", icon: "arrow.clockwise", isLoading: true) { }
                    RMVoiceInputButton(recording: false) { }
                    RMFloatingActionButton(title: "新录音", icon: "mic") { }
                }
            }
            Section("卡片") {
                RMMemoryCard(title: "父亲送我去车站", date: "2026 年 10 月 12 日")
                RMAudioMemoryCard(title: "一段讲述", duration: "03:24", date: "2026 年 10 月 12 日")
                RMPersonCard(name: "父亲", relationship: "本人原文中的关系")
                RMTimelineCard(date: "2026 年 10 月 12 日") {
                    RMContentCard(title: "那天的一个片段", kind: .text)
                }
                RMRecordingCard(title: "一段本机录音", status: "待核对文字")
                RMContentCard(title: "图片条目", kind: .image, showsChevron: false)
            }
            Section("输入与导航") {
                RMNavigationHeader(title: "我的记忆")
                RMTextField(title: "标题", text: $input)
                RMMultilineInput(title: "核对文字", text: $multiline, minimumHeight: RMMetrics.sampleEditorHeight)
                RMSearchBar(text: $search)
                RMSegmentedControl(title: "内容", selection: $selection) {
                    Text("记忆").tag("记忆")
                    Text("原音").tag("原音")
                }
                RMMessageComposer {
                    HStack {
                        RMIconButton(title: "更多", icon: "plus") { }
                        TextField("输入消息", text: $input).rmInputSurface()
                        RMIconButton(title: "发送", icon: "arrow.up") { }
                    }
                }
                Text("我记得那天。").rmMessageBubble(outgoing: true)
                Text("根据记忆推测的回应。").rmMessageBubble()
                HStack {
                    RMCallControl(title: "静音", icon: "mic.slash") { }
                    RMCallControl(title: "打断", icon: "hand.raised") { }
                    RMCallControl(title: "结束", icon: "phone.down", destructive: true) { }
                }
            }
            Section("原音与反馈") {
                RMAudioPlayer(playing: playing, position: position, duration: 204, showsProgress: true,
                              play: { playing.toggle() }, seek: { position = $0 })
                RMRecordingWaveform(levels: [0.1, 0.15, 0.3, 0.55, 0.2, 0.1])
                RMFeedback(title: "正在读取", kind: .loading)
                RMFeedback(title: "还没有记忆", kind: .empty)
                RMFeedback(title: "连接未完成", message: "稍后重试。", kind: .error)
                RMFeedback(title: "已保存", kind: .success)
                RMProgressIndicator(title: "正在上传", value: 0.6)
                RMToast(message: "已保存")
                RMFlowerSaveFeedback(active: toast)
            }
        }
        .scrollContentBackground(.hidden).background(RMColors.background)
        .foregroundStyle(RMColors.text).tint(RMColors.action)
        .navigationTitle("RM 组件").navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("design.showcase")
    }
    private func colorRow(_ name: String, color: Color) -> some View {
        HStack {
            RoundedRectangle(cornerRadius: RMRadius.card).fill(color)
                .frame(width: RMMetrics.inlineFlower, height: RMMetrics.inlineFlower)
            Text(name).font(RMTypography.detail)
        }
    }
}

#Preview("Light") { NavigationStack { DesignSystemShowcase() }.preferredColorScheme(.light) }
#Preview("Dark") { NavigationStack { DesignSystemShowcase() }.preferredColorScheme(.dark) }
#Preview("Large Type") { NavigationStack { DesignSystemShowcase() }.environment(\.dynamicTypeSize, .accessibility3) }
#Preview("Motion Disabled") { NavigationStack { DesignSystemShowcase() }.environment(\.rmAnimationsDisabled, true) }
#Preview("Native Tabs") {
    RMTabBar(selection: .constant(0)) {
        NavigationStack { DesignSystemShowcase() }.tabItem { Label("组件", systemImage: "square.grid.2x2") }.tag(0)
        NavigationStack { Text("记忆").font(RMTypography.title) }.tabItem { Label("记忆", systemImage: "book.closed") }.tag(1)
    }
}

#if DEBUG
/// Offline AVAudioPlayer preview: the flower uses the same measured input as the app.
struct TwinAudioMotionPreview: View {
    @EnvironmentObject private var model: AppModel
    @State private var gold = false

    private var fixture: LocalRecording? {
        model.visibleLocalRecordings.first { $0.id == "00000000-0000-0000-0000-000000000010" }
    }
    private var stateLabel: String {
        model.isPlaying ? "播放中" : model.playbackID == fixture?.id && fixture != nil ? "已暂停" : "未播放"
    }
    private var levelLabel: String {
        model.playbackAudioLevel.map { String(format: "%.3f", $0) } ?? "无音频"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                VStack(spacing: 8) {
                    Text("让声音泛起涟漪")
                        .font(.title2.weight(.medium))
                    Text("合成测试音频 · 实际音量驱动")
                        .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                }
                TwinPresence(state: model.isPlaying ? .speaking : .idle,
                             size: 220, original: gold, audioLevel: model.playbackAudioLevel)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 24)
                VStack(spacing: 8) {
                    Text(stateLabel)
                        .font(.headline)
                        .accessibilityIdentifier("audioMotion.state")
                    Text("实测音量  \(levelLabel)")
                        .monospacedDigit().font(.footnote)
                        .foregroundStyle(RMTwinColors.secondaryText)
                        .accessibilityLabel("实测音量")
                        .accessibilityValue(levelLabel)
                        .accessibilityIdentifier("audioMotion.level")
                    Text("音量增强时光芒扩张，静音时自然收回。")
                        .font(.footnote).foregroundStyle(RMTwinColors.secondaryText)
                        .multilineTextAlignment(.center)
                }
                HStack(spacing: 16) {
                    Button {
                        if let fixture { model.playLocalRecording(fixture.id) }
                    } label: {
                        Label(model.isPlaying ? "暂停" : "播放测试音频", systemImage: model.isPlaying ? "pause.fill" : "play.fill")
                            .frame(maxWidth: .infinity).padding(.vertical, 12)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(RMTwinColors.accent).foregroundStyle(RMTwinColors.background)
                    .disabled(fixture == nil)
                    .accessibilityIdentifier("audioMotion.play")
                    Button {
                        model.stopPlayback()
                    } label: {
                        Label("停止", systemImage: "stop.fill").padding(.vertical, 12)
                    }
                    .buttonStyle(.bordered).tint(RMTwinColors.accent)
                    .accessibilityIdentifier("audioMotion.stop")
                }
                Toggle("金色原声样式", isOn: $gold)
                    .tint(RMTwinColors.gold)
                    .accessibilityIdentifier("audioMotion.gold")
                Text("仅演示视觉样式。此音频是本机生成的音调与静音，不是任何人的原音或声音样本。")
                    .font(.footnote).foregroundStyle(RMTwinColors.secondaryText)
                    .multilineTextAlignment(.center)
            }
            .padding(24)
        }
        .foregroundStyle(RMTwinColors.text)
        .background { TwinAtmosphere() }
        .navigationTitle("音频动效预览")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .task {
            if ProcessInfo.processInfo.arguments.contains("--uitest-audio-autoplay"), let fixture {
                model.playLocalRecording(fixture.id)
            }
        }
        .onDisappear { model.stopPlayback() }
    }
}
#endif
