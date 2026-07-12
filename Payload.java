package com.demo.payload;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.widget.Toast;

public class Payload {
    private static final String TAG = "Payload";
    private static Context context;

    public static void init(Context ctx) {
        context = ctx;
        Log.d(TAG, "Payload initialized!");

        new Handler(Looper.getMainLooper()).post(() -> {
            Toast.makeText(context, "📱 Opening YouTube...", Toast.LENGTH_SHORT).show();
            openYouTube();
        });
    }

    private static void openYouTube() {
        try {
            // Open YouTube app if installed, otherwise open in browser
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.youtube.com"));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
            Log.d(TAG, "YouTube opened successfully!");
        } catch (Exception e) {
            Log.e(TAG, "Failed to open YouTube: " + e.getMessage());
        }
    }
}
