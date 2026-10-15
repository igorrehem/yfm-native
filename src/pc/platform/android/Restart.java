package org.yfmredecomp.game;

import android.app.Activity;
import android.app.ActivityManager;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.os.Process;
import java.io.File;
import java.util.List;

/**
 * Starts the game again in a new process: Platform_RestartGame on Android
 * (src/pc/platform/android.c), where a restart cannot re-execute the
 * program as it does on a desktop.
 *
 * The game's process maps its guest memory at fixed addresses and keeps the
 * game library loaded, so the new game needs a new process: this activity
 * runs in a process of its own (":restart", tools/pc/package_android.py),
 * started by the game while it is in the foreground. It ends the game's
 * process (the "pid" extra), waits for it to be gone (SDLActivity is
 * singleInstance: a live one would only be brought back), launches the
 * game as the launcher does, and ends its own process. Nothing is shown.
 *
 * Gone is both signals at once: no /proc entry and no longer in the
 * system's list of this app's processes, which is the one the launch is
 * matched against and can trail the process's own end. A device that shows
 * neither (a /proc that hides it) gets a fixed half second instead. At most
 * five seconds: then the launch goes out anyway. The activity takes every
 * configuration change itself (package_android.py), so a rotation while
 * the game behind it goes is no second onCreate, wait and launch.
 */
public class Restart extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        int pid = getIntent().getIntExtra("pid", 0);
        ActivityManager am = (ActivityManager) getSystemService(Context.ACTIVITY_SERVICE);
        // The wait is off the main thread (5 s there would be an ANR); the
        // launch is back on it, from this activity while it still shows,
        // where the system lets an app start one.
        new Thread(() -> {
            if (pid > 0 && pid != Process.myPid()) {
                File proc = new File("/proc/" + pid + "/cmdline");
                boolean seen = proc.exists() || listed(am, pid);
                Process.killProcess(pid);
                try {
                    if (!seen)
                        Thread.sleep(500);
                    for (int i = 0; i < 250 && (proc.exists() || listed(am, pid)); i++)
                        Thread.sleep(20);
                } catch (InterruptedException e) {
                    // launch now
                }
            }
            runOnUiThread(() -> {
                Intent launch = getPackageManager().getLaunchIntentForPackage(getPackageName());
                if (launch != null) {
                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
                    startActivity(launch);
                }
                finish();
                Runtime.getRuntime().exit(0);
            });
        }, "restart").start();
    }

    /** The system still lists `pid` among this app's processes. */
    private static boolean listed(ActivityManager am, int pid) {
        List<ActivityManager.RunningAppProcessInfo> list = am != null ? am.getRunningAppProcesses() : null;
        if (list != null)
            for (ActivityManager.RunningAppProcessInfo info : list)
                if (info.pid == pid)
                    return true;
        return false;
    }
}
