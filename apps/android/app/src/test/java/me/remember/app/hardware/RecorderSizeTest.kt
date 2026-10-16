package me.remember.app.hardware

import org.junit.Assert.*
import org.junit.Test

class RecorderSizeTest {
    @Test fun displayUsesMeasuredDecimalMegabytesWithoutInventingUnknownValues() {
        assertEquals("0.280 MB", recorderMegabytes(279710))
        assertEquals("0.076 MB", recorderMegabytes(76194))
        assertEquals("62541.529 MB", recorderKilobytesAsMb(61075712))
        assertEquals("未知", recorderMegabytes(null))
        assertEquals("未知", recorderMegabytes(-1))
        assertEquals("<0.001 MB", recorderMegabytes(160))
        assertEquals("0.000 MB", recorderMegabytes(0))
    }
}
