package me.remember.app.hardware

object HardwareTransportFactory {
    fun create(events: HardwareEvents): HardwareTransport = error("此安装包未包含录音豆 SDK，请安装设备联调版。")
}
