import AVFoundation
import Foundation

@MainActor
final class RecordingAudioEvents: NSObject, AVAudioRecorderDelegate {
    weak var recorder: AVAudioRecorder?
    var finished: ((Bool) -> Void)?
    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        complete(ObjectIdentifier(recorder), successfully: flag)
    }
    nonisolated func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: (any Error)?) {
        complete(ObjectIdentifier(recorder), successfully: false)
    }
    private nonisolated func complete(_ id: ObjectIdentifier, successfully flag: Bool) {
        Task { @MainActor [weak self] in
            guard let self, let recorder = self.recorder, ObjectIdentifier(recorder) == id else { return }
            // Encode-error and finish callbacks may both arrive for one recorder.
            self.recorder = nil
            self.finished?(flag)
        }
    }
}
