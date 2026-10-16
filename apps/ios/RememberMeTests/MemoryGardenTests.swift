import XCTest
import UIKit
@testable import RememberMe

@MainActor
final class MemoryGardenTests: XCTestCase {
    func testAllTenFlowerArtworksExistInTheCompiledAssetCatalog() throws {
        XCTAssertEqual(GardenArtwork.allCases.count, 10)
        for artwork in GardenArtwork.allCases {
            let image = try XCTUnwrap(UIImage(named: artwork.rawValue), artwork.rawValue)
            XCTAssertGreaterThan(image.size.width, 100)
            XCTAssertGreaterThan(image.size.height, 100)
            XCTAssertNotNil(image.cgImage)
        }
    }
    func testTimelineUsesCaptureDayNotFreeformEventTimeAndKeepsUnknownLast() throws {
        func entry(_ id: String, capture: String, event: String = "大学时") -> GardenEntry {
            GardenEntry(id: id, title: id, text: id, label: "故事", date: event, sortDate: capture,
                        section: .stories, memories: [], evidence: [])
        }
        let zone = try XCTUnwrap(TimeZone(identifier: "Asia/Singapore"))
        let groups = GardenTimelineProjection.groups([
            entry("unknown", capture: "unknown", event: "1999 年"),
            entry("before", capture: "2026-10-13T15:59:00Z"),
            entry("after", capture: "2026-10-13T16:01:00.000Z"),
            entry("same-day", capture: "2026-10-14T01:00:00Z")
        ], timeZone: zone)
        XCTAssertEqual(groups.map(\.id), ["2026.10.14", "2026.10.13", "undated"])
        XCTAssertEqual(groups[0].entries.map(\.id), ["same-day", "after"])
        XCTAssertEqual(groups.last?.title, "录入时间未知")
        XCTAssertFalse(groups.contains { $0.title.contains("1999") })
        XCTAssertTrue(GardenTimelineProjection.groups([], timeZone: zone).isEmpty)
    }
    func testTimelineFactBranchesRequireSharedEvidenceNotSimilarTitlesOrEpisode() {
        let entry = GardenEntry(id: "entry", title: "一起种树", text: "一起种树", label: "故事", date: "大学时", sortDate: "",
                                section: .stories, memories: [memory("m1")], evidence: [])
        func item(_ id: String, evidence: [String]) -> GardenGraphItem {
            GardenGraphItem(fact: GraphFactRecord(fact_id: id, subject_id: "subject", kind: "EVENT", content: "一起种树",
                evidence_ids: evidence, model_version: "fixture", valid_from: nil, valid_to: nil), memories: [memory("m2")])
        }
        let linked = GardenTimelineProjection.linkedFacts(for: entry, items: [item("match", evidence: ["e_m1"]),
            item("same-title-and-episode", evidence: ["e_m2"]), item("unproven", evidence: [])])
        XCTAssertEqual(linked.map(\.id), ["match"])
    }
    func testGardenParticlesAreBoundedAndInvalidTimesDoNotAnimate() {
        XCTAssertTrue(GardenPetalMotion.particles(time: .nan).isEmpty)
        XCTAssertTrue(GardenPetalMotion.particles(time: -1).isEmpty)
        for time in stride(from: 0.0, to: 300, by: 0.3) {
            let particles = GardenPetalMotion.particles(time: time)
            XCTAssertEqual(particles.count, 7)
            for particle in particles {
                XCTAssertTrue((0...1).contains(particle.x))
                XCTAssertTrue((0...1).contains(particle.y))
                XCTAssertTrue((0...0.38).contains(particle.opacity))
                XCTAssertTrue((-50...50).contains(particle.angle))
            }
        }
    }
    private func pairing(actor: String = "actor", subject: String = "subject", server: String = "https://fixture.invalid", token: String = "fixture") -> Pairing {
        Pairing(baseURL: server, fingerprint: String(repeating: "a", count: 64), token: token,
                actorID: actor, subjectID: subject, consentID: "fixture-consent")
    }
    private func memory(_ id: String, episode: String = "ep", kind: String = "EVENT", source: String = "SUBJECT", evidenceIDs: [String]? = nil) -> MemoryRecord {
        MemoryRecord(memory_item_id: id, episode_id: episode, content: "原文里的真实记录 " + id, memory_type: kind,
            domain: nil, source_type: source, confidence: 0.8, model_version: "fixture", recorded_at: "2026-10-14T00:00:00Z",
            transcript: "真实原文", stt_model_version: "fixture", capture_source: "IOS_MIC",
            evidence: (evidenceIDs ?? ["e_" + id]).map { EvidenceRecord(evidence_id: $0, excerpt: "真实原文", source_type: source,
                source_ref: episode, span_start: 0, span_end: 4) })
    }
    private func episode(_ id: String = "ep", status: String = "ready") -> EpisodeRecord {
        EpisodeRecord(episode_id: id, status: status, source: "IOS_MIC", recorded_at: "2026-10-14T00:00:00Z",
            duration_ms: 10000, transcript: "真实原文", stt_backend: "fixture", stt_model_version: "fixture", model_version: "fixture", error_code: nil)
    }
    private func evidence(_ id: String = "e_m1", episode: String = "ep") -> ReviewEvidence {
        ReviewEvidence(evidence_id: id, episode_id: episode, excerpt: "真实原文", source_type: "SUBJECT", temporal_context: nil)
    }
    private func record(_ id: String = "story", kind: String = "story", status: String = "confirmed", valid: Bool = true,
                        historical: Bool = false, evidenceIDs: [String] = ["e_m1"], sources: [ReviewEvidence]? = nil,
                        facets: [String] = ["EPISODIC_MEMORY"], aliases: [String] = []) throws -> ReviewRecord {
        let object: [String: Any] = ["id":id,"kind":kind,"title":"整理后的故事","text":"从原文整理的经历",
            "evidence_ids":evidenceIDs,"facets":facets,"time_text":"","place_text":"","aliases":aliases,
            "same_event":false,"recipient_label":"","status":status,"revision":1,"model_version":"fixture","prompt_version":"fixture",
            "evidence":(sources ?? [evidence()]).map { ["evidence_id":$0.id,"episode_id":$0.episode_id,"excerpt":$0.excerpt,"source_type":$0.source_type] },
            "source_valid":valid,"historical":historical]
        return try JSONDecoder().decode(ReviewRecord.self,from:JSONSerialization.data(withJSONObject:object))
    }
    private func overview(_ records: [ReviewRecord] = [], sources: [ReviewEvidence] = [], subject: String = "subject", role: String = "owner") -> ReviewOverview {
        ReviewOverview(subject_id: subject, role: role, records: records, source_evidence: sources, style: ReviewStyle(enabled: false, revision: 0))
    }
    func testGraphUsesOnlySameSubjectsFactsWithAllVisibleEvidence() {
        func fact(_ id: String, subject: String = "subject", evidence: [String]) -> GraphFactRecord {
            GraphFactRecord(fact_id: id, subject_id: subject, kind: "RELATIONSHIP", content: "一起种树",
                            evidence_ids: evidence, model_version: "fixture", valid_from: nil, valid_to: nil)
        }
        let facts = [fact("linked", evidence: ["e_m1", "e_m2"]),
                     fact("other-subject", subject: "other", evidence: ["e_m1"]),
                     fact("missing", evidence: ["e_m1", "unknown"]), fact("unproven", evidence: [])]
        let items = GardenGraphProjection.items(facts: facts, memories: [memory("m1"), memory("m2")], subjectID: "subject")
        XCTAssertEqual(items.map(\.id), ["linked"])
        XCTAssertEqual(items.first?.memories.map(\.id), ["m1", "m2"])
        XCTAssertTrue(GardenGraphProjection.items(facts: facts, memories: [memory("m1")], subjectID: "subject").isEmpty)
    }
    func testOlderModelWithoutGraphStillDecodesAndNewGraphKeepsVersionAndTime() throws {
        let old = try JSONDecoder().decode(PersonModelReply.self, from: Data(#"{"version":2,"domains":[]}"#.utf8))
        XCTAssertTrue(old.graph_facts.isEmpty)
        let current = try JSONDecoder().decode(PersonModelReply.self, from: Data(#"{"version":3,"domains":[],"graph_facts":[{"fact_id":"fact","subject_id":"subject","kind":"PERSON","content":"朋友","evidence_ids":["source"],"model_version":"real-version","valid_from":"2026-10-14T00:00:00Z"}]}"#.utf8))
        XCTAssertEqual(current.graph_facts.first?.model_version, "real-version")
        XCTAssertEqual(current.graph_facts.first?.valid_from, "2026-10-14T00:00:00Z")
    }
    func testEachExtractedEventRemainsSeparateEvenInSameRecording() {
        let rows = MemoryGardenProjection.entries(memories: [memory("m2"),memory("m1"),memory("m3",episode:"other")],
            episodes:[episode(),episode("other")],overview:nil)
        XCTAssertEqual(rows.map(\.id),["event:m1","event:m2","event:m3"])
        XCTAssertEqual(rows.map { $0.memories.map(\.id) },[["m1"],["m2"],["m3"]])
        XCTAssertTrue(rows.allSatisfy { $0.label == "AI 整理的事件" && $0.section == .stories })
    }
    func testApprovedStoryUsesExactEvidenceAndLeavesUnrelatedMemoriesVisible() throws {
        let rows = MemoryGardenProjection.entries(memories:[memory("m1"),memory("event-shared",evidenceIDs:["e_m1"]),memory("m2")],episodes:[episode()],
            overview:overview([try record()],sources:[evidence()]))
        XCTAssertEqual(rows.count,2)
        XCTAssertEqual(Set(rows.first(where:{$0.id=="record:story"})?.memories.map(\.id) ?? []),["m1","event-shared"])
        XCTAssertEqual(rows.first(where:{$0.id=="record:story"})?.label,"本人核对的故事")
        XCTAssertEqual(rows.first(where:{$0.id=="event:m2"})?.memories.map(\.id),["m2"])
    }
    func testOwnerPendingStoryAppearsAutomaticallyWithoutConfirmationLabel() throws {
        let rows = MemoryGardenProjection.entries(memories:[memory("m1")],episodes:[episode()],
            overview:overview([try record(status:"pending")],sources:[evidence()]))
        XCTAssertEqual(rows.map(\.id),["record:story"])
        XCTAssertEqual(rows.first?.label,"整理的故事")
        XCTAssertFalse(rows.first?.label.contains("核对") ?? true)
        XCTAssertEqual(rows.first?.memories.map(\.id),["m1"])
    }
    func testReaderDoesNotSeePendingStory() throws {
        let rows = MemoryGardenProjection.entries(memories:[],episodes:[episode()],
            overview:overview([try record(status:"pending")],sources:[evidence()],role:"reader"))
        XCTAssertTrue(rows.isEmpty)
    }
    func testStaleHistoricalAndMissingSourcesNeverBecomeFlowers() throws {
        for row in [try record(valid:false),try record(historical:true),try record(status:"pending",valid:false),
                    try record(status:"pending",historical:true)] {
            let entries=MemoryGardenProjection.entries(memories:[],episodes:[episode()],overview:overview([row],sources:[evidence()]))
            XCTAssertTrue(entries.isEmpty)
        }
        XCTAssertTrue(MemoryGardenProjection.entries(memories:[],episodes:[episode()],overview:overview([try record()],sources:[])).isEmpty)
        XCTAssertTrue(MemoryGardenProjection.entries(memories:[],episodes:[episode()],
            overview:overview([try record(evidenceIDs:[],sources:[])],sources:[evidence()])).isEmpty)
    }
    func testEveryStorySourceMustBePresentAndItsRecordingReady() throws {
        let first = evidence(), second = evidence("e_m2",episode:"other")
        let story = try record(status:"pending",evidenceIDs:[first.id,second.id],sources:[first,second])
        let availableEpisodes = [episode(),episode("other")]
        let rows = MemoryGardenProjection.entries(memories:[],episodes:availableEpisodes,
            overview:overview([story],sources:[first,second]))
        XCTAssertEqual(rows.map(\.id),["record:story"])
        XCTAssertEqual(rows.first?.evidence.map(\.id),[first.id,second.id])
        XCTAssertTrue(MemoryGardenProjection.entries(memories:[],episodes:availableEpisodes,
            overview:overview([story],sources:[first])).isEmpty)
        XCTAssertTrue(MemoryGardenProjection.entries(memories:[],episodes:[episode(),episode("other",status:"processing")],
            overview:overview([story],sources:[first,second])).isEmpty)
        let missingEmbeddedEvidence = try record(evidenceIDs:[first.id,second.id],sources:[first])
        XCTAssertTrue(MemoryGardenProjection.entries(memories:[],episodes:availableEpisodes,
            overview:overview([missingEmbeddedEvidence],sources:[first,second])).isEmpty)
    }
    func testRemovingSourceEpisodeHidesApprovedStoryAndMemory() throws {
        XCTAssertTrue(MemoryGardenProjection.entries(memories:[memory("m1")],episodes:[],
            overview:overview([try record()],sources:[evidence()])).isEmpty)
    }
    func testNonEventFragmentsAndNonStoryRecordsDoNotBecomeFlowers() throws {
        let fragments = [memory("p1",kind:"PERSON",source:"THIRD_PARTY"),memory("p2",kind:"PERSON"),
            memory("observation",kind:"OBSERVATION"),memory("note",kind:"NOTE"),memory("preference",kind:"PREFERENCE")]
        let records = try ["person","observation","note","preference"].map { try record($0,kind:$0) }
        XCTAssertTrue(MemoryGardenProjection.entries(memories:fragments,episodes:[episode()],
            overview:overview(records,sources:[evidence()])).isEmpty)
    }
    func testAutoEventLinksOnlyActiveMemoriesSharingActualEvidence() throws {
        let rows = MemoryGardenProjection.entries(memories:[memory("m1"),
            memory("related",kind:"PREFERENCE",evidenceIDs:["e_m1"]),memory("same-recording",kind:"PERSON"),
            memory("not-ready",episode:"processing",kind:"PERSON",evidenceIDs:["e_m1"])],
            episodes:[episode(),episode("processing",status:"processing")],overview:nil)
        let entry = try XCTUnwrap(rows.first)
        XCTAssertEqual(rows.map(\.id),["event:m1"])
        XCTAssertEqual(entry.memories.map(\.id),["m1","related"])
        XCTAssertEqual(entry.title,memory("m1").content)
    }
    func testEventsNeedReadyRecordingAndActualEvidence() {
        XCTAssertTrue(MemoryGardenProjection.entries(memories:[memory("m1")],episodes:[episode(status:"processing")],overview:nil).isEmpty)
        XCTAssertTrue(MemoryGardenProjection.entries(memories:[memory("m1",evidenceIDs:[])],episodes:[episode()],overview:nil).isEmpty)
    }
    func testInvalidStoriesDoNotSuppressCurrentEventFallback() throws {
        for story in [try record(valid:false),try record(historical:true),try record(status:"pending",valid:false),
                      try record(status:"pending",historical:true),try record(sources:[])] {
            let rows = MemoryGardenProjection.entries(memories:[memory("m1")],episodes:[episode()],
                overview:overview([story],sources:[evidence()]))
            XCTAssertEqual(rows.map(\.id),["event:m1"])
        }
    }
    func testRejectedStoryCannotReappearAsEventEvenAfterEmbeddedSourcesWereCleared() throws {
        for rejected in [try record(status:"rejected"),
                         try record(status:"rejected",valid:false,historical:true,sources:[])] {
            let rows = MemoryGardenProjection.entries(memories:[memory("m1"),memory("m2")],episodes:[episode()],
                overview:overview([rejected],sources:[]))
            XCTAssertEqual(rows.map(\.id),["event:m2"])
        }
    }
    func testRejectedNonStoryRecordDoesNotRemoveEvent() throws {
        let rows = MemoryGardenProjection.entries(memories:[memory("m1")],episodes:[episode()],
            overview:overview([try record(kind:"person",status:"rejected")],sources:[evidence()]))
        XCTAssertEqual(rows.map(\.id),["event:m1"])
    }
    func testVisibilityStoresOnlyIDsAndIsolatesServerActorAndSubject() throws {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let store=GardenVisibilityStore(root:root)
        try store.save(["episode:ep"],owner:RecordingOwner(pairing()))
        XCTAssertEqual(try store.load(RecordingOwner(pairing(token:"replacement-token"))),["episode:ep"])
        for other in [pairing(actor:"other"),pairing(subject:"other"),pairing(server:"https://other.invalid")] {
            XCTAssertTrue(try store.load(RecordingOwner(other)).isEmpty)
        }
        let files=try FileManager.default.contentsOfDirectory(at:root,includingPropertiesForKeys:nil)
        let data=try Data(contentsOf:files[0]);let text=String(decoding:data,as:UTF8.self)
        XCTAssertEqual(try JSONDecoder().decode([String].self,from:data),["episode:ep"])
        XCTAssertFalse(text.contains("fixture"));XCTAssertFalse(text.contains("真实原文"))
    }
    func testHideAndRestoreDoNotChangeUnderlyingEntry() {
        let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:root) }
        let visibility=GardenVisibility(root:root);let owner=pairing()
        visibility.configure(owner);visibility.setHidden("episode:ep",hidden:true,pairing:owner)
        XCTAssertTrue(visibility.hidden.contains("episode:ep"))
        visibility.configure(pairing(actor:"other"));XCTAssertTrue(visibility.hidden.isEmpty)
        visibility.configure(owner);XCTAssertTrue(visibility.hidden.contains("episode:ep"))
        visibility.setHidden("episode:ep",hidden:false,pairing:owner);XCTAssertTrue(visibility.hidden.isEmpty)
    }
    func testLateResponseAfterLogoutCannotRestorePreviousPersonsRecords() async throws {
        var pending: CheckedContinuation<ReviewOverview,Error>?
        let workspace=MemoryGardenWorkspace(loader:{ _ in try await withCheckedThrowingContinuation { pending=$0 } })
        let load=Task { await workspace.reload(pairing()) }
        while pending==nil { await Task.yield() }
        await workspace.reload(nil)
        pending?.resume(returning:overview([try record()],sources:[evidence()]))
        await load.value
        XCTAssertNil(workspace.overview);XCTAssertNil(workspace.scope);XCTAssertFalse(workspace.isLoading)
    }
    func testForeignSubjectAndReaderResponsesAreRejected() async {
        for reply in [overview(subject:"other"),overview(role:"reader")] {
            let workspace=MemoryGardenWorkspace(loader:{ _ in reply });await workspace.reload(pairing())
            XCTAssertTrue(workspace.denied);XCTAssertNil(workspace.overview)
        }
    }
    func testAuthFailureClosesGardenAndOldServiceHasExplicitFallback() async {
        let owner = pairing(), revision = UUID()
        let denied=MemoryGardenWorkspace(loader:{ _ in throw APIError.server(403,"fixture") })
        await denied.reload(owner,revision:revision,memoryIDs:["m1"],modelVersion:2)
        XCTAssertTrue(denied.denied);XCTAssertNil(denied.overview)
        XCTAssertFalse(denied.canDisplayEntries(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:2))
        let old=MemoryGardenWorkspace(loader:{ _ in throw APIError.server(404,"fixture") })
        await old.reload(owner,revision:revision,memoryIDs:["m1"],modelVersion:2)
        XCTAssertFalse(old.denied);XCTAssertNotNil(old.notice);XCTAssertNil(old.overview)
        XCTAssertTrue(old.canDisplayEntries(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:2))
        XCTAssertFalse(old.canDisplayEntries(for:owner,revision:UUID(),memoryIDs:["m1"],modelVersion:2))
    }
    func testPendingOverviewAndTemporaryFailureDoNotResurrectEventFallback() async {
        var pending: CheckedContinuation<ReviewOverview,Error>?
        let workspace = MemoryGardenWorkspace(loader:{ _ in try await withCheckedThrowingContinuation { pending=$0 } })
        let owner = pairing(), revision = UUID()
        XCTAssertFalse(workspace.canDisplayEntries(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:2))
        let load = Task { await workspace.reload(owner,revision:revision,memoryIDs:["m1"],modelVersion:2) }
        while pending == nil { await Task.yield() }
        XCTAssertTrue(workspace.isLoading)
        XCTAssertFalse(workspace.canDisplayEntries(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:2))
        pending?.resume(throwing:APIError.server(500,"fixture"))
        await load.value
        XCTAssertFalse(workspace.isLoading)
        XCTAssertFalse(workspace.denied)
        XCTAssertNotNil(workspace.notice)
        XCTAssertFalse(workspace.canDisplayEntries(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:2))
    }
    func testModelRevisionAndChangedMemorySetInvalidateCachedStoriesImmediately() async {
        let workspace=MemoryGardenWorkspace(loader:{ _ in self.overview() })
        let revision=UUID(), owner=pairing()
        await workspace.reload(owner,revision:revision,memoryIDs:["m1"],modelVersion:2)
        XCTAssertNotNil(workspace.currentOverview(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:2))
        XCTAssertTrue(workspace.canDisplayEntries(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:2))
        XCTAssertNil(workspace.currentOverview(for:owner,revision:UUID(),memoryIDs:["m1"],modelVersion:2))
        XCTAssertNil(workspace.currentOverview(for:owner,revision:revision,memoryIDs:[],modelVersion:2))
        XCTAssertNil(workspace.currentOverview(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:3))
        XCTAssertNil(workspace.currentOverview(for:pairing(actor:"other"),revision:revision,memoryIDs:["m1"],modelVersion:2))
        XCTAssertFalse(workspace.canDisplayEntries(for:owner,revision:UUID(),memoryIDs:["m1"],modelVersion:2))
        XCTAssertFalse(workspace.canDisplayEntries(for:owner,revision:revision,memoryIDs:[],modelVersion:2))
        XCTAssertFalse(workspace.canDisplayEntries(for:owner,revision:revision,memoryIDs:["m1"],modelVersion:3))
        XCTAssertFalse(workspace.canDisplayEntries(for:pairing(actor:"other"),revision:revision,memoryIDs:["m1"],modelVersion:2))
    }
    func testSearchIncludesEvidenceLinkedFragmentsWithoutUnrelatedSameRecordingMemories() throws {
        let entry=try XCTUnwrap(MemoryGardenProjection.entries(memories:[memory("m1"),
            memory("linked-fragment",kind:"NOTE",evidenceIDs:["e_m1"]),memory("unrelated-fragment",kind:"NOTE")],
            episodes:[episode()],overview:nil).first)
        XCTAssertTrue(entry.matches("linked-fragment"));XCTAssertTrue(entry.matches("  linked-fragment  "))
        XCTAssertFalse(entry.matches("unrelated-fragment"))
        XCTAssertTrue(entry.matches("   "));XCTAssertFalse(entry.matches("从未提过的人"))
    }
    func testRecordingDateUsesDeviceTimeZoneWithoutInventingEventDate() throws {
        let zone=try XCTUnwrap(TimeZone(identifier:"Asia/Singapore"))
        XCTAssertEqual(MemoryGardenProjection.recordingDate("2026-10-13T18:00:00.000Z",timeZone:zone),"录入于 2026-10-14")
        XCTAssertEqual(MemoryGardenProjection.recordingDate("unknown",timeZone:zone),"录入日期未知")
    }
    func testFlowerFieldGroupsUngroupedMemoriesByRecordingRatherThanInventingStories() {
        let rows = GardenHomeProjection.entries(memories: [memory("event-a"), memory("event-b"), memory("preference", kind: "PREFERENCE"),
            memory("other", episode: "other")], episodes: [episode(), episode("other")], overview: nil)
        XCTAssertEqual(rows.count, 2)
        XCTAssertEqual(rows.first(where: { $0.id == "episode:ep" })?.memories.map(\.id), ["event-a", "event-b", "preference"])
        XCTAssertTrue(rows.allSatisfy { $0.label.contains("尚未归组") })
    }
    func testStoryNeverDisplaysMemorySummaryWhoseOtherEvidenceIsOutsideStory() throws {
        let story = try record(facets: ["EXPERIENCE"])
        let rows = MemoryGardenProjection.entries(memories: [memory("whole", evidenceIDs: ["e_m1", "e_private"]),
            memory("m1")], episodes: [episode()], overview: overview([story], sources: [evidence()]))
        XCTAssertEqual(rows.first(where: { $0.id == "record:story" })?.memories.map(\.id), ["m1"])
    }
    func testSameEvidenceIDWithChangedContentCannotRevealNarrativeTitle() throws {
        let row = try record(facets: ["EXPERIENCE"])
        let replaced = ReviewEvidence(evidence_id: "e_m1", episode_id: "ep", excerpt: "修改后的原话", source_type: "SUBJECT", temporal_context: nil)
        for source in [replaced, evidence(episode: "other")] {
            let current = overview([row], sources: [source])
            XCTAssertFalse(GardenNarrativeProjection.hasCurrentEvidence(row, overview: current, episodes: [episode(), episode("other")]))
            XCTAssertTrue(GardenNarrativeProjection.records(current, episodes: [episode(), episode("other")]).isEmpty)
            XCTAssertTrue(MemoryGardenProjection.entries(memories: [], episodes: [episode(), episode("other")], overview: current).isEmpty)
        }
    }
    func testPersonViewsAndEightFacetsFilterActualConfirmedRecords() throws {
        let rows = [try record("life", facets: ["EXPERIENCE", "FEELINGS"]),
                    try record("friend", kind: "person", facets: ["RELATIONSHIPS"], aliases: ["老王"]),
                    try record("choice", kind: "observation", facets: ["VALUES", "WISHES"]),
                    try record("words", kind: "style", facets: ["EXPRESSION"]),
                    try record("pending", status: "pending", facets: ["VALUES"])]
        let current = overview(rows, sources: [evidence()])
        XCTAssertEqual(GardenFacet.allCases.count, 8)
        XCTAssertEqual(GardenPersonView.allCases.count, 4)
        XCTAssertEqual(GardenNarrativeProjection.records(current, episodes: [episode()], view: .people).map(\.id), ["friend"])
        XCTAssertEqual(GardenNarrativeProjection.records(current, episodes: [episode()], view: .choices).map(\.id), ["choice"])
        XCTAssertEqual(GardenNarrativeProjection.records(current, episodes: [episode()], view: .expression).map(\.id), ["words"])
        XCTAssertEqual(GardenNarrativeProjection.records(current, episodes: [episode()], facet: .feelings).map(\.id), ["life"])
        XCTAssertEqual(GardenNarrativeProjection.records(current, episodes: [episode()], query: " 老王 ").map(\.id), ["friend"])
        XCTAssertEqual(GardenNarrativeProjection.records(current, episodes: [episode()], pending: true).map(\.id), ["pending"])
        XCTAssertTrue(GardenNarrativeProjection.records(overview(rows, sources: [evidence()], role: "reader"), episodes: [episode()]).isEmpty)
    }
    func testOverviewOlderPayloadAndCurrentUnderstandingExtrasDecode() throws {
        let old = try JSONDecoder().decode(ReviewOverview.self, from: Data(#"{"subject_id":"subject","role":"owner","records":[],"source_evidence":[],"style":{"enabled":false,"revision":0}}"#.utf8))
        XCTAssertTrue(old.understandings.isEmpty); XCTAssertNil(old.next_question)
        let current = try JSONDecoder().decode(ReviewOverview.self, from: Data(#"{"subject_id":"subject","role":"owner","records":[],"source_evidence":[{"evidence_id":"e_m1","episode_id":"ep","excerpt":"真实原文","source_type":"SUBJECT"}],"style":{"enabled":false,"revision":0},"understandings":[{"candidate_id":"candidate","statement":"本人确认的理解","context":"一起做事时","status":"confirmed","evidence_ids":["e_m1"],"counter_evidence_ids":[],"evidence":[{"evidence_id":"e_m1","episode_id":"ep","excerpt":"真实原文","source_type":"SUBJECT"}],"counter_evidence":[],"model_version":"model-v1"}],"next_question":{"id":"next","text":"愿意再讲一点吗？","reason":"资料中的空白","evidence_ids":["e_m1"]}}"#.utf8))
        let understanding = try XCTUnwrap(current.understandings.first)
        XCTAssertTrue(understanding.isCurrent(sources: current.source_evidence, episodes: [episode()]))
        XCTAssertFalse(understanding.isCurrent(sources: [], episodes: [episode()]))
        XCTAssertFalse(understanding.isCurrent(sources: current.source_evidence, episodes: [episode(status: "processing")]))
        XCTAssertEqual(current.next_question?.id, "next")
    }
    func testHistoricalSnapshotsHideWhenAnyRequiredSourceIsMissing() throws {
        let history = try JSONDecoder().decode(GardenHistoryReply.self, from: Data(#"{"items":[{"revision":1,"action":"create","created_at":"2026-10-16T00:00:00Z","record":{"title":"旧内容","text":"两段来源","evidence_ids":["a","b"]}},{"revision":2,"action":"edit","created_at":"2026-10-16T01:00:00Z","record":{"title":"新内容","text":"单段来源","evidence_ids":["a"]}}]}"#.utf8))
        XCTAssertEqual(history.currentItems(evidenceIDs: ["a"]).map(\.revision), [2])
        XCTAssertTrue(history.currentItems(evidenceIDs: []).isEmpty)
    }
    func testUngroupedMemoryAndOpenedPetalRequireEveryCurrentSourceTuple() {
        let row = memory("m1")
        XCTAssertTrue(GardenMemorySourceProjection.isCurrent(row, sources: [evidence()], episodes: [episode()]))
        for sources in [[], [evidence(episode: "other")],
                        [ReviewEvidence(evidence_id: "e_m1", episode_id: "ep", excerpt: "别的文字", source_type: "SUBJECT", temporal_context: nil)]] {
            XCTAssertFalse(GardenMemorySourceProjection.isCurrent(row, sources: sources, episodes: [episode(), episode("other")]))
            XCTAssertTrue(GardenHomeProjection.entries(memories: [row], episodes: [episode(), episode("other")], overview: overview(sources: sources)).isEmpty)
        }
    }
}
