import Foundation
import Speech

@MainActor
protocol LocalSpeechTranscriber {
    func transcribe(_ file: URL) async throws -> String
}

enum LocalSpeechError: LocalizedError {
    case unavailable, denied, busy, failed(String), empty, timedOut
    var errorDescription: String? {
        switch self {
        case .unavailable: "这台 iPhone 暂不支持中文离线转写。原音已保留，可连接记忆服务转写。"
        case .denied: "语音识别权限未允许。可在系统设置中开启，或连接记忆服务转写。"
        case .busy: "已有一段录音正在本机转写，请稍后再试。"
        case .failed(let message): "本机转写未完成：\(message)。原音已保留。"
        case .empty: "没有识别出文字。原音已保留，请回听后再试。"
        case .timedOut: "本机转写超时。原音已保留，可重试或连接记忆服务转写。"
        }
    }
}

@MainActor
protocol LocalSpeechRecognitionSession: AnyObject {
    func cancel()
}

@MainActor
protocol LocalSpeechRecognitionDriver {
    var supportsOnDeviceRecognition: Bool { get }
    func requestAuthorization(_ completion: @escaping @MainActor @Sendable (Bool) -> Void)
    func start(_ file: URL, completion: @escaping @MainActor @Sendable (Result<String, Error>) -> Void) throws -> any LocalSpeechRecognitionSession
}

@MainActor
private final class DeviceSpeechRecognitionSession: LocalSpeechRecognitionSession {
    let task: SFSpeechRecognitionTask
    init(_ task: SFSpeechRecognitionTask) { self.task = task }
    func cancel() { task.cancel() }
}

@MainActor
private final class DeviceSpeechRecognitionDriver: LocalSpeechRecognitionDriver {
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-Hans-CN"))
    var supportsOnDeviceRecognition: Bool { recognizer?.supportsOnDeviceRecognition == true }
    func requestAuthorization(_ completion: @escaping @MainActor @Sendable (Bool) -> Void) {
        SFSpeechRecognizer.requestAuthorization { status in
            let allowed = status == .authorized
            Task { @MainActor in completion(allowed) }
        }
    }
    func start(_ file: URL, completion: @escaping @MainActor @Sendable (Result<String, Error>) -> Void) throws -> any LocalSpeechRecognitionSession {
        guard let recognizer, recognizer.supportsOnDeviceRecognition else { throw LocalSpeechError.unavailable }
        let request = SFSpeechURLRecognitionRequest(url: file)
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = false
        return DeviceSpeechRecognitionSession(recognizer.recognitionTask(with: request) { result, error in
            let text = result?.isFinal == true ? result?.bestTranscription.formattedString : nil
            let message = error?.localizedDescription
            Task { @MainActor in
                if let text { completion(.success(text)) }
                else if let message { completion(.failure(LocalSpeechError.failed(message))) }
            }
        })
    }
}

/// Never falls back to Apple's network recognizer or any cloud provider.
@MainActor
final class OnDeviceSpeechTranscriber: LocalSpeechTranscriber {
    private let driver: any LocalSpeechRecognitionDriver
    private let timeout: Duration
    private var operationID: UUID?
    private var task: (any LocalSpeechRecognitionSession)?
    private var completion: CheckedContinuation<String, Error>?
    private var deadline: Task<Void, Never>?

    init(driver: any LocalSpeechRecognitionDriver, timeout: Duration = .seconds(90)) {
        self.driver = driver; self.timeout = timeout
    }
    convenience init() { self.init(driver: DeviceSpeechRecognitionDriver()) }

    func transcribe(_ file: URL) async throws -> String {
        try Task.checkCancellation()
        guard operationID == nil else { throw LocalSpeechError.busy }
        guard driver.supportsOnDeviceRecognition else { throw LocalSpeechError.unavailable }
        // Reserve the operation before the authorization callback can suspend us.
        let id = UUID()
        operationID = id
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                guard operationID == id, !Task.isCancelled else {
                    if operationID == id { operationID = nil }
                    continuation.resume(throwing: CancellationError()); return
                }
                completion = continuation
                driver.requestAuthorization { [weak self] allowed in
                    self?.authorized(allowed, file: file, id: id)
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in self?.finish(.failure(CancellationError()), id: id) }
        }
    }

    private func authorized(_ allowed: Bool, file: URL, id: UUID) {
        guard operationID == id else { return }
        guard allowed else { finish(.failure(LocalSpeechError.denied), id: id); return }
        do {
            let recognition = try driver.start(file) { [weak self] result in
                self?.finish(result.flatMap { text in
                    let clean = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    return clean.isEmpty ? .failure(LocalSpeechError.empty) : .success(clean)
                }, id: id)
            }
            // A driver may deliver its final result synchronously while starting.
            guard operationID == id else { recognition.cancel(); return }
            task = recognition
            let timeout = timeout
            deadline = Task { [weak self] in
                do { try await Task.sleep(for: timeout) } catch { return }
                self?.finish(.failure(LocalSpeechError.timedOut), id: id)
            }
        } catch { finish(.failure(error), id: id) }
    }

    private func finish(_ result: Result<String, Error>, id: UUID) {
        guard operationID == id, let completion else { return }
        operationID = nil
        self.completion = nil
        deadline?.cancel(); deadline = nil
        task?.cancel(); task = nil
        completion.resume(with: result)
    }
}
