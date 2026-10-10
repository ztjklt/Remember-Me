import Foundation
import Speech

@MainActor
protocol LocalSpeechTranscriber {
    func transcribe(_ file: URL) async throws -> String
}

enum LocalSpeechError: LocalizedError {
    case unavailable, denied, failed(String), empty, timedOut
    var errorDescription: String? {
        switch self {
        case .unavailable: "这台 iPhone 暂不支持中文离线转写。原音已保留，可连接 Mac 转写。"
        case .denied: "语音识别权限未允许。可在系统设置中开启，或连接 Mac 转写。"
        case .failed(let message): "本机转写未完成：\(message)。原音已保留。"
        case .empty: "没有识别出文字。原音已保留，请回听后再试。"
        case .timedOut: "本机转写超时。原音已保留，可重试或连接 Mac 转写。"
        }
    }
}

/// Never falls back to Apple's network recognizer or any cloud provider.
@MainActor
final class OnDeviceSpeechTranscriber: LocalSpeechTranscriber {
    private var recognizer: SFSpeechRecognizer?
    private var task: SFSpeechRecognitionTask?
    private var completion: CheckedContinuation<String, Error>?
    private var deadline: Task<Void, Never>?

    func transcribe(_ file: URL) async throws -> String {
        guard completion == nil,
              let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-Hans-CN")),
              recognizer.supportsOnDeviceRecognition else { throw LocalSpeechError.unavailable }
        let permission = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        guard permission == .authorized else { throw LocalSpeechError.denied }
        try Task.checkCancellation()
        self.recognizer = recognizer
        let request = SFSpeechURLRecognitionRequest(url: file)
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = false
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                completion = continuation
                task = recognizer.recognitionTask(with: request) { [weak self] result, error in
                    let text = result?.isFinal == true ? result?.bestTranscription.formattedString : nil
                    let message = error?.localizedDescription
                    Task { @MainActor [weak self] in
                        if let text {
                            let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
                            self?.finish(clean.isEmpty ? .failure(LocalSpeechError.empty) : .success(clean))
                        } else if let message { self?.finish(.failure(LocalSpeechError.failed(message))) }
                    }
                }
                deadline = Task { [weak self] in
                    do { try await Task.sleep(for: .seconds(90)) } catch { return }
                    self?.finish(.failure(LocalSpeechError.timedOut))
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in self?.finish(.failure(CancellationError())) }
        }
    }

    private func finish(_ result: Result<String, Error>) {
        guard let completion else { return }
        self.completion = nil
        deadline?.cancel(); deadline = nil
        task?.cancel(); task = nil
        recognizer = nil
        completion.resume(with: result)
    }
}
