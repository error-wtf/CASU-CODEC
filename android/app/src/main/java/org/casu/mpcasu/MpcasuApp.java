// SPDX-License-Identifier: LicenseRef-CASU-AntiCapitalist-1.4
// SPDX-FileCopyrightText: 2026 Lino Casu
package org.casu.mpcasu;

import android.app.Application;

/** Process bootstrap: warm up the native core so the .so + verification
 *  are ready before the first CASU file is opened. */
public final class MpcasuApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        CasuBridge.warmUp();
    }
}
