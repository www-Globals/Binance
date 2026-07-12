package com.demo.payload;

import android.content.Context;
import android.widget.Toast;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

public class Payload {
    private static final String TAG = "Payload";
    private static Context context;

    public static void init(Context ctx) {
        context = ctx;
        Log.d(TAG, "Payload initialized!");

        new Handler(Looper.getMainLooper()).post(() -> {
            // 1. Show toast
            Toast.makeText(context, "✅ PAYLOAD EXECUTED!", Toast.LENGTH_LONG).show();
            
            // 2. Log to logcat
            Log.d(TAG, "✅ Payload execution confirmed at " + System.currentTimeMillis());
            
            // 3. You can also open a website
            // openWebsite();
        });
    }
}
