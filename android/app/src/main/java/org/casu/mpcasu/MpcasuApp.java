package org.casu.mpcasu;

import android.app.Application;
import android.content.Context;

/** Application holder: static context for the library scanner. */
public class MpcasuApp extends Application {
    private static Context appContext;

    @Override public void onCreate() {
        super.onCreate();
        appContext = getApplicationContext();
    }

    static Context context() { return appContext; }
}
