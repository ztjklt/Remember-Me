import SwiftUI

struct PortraitFacetItem: Identifiable {
    let memory: MemoryRecord
    let category: String
    let label: String
    let quote: String
    var id: String { memory.id + ":" + category + ":" + label + ":" + quote }
}

extension AppModel {
    var portraitFacets: [PortraitFacetItem] {
        memories.flatMap { memory in
            (memoryMetadata[memory.id]?.facets ?? []).compactMap { facet in
                let sources = memory.evidence.filter { facet.evidence_ids.contains($0.id) }
                guard !sources.isEmpty, Set(facet.evidence_ids).isSubset(of: Set(memory.evidence.map(\.id))),
                      sources.contains(where: { ($0.excerpt ?? "").contains(facet.quote) }),
                      sources.allSatisfy({ ["SUBJECT", "CALIBRATION"].contains($0.source_type) }) else { return nil }
                return PortraitFacetItem(memory: memory, category: facet.category, label: facet.label, quote: facet.quote)
            }
        }
    }
    func facets(_ category: String) -> [PortraitFacetItem] {
        portraitFacets.filter { $0.category == category }.sorted { $0.memory.recorded_at < $1.memory.recorded_at }
    }
    func associatedMemories(_ trait: TraitRecord) -> [MemoryRecord] {
        memories.filter { memory in
            (trait.memory_item_ids ?? []).contains(memory.id) || memory.evidence.contains {
                (trait.evidence_ids + trait.counter_evidence_ids).contains($0.id)
            }
        }
    }
    var expressionEvidence: [String] {
        var seen = Set<String>()
        return memories.flatMap(\.evidence).compactMap { evidence in
            guard ["SUBJECT", "CALIBRATION"].contains(evidence.source_type), seen.insert(evidence.id).inserted,
                  let excerpt = evidence.excerpt, !excerpt.isEmpty else { return nil }
            return excerpt
        }
    }
}

struct FacetEvidenceRow: View {
    let item: PortraitFacetItem
    var body: some View {
        NavigationLink { MemoryDetailView(memory: item.memory) } label: {
            VStack(alignment: .leading, spacing: 8) {
                Text(item.label).foregroundStyle(Ink.text)
                Text("“\(item.quote)”").font(.subheadline).foregroundStyle(Ink.muted)
                Text("\(item.memory.recorded_at.prefix(10)) · AI 理解 · 查看原文并纠正")
                    .font(.caption).foregroundStyle(Ink.coral)
            }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
        }.buttonStyle(.plain)
    }
}

struct AudioObservationRows: View {
    @EnvironmentObject private var model: AppModel
    private var recordings: [MemoryRecord] {
        var seen = Set<String>()
        return model.memories.filter { memory in
            model.memoryMetadata[memory.id]?.audio_observation?.status == "available" && seen.insert(memory.episode_id).inserted
        }
    }
    var body: some View {
        ForEach(recordings) { memory in
            if let audio = model.memoryMetadata[memory.id]?.audio_observation {
                NavigationLink { MemoryDetailView(memory: memory) } label: {
                    VStack(alignment: .leading, spacing: 7) {
                        Label("原音观测 · \(memory.recorded_at.prefix(10))", systemImage: "waveform")
                        if let loudness = audio.rms_dbfs { Text("平均响度 \(loudness, specifier: "%.1f") dBFS") }
                        if let silence = audio.silence_fraction { Text("低响度片段占比 \(silence * 100, specifier: "%.0f")%") }
                        if let seconds = audio.analyzed_seconds { Text("分析录音前 \(seconds, specifier: "%.1f") 秒") }
                        Text("录音信号观测，不能据此判断心理健康或周围声源。")
                            .font(.caption).foregroundStyle(Ink.muted)
                    }.font(.subheadline).foregroundStyle(Ink.text).frame(maxWidth: .infinity, alignment: .leading)
                        .padding(16).background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                }.buttonStyle(.plain)
            }
        }
    }
}

