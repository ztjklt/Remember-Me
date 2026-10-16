package me.remember.app.hardware;

import com.oceanwing.soundcore.spplink.SoundcoreSDK;

public final class HardwareTransportFactory {
    public static HardwareTransport create(HardwareEvents events) {
        return new Soundcore1302Bridge(SoundcoreSDK.Companion.getProxy(), events);
    }
}
