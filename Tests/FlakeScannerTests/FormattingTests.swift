import XCTest

final class UnitsTests: XCTestCase {
    func testBytesNamesTheUnit() {
        let text = Units.bytes(2_000_000)
        XCTAssertTrue(text.contains("MB"), text)
        XCTAssertTrue(text.hasPrefix("2"), text)
    }

    func testBytesHandlesLargeCounts() {
        let text = Units.bytes(5_000_000_000)
        XCTAssertTrue(text.contains("GB"), text)
    }
}

final class NumTests: XCTestCase {
    func testFixedPadsToTheRequestedDecimals() {
        XCTAssertEqual(Num.fixed(12.5, 2), "12.50")
        XCTAssertEqual(Num.fixed(3, 0), "3")
        XCTAssertEqual(Num.fixed(0, 3), "0.000")
        XCTAssertEqual(Num.fixed(7, 1), "7.0")
    }

    func testFixedRounds() {
        XCTAssertEqual(Num.fixed(0.126, 2), "0.13")
        XCTAssertEqual(Num.fixed(0.124, 2), "0.12")
        XCTAssertEqual(Num.fixed(2.6, 0), "3")
        XCTAssertEqual(Num.fixed(-0.006, 2), "-0.01")
        XCTAssertEqual(Num.fixed(-1.46, 1), "-1.5")
    }

    func testFixedKeepsTheSignOfNegativeValues() {
        XCTAssertEqual(Num.fixed(-1.5, 1), "-1.5")
        XCTAssertEqual(Num.fixed(-90, 2), "-90.00")
    }

    func testFixedNegativeZeroHasNoSign() {
        let negativeZero = -0.0
        XCTAssertEqual(negativeZero.sign, .minus)
        XCTAssertEqual(Num.fixed(negativeZero, 2), "0.00")
        XCTAssertEqual(Num.fixed(negativeZero, 0), "0")
    }

    func testFixedTinyNegativeValueThatRoundsToZeroHasNoSign() {
        XCTAssertEqual(Num.fixed(-0.001, 2), "0.00")
        XCTAssertEqual(Num.fixed(-0.4, 0), "0")
    }

    func testFixedNonFiniteValuesAreEmpty() {
        XCTAssertEqual(Num.fixed(Double.nan, 2), "")
        XCTAssertEqual(Num.fixed(Double.infinity, 2), "")
        XCTAssertEqual(Num.fixed(-Double.infinity, 2), "")
    }

    func testFixedNegativeDecimalsCountAsZero() {
        XCTAssertEqual(Num.fixed(1.6, -1), "2")
    }

    func testFixedUsesAPointAndNoGrouping() {
        XCTAssertEqual(Num.fixed(1234567.891, 1), "1234567.9")
    }
}

final class CSVTests: XCTestCase {
    func testEscapeLeavesPlainFieldsAlone() {
        XCTAssertEqual(CSV.escape("wall 1"), "wall 1")
        XCTAssertEqual(CSV.escape(""), "")
        XCTAssertEqual(CSV.escape("12.5"), "12.5")
    }

    func testEscapeQuotesFieldsWithCommas() {
        XCTAssertEqual(CSV.escape("a,b"), "\"a,b\"")
    }

    func testEscapeDoublesEmbeddedQuotes() {
        XCTAssertEqual(CSV.escape("5' 3.0\""), "\"5' 3.0\"\"\"")
        XCTAssertEqual(CSV.escape("say \"hi\""), "\"say \"\"hi\"\"\"")
    }

    func testEscapeQuotesFieldsWithNewlines() {
        XCTAssertEqual(CSV.escape("line1\nline2"), "\"line1\nline2\"")
    }

    func testMakeJoinsRowsAndEndsWithNewline() {
        XCTAssertEqual(CSV.make([["a", "b"], ["1", "2"]]), "a,b\n1,2\n")
    }

    func testMakeEscapesEachField() {
        XCTAssertEqual(CSV.make([["x,y", "z"]]), "\"x,y\",z\n")
    }

    func testMakeWithNoRowsIsJustANewline() {
        XCTAssertEqual(CSV.make([]), "\n")
    }

    func testMakeWithNumFixedCells() {
        XCTAssertEqual(CSV.make([["angle_deg", "n"], [Num.fixed(-0.0, 2), "3"]]), "angle_deg,n\n0.00,3\n")
    }
}
