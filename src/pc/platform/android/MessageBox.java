package org.yfmredecomp.game;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.view.KeyEvent;

/**
 * The game's message boxes on Android (Android_ShowMessageBox,
 * src/pc/platform/android.c), in place of SDL's: the first run's welcome,
 * the error boxes and the start-up report.
 *
 * <p>SDL's box (SDLActivity.messageboxCreateAndShow) lays the message and
 * the buttons out one under the other with nothing to scroll, so a message
 * taller than the dialog pushes the buttons out of it: in landscape, where
 * the activity always is, with the system's font size turned up, the
 * welcome showed its text and no "Choose disc image..." to press. The
 * system's own alert keeps the message in a scrolling panel and its
 * buttons on a bar under it, whatever the message's height.
 *
 * <p>Up to three buttons, the alert's three places: the one the return key
 * presses (or, with none, the first of the others) on the right
 * (positive), the one the escape key presses left of it (negative), any
 * other at the bar's far left (neutral). {@link #show} returns -2 for a box
 * it cannot lay out that way, and android.c shows SDL's.
 */
public final class MessageBox {
    private static final int RETURN_KEY = 0x1; // SDL_MESSAGEBOX_BUTTON_RETURNKEY_DEFAULT
    private static final int ESCAPE_KEY = 0x2; // SDL_MESSAGEBOX_BUTTON_ESCAPEKEY_DEFAULT

    private MessageBox() {
    }

    /**
     * Shows the box on the activity's main thread and waits, on the
     * calling thread (the game's, never the main one), for a button: its
     * id, -1 when the box went away without one, -2 when it could not be
     * shown this way.
     */
    public static int show(final Activity activity, final String title, final String message,
                           final String[] texts, final int[] ids, final int[] flags) {
        if (texts.length == 0 || texts.length > 3 || ids.length != texts.length || flags.length != texts.length)
            return -2;
        // which of the alert's places each button takes: -1 positive,
        // -2 negative, -3 neutral (DialogInterface.BUTTON_*)
        final int[] place = new int[texts.length];
        boolean positive = false, negative = false;
        for (int i = 0; i < texts.length; i++) {
            if (!positive && (flags[i] & RETURN_KEY) != 0) {
                place[i] = DialogInterface.BUTTON_POSITIVE;
                positive = true;
            }
        }
        for (int i = 0; i < texts.length; i++) {
            if (place[i] == 0 && !negative && (flags[i] & ESCAPE_KEY) != 0) {
                place[i] = DialogInterface.BUTTON_NEGATIVE;
                negative = true;
            }
        }
        boolean neutral = false;
        for (int i = 0; i < texts.length; i++) {
            if (place[i] != 0)
                continue;
            if (!positive) {
                place[i] = DialogInterface.BUTTON_POSITIVE;
                positive = true;
            } else if (!neutral) {
                place[i] = DialogInterface.BUTTON_NEUTRAL;
                neutral = true;
            } else {
                place[i] = DialogInterface.BUTTON_NEGATIVE;
                negative = true;
            }
        }
        final Object lock = new Object();
        final int[] chosen = {-1};
        final boolean[] done = {false};
        activity.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                AlertDialog dialog = null;
                try {
                    AlertDialog.Builder builder = new AlertDialog.Builder(activity,
                            android.R.style.Theme_DeviceDefault_Dialog_Alert);
                    builder.setTitle(title).setMessage(message).setCancelable(false);
                    for (int i = 0; i < texts.length; i++) {
                        final int id = ids[i];
                        DialogInterface.OnClickListener click = new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int which) {
                                chosen[0] = id;
                            }
                        };
                        if (place[i] == DialogInterface.BUTTON_POSITIVE)
                            builder.setPositiveButton(texts[i], click);
                        else if (place[i] == DialogInterface.BUTTON_NEGATIVE)
                            builder.setNegativeButton(texts[i], click);
                        else
                            builder.setNeutralButton(texts[i], click);
                    }
                    // the keys SDL's box answers: return and escape press
                    // their buttons
                    builder.setOnKeyListener(new DialogInterface.OnKeyListener() {
                        @Override
                        public boolean onKey(DialogInterface d, int keyCode, KeyEvent event) {
                            int wanted = keyCode == KeyEvent.KEYCODE_ENTER ? RETURN_KEY
                                    : keyCode == KeyEvent.KEYCODE_ESCAPE ? ESCAPE_KEY : 0;
                            if (wanted == 0)
                                return false;
                            for (int i = 0; i < texts.length; i++) {
                                if ((flags[i] & wanted) != 0) {
                                    if (event.getAction() == KeyEvent.ACTION_UP)
                                        ((AlertDialog) d).getButton(place[i]).performClick();
                                    return true;
                                }
                            }
                            return false;
                        }
                    });
                    builder.setOnDismissListener(new DialogInterface.OnDismissListener() {
                        @Override
                        public void onDismiss(DialogInterface d) {
                            finish(lock, done);
                        }
                    });
                    dialog = builder.create();
                    dialog.show();
                } catch (RuntimeException e) {
                    // a box that could not be shown (the activity going
                    // away): the game goes on as if it was closed
                    if (dialog == null || !dialog.isShowing())
                        finish(lock, done);
                }
            }
        });
        synchronized (lock) {
            while (!done[0]) {
                try {
                    lock.wait();
                } catch (InterruptedException e) {
                    // keep waiting: the box is still up
                }
            }
        }
        return chosen[0];
    }

    private static void finish(Object lock, boolean[] done) {
        synchronized (lock) {
            done[0] = true;
            lock.notifyAll();
        }
    }
}
