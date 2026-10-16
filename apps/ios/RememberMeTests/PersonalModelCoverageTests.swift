import XCTest
@testable import RememberMe
final class PersonalModelCoverageTests:XCTestCase {
    func testUnknownAndOutOfRangeServerCoverageCannotShowCompletePerson() throws {
        func decode(_ value:Int) throws -> ModelCoverage {
            let data=try JSONSerialization.data(withJSONObject:["subject_id":"s","model_version":0,"metric_version":"seven-domains-five-sources-v1","percentage":value,"cap_percentage":95,"covered_units":0,"target_units":35,"domains":[],"explanation":"资料覆盖"])
            return try JSONDecoder().decode(ModelCoverage.self,from:data)
        }
        XCTAssertEqual(try decode(0).displayedPercentage,0)
        XCTAssertEqual(try decode(100).displayedPercentage,95)
        XCTAssertEqual(try decode(-3).displayedPercentage,0)
    }
}
