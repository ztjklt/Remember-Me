import SwiftUI

struct TwinVoiceCallView: View {
    @EnvironmentObject private var model: AppModel
    @Environment(\.rmAnimationsDisabled) private var animationsDisabled
    @ObservedObject var call: TwinVoiceCallModel
    @State private var ownVoice = false
    @State private var isSaving = false
    @State private var showRevoke = false
    @State private var showRetryVoice = false
    @State private var showCloudConsent = false
    @State private var showEnrollment = false
    @State private var showConversationDetails = false
    @State private var editSampleText = false
    private var guide: String { AppModel.voiceReadingPrompt }
    private struct ProfilePollingKey: Equatable {
        let profileID: String?
        let status: String?
        let naturalPreparation: Bool
        let active: Bool
    }
    private var profilePollingKey: ProfilePollingKey {
        ProfilePollingKey(profileID: call.profile?.profile_id, status: call.profile?.status,
                          naturalPreparation: call.capabilities?.natural_voice_preparation == true,
                          active: call.isActive)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: RMSpacing.lg) {
                callHero
                if let notice = call.notice {
                    Label(notice, systemImage: "info.circle").font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                }
                if let error = model.errorMessage {
                    Label(error, systemImage: "exclamationmark.circle").font(.subheadline).foregroundStyle(.red)
                }
                if call.isActive {
                    HStack {
                        Label(call.audioRoute, systemImage: call.audioRouteSymbol).font(RMTypography.caption)
                            .accessibilityIdentifier("voiceCall.audioRoute")
                        Spacer()
                        Menu {
                            Button("手机扬声器", systemImage: "speaker.wave.2.fill") {
                                Task { await call.selectSpeaker(true) }
                            }.accessibilityIdentifier("voiceCall.speaker")
                            Button("听筒／已连接耳机", systemImage: "iphone") {
                                Task { await call.selectSpeaker(false) }
                            }.accessibilityIdentifier("voiceCall.systemOutput")
                        } label: {
                            Label("切换输出", systemImage: "speaker.wave.2")
                                .font(RMTypography.caption).frame(minHeight: RMMetrics.touchTarget)
                        }.disabled(!call.canSelectAudioOutput)
                            .accessibilityIdentifier("voiceCall.outputPicker")
                    }
                    Text("可直接用手机扬声器和麦克风通话，无需连接蓝牙。锁屏或切到后台时会结束。")
                        .font(RMTypography.caption).foregroundStyle(RMTwinColors.secondaryText)
                } else if let caps = call.capabilities, caps.available {
                    Label("默认使用手机扬声器，无需连接蓝牙", systemImage: "speaker.wave.2.fill")
                        .font(RMTypography.caption).foregroundStyle(RMTwinColors.secondaryText)
                    voiceSelector
                    Text(call.capabilities?.dialogue_capture_available == true
                         ? "点击开始即确认本次录音、云端对话和声音识别；匹配本人的原话会自动整理为记忆。"
                         : "点击开始即确认本次云端语音对话与声音识别。")
                        .font(RMTypography.caption).foregroundStyle(RMTwinColors.secondaryText).accessibilityIdentifier("voiceCall.startNotice")
                    DisclosureGroup("通话用途") { Text(caps.notice).font(RMTypography.caption) }
                    if caps.voiceprint_available == true {
                        VStack(alignment:.leading,spacing:10) {
                            Text(caps.owner_voice_registered == true ? "声纹识别 · 已记住本人声音" : "声纹识别 · 在聊天里记住我的声音").font(.headline)
                            Text(caps.owner_voice_registered == true ? "多人可以轮流说话；只有匹配本人的发言会更新本人记忆。" : "开始后，用自己的声音介绍一下自己，例如：你好，我叫小王，这是我自己的声音。之后照常聊天即可。").font(.footnote).foregroundStyle(RMTwinColors.secondaryText)
                        }.voiceCard()
                    }
                    if caps.personal_voice_available != false { voiceProgress }
                    if caps.personal_voice_available == false {
                        Text("当前使用默认声音。原本人音色已保留，待新线路支持后可继续使用。")
                            .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                    } else if call.profile?.ready == true {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("听听像不像你").font(.headline)
                            Text("音色复刻已完成。试听一段合成声音，由你判断是否像自己。")
                                .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                            Button(model.playbackLoading ? "正在生成音色试听…" : model.playbackID == "realtime-voice-preview" && model.isPlaying ? "停止音色试听" : "试听复刻后的音色", systemImage: "speaker.wave.2") {
                                if model.playbackID == "realtime-voice-preview", model.isPlaying { model.stopPlayback() }
                                else { Task { await model.previewRealtimeVoice() } }
                            }.buttonStyle(.bordered).disabled(model.playbackLoading || model.isBusy)
                                .accessibilityIdentifier("voiceCall.preview")
                            if model.personalVoiceAccepted {
                                Label("已确认使用这个音色", systemImage: "checkmark.circle.fill").foregroundStyle(RMColors.success)
                                    .accessibilityIdentifier("voiceCall.voiceAccepted")
                            } else {
                                Text(model.realtimeVoiceReview?.status == "rejected" ? "已记录音色不像你。可以重新录制，也可以再次试听后确认。" : "试听后确认是否像你；确认前继续使用默认声音。")
                                    .font(.footnote).foregroundStyle(RMTwinColors.secondaryText)
                                Button("像我，确认使用") {
                                    Task {
                                        await model.reviewRealtimeVoice(accepted: true)
                                        if model.personalVoiceAccepted { model.useDefaultRealtimeVoice = false }
                                    }
                                }
                                    .buttonStyle(.borderedProminent)
                                    .disabled(model.realtimeVoiceReview?.profile_id != call.profile?.profile_id || model.realtimeVoiceReview?.previewed_at == nil || model.isBusy)
                                    .accessibilityIdentifier("voiceCall.acceptVoice")
                                Button("不像我") { Task { await model.reviewRealtimeVoice(accepted: false) } }
                                    .buttonStyle(.bordered).disabled(model.isBusy)
                                    .accessibilityIdentifier("voiceCall.rejectVoice")
                            }
                            Button("重新录制本人音色", systemImage: "arrow.clockwise") { showRetryVoice = true }
                                .disabled(model.isBusy).accessibilityIdentifier("voiceCall.retryVoice")
                        }.voiceCard()
                    } else if ["enrolling", "enrollment_unknown"].contains(call.profile?.status ?? "") {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(call.profile?.status == "enrollment_unknown" ? "上次提交结果尚未确认，请检查音色状态。" : "正在准备你的本人音色。就绪后可以切换，现在也可先用默认声音通话。")
                                .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                            Button("检查音色是否就绪") { Task { await call.refreshProfile() } }
                                .buttonStyle(.bordered).accessibilityIdentifier("voiceCall.checkProfile")
                        }.voiceCard()
                    } else if call.profile?.profile_id != nil {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("本次声音准备未完成，可以重新录制。默认声音仍可使用。")
                                .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                            Button("重新录制本人音色") { showRetryVoice = true }
                                .disabled(model.isBusy).accessibilityIdentifier("voiceCall.retryVoice")
                        }.voiceCard()
                    } else {
                        VStack(alignment: .leading, spacing: 0) {
                            Button { showEnrollment.toggle() } label: {
                                HStack(alignment: .top, spacing: 12) {
                                    Label(model.voiceSampleURL == nil ? "声音复刻 · 录制本人声音" : "声音复刻 · 继续提交样本", systemImage: "mic.badge.plus")
                                        .font(.headline).multilineTextAlignment(.leading)
                                    Spacer(minLength: 8)
                                    Image(systemName: showEnrollment ? "chevron.up" : "chevron.down").font(.caption.weight(.semibold)).padding(.top, 5)
                                }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                            }.buttonStyle(.plain).accessibilityIdentifier("voiceCall.enrollmentDetails")
                                .accessibilityValue(showEnrollment ? "已展开" : "已收起")
                            if showEnrollment { enrollment(policy: caps.policy).padding(.top, 14) }
                        }.voiceCard()
                    }
                    if call.profile?.voice_consent_id != nil || model.voiceConsentID != nil {
                        Button("撤销声音授权并删除样本", role: .destructive) { showRevoke = true }
                            .frame(minHeight: 44).disabled(isSaving)
                    }
                }
                if call.isPreparing { ProgressView("正在检查语音服务…") }
                if !call.isActive {
                    Button("刷新语音服务", systemImage: "arrow.clockwise") { Task { await model.prepareRealtimeVoice() } }
                        .frame(minHeight: 44).disabled(call.isPreparing).accessibilityIdentifier("voiceCall.refresh")
                }
            }.padding(RMSpacing.page).frame(maxWidth: RMMetrics.maximumReadingWidth).frame(maxWidth: .infinity).foregroundStyle(RMTwinColors.text)
        }
        .rmDismissibleKeyboard()
        .background { TwinAtmosphere() }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if call.isActive { controls().padding(RMSpacing.md).background(callBarBackground) }
            else if call.capabilities?.available == true { callLaunch.padding(RMSpacing.md).background(callBarBackground) }
        }
        .navigationTitle("语音通话").navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.hidden, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .tint(RMTwinColors.accent)
        .environment(\.colorScheme, .dark)
        .toolbar {
            if call.isActive {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showConversationDetails = true } label: {
                        Image(systemName: "text.bubble").font(.system(size: 19))
                            .foregroundStyle(RMTwinColors.text)
                            .frame(width: RMMetrics.touchTarget, height: RMMetrics.touchTarget)
                    }.buttonStyle(RMQuietPressStyle())
                        .accessibilityLabel("查看本轮对话")
                        .accessibilityIdentifier("voiceCall.conversationDetails")
                }
            }
        }
        .interactiveDismissDisabled(call.isActive || model.isVoiceRecording || isSaving)
        .sheet(isPresented: $showConversationDetails) {
            NavigationStack {
                ScrollView { activeConversation.padding(RMSpacing.page) }
                    .foregroundStyle(RMTwinColors.text)
                    .background { TwinAtmosphere() }.navigationTitle("本轮对话").navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("关闭") { showConversationDetails = false } } }
                    .safeAreaInset(edge: .bottom) {
                        if call.isActive { controls(prefix: "voiceCall.details").padding(RMSpacing.md).background(callBarBackground) }
                    }
            }.tint(RMTwinColors.accent)
                .toolbarBackground(.hidden, for: .navigationBar)
                .toolbarColorScheme(.dark, for: .navigationBar)
                .environment(\.colorScheme, .dark)
                .presentationDetents([.large])
        }
        .task {
            showEnrollment = model.voiceSampleURL != nil
            await model.prepareRealtimeVoice()
        }
        .task(id: call.profile?.profile_id) {
            await model.refreshRealtimeVoiceReview()
        }
        .alert("使用云端孪生回答通话问题？", isPresented: $showCloudConsent) {
            Button("同意云端问答") { Task { await model.enableCloudTwin() } }
            Button("取消", role: .cancel) { }
        } message: {
            Text("问题、相关旧聊天、会话摘要和相关记忆文字会发送给现有云端模型。你可以查看和清除聊天记忆，也可以在「我的」撤销问答授权。通话原音不会自动保存为记忆。")
        }
        .alert("撤销个人声音授权？", isPresented: $showRevoke) {
            Button("撤销并删除", role: .destructive) {
                Task { await model.revokeRealtimeVoice() }
            }
            Button("取消", role: .cancel) { }
        } message: { Text("已生成的本人音色将停用，样本删除；服务端也会请求百炼删除音色。") }
        .alert("重新录制本人音色？", isPresented: $showRetryVoice) {
            Button("删除旧音色并重录", role: .destructive) {
                Task {
                    await model.retryRealtimeVoice()
                    if call.profile?.profile_id == nil { showEnrollment = true }
                }
            }
            Button("取消", role: .cancel) { }
        } message: { Text("旧音色与复刻样本会删除，原有录音和记忆保留。你可以重新录制样本，也可以继续用默认声音聊天取样。") }
        .task(id: profilePollingKey) {
            guard !call.isActive else { return }
            for _ in 0..<20 {
                guard !Task.isCancelled, !call.isActive, call.profile?.ready != true else { return }
                let pending = ["enrolling", "enrollment_unknown"].contains(call.profile?.status ?? "")
                guard pending || (call.capabilities?.natural_voice_preparation == true && call.profile?.profile_id == nil) else { return }
                await call.refreshProfile()
                do { try await Task.sleep(for: .seconds(pending ? 3 : 6)) } catch { return }
            }
        }
        .onDisappear { if !call.isActive { model.cancelNaturalCallStart() } }
        .onChange(of: model.voiceSampleURL) { _, _ in ownVoice = false; editSampleText = false }
        .onChange(of: model.voiceSampleTranscript) { _, _ in ownVoice = false }

        .onChange(of: call.isActive) { _, active in if !active { showConversationDetails = false } }
    }
    private var selectedDefault: Bool { model.useDefaultRealtimeVoice && call.capabilities?.default_voice_available == true }
    private var voiceSelector: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(selectedDefault ? "当前通话声音：默认声音" : "当前通话声音：本人音色", systemImage: "speaker.wave.2.fill")
                .font(.headline).foregroundStyle(RMTwinColors.accent).accessibilityIdentifier("voiceCall.selectedVoice")
            if call.capabilities?.default_voice_available == true, model.personalVoiceAccepted {
                RMSegmentedControl(title: "通话声音", selection: Binding(get: { selectedDefault }, set: { model.useDefaultRealtimeVoice = $0 })) {
                    Text("默认声音").tag(true)
                    Text("本人音色").tag(false)
                }.accessibilityIdentifier("voiceCall.voiceChoice")
            }
            if selectedDefault {
                Text(model.personalVoiceAccepted ? "本次将使用默认声音，可切换到已确认的本人音色。" : "本人音色需试听并确认后，才能用于通话。")
                    .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
            }
        }.voiceCard()
    }
    private var callLaunch: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let reason = startBlockedReason {
                Label(reason, systemImage: "info.circle").font(.caption).foregroundStyle(RMTwinColors.secondaryText)
                    .fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("voiceCall.blockedReason")
            }
            Button {
                model.stopPlayback()
                Task { await model.startNaturalVoiceCall(useDefault: selectedDefault) }
            } label: {
                Label(selectedDefault ? "用默认声音通话" : "用本人音色通话", systemImage: "phone.fill")
                    .font(.headline).foregroundStyle(RMTwinColors.text)
                    .frame(maxWidth: .infinity, minHeight: RMMetrics.buttonHeight)
                    .background(RMTwinColors.accent.opacity(0.26), in: RoundedRectangle(cornerRadius: 18))
                    .overlay { RoundedRectangle(cornerRadius: 18).strokeBorder(RMTwinColors.accent.opacity(0.5), lineWidth: 1) }
            }.buttonStyle(RMQuietPressStyle()).disabled(startBlockedReason != nil || call.isPreparing)
                .accessibilityLabel(selectedDefault ? "用默认声音通话" : "用本人音色通话").accessibilityIdentifier("voiceCall.start")
        }
    }
    private var startBlockedReason: String? {
        if !selectedDefault, call.profile?.ready != true {
            return ["enrolling", "enrollment_unknown"].contains(call.profile?.status ?? "")
                ? "音色准备中" : "请先设置本人音色"
        }
        if !selectedDefault, !model.personalVoiceAccepted { return "请先试听，并确认使用这个本人音色" }
        if !selectedDefault, call.profile?.voice_consent_id == nil { return "请刷新声音授权" }
        if model.isSpeakerRecording || model.isRecording || model.isVoiceRecording || model.isQueryRecording { return "请先结束录音" }
        if model.isBusy || isSaving { return "正在处理，请稍候" }
        return nil
    }
    private var voiceProgress: some View {
        let ready = call.profile?.ready == true
        let processing = ["enrolling", "enrollment_unknown"].contains(call.profile?.status ?? "")
        let submitted = call.profile?.profile_id != nil
        let recorded = model.voiceSampleURL != nil || submitted
        return VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: ready ? "checkmark.seal.fill" : processing ? "hourglass" : "mic.circle.fill")
                    .font(.title2).foregroundStyle(ready ? RMColors.success : RMTwinColors.accent)
                VStack(alignment: .leading, spacing: 5) {
                    Text(ready ? (model.personalVoiceAccepted ? "本人音色已确认" : "本人音色待试听确认") : processing ? "正在复刻你的音色" : submitted ? "音色复刻未完成" : recorded ? "等待提交声音样本" : "尚未设置本人音色")
                        .font(.headline).accessibilityIdentifier("voiceCall.profileStatus")
                    Text(ready ? (model.personalVoiceAccepted ? (selectedDefault ? "已确认；本次仍选择了默认声音" : "本次将使用你已确认的本人音色") : "复刻完成，试听并确认后用于通话") : processing ? "页面会自动检查，无需重复提交" : recorded ? "声音已保存在手机，确认后才能复刻" : "先正常聊天，清晰的声音片段会用于准备本人音色")
                        .font(.caption).foregroundStyle(RMTwinColors.secondaryText)
                }
                if processing { ProgressView() }
            }
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 14) {
                    compactStep("1", title: call.capabilities?.natural_voice_preparation == true ? "聊天取样" : "录制样本", complete: recorded)
                    compactStep("2", title: call.capabilities?.natural_voice_preparation == true ? "自动准备" : "提交复刻", complete: submitted)
                    compactStep("3", title: "音色就绪", complete: ready)
                }
                VStack(alignment: .leading, spacing: 10) {
                    progressStep("1", title: call.capabilities?.natural_voice_preparation == true ? "聊天取样" : "录制样本", detail: call.capabilities?.natural_voice_preparation == true ? "短句也会自动累积" : "5–15 秒本人声音", complete: recorded)
                    progressStep("2", title: call.capabilities?.natural_voice_preparation == true ? "自动准备" : "提交复刻", detail: call.capabilities?.natural_voice_preparation == true ? "清晰单人片段后台处理" : "核对文字并确认本人声音", complete: submitted)
                    progressStep("3", title: "音色就绪", detail: "完成后可试听", complete: ready)
                }
            }
        }.voiceCard()
    }
    private func compactStep(_ number: String, title: String, complete: Bool) -> some View {
        Label {
            Text(title).font(.caption.weight(.medium))
        } icon: {
            if complete { Image(systemName: "checkmark.circle.fill").foregroundStyle(RMColors.success) }
            else { Text(number).font(.caption.monospacedDigit()).foregroundStyle(RMTwinColors.secondaryText) }
        }.fixedSize(horizontal: true, vertical: false)
    }
    private func progressStep(_ number: String, title: String, detail: String, complete: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                Circle().fill(complete ? RMColors.success.opacity(0.15) : RMTwinColors.raisedSurface).frame(width: 30, height: 30)
                if complete { Image(systemName: "checkmark").foregroundStyle(RMColors.success) }
                else { Text(number).font(.caption.weight(.semibold)).foregroundStyle(RMTwinColors.secondaryText) }
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(RMTwinColors.secondaryText)
            }
        }
    }
    private func controls(prefix: String = "voiceCall") -> some View {
        HStack(alignment: .top, spacing: RMSpacing.md) {
            TwinCallControl(title: call.muted ? "取消静音" : "静音", icon: call.muted ? "mic.slash.fill" : "mic.fill", selected: call.muted) {
                Task { await call.toggleMute() }
            }.disabled(call.isChangingMute || ![.awaitingSpeech, .listening, .thinking, .speaking].contains(call.state))
                .accessibilityIdentifier("\(prefix).mute")
            TwinCallControl(title: "打断", icon: "hand.raised.fill") { Task { await call.interrupt() } }
                .disabled(![.thinking, .speaking].contains(call.state)).accessibilityIdentifier("\(prefix).interrupt")
            TwinCallControl(title: "结束", icon: "phone.down.fill", destructive: true) { Task { await call.end() } }
                .accessibilityIdentifier("\(prefix).end")
        }.disabled(call.state == .ending)
    }
    private var callHero: some View {
        VStack(spacing: RMSpacing.lg) {
            Text("REMEMBER ME")
                .font(.system(size: 10, weight: .medium)).tracking(4)
                .foregroundStyle(RMTwinColors.secondaryText)
                .accessibilityHidden(true)
            TwinPresence(state: flowerState, size: call.isActive ? 176 : 132, audioLevel: presenceAudioLevel)
                .environment(\.rmAnimationsDisabled, animationsDisabled || showConversationDetails)
                .padding(.vertical, call.isActive ? RMSpacing.lg : RMSpacing.sm)
            VStack(spacing: 10) {
                Text(presenceName)
                    .font(.system(.largeTitle, design: .serif).weight(.light))
                    .foregroundStyle(RMTwinColors.text)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Text(displayStatus).font(RMTypography.detail).foregroundStyle(RMTwinColors.accent)
                    .multilineTextAlignment(.center).accessibilityIdentifier("voiceCall.state")
                    .accessibilityValue(call.statusText)
            }
            if call.isActive {
                if let mode = call.activeVoiceMode {
                    Label(mode == "personal" ? "本次通话：本人音色" : "本次通话：默认声音", systemImage: "speaker.wave.2.fill")
                        .font(RMTypography.caption).foregroundStyle(RMTwinColors.secondaryText)
                        .accessibilityIdentifier("voiceCall.activeVoice")
                }
                speakerIdentity
            }
        }.frame(maxWidth: .infinity).padding(.vertical, call.isActive ? RMSpacing.xl : RMSpacing.md)
    }
    private var presenceName: String {
        let name = model.pairing?.spaceName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return name.isEmpty ? "另一个我" : name
    }
    private var callBarBackground: some View {
        RMTwinColors.background
            .overlay(alignment: .top) { Rectangle().fill(RMTwinColors.divider).frame(height: 1) }
            .ignoresSafeArea(edges: .bottom)
    }
    private var speakerIdentity: some View {
        let names = call.identifiedSpeakerNames
        return Label(names.isEmpty ? "暂未确认说话人" : "声纹匹配：" + names.joined(separator: "、"),
                     systemImage: names.isEmpty ? "person.crop.circle.dashed" : "person.crop.circle.badge.checkmark")
            .font(RMTypography.body.weight(.semibold))
            .foregroundStyle(names.isEmpty ? RMTwinColors.secondaryText : RMColors.success)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("voiceCall.speakerIdentity")
    }
    private var displayStatus: String {
        switch call.state {
        case .idle: "准备语音通话"
        case .connecting: "正在连接"
        case .awaitingSpeech: "已接通，请开始说话"
        case .listening: call.muted ? "已静音" : "正在倾听"
        case .thinking: "正在思考"
        case .speaking: "正在回应"
        case .reconnecting: "正在重新连接"
        case .ending: "正在结束"
        case .failed: "通话未能继续"
        }
    }
    private var flowerState: RMFlowerState {
        if !call.isActive, model.playbackID == "realtime-voice-preview", model.isPlaying { return .speaking }
        return switch call.state {
        case .idle: .idle
        case .connecting, .reconnecting, .thinking: .thinking
        case .awaitingSpeech: call.muted ? .paused : .listening
        case .listening: call.muted ? .paused : .listening
        case .speaking: .speaking
        case .ending: .paused
        case .failed: .unavailable
        }
    }
    private var presenceAudioLevel: Double? {
        if call.isActive { return call.displayedAudioLevel }
        return model.playbackID == "realtime-voice-preview" && model.isPlaying ? model.playbackAudioLevel : nil
    }
    private var activeConversation: some View {
        VStack(alignment: .leading, spacing: 20) {
            if call.isActive { speakerIdentity }
            VStack(alignment: .leading, spacing: 10) {
                Text(call.capabilities == nil ? "通话声音由服务提供" : selectedDefault ? "通话使用默认声音" : "通话使用本人复刻音色")
                    .font(.caption).foregroundStyle(RMTwinColors.secondaryText)
            }.voiceCard()
            if !call.question.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("你刚才说").font(.caption).foregroundStyle(RMTwinColors.secondaryText)
                    Text(call.question).font(.body).textSelection(.enabled)
                }.voiceCard()
            }
            if let answer = call.answer {
                VStack(alignment: .leading, spacing: 12) {
                    Label(answer.response_type == "ORIGINAL" ? "本人原话" : answer.response_type == "SIMULATION" ? "根据记忆推测" : answer.response_type == "CONVERSATION" ? "通话中的交流回应" : "还不能确定", systemImage: "quote.bubble")
                        .font(.caption.weight(.semibold)).foregroundStyle(answer.response_type == "ORIGINAL" ? RMTwinColors.gold : RMTwinColors.accent)
                    Text(answer.checkedExpression ?? answer.answer).font(.body).textSelection(.enabled)
                    if !answer.evidence.isEmpty {
                        DisclosureGroup("查看回答依据") {
                            ForEach(answer.evidence) { source in
                                if let excerpt = source.excerpt { Text("“\(excerpt)”").font(.subheadline).foregroundStyle(RMTwinColors.secondaryText).padding(.top, 8) }
                            }
                        }.font(.caption)
                    }
                }.voiceCard(original: answer.response_type == "ORIGINAL").accessibilityIdentifier("voiceCall.answer")
            }
        }
    }
    private func enrollment(policy: String) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("照着读下面这句话，约 5–15 秒。")
                .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
            Text(guide).font(RMTypography.body)
                .padding(RMSpacing.md).twinGlass(cornerRadius: 14)
                .accessibilityIdentifier("voiceCall.readingPrompt")
            Button(model.isVoiceRecording ? "读完了，结束录音" : model.voiceSampleURL == nil ? "开始朗读" : "重新朗读", systemImage: model.isVoiceRecording ? "stop.circle" : "mic") {
                Task {
                    if model.isVoiceRecording { await model.finishAuxiliaryRecording() }
                    else { ownVoice = false; editSampleText = false; await model.startVoiceSample(readingPrompt: guide) }
                }
            }.buttonStyle(.bordered).disabled(isSaving || model.isBusy)
                .accessibilityIdentifier("voiceCall.recordSample")
            if model.isVoiceRecording { Text("已录 \(model.auxiliarySeconds) 秒") }
            if model.voiceSampleURL != nil && !model.isVoiceRecording {
                Text("试听后确认，就可以复刻你的声音。")
                    .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                    .accessibilityIdentifier("voiceCall.samplePending")
                Button("试听本人样本") { model.playVoiceSample() }.buttonStyle(.bordered)
                if model.voiceSampleTranscript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text("这段旧样本没有对应文字。点「重新朗读」，读完即可继续，无需打字。")
                        .font(.subheadline).foregroundStyle(RMTwinColors.secondaryText)
                        .accessibilityIdentifier("voiceCall.rerecordHint")
                } else {
                    if model.voiceSampleReadingPrompt == nil || model.voiceSampleTranscript != guide {
                        Text("这段样本的文字").font(.subheadline)
                        Text(model.voiceSampleTranscript).font(RMTypography.body)
                    }
                    Toggle("我确认只有本人声音，且录音与文字一致", isOn: $ownVoice)
                        .accessibilityIdentifier("voiceCall.confirmSample")
                }
                DisclosureGroup("读错了？修改文字或重新朗读", isExpanded: $editSampleText) {
                    TextEditor(text: $model.voiceSampleTranscript)
                        .font(RMTypography.body).foregroundStyle(RMTwinColors.text)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: RMMetrics.sampleEditorHeight)
                        .padding(RMSpacing.sm)
                        .background(RMTwinColors.raisedSurface, in: RoundedRectangle(cornerRadius: 14))
                        .accessibilityLabel("录音中实际说出的文字")
                        .accessibilityIdentifier("voiceCall.sampleTranscript")
                        .onChange(of: model.voiceSampleTranscript) { _, text in model.saveVoiceSampleTranscript(text) }
                }.font(.subheadline)
                Button(isSaving ? "正在提交…" : "确认并复刻我的声音", systemImage: "lock.shield") {
                    isSaving = true
                    Task { await model.enrollRealtimeVoice(policy: policy); isSaving = false }
                }.buttonStyle(.borderedProminent)
                    .disabled(isSaving || !ownVoice || model.isVoiceRecording || model.voiceSampleTranscript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityIdentifier("voiceCall.enroll")
            }
        }
    }
}


private extension View {
    func voiceCard(original: Bool = false) -> some View {
        padding(RMSpacing.md).frame(maxWidth: .infinity, alignment: .leading)
            .twinGlass(cornerRadius: 18, original: original)
    }
}

private struct TwinCallControl: View {
    let title: String
    let icon: String
    var destructive = false
    var selected = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: RMSpacing.xs) {
                Image(systemName: icon).font(.system(size: RMMetrics.icon))
                    .foregroundStyle(destructive ? RMColors.onDanger : RMTwinColors.text)
                    .frame(width: RMMetrics.controlDiameter, height: RMMetrics.controlDiameter)
                    .background(destructive ? RMColors.danger : selected ? RMTwinColors.accent.opacity(0.4) : RMTwinColors.surface, in: Circle())
                    .overlay { Circle().strokeBorder(destructive ? Color.clear : RMTwinColors.divider, lineWidth: 1) }
                Text(title).font(RMTypography.caption).foregroundStyle(RMTwinColors.text)
                    .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }.frame(maxWidth: .infinity)
        }.buttonStyle(RMQuietPressStyle())
            .accessibilityLabel(title).accessibilityValue(selected ? "已开启" : "")
    }
}