struct PortraitFlowView: View {
    @EnvironmentObject private var model: AppModel
    let kind: String
    private var title: String {
        switch kind { case "event": "事件时间线"; case "mood": "情绪与回忆视角"; case "decision": "决策与价值"; default: "表达记录" }
    }
    private var domains: [DomainRecord] {
        model.domains.filter { kind == "decision" ? ["VALUES_BELIEFS", "DECISION_PATTERNS"].contains($0.domain) : $0.domain == "EXPRESSION" }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("来自当前有效记忆；每个节点都可以回到原文。时间表示录音时间，有明确事件日期时单独标注。")
                    .font(.subheadline).foregroundStyle(Ink.muted)
                if let error = model.portraitRefreshError { Text(error).foregroundStyle(Ink.muted) }
                if kind == "event" {
                    ForEach(model.memories.filter { $0.memory_type == "EVENT" }.sorted { $0.recorded_at < $1.recorded_at }) { memory in
                        NavigationLink { MemoryDetailView(memory: memory) } label: {
                            HStack(alignment: .top, spacing: 12) {
                                Image(systemName: "circle.fill").font(.caption).foregroundStyle(Ink.coral)
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(String(memory.recorded_at.prefix(10))).font(.caption).foregroundStyle(Ink.muted)
                                    Text(memory.content).foregroundStyle(Ink.text)
                                    Text("\(memory.evidence.count) 条原文依据").font(.caption).foregroundStyle(Ink.coral)
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                                .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                        }.buttonStyle(.plain)
                    }
                } else if kind == "mood" {
                    ForEach(model.portraitFacets.filter { ["mood", "psychology", "filter"].contains($0.category) }
                        .sorted { $0.memory.recorded_at < $1.memory.recorded_at }) { item in FacetEvidenceRow(item: item) }
                    ForEach(model.memories.filter { $0.memory_type == "EMOTION" && model.memoryMetadata[$0.id]?.facets?.isEmpty != false }) { memory in
                        NavigationLink(memory.content) { MemoryDetailView(memory: memory) }
                    }
                } else {
                    if kind == "expression", !model.expressionEvidence.isEmpty {
                        let corpus = model.expressionEvidence.joined(separator: "。")
                        let sentences = corpus.split(whereSeparator: { "。！？!?\n".contains($0) })
                        VStack(alignment: .leading, spacing: 8) {
                            Text("当前有效原文片段的表达统计").font(.headline)
                            Text("\(model.expressionEvidence.count) 个片段 · 平均句长 \(sentences.isEmpty ? 0 : sentences.reduce(0) { $0 + $1.count } / sentences.count) 字")
                            ForEach(["因为", "但是", "所以", "先", "再"].filter { corpus.contains($0) }, id: \.self) { word in
                                Text("「\(word)」出现 \(corpus.components(separatedBy: word).count - 1) 次")
                            }
                            Text("统计来自可查看的证据片段，片段数量会随删除或纠正更新。")
                                .font(.caption).foregroundStyle(Ink.muted)
                        }.font(.subheadline).frame(maxWidth: .infinity, alignment: .leading).padding(16)
                            .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                    }
                    ForEach(domains) { domain in
                        ForEach(domain.traits) { trait in
                            NavigationLink { TraitEvidenceView(trait: trait) } label: {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(trait.statement).foregroundStyle(Ink.text)
                                    if let context = trait.context { Text(context).font(.subheadline).foregroundStyle(Ink.muted) }
                                    Text("\(trait.status == "superseded" ? "过去的理解" : trait.status == "unresolved" ? "等待澄清" : "当前理解") · \(trait.evidence_ids.count) 条依据 · \(trait.counter_evidence_ids.count) 条不同说法")
                                        .font(.caption).foregroundStyle(Ink.coral)
                                    Text(model.associatedMemories(trait).map { String($0.recorded_at.prefix(10)) }.sorted().joined(separator: " → "))
                                        .font(.caption).foregroundStyle(Ink.muted)
                                }.frame(maxWidth: .infinity, alignment: .leading).padding(16)
                                    .background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
                            }.buttonStyle(.plain)
                        }
                    }
                    if kind == "expression" { ForEach(model.facets("expression")) { item in FacetEvidenceRow(item: item) } }
                }
                if model.memories.isEmpty { ContentUnavailableView("还没有有效记忆", systemImage: "point.3.connected.trianglepath.dotted") }
            }.padding(20)
        }.background(Ink.paper.ignoresSafeArea()).navigationTitle(title).navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refresh() }
    }
}

