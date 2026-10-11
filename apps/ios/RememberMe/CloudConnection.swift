import Foundation
import SwiftUI

enum ECSConfiguration {
    // Same IP certificate shipped by Android 0.9.2; never accept a fetched pin.
    static let baseURL = "https://39.108.183.47"
    static let fingerprint = "b55251a4d7ceb4c0934c0b65ea7eab172de760a13b953cc72e43a60423aff00c"
}

struct CloudServiceInfo: Decodable {
    let api_version: String
    let registration_allowed: Bool
}
struct CloudLoginReply: Decodable {
    let actor_token: String
    let actor_id: String
    let display_name: String
}
struct CloudSpace: Decodable, Identifiable {
    let subject_id: String
    let display_name: String
    let role: String
    var id: String { subject_id }
}
struct CloudSpacesReply: Decodable {
    let actor_id: String
    let display_name: String
    let items: [CloudSpace]
}
struct BackendCapabilities: Decodable {
    let stt: String
    let stt_processing: String
    let stt_configured: Bool
    let cloud_asr_policy: String?
    let stt_model: String?
    let stt_host: String?
    let ai_available: Bool
    var uploadNotice: String {
        if stt_processing == "cloud" {
            return "本段完整原音将上传记忆服务，并发送至 \(stt_host ?? "服务指定的转写供应商")，使用 \(stt_model ?? stt) 转写。供应商可能临时保存音频副本。原音和机器稿保留，文字由你核对后才整理记忆。"
        }
        return "本段原音将上传记忆服务转写。文字由你核对后才整理记忆。"
    }
}

struct ServiceConnectionView: View {
    @EnvironmentObject private var model: AppModel
    @State private var route = "ecs"
    var body: some View {
        VStack(spacing: 0) {
            Picker("连接方式", selection: $route) {
                Text("云端服务").tag("ecs")
                Text("Mac 配对").tag("mac")
            }.pickerStyle(.segmented).padding()
            if route == "ecs" { ECSLoginView() } else { PairingView() }
        }
        .navigationTitle("连接记忆服务")
        .onChange(of: model.pairingServer) { _, value in
            if !value.isEmpty { route = "mac" }
        }
        .onAppear { if !model.pairingCode.isEmpty && model.pairing?.isCloud != true { route = "mac" } }
    }
}

private struct ECSLoginView: View {
    @EnvironmentObject private var model: AppModel
    @State private var username = ""
    @State private var password = ""
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("REMEMBER ME · 云端记忆").font(.caption.weight(.semibold)).foregroundStyle(Ink.coral)
                Text("和 Android 使用同一个记忆服务。")
                    .font(.title2.weight(.semibold))
                Text("录音先留在 iPhone。你同意上传转写、核对文字并确认整理后，才生成记忆。个人声音另行授权。")
                    .foregroundStyle(Ink.muted)
                Label(model.connectionStatus, systemImage: "network")
                    .font(.subheadline).accessibilityIdentifier("ecs.status")
                Button("检查连接") { Task { await model.checkECSConnection() } }
                    .disabled(model.isBusy).buttonStyle(.bordered)
                if let pairing = model.pairing, pairing.isCloud {
                    Text("当前账号：\(pairing.displayName ?? "已登录")")
                    Text("当前空间：\(pairing.spaceName ?? "本人空间")")
                    Button("退出云端账号", role: .destructive) { Task { await model.disconnectCloud() } }
                        .disabled(model.connectionChangeBlocked)
                }
                VStack(spacing: 12) {
                    TextField("内测账号", text: $username)
                        .textContentType(.username).textInputAutocapitalization(.never)
                        .autocorrectionDisabled().accessibilityIdentifier("ecs.username")
                    Divider()
                    SecureField("密码", text: $password)
                        .textContentType(.password).accessibilityIdentifier("ecs.password")
                }.padding(18).background(Ink.cream, in: RoundedRectangle(cornerRadius: 16))
                ActionButton(title: model.isBusy ? "正在登录…" : "登录云端服务", icon: "lock.shield") {
                    let entered = password
                    password = ""
                    Task { await model.loginECS(username: username, password: entered) }
                }.disabled(model.connectionChangeBlocked || username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty)
                    .accessibilityIdentifier("ecs.login")
                ForEach(model.cloudSpaces) { space in
                    Button {
                        Task { await model.selectCloudSpace(space.id) }
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(space.display_name)
                                Text(space.role == "owner" ? "本人空间" : "亲友空间 · 此版接入稍后提供")
                                    .font(.caption).foregroundStyle(Ink.muted)
                            }
                            Spacer()
                            if model.pairing?.subjectID == space.id { Image(systemName: "checkmark") }
                        }.frame(minHeight: 48)
                    }.disabled(space.role != "owner" || model.connectionChangeBlocked)
                }
                Text("注册暂未开放，请使用独立内测账号。公开演示账号只放虚构材料。旧 Mac 录音仍保留，不会自动传到云端。")
                    .font(.caption).foregroundStyle(Ink.muted)
                if model.hasSavedMacConnection {
                    Button("恢复上次 Mac 连接") { Task { await model.restoreMacConnection() } }
                        .disabled(model.connectionChangeBlocked)
                }
                if model.otherServiceRecordingCount > 0 {
                    Text("另有 \(model.otherServiceRecordingCount) 段录音留在原空间；切回对应服务后可查看。")
                        .font(.caption).foregroundStyle(Ink.muted)
                }
            }.padding(24)
        }.background(Ink.paper.ignoresSafeArea())
    }
}

/// Capture approval binds the displayed provider policy to this exact upload.
struct RecordingUploadButton: View {
    @EnvironmentObject private var model: AppModel
    @State private var showConsent = false
    @State private var policy: String?
    @State private var showConnection = false
    var body: some View {
        ActionButton(title: model.isBusy || model.isPollingEpisode ? "正在处理…" : model.pairing == nil ? "连接服务后转写" : model.episodeID == nil ? "提交并转成文字" : "继续查看处理结果", icon: "text.bubble") {
            if model.pairing == nil { showConnection = true }
            else if model.pairing?.isCloud == true && model.episodeID == nil {
                Task {
                    if let approved = await model.prepareCloudASR() {
                        policy = approved; showConsent = true
                    }
                }
            } else { Task { await model.sendRecording() } }
        }.disabled(model.isBusy || model.isPollingEpisode || model.isLocalTranscribing)
        .confirmationDialog("上传本段原音并转写？", isPresented: $showConsent, titleVisibility: .visible) {
            Button("同意本段上传与转写") { Task { await model.sendRecording(cloudASRPolicy: policy) } }
            Button("只保留在手机", role: .cancel) { }
        } message: { Text(model.cloudCapabilities?.uploadNotice ?? "") }
        .sheet(isPresented: $showConnection) {
            NavigationStack {
                ServiceConnectionView().toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("关闭") { showConnection = false }
                    }
                }
            }.onChange(of: model.pairing?.token) { _, token in
                if token != nil { showConnection = false }
            }
        }
    }
}
