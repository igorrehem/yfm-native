package org.yfmredecomp.game;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileNotFoundException;

/* The crash report the player shares (src/pc/platform/android_report.c),
 * handed to the app they pick in the system's share sheet: read only, one
 * file at a time, and only to an app the share's Intent grants it to
 * (android:exported="false", android:grantUriPermissions="true" in
 * tools/pc/package_android.py's manifest). The files are the ones
 * android_report.c writes into the cache folder's shared/; a name with a
 * slash or starting with a dot is refused, so nothing else is reached. One
 * of the port's own Java classes (src/pc/platform/android/*.java, compiled
 * with SDL's by package_android.py); the game's activity is SDL's
 * SDLActivity. */
public class ReportProvider extends ContentProvider {
    public static final String AUTHORITY = "org.yfmredecomp.game.reports";

    private File file(Uri uri) throws FileNotFoundException {
        String name = uri.getLastPathSegment();
        if (name == null || name.isEmpty() || name.startsWith(".") || name.contains("/") || name.contains("\\")) {
            throw new FileNotFoundException(String.valueOf(uri));
        }
        File file = new File(new File(getContext().getCacheDir(), "shared"), name);
        if (!file.isFile()) throw new FileNotFoundException(String.valueOf(uri));
        return file;
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public String getType(Uri uri) {
        return "text/plain";
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (mode != null && !mode.equals("r")) throw new FileNotFoundException("read only: " + uri);
        return ParcelFileDescriptor.open(file(uri), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    /* The name and size the receiving app shows (Discord, mail, chats). */
    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] arguments, String order) {
        File file;
        try {
            file = file(uri);
        } catch (FileNotFoundException missing) {
            return null;
        }
        if (projection == null) projection = new String[] {OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE};
        String[] columns = new String[projection.length];
        Object[] row = new Object[projection.length];
        int count = 0;
        for (String column : projection) {
            if (OpenableColumns.DISPLAY_NAME.equals(column)) {
                columns[count] = column;
                row[count++] = file.getName();
            } else if (OpenableColumns.SIZE.equals(column)) {
                columns[count] = column;
                row[count++] = file.length();
            }
        }
        String[] kept = new String[count];
        Object[] values = new Object[count];
        System.arraycopy(columns, 0, kept, 0, count);
        System.arraycopy(row, 0, values, 0, count);
        MatrixCursor cursor = new MatrixCursor(kept, 1);
        cursor.addRow(values);
        return cursor;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("read only");
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] arguments) {
        throw new UnsupportedOperationException("read only");
    }

    @Override
    public int delete(Uri uri, String selection, String[] arguments) {
        throw new UnsupportedOperationException("read only");
    }
}
