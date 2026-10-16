import Foundation
import XCTest
@testable import RememberMe
#if canImport(module_spplinkKit)
@preconcurrency import module_spplinkKit

private final class SoundcoreEventLog: @unchecked Sendable {
    private let lock = NSLock()
    private var events: [SoundcoreEvent] = []
    func append(_ event: SoundcoreEvent) { lock.withLock { events.append(event) } }
    var values: [SoundcoreEvent] { lock.withLock { events } }
}

final class SoundcoreCallbackTests: XCTestCase {
    func testBindingWaitsForPhysicalConfirmationAndIgnoresOtherDevices() {
        let events = SoundcoreEventLog()
        let callback = SoundcoreCallbacks { events.append($0) }
        callback.select(device)
        callback.onSendBindingDeviceCMDSuccess(macAddress: device.mac, uuid: device.id)
        callback.onDeviceBindConfirm(macAddress: "foreign", uuid: device.id)
        XCTAssertEqual(events.values.count, 1)
        guard case .bindingPending = events.values[0] else { return XCTFail("Command delivery is not binding confirmation") }
        callback.onDeviceBindConfirm(macAddress: device.mac, uuid: device.id)
        guard case .bound = events.values.last else { return XCTFail("Physical confirmation must finish binding") }
    }

    func testProgressRealtimeAndDecodeDoNotToggleTheSameMarkerMoreThanOnce() {
        let events = SoundcoreEventLog()
        let callback = SoundcoreCallbacks { events.append($0) }
        callback.select(device)
        callback.onTransferFileProgress(macAddress: device.mac, uuid: device.id,
            fileID: 123, total: -1, current: 160, sequenceNumber: 10, isMark: true)
        let bytes = KotlinByteArray(size: 160)
        bytes.set(index: 0, value: -1)
        callback.onReceiveAudioFragment(macAddress: device.mac, uuid: device.id, fileID: 123,
            audioData: bytes, isAppendPreAudio: false, sequenceNumber: 10, isMark: true)
        let markers = KotlinIntArray(size: 3)
        markers.set(index: 0, value: 200); markers.set(index: 1, value: 200); markers.set(index: 2, value: 600)
        callback.onDecodeFileMarkers(macAddress: device.mac, uuid: device.id, fileID: 123, markerTimes: markers)
        callback.onDecodeFileMarkers(macAddress: device.mac, uuid: device.id, fileID: 123, markerTimes: markers)
        let markerEvents = events.values.compactMap { event -> ([Int], Bool)? in
            if case .markers(let file, let times, let final) = event, file == 123 { return (times, final) }
            return nil
        }
        XCTAssertEqual(markerEvents.count, 2)
        XCTAssertEqual(markerEvents[0].0, [200]); XCTAssertFalse(markerEvents[0].1)
        XCTAssertEqual(markerEvents[1].0, [200, 600]); XCTAssertTrue(markerEvents[1].1)
        guard let fragment = events.values.first(where: {
            if case .realtimeFragment = $0 { return true }; return false
        }), case .realtimeFragment(let file, let sequence, let append, let data, let marked) = fragment else {
            return XCTFail("Expected an immutable audio snapshot")
        }
        XCTAssertEqual(file, 123); XCTAssertEqual(sequence, 10); XCTAssertFalse(append)
        XCTAssertEqual(data.count, 160); XCTAssertEqual(data.first, 255); XCTAssertTrue(marked)
        bytes.set(index: 0, value: 0)
        XCTAssertEqual(data.first, 255, "Kotlin mutable buffers cannot cross callback executors")
    }

    func testInvalidMarkerCannotClaimACompleteTimeline() {
        let events = SoundcoreEventLog()
        let callback = SoundcoreCallbacks { events.append($0) }
        callback.select(device)
        let markers = KotlinIntArray(size: 1)
        markers.set(index: 0, value: -1)
        callback.onDecodeFileMarkers(macAddress: device.mac, uuid: device.id, fileID: 123, markerTimes: markers)
        guard case .markers(_, let offsets, let final) = events.values.last else { return XCTFail("Expected incomplete marker evidence") }
        XCTAssertEqual(offsets, [-1]); XCTAssertFalse(final)
    }

    func testStoppingScanForConnectionDoesNotCreateASyncFailure() {
        let events = SoundcoreEventLog()
        let callback = SoundcoreCallbacks { events.append($0) }
        callback.setScanning(true)
        callback.setScanning(false)
        // Official SDK documents a scan-interruption callback after stopScan.
        callback.onScanError(result: 0)
        XCTAssertTrue(events.values.isEmpty)
        callback.setScanning(true)
        callback.onScanError(result: 1)
        XCTAssertEqual(events.values.count, 1)
    }

    private var device: RecordingBeanDevice {
        RecordingBeanDevice(id: "selected-device", mac: "selected-mac", name: "Test bean", product: "D3200")
    }
}
#endif
