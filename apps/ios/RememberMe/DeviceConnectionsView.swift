import AVKit
import SwiftUI

struct DeviceConnectionsCards: View {
    @ObservedObject var devices: DeviceConnectionsModel
    var body: some View {
        HStack(alignment: .top, spacing: RMSpacing.sm) {
            deviceCard(image: "DeviceRecordingBean", title: "录音豆", status: devices.beanState,
                       detail: devices.recording ? (devices.paused ? "录音已暂停" : "正在录音") : "Anker soundcore",
                       connected: devices.connected != nil)
            deviceCard(image: "DeviceEarbuds", title: "耳机", status: devices.headphonesName == nil ? "未使用" : "使用中",
                       detail: devices.headphonesName ?? "选择 iPhone 音频设备", connected: devices.headphonesName != nil)
        }
        .padding(.vertical, RMSpacing.xs)
        .environment(\.colorScheme, .light)
    }
    private func deviceCard(image: String, title: String, status: String, detail: String, connected: Bool) -> some View {
        VStack(alignment: .leading, spacing: RMSpacing.xs) {
            Image(image).resizable().scaledToFit().frame(maxWidth: .infinity).frame(height: 126)
                .accessibilityHidden(true)
            Text(title).font(RMTypography.heading).foregroundStyle(Ink.text)
            Label(status, systemImage: connected ? "checkmark.circle.fill" : "circle.dashed")
                .font(RMTypography.caption).foregroundStyle(connected ? RMColors.success : Ink.muted)
                .fixedSize(horizontal: false, vertical: true)
            Text(detail).font(RMTypography.caption).foregroundStyle(Ink.muted)
                .fixedSize(horizontal: false, vertical: true)
            if image == "DeviceRecordingBean", let level = devices.battery {
                Label("电量 \(level)%", systemImage: "battery.100percent").font(RMTypography.caption)
            }
        }.frame(maxWidth: .infinity, alignment: .topLeading).accessibilityElement(children: .combine)
            .accessibilityIdentifier(image == "DeviceRecordingBean" ? "devices.bean.status" : "devices.headphones.status")
    }
}
struct DeviceConnectionsView: View {
    @EnvironmentObject private var model: AppModel
    @ObservedObject var devices: DeviceConnectionsModel
    @State private var showDevicePurpose = false
    var body: some View {
        List {
            Section {
                DeviceConnectionsCards(devices: devices)
                    .listRowBackground(Color.white)
                    .listRowSeparator(.hidden)
            }
            Section("录音豆") {
                Toggle("连接后自动同步录音", isOn: $devices.automaticSync)
                Text("原音完整保存，后台自动整理记忆。普通内容可归并，重点对话完整保留。")
                    .font(RMTypography.caption).foregroundStyle(Ink.muted)
                if let connected = devices.connected {
                    Text(connected.name).font(RMTypography.heading)
                    Button("同步录音列表") { devices.syncFiles() }.disabled(devices.busy)
                    if devices.recording {
                        Button(devices.paused ? "继续录音" : "暂停录音") { devices.setPaused() }
                        Button(devices.priorityActive ? "结束重点" : "开始重点", systemImage: devices.priorityActive ? "flag.fill" : "flag") {
                            devices.togglePriority()
                        }.disabled(!devices.receivingLiveAudio || devices.paused)
                            .accessibilityIdentifier("devices.priority.toggle")
                        Label(devices.receivingLiveAudio ? "正在持续接收原音" : "等待实时音频", systemImage: "waveform")
                            .font(RMTypography.caption).foregroundStyle(Ink.muted)
                    } else {
                        Text("等待设备开始录音，开始后会自动接收并整理。")
                            .font(RMTypography.detail).foregroundStyle(Ink.muted)
                    }
                    Button("绑定此录音豆") { devices.bind() }.disabled(devices.busy)
                    Button("断开连接") { devices.disconnect() }
                } else {
                    Button(devices.busy ? "正在连接…" : "查找录音豆") {
                        if model.pairing == nil {
                            Task { await devices.scan(pairing: nil, client: nil) }
                        } else { showDevicePurpose = true }
                    }.disabled(devices.busy || model.connectionChangeBlocked).accessibilityIdentifier("devices.scan")
                    ForEach(devices.devices) { device in
                        Button { devices.connect(device) } label: { Label(device.name, systemImage: "dot.radiowaves.left.and.right") }
                            .disabled(devices.busy)
                    }
                }
                if let value = devices.progress { ProgressView(value: Double(value), total: 100) { Text("正在取回录音 \(value)%") } }
                if let message = devices.message { Text(message).font(RMTypography.detail).foregroundStyle(Ink.muted) }
            }
            Section("耳机") {
                Label(devices.headphonesName.map { "正在使用：" + $0 } ?? "当前未使用耳机", systemImage: "headphones")
                    .font(RMTypography.detail)
                HStack {
                    Text("连接或切换耳机")
                    Spacer()
                    SystemAudioRoutePicker().frame(width: 44, height: 44)
                        .accessibilityIdentifier("devices.audioRoute")
                }
                Text("已配对的耳机可通过右侧按钮选择。首次连接请在 iPhone「设置 → 蓝牙」中配对；这里实时显示当前使用的音频设备。耳机断开时会暂停手机录音。")
                    .font(RMTypography.caption).foregroundStyle(Ink.muted)
            }
            if !devices.files.isEmpty {
                Section("设备上的录音") {
                    ForEach(devices.files) { file in
                        Button {
                            devices.download(file)
                        } label: {
                            VStack(alignment: .leading, spacing: RMSpacing.xs) {
                                Text(Date(timeIntervalSince1970: Double(UInt32(bitPattern: file.id))).formatted(date: .abbreviated, time: .shortened))
                                Text("同步到我的录音").font(RMTypography.caption).foregroundStyle(Ink.muted)
                            }
                        }.disabled(devices.busy).accessibilityIdentifier("devices.import.\(file.id)")
                    }
                }
            }
            Section("同步到记忆") {
                if let notice = model.deviceSyncNotice { Text(notice).font(RMTypography.detail).foregroundStyle(Ink.muted) }
                Button(model.isSyncingDeviceRecordings ? "正在整理…" : "重试整理已同步录音") { model.processDeviceRecordingQueue() }
                    .disabled(model.isSyncingDeviceRecordings)
            }
            Section {
                Text("重点从标记开始，到下一次标记结束。两次标记之间的对话不精简；退出重点后继续保存原音。设备实体按键与佩戴自动开录需固件支持，尚未实机确认。")
                    .font(RMTypography.detail).foregroundStyle(Ink.muted)
                Text("同步保留设备原文件。只有匹配本人的声音能更新本人人物模型；其他人的话保留来源并待核对。转写中的必要原话证据仍保留，重复机器稿在整理成功后清理。")
                    .font(RMTypography.detail).foregroundStyle(Ink.muted)
            }
        }.scrollContentBackground(.hidden).background(Ink.paper).navigationTitle("蓝牙连接")
            .navigationBarTitleDisplayMode(.inline)
            .confirmationDialog("连接并整理录音豆内容？", isPresented: $showDevicePurpose, titleVisibility: .visible) {
                Button("同意用途并查找") {
                    Task { await devices.scan(pairing: model.pairing, client: model.dialogueClient()) }
                }
                Button("取消", role: .cancel) {}
            } message: {
                Text("会取回设备上尚未导入的录音，保存原音，并按当前服务进行转写和声音识别、整理本人记忆。可先关闭自动同步再逐条选择。重点内容完整保留；声音复刻另行授权。")
            }
            .task { devices.reconcile(owner: model.pairing.map(RecordingOwner.init)) }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
                devices.refreshHeadphones()
            }
    }
}
private struct SystemAudioRoutePicker: UIViewRepresentable {
    func makeUIView(context: Context) -> AVRoutePickerView {
        let picker = AVRoutePickerView()
        picker.prioritizesVideoDevices = false
        picker.tintColor = UIColor(RMColors.action)
        picker.activeTintColor = UIColor(RMColors.success)
        picker.accessibilityLabel = "连接或切换耳机"
        return picker
    }
    func updateUIView(_ uiView: AVRoutePickerView, context: Context) {}
}
