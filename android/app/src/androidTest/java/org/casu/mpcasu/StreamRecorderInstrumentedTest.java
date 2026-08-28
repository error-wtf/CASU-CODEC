// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
package org.casu.mpcasu;

import android.content.Context;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.File;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/**
 * On-device verification of the MediaCodec-backed StreamRecorder against real
 * network radio streams (M4A audio-only + MP4 video-and-audio).
 * MP3 encoder not available on all devices/emulators; M4A (AAC) is universal.
 */
@RunWith(AndroidJUnit4.class)
public class StreamRecorderInstrumentedTest {

    private static final String RADIO_MP3 =
            "https://ice1.somafm.com/groovesalad-128-mp3";

    @Test
    public void recordRadioM4a() throws Exception {
        Context ctx = InstrumentationRegistry.getInstrumentation()
                .getTargetContext();
        File dir = new File(ctx.getExternalFilesDir(null), "rec-test");
        dir.mkdirs();
        File out = new File(dir, "radio.m4a");
        if (out.exists() && !out.delete())
            throw new AssertionError("cannot remove stale M4A test output");

        AtomicReference<String> error = new AtomicReference<>();
        final CountDownLatch finished = new CountDownLatch(1);

        StreamRecorder rec = new StreamRecorder(ctx, RADIO_MP3, out,
                StreamRecorder.FMT_M4A, new StreamRecorder.Listener() {
            @Override public void onStarted(String info) { }
            @Override public void onProgress(long seconds, long bytes) { }
            @Override public void onFinished(String fileName, long bytes, String err) {
                error.set(err);
                finished.countDown();
            }
        });
        rec.start();
        Thread.sleep(10000);  // record 10 seconds
        rec.stop();
        // Wait for callback, but also check file directly
        if (!finished.await(30, TimeUnit.SECONDS))
            throw new AssertionError("M4A recorder did not finish after stop()");
        if (error.get() != null) throw new AssertionError("recording error: " + error.get());
        if (!out.exists() || out.length() < 50 * 1024) {
            throw new AssertionError("M4A too small / missing: " + out.length() + " exists=" + out.exists());
        }
    }

    @Test
    public void recordRadioMp4() throws Exception {
        Context ctx = InstrumentationRegistry.getInstrumentation()
                .getTargetContext();
        File dir = new File(ctx.getExternalFilesDir(null), "rec-test");
        dir.mkdirs();
        File out = new File(dir, "radio.mp4");
        if (out.exists() && !out.delete())
            throw new AssertionError("cannot remove stale MP4 test output");

        AtomicReference<String> error = new AtomicReference<>();
        final CountDownLatch finished = new CountDownLatch(1);

        StreamRecorder rec = new StreamRecorder(ctx, RADIO_MP3, out,
                StreamRecorder.FMT_MP4, new StreamRecorder.Listener() {
            @Override public void onStarted(String info) { }
            @Override public void onProgress(long seconds, long bytes) { }
            @Override public void onFinished(String fileName, long bytes, String err) {
                error.set(err);
                finished.countDown();
            }
        });
        rec.start();
        Thread.sleep(10000);
        rec.stop();
        if (!finished.await(30, TimeUnit.SECONDS))
            throw new AssertionError("MP4 recorder did not finish after stop()");
        if (error.get() != null) throw new AssertionError("recording error: " + error.get());
        if (!out.exists() || out.length() < 50 * 1024) {
            throw new AssertionError("MP4 too small / missing: " + out.length() + " exists=" + out.exists());
        }
    }
}
