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
            Toast.makeText(context, "✅ Payload loaded!", Toast.LENGTH_LONG).show();
        });
    }
}
