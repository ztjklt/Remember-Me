import AVFoundation
import Foundation
import UIKit

@MainActor
final class AudioCapture: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published private(set) var fileURL: URL?
    @Published private(set) var recordedAt: Date?
    @Published private(set) var elapsed: TimeInterval = 0
    @Published private(set) var isRecording = false
    @Published private(set) var isPaused = false
    @Published private(set) var isPlaying = false
    @Published var message: String?

    private var recorder: AVAudioRecorder?
    private var player: AVAudioPlayer?
    private var timer: Timer?

    override init() {
        super.init()
        loadLatestRecording()
        NotificationCenter.default.addObserver(
            self, selector: #selector(saveWhenBackgrounded),
            name: UIApplication.didEnterBackgroundNotification, object: nil
        )
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    func start() async {
        guard !isRecording else { return }
        let allowed = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { granted in
                continuation.resume(returning: granted)
            }
        }
        guard allowed else {
            message = "麦克风权限未授予。请在系统设置中允许录音。"
            return
        }
        do {
            stopPlayback()
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
            try session.setActive(true)
            let directory = try recordingsDirectory()
            let url = directory.appendingPathComponent("episode-\(UUID().uuidString).m4a")
            let settings: [String: Any] = [
                AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
                AVSampleRateKey: 44_100,
                AVNumberOfChannelsKey: 1,
                AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
            ]
            let next = try AVAudioRecorder(url: url, settings: settings)
            next.prepareToRecord()
            guard next.record() else {
                message = "录音无法启动。"
                return
            }
            recorder = next
            fileURL = url
            recordedAt = Date()
            UserDefaults.standard.set(recordedAt, forKey: recordingDateKey(url))
            elapsed = 0
            isRecording = true
            isPaused = false
            message = nil
            timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
                Task { @MainActor in self?.elapsed = self?.recorder?.currentTime ?? 0 }
            }
        } catch {
            message = "录音启动失败：\(error.localizedDescription)"
        }
    }

    func pauseOrResume() {
        guard let recorder, isRecording else { return }
        if isPaused {
            guard recorder.record() else {
                message = "无法继续录音，请先保存。"
                return
            }
            isPaused = false
        } else {
            recorder.pause()
            isPaused = true
        }
    }

    func stop() {
        guard isRecording else { return }
        elapsed = recorder?.currentTime ?? elapsed
        recorder?.stop()
        recorder = nil
        timer?.invalidate()
        timer = nil
        isRecording = false
        isPaused = false
        try? AVAudioSession.sharedInstance().setActive(false)
        message = "录音已保存在本机；上传失败也不会删除原文件。"
    }

    func importAudio(from source: URL) {
        guard !isRecording else {
            message = "请先保存当前录音再导入。"
            return
        }
        let extensionName = source.pathExtension.lowercased()
        guard ["m4a", "wav"].contains(extensionName) else {
            message = "目前可导入 .m4a 或 .wav 录音。"
            return
        }
        let access = source.startAccessingSecurityScopedResource()
        defer { if access { source.stopAccessingSecurityScopedResource() } }
        var copiedFile: URL?
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: source.path)
            guard let size = attributes[.size] as? NSNumber,
                  size.intValue > 0, size.intValue <= 25 * 1024 * 1024 else {
                message = "文件为空或超过 25 MiB 上传限制。"
                return
            }
            stopPlayback()
            let destination = try recordingsDirectory()
                .appendingPathComponent("import-\(UUID().uuidString).\(extensionName)")
            try FileManager.default.copyItem(at: source, to: destination)
            copiedFile = destination
            let candidate = try AVAudioPlayer(contentsOf: destination)
            fileURL = destination
            setRecordedAt((try? source.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? Date())
            elapsed = candidate.duration
            message = "文件已复制到本机。请核对录制时间，并确认录音对象的同意。"
        } catch {
            if let copiedFile { try? FileManager.default.removeItem(at: copiedFile) }
            message = "导入失败：\(error.localizedDescription)"
        }
    }

    func setRecordedAt(_ date: Date) {
        guard let fileURL, !isRecording else { return }
        recordedAt = date
        UserDefaults.standard.set(date, forKey: recordingDateKey(fileURL))
    }

    func playOrStop() {
        guard !isRecording, let fileURL else { return }
        if isPlaying {
            stopPlayback()
            return
        }
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            let player = try AVAudioPlayer(contentsOf: fileURL)
            player.delegate = self
            player.prepareToPlay()
            guard player.play() else {
                message = "录音无法播放。"
                return
            }
            self.player = player
            isPlaying = true
            message = nil
        } catch {
            message = "播放失败：\(error.localizedDescription)"
        }
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        isPlaying = false
        self.player = nil
        try? AVAudioSession.sharedInstance().setActive(false)
    }

    private func stopPlayback() {
        player?.stop()
        player = nil
        isPlaying = false
        try? AVAudioSession.sharedInstance().setActive(false)
    }

    @objc private func saveWhenBackgrounded() {
        if isRecording { stop() }
    }

    private func recordingsDirectory() throws -> URL {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let directory = documents.appendingPathComponent("Recordings", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory
    }

    private func recordingDateKey(_ url: URL) -> String {
        "recordedAt:\(url.lastPathComponent)"
    }

    private func loadLatestRecording() {
        guard let directory = try? recordingsDirectory(),
              let files = try? FileManager.default.contentsOfDirectory(
                at: directory, includingPropertiesForKeys: [.creationDateKey], options: [.skipsHiddenFiles]
              ) else { return }
        let latest = files.filter { ["m4a", "wav"].contains($0.pathExtension.lowercased()) }
            .max { lhs, rhs in
                let left = (try? lhs.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? .distantPast
                let right = (try? rhs.resourceValues(forKeys: [.creationDateKey]).creationDate) ?? .distantPast
                return left < right
            }
        guard let latest else { return }
        fileURL = latest
        recordedAt = (UserDefaults.standard.object(forKey: recordingDateKey(latest)) as? Date)
            ?? (try? latest.resourceValues(forKeys: [.creationDateKey]).creationDate)
            ?? Date()
        if let player = try? AVAudioPlayer(contentsOf: latest) { elapsed = player.duration }
    }
}
