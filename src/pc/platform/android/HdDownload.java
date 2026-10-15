package org.yfmredecomp.game;

import android.app.DownloadManager;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.ConnectException;
import java.net.HttpURLConnection;
import java.net.NoRouteToHostException;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.net.UnknownHostException;
import java.security.MessageDigest;

/**
 * The network of the HD pack's download (src/pc/mods/hd_pack.h, HdNet),
 * called by android.c on the download's own threads (never the game's),
 * which block in it.
 *
 * <p>The question to GitHub's API is one HttpURLConnection GET ({@link
 * #open}, {@link #read}, {@link #close}). The pack itself goes through the
 * system's DownloadManager ({@link #fetch}, {@link #poll}, {@link #stop}):
 * Android 15 closes an app's own connections a few seconds after it leaves
 * the screen and freezes the app, so a download of a hundred megabytes in
 * the game's process ended whenever the player switched away; the system's
 * goes on, with its notification, and waits for the network when there is
 * none. Nothing escapes as an exception: failures are codes (android.c's
 * HD_NET_*: -1 no network, -2 timed out, -3 failed, -4 no download
 * manager).
 */
public final class HdDownload {
    /** 0, or an HD_NET_* code. */
    public int error;
    /** The HTTP status once connected. */
    public int status;
    private HttpURLConnection connection;
    private InputStream in;

    private static int reason(IOException e) {
        if (e instanceof UnknownHostException || e instanceof ConnectException || e instanceof NoRouteToHostException) {
            return -1;
        }
        if (e instanceof SocketTimeoutException) {
            return -2;
        }
        String message = e.getMessage();
        if (message != null && (message.contains("ENETUNREACH") || message.contains("unreachable"))) {
            return -1;
        }
        return -3;
    }

    /** A GET of GitHub's JSON API (redirects followed). */
    public static HdDownload open(String url) {
        HdDownload d = new HdDownload();
        try {
            d.connection = (HttpURLConnection) new URL(url).openConnection();
            d.connection.setConnectTimeout(15000);
            d.connection.setReadTimeout(20000);
            d.connection.setInstanceFollowRedirects(true);
            d.connection.setRequestProperty("User-Agent", "YFM-ReDecomp-Android");
            d.connection.setRequestProperty("Accept", "application/vnd.github+json");
            d.connection.setRequestProperty("X-GitHub-Api-Version", "2022-11-28");
            d.status = d.connection.getResponseCode();
            if (d.status == 200) {
                d.in = d.connection.getInputStream();
            }
        } catch (IOException e) {
            d.error = reason(e);
            d.close();
        } catch (Exception e) {
            d.error = -3;
            d.close();
        }
        return d;
    }

    /** Bytes read into {@code into} (at most {@code max}), 0 at the end, else an HD_NET_* code. */
    public int read(byte[] into, int max) {
        if (in == null) {
            return 0;
        }
        try {
            int n = in.read(into, 0, Math.min(max, into.length));
            return n < 0 ? 0 : n;
        } catch (IOException e) {
            return reason(e);
        } catch (Exception e) {
            return -3;
        }
    }

    public void close() {
        try {
            if (in != null) {
                in.close();
            }
        } catch (IOException e) {
            // closing a finished or failed answer: nothing to tell
        }
        in = null;
        if (connection != null) {
            connection.disconnect();
        }
        connection = null;
    }

    private static DownloadManager manager(Context context) {
        return (DownloadManager) context.getSystemService(Context.DOWNLOAD_SERVICE);
    }

    /**
     * Starts the download of {@code url} into {@code path} (in the app's
     * external files folder, where DownloadManager may write without a
     * permission): its id, else -4 (the download manager is turned off) or -3.
     */
    public static long fetch(Context context, String url, String path, String title) {
        try {
            DownloadManager dm = manager(context);
            if (dm == null) {
                return -4;
            }
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            request.setDestinationUri(Uri.fromFile(new File(path)));
            request.setTitle(title);
            request.addRequestHeader("User-Agent", "YFM-ReDecomp-Android");
            // shown while it runs; a finished .zip is not something to open
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE);
            return dm.enqueue(request);
        } catch (IllegalArgumentException e) {
            return -4; // the Downloads provider is disabled
        } catch (Exception e) {
            return -3;
        }
    }

    /**
     * {state, bytes so far, reason}: state 1 running, 2 waiting (for the
     * network or a retry), 3 done, 4 failed (reason: an HTTP status or
     * DownloadManager's ERROR_*), 5 gone (cancelled outside the game).
     */
    public static long[] poll(Context context, long id) {
        long[] out = {5, 0, 0};
        Cursor row = null;
        try {
            DownloadManager dm = manager(context);
            row = dm == null ? null : dm.query(new DownloadManager.Query().setFilterById(id));
            if (row != null && row.moveToFirst()) {
                int state = row.getInt(row.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                out[1] = row.getLong(row.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                out[2] = row.getInt(row.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON));
                out[0] = state == DownloadManager.STATUS_SUCCESSFUL ? 3
                        : state == DownloadManager.STATUS_FAILED ? 4
                        : state == DownloadManager.STATUS_PAUSED ? 2 : 1;
            }
        } catch (Exception e) {
            out[0] = 4;
            out[2] = 1000;
        } finally {
            if (row != null) {
                row.close();
            }
        }
        return out;
    }

    /** The file a finished download was saved as (DownloadManager names it), or "". */
    public static String where(Context context, long id) {
        Cursor row = null;
        try {
            DownloadManager dm = manager(context);
            row = dm == null ? null : dm.query(new DownloadManager.Query().setFilterById(id));
            if (row != null && row.moveToFirst()) {
                String uri = row.getString(row.getColumnIndexOrThrow(DownloadManager.COLUMN_LOCAL_URI));
                String path = uri == null ? null : Uri.parse(uri).getPath();
                return path == null ? "" : path;
            }
        } catch (Exception e) {
            // no row: the caller keeps the name it asked for
        } finally {
            if (row != null) {
                row.close();
            }
        }
        return "";
    }

    /** Ends and forgets it (its file, if still at its path, goes too). */
    public static void stop(Context context, long id) {
        try {
            DownloadManager dm = manager(context);
            if (dm != null) {
                dm.remove(id);
            }
        } catch (Exception e) {
            // already gone
        }
    }

    /** Stops every download of this app's the system still has (a job cut short when the app ended). */
    public static void forget(Context context) {
        Cursor row = null;
        try {
            DownloadManager dm = manager(context);
            row = dm == null ? null : dm.query(new DownloadManager.Query());
            while (row != null && row.moveToNext()) {
                dm.remove(row.getLong(row.getColumnIndexOrThrow(DownloadManager.COLUMN_ID)));
            }
        } catch (Exception e) {
            // nothing to forget
        } finally {
            if (row != null) {
                row.close();
            }
        }
    }

    /** The lowercase hex SHA-256 of the file {@code path}, or "". */
    public static String sha256(String path) {
        try (InputStream file = new FileInputStream(path)) {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[1 << 16];
            int n;
            while ((n = file.read(buffer)) > 0) {
                sha.update(buffer, 0, n);
            }
            StringBuilder hex = new StringBuilder(64);
            for (byte b : sha.digest()) {
                hex.append(Character.forDigit((b >> 4) & 15, 16)).append(Character.forDigit(b & 15, 16));
            }
            return hex.toString();
        } catch (Exception e) {
            return "";
        }
    }
}