struct EvidenceConnectionGraph: View {
    @EnvironmentObject private var model: AppModel
    private var memories: [MemoryRecord] { Array(model.memories.prefix(6)) }
    private var traits: [TraitRecord] {
        Array(model.domains.flatMap(\.traits).filter { trait in
            trait.status != "superseded" && memories.contains { memory in memory.evidence.contains { trait.evidence_ids.contains($0.id) } }
        }.prefix(8))
    }
    var body: some View {
        if !memories.isEmpty {
            GeometryReader { geometry in
                let labels = memories.map { $0.content } + traits.map { $0.statement }
                let size = geometry.size
                let count = labels.count
                let points = (0..<count).map { index in
                    let angle = Double(index) * 2 * Double.pi / Double(max(1, count)) - Double.pi / 2
                    return CGPoint(x: size.width / 2 + cos(angle) * max(0, size.width / 2 - 50),
                                   y: size.height / 2 + sin(angle) * max(0, size.height / 2 - 40))
                }
                Canvas { context, _ in
                    for (mi, memory) in memories.enumerated() {
                        for (ti, trait) in traits.enumerated() {
                            let weight = Set(memory.evidence.map(\.id)).intersection(trait.evidence_ids).count
                            if weight > 0 {
                                var path = Path(); path.move(to: points[mi]); path.addLine(to: points[memories.count + ti])
                                context.stroke(path, with: .color(Ink.coral.opacity(0.4)), lineWidth: CGFloat(min(weight, 4)))
                            }
                        }
                    }
                    for (index, text) in labels.enumerated() {
                        let point = points[index]
                        context.fill(Path(ellipseIn: CGRect(x: point.x - 7, y: point.y - 7, width: 14, height: 14)),
                                     with: .color(index < memories.count ? Ink.coral : Ink.muted))
                        context.draw(Text(String(text.prefix(8))).font(.caption2).foregroundStyle(Ink.text),
                                     at: CGPoint(x: point.x, y: point.y + 18))
                    }
                }.accessibilityElement(children: .ignore)
                    .accessibilityLabel("\(memories.count) 条记忆与 \(traits.count) 项理解的证据关系；下方列表可查看每个节点。")
            }.frame(height: 290).background(Ink.cream, in: RoundedRectangle(cornerRadius: 14))
            Text("连线表示共同原文证据，粗细表示证据条数；只展示最近六条记忆及其理解。")
                .font(.caption).foregroundStyle(Ink.muted)
            ForEach(traits) { trait in
                NavigationLink { TraitEvidenceView(trait: trait) } label: {
                    Label("\(trait.statement) · \(trait.evidence_ids.count) 条依据", systemImage: "link")
                }
            }
            if !model.graphFacts.isEmpty {
                DisclosureGroup("人物、事件与关系事实") {
                    ForEach(model.graphFacts) { fact in
                        if let memory = model.memories.first(where: { !Set($0.evidence.map(\.id)).intersection(fact.evidence_ids).isEmpty }) {
                            NavigationLink { MemoryDetailView(memory: memory) } label: {
                                VStack(alignment: .leading, spacing: 5) {
                                    Text(fact.content).foregroundStyle(Ink.text)
                                    Text("\(["PERSON": "人物", "EVENT": "经历", "RELATIONSHIP": "关系"][fact.kind] ?? "事实") · \(fact.evidence_ids.count) 条依据")
                                        .font(.caption).foregroundStyle(Ink.coral)
                                }.padding(.vertical, 8)
                            }
                        }
                    }
                }
            }
        } else {
            ContentUnavailableView("关系图等待你的真实记录", systemImage: "point.3.connected.trianglepath.dotted")
        }
    }
}
